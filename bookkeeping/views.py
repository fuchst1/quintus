import hashlib
import json
import logging
import os
import re
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Prefetch, Q, Sum
from django.db import transaction as db_transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import DeleteView, TemplateView, UpdateView

from .bank_statement_parser import BankStatementParseError
from .booking_resets import (
    reset_bank_transaction_booking,
    reset_manual_invoice_booking,
)
from .bank_statements import (
    BankStatementImportError,
    display_bank_statement,
    import_bank_statement,
    json_control_for_statement,
    refresh_pending_paperless_tasks,
    refresh_unsynced_completed_references,
    retry_bank_statement,
)
from .accountant_package import (
    AccountantPackageError,
    build_accountant_package,
    inspect_accountant_package,
)
from .formatting import format_austrian_decimal, format_austrian_money
from .category_display import category_description
from .csv_export import (
    CsvExportError,
    export_reviewed_transactions_csv,
    quarter_bounds,
)
from .matching import build_booking_entry_snapshot, match_imported_transactions
from .forms import (
    BankTransactionNoteForm,
    BankStatementUploadForm,
    BookingEntryForm,
    BookingEntryFormSet,
    ManualInvoiceEntryFormSet,
    ManualInvoiceForm,
    ManualInvoiceUploadForm,
    MatchingRuleBookingTemplateFormSet,
    MatchingRuleForm,
    MatchingRuleVersionForm,
    QuarterBalanceForm,
    SupportingDocumentUploadForm,
)
from .models import (
    BankStatement,
    BankTransaction,
    BookingEntry,
    MatchingRule,
    ManualInvoice,
    ManualInvoiceEntry,
    QuarterBalance,
    SupportingDocument,
)
from .manual_invoices import (
    ManualInvoiceDeletionError,
    ManualInvoiceImportError,
    delete_manual_invoice_completely,
    delete_manual_invoice_from_paperless,
    display_manual_invoice,
    duplicate_manual_invoice_warning,
    import_manual_invoice,
    refresh_pending_manual_invoice_tasks,
    retry_manual_invoice,
    start_manual_invoice_upload,
)
from .paperless_invoice_import import (
    PaperlessInvoiceImportError,
    import_paperless_invoices,
)
from .invoice_ai import (
    OCR_UNAVAILABLE_MESSAGE,
    ai_ui_state,
    formset_initial_from_analysis,
    run_manual_invoice_analysis,
)
from .paperless import BookkeepingPaperlessError, PaperlessClient
from .supporting_documents import (
    SupportingDocumentError,
    delete_supporting_document_from_paperless,
    display_supporting_document,
    import_supporting_document,
    refresh_pending_supporting_documents,
    remove_supporting_document,
    retry_supporting_document,
)


OPEN_FILTER = "open"
BANK_IMPORT_FILTER = "bank_import"
BOOKING_READY_STATUSES = (
    BankTransaction.Status.REVIEWED,
    BankTransaction.Status.BOOKED,
)
STATUS_NAVIGATION = (
    {
        "value": OPEN_FILTER,
        "label": "Offen",
        "heading": "Offene Transaktionen",
        "empty_label": "offenen",
        "icon": "bi-inbox",
    },
    {
        "value": BankTransaction.Status.REVIEWED,
        "label": "Buchungsfertig",
        "heading": "Buchungsfertige Transaktionen",
        "empty_label": "buchungsfertigen",
        "icon": "bi-search",
    },
)
STATUS_VALUES = {
    BANK_IMPORT_FILTER,
    OPEN_FILTER,
    BankTransaction.Status.IMPORTED,
    BankTransaction.Status.MATCHED,
    BankTransaction.Status.REVIEWED,
    BankTransaction.Status.BOOKED,
}
STATUS_DETAILS = {
    item["value"]: item
    for item in STATUS_NAVIGATION
}
STATUS_DETAILS.update(
    {
        BANK_IMPORT_FILTER: {
            "value": BANK_IMPORT_FILTER,
            "label": "Bankimport",
            "heading": "Bankimport",
            "empty_label": "",
            "icon": "bi-upload",
        },
        BankTransaction.Status.IMPORTED: {
            "value": BankTransaction.Status.IMPORTED,
            "label": "Offen",
            "heading": "Offene Transaktionen",
            "empty_label": "offenen",
            "icon": "bi-inbox",
        },
        BankTransaction.Status.MATCHED: {
            "value": BankTransaction.Status.MATCHED,
            "label": "Zugeordnet",
            "heading": "Zugeordnete Transaktionen",
            "empty_label": "zugeordneten",
            "icon": "bi-check2-square",
        },
        BankTransaction.Status.BOOKED: {
            "value": BankTransaction.Status.BOOKED,
            "label": "Buchungsfertig",
            "heading": "Buchungsfertige Transaktionen",
            "empty_label": "buchungsfertigen",
            "icon": "bi-search",
        },
    }
)
NOTE_EDITABLE_STATUSES = frozenset(
    {
        BankTransaction.Status.MATCHED,
        BankTransaction.Status.REVIEWED,
        BankTransaction.Status.BOOKED,
    }
)
GERMAN_MONTH_NAMES = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
MONTH_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])$")
EXPORT_PERIOD_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<quarter>Q[1-4])$")
PERIOD_TYPES = ("month", "quarter")
logger = logging.getLogger(__name__)


def supporting_document_owner_url(document):
    """Return the fixed detail URL for the document's actual owner."""
    if document.matching_rule_id is not None:
        return reverse(
            "matching_rule_detail",
            kwargs={"pk": document.matching_rule_id},
        )
    if document.bank_transaction_id is not None:
        return reverse(
            "bank_transaction_booking",
            kwargs={"pk": document.bank_transaction_id},
        )
    raise ValueError("SupportingDocument hat keinen gültigen Besitzer.")


def _parse_month(value):
    if not isinstance(value, str):
        return None
    match = MONTH_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        return date(int(match.group("year")), int(match.group("month")), 1)
    except ValueError:
        return None


def _month_label(month_key):
    month = _parse_month(month_key)
    if month is None:
        return ""
    return f"{GERMAN_MONTH_NAMES[month.month - 1]} {month.year}"


def _month_bounds(month_key):
    month = _parse_month(month_key)
    if month is None:
        return None
    return month, date(month.year, month.month, monthrange(month.year, month.month)[1])


def _month_filter(month_key):
    bounds = _month_bounds(month_key)
    if bounds is None:
        return {}
    start, end = bounds
    return {"booking_date__gte": start, "booking_date__lte": end}


def _available_export_quarters():
    available_quarters = {
        (
            payment_date.year,
            f"Q{((payment_date.month - 1) // 3) + 1}",
        )
        for payment_date in BookingEntry.objects.filter(
            bank_transaction__status__in=BOOKING_READY_STATUSES,
        ).values_list("payment_date", flat=True)
    }
    available_quarters.update(
        (
            booking_date.year,
            f"Q{((booking_date.month - 1) // 3) + 1}",
        )
        for booking_date in BankTransaction.objects.filter(
            status__in=BOOKING_READY_STATUSES,
        ).values_list("booking_date", flat=True)
    )
    available_quarters.update(
        (
            payment_date.year,
            f"Q{((payment_date.month - 1) // 3) + 1}",
        )
        for payment_date in ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
        ).values_list("payment_date", flat=True)
    )
    return sorted(available_quarters, reverse=True)


def _available_transaction_quarters():
    return sorted(
        {
            (
                booking_date.year,
                f"Q{((booking_date.month - 1) // 3) + 1}",
            )
            for booking_date in BankTransaction.objects.values_list(
                "booking_date", flat=True
            )
        },
        reverse=True,
    )


def _period_bounds(period_type, period):
    if period_type == "month":
        return _month_bounds(period)
    if period_type == "quarter":
        return _export_period_bounds(period)
    return None


def _period_label(period_type, period):
    if period_type == "month":
        return _month_label(period)
    parsed_period = _parse_export_period(period)
    if parsed_period is None:
        return ""
    year, quarter = parsed_period.split("-", 1)
    return f"{quarter} {year}"


def _period_value(period_type, value):
    if period_type == "month":
        parsed = _parse_month(value)
        return value if parsed is not None else ""
    if period_type == "quarter":
        return _parse_export_period(value) or ""
    return ""


def _month_key(value):
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    return str(value or "")[:7]


def _quarter_key(value):
    if not isinstance(value, date):
        return ""
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def _available_ready_months():
    months = {
        payment_date.strftime("%Y-%m")
        for payment_date in BookingEntry.objects.filter(
            bank_transaction__status__in=BOOKING_READY_STATUSES,
        ).values_list("payment_date", flat=True)
    }
    months.update(
        booking_date.strftime("%Y-%m")
        for booking_date in BankTransaction.objects.filter(
            status__in=BOOKING_READY_STATUSES,
        ).values_list("booking_date", flat=True)
    )
    months.update(
        payment_date.strftime("%Y-%m")
        for payment_date in ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
        ).values_list("payment_date", flat=True)
    )
    return sorted(months, reverse=True)


def _available_dashboard_months():
    months = {
        booking_date.strftime("%Y-%m")
        for booking_date in BankTransaction.objects.values_list(
            "booking_date", flat=True
        )
    }
    months.update(
        payment_date.strftime("%Y-%m")
        for payment_date in BookingEntry.objects.values_list(
            "payment_date", flat=True
        )
    )
    months.update(BankStatement.objects.values_list("booking_month", flat=True))
    months.update(
        payment_date.strftime("%Y-%m")
        for payment_date in ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
        ).values_list("payment_date", flat=True)
    )
    return sorted(months, reverse=True)


def _available_dashboard_quarters():
    quarters = {
        _quarter_key(booking_date)
        for booking_date in BankTransaction.objects.values_list(
            "booking_date", flat=True
        )
    }
    quarters.update(
        _quarter_key(payment_date)
        for payment_date in BookingEntry.objects.values_list(
            "payment_date", flat=True
        )
    )
    quarters.update(
        BankStatement.objects.values_list("booking_quarter", flat=True)
    )
    quarters.update(
        _quarter_key(payment_date)
        for payment_date in ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
        ).values_list("payment_date", flat=True)
    )
    return sorted(
        (period for period in quarters if _parse_export_period(period)),
        reverse=True,
    )


def _dashboard_period_selection(params, available_months, available_quarters):
    requested_type = params.get("period_type")
    requested_period = params.get("period")
    if requested_type not in PERIOD_TYPES:
        if params.get("dashboard_period"):
            requested_type = "quarter"
            requested_period = params.get("dashboard_period")
        else:
            requested_type = "month"
    available = (
        available_months if requested_type == "month" else available_quarters
    )
    selected = _period_value(requested_type, requested_period)
    if selected in available:
        return requested_type, selected
    if available:
        return requested_type, available[0]
    return requested_type, ""


def _dashboard_statement_queryset(period_type, period):
    if period_type == "month":
        return BankStatement.objects.filter(booking_month=period)
    return BankStatement.objects.filter(booking_quarter=period)


def _dashboard_context(params):
    available_months = _available_dashboard_months()
    available_quarters = _available_dashboard_quarters()
    dashboard_period_type, dashboard_period = _dashboard_period_selection(
        params,
        available_months,
        available_quarters,
    )
    period_range = _period_bounds(dashboard_period_type, dashboard_period)
    context = {
        "available_dashboard_months": [
            {"value": value, "label": _month_label(value)}
            for value in available_months
        ],
        "available_dashboard_quarters": [
            {"value": value, "label": _period_label("quarter", value)}
            for value in available_quarters
        ],
        "dashboard_period_type": dashboard_period_type,
        "dashboard_period": dashboard_period,
        "dashboard_period_label": _period_label(
            dashboard_period_type,
            dashboard_period,
        ),
        "dashboard_has_data": False,
        "dashboard_total": 0,
        "dashboard_open": 0,
        "dashboard_ready": 0,
        "dashboard_booking_entries": 0,
        "dashboard_processed_percentage": "0.00",
        "dashboard_processed_percent": "0,00 %",
        "dashboard_processed_width": "0",
        "dashboard_incoming": "0,00 EUR",
        "dashboard_outgoing": "0,00 EUR",
        "dashboard_balance": "0,00 EUR",
        "dashboard_auto_matched": 0,
        "dashboard_without_matching": 0,
        "dashboard_active_matching_rules": MatchingRule.objects.filter(
            active=True
        ).count(),
        "dashboard_statement_count": 0,
        "dashboard_reconciliation": "–",
    }
    if period_range is None:
        return context

    aggregate = BankTransaction.objects.filter(
        booking_date__gte=period_range[0],
        booking_date__lte=period_range[1],
    ).aggregate(
        total=Count("id"),
        open_count=Count(
            "id",
            filter=Q(
                status__in=(
                    BankTransaction.Status.IMPORTED,
                    BankTransaction.Status.MATCHED,
                )
            ),
        ),
        ready_count=Count("id", filter=Q(status__in=BOOKING_READY_STATUSES)),
        incoming=Sum("amount", filter=Q(amount__gt=0)),
        outgoing=Sum("amount", filter=Q(amount__lt=0)),
        balance=Sum("amount"),
        auto_matched=Count("id", filter=Q(matched_rule__isnull=False)),
        without_matching=Count("id", filter=Q(matched_rule__isnull=True)),
    )
    statement_qs = _dashboard_statement_queryset(
        dashboard_period_type,
        dashboard_period,
    )
    statements = list(statement_qs.order_by("-statement_date", "-id"))
    booking_entry_count = BookingEntry.objects.filter(
        payment_date__gte=period_range[0],
        payment_date__lte=period_range[1],
    ).count() + ManualInvoiceEntry.objects.filter(
        manual_invoice__status=ManualInvoice.Status.READY,
        payment_date__gte=period_range[0],
        payment_date__lte=period_range[1],
    ).count()
    total = aggregate["total"] or 0
    ready_count = aggregate["ready_count"] or 0
    incoming = aggregate["incoming"] or Decimal("0")
    outgoing = aggregate["outgoing"] or Decimal("0")
    balance = aggregate["balance"] or Decimal("0")
    processed_percentage = (
        (Decimal(ready_count) * Decimal("100") / Decimal(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if total
        else Decimal("0.00")
    )
    reconciliation = "–"
    if statements:
        controls = [json_control_for_statement(statement) for statement in statements]
        if any(control["status"] == "danger" for control in controls):
            reconciliation = "Abweichung"
        elif all(control["status"] == "success" for control in controls):
            reconciliation = "Stimmt überein"
        else:
            reconciliation = "Noch offen"
    context.update(
        {
            "dashboard_has_data": bool(total or booking_entry_count or statements),
            "dashboard_total": total,
            "dashboard_open": aggregate["open_count"] or 0,
            "dashboard_ready": ready_count,
            "dashboard_booking_entries": booking_entry_count,
            "dashboard_processed_percentage": str(processed_percentage),
            "dashboard_processed_percent": f"{format_austrian_decimal(processed_percentage)} %",
            "dashboard_processed_width": str(processed_percentage),
            "dashboard_incoming": format_austrian_money(incoming, "EUR"),
            "dashboard_outgoing": format_austrian_money(abs(outgoing), "EUR"),
            "dashboard_balance": format_austrian_money(balance, "EUR"),
            "dashboard_auto_matched": aggregate["auto_matched"] or 0,
            "dashboard_without_matching": aggregate["without_matching"] or 0,
            "dashboard_statement_count": len(statements),
            "dashboard_reconciliation": reconciliation,
        }
    )
    return context


def _bank_import_context(params):
    del params
    refresh_pending_paperless_tasks()
    synchronization_errors = refresh_unsynced_completed_references()
    bank_statements = []
    for statement in BankStatement.objects.order_by(
        "-statement_date", "-statement_year", "-statement_number"
    ):
        displayed_statement = display_bank_statement(statement)
        displayed_statement["month"] = _month_label(statement.booking_month)
        if statement.pk in synchronization_errors:
            displayed_statement["paperless_error"] = synchronization_errors[
                statement.pk
            ]
        bank_statements.append(displayed_statement)

    return {"bank_statements": bank_statements}


def _parse_export_period(value):
    if not isinstance(value, str):
        return None
    match = EXPORT_PERIOD_PATTERN.fullmatch(value.upper())
    if match is None:
        return None
    period = f"{match.group('year')}-{match.group('quarter')}"
    if quarter_bounds(match.group("year"), match.group("quarter")) is None:
        return None
    return period


def _export_period_bounds(period):
    parsed_period = _parse_export_period(period)
    if parsed_period is None:
        return None
    year, quarter = parsed_period.split("-", 1)
    return quarter_bounds(year, quarter)


def _validate_accountant_package_period(period_type, period):
    available_periods = (
        _available_ready_months()
        if period_type == "month"
        else [
            f"{year}-{quarter}"
            for year, quarter in _available_export_quarters()
        ]
        if period_type == "quarter"
        else []
    )
    if period not in available_periods:
        raise AccountantPackageError(
            "Der ausgewählte Zeitraum ist nicht als buchungsfertiger Zeitraum verfügbar."
        )
    return period_type, period


def _accountant_package_response(request):
    period_type = request.POST.get("period_type") or request.GET.get(
        "period_type",
        "",
    )
    period = request.POST.get("period") or request.GET.get("period", "")
    _validate_accountant_package_period(period_type, period)
    result = build_accountant_package(
        period_type=period_type,
        period=period,
    )
    response = FileResponse(
        result.file,
        as_attachment=True,
        filename=result.filename,
        content_type="application/zip",
    )
    response["Cache-Control"] = "no-store"
    return response


MONEY_QUANTUM = Decimal("0.01")


def _quantize_money(value):
    return (value or Decimal("0")).quantize(MONEY_QUANTUM)


def _quarter_balance_form(period, data=None):
    parsed_period = _parse_export_period(period)
    if parsed_period is None:
        return QuarterBalanceForm(data)
    year, quarter = parsed_period.split("-", 1)
    balance = QuarterBalance.objects.filter(
        year=int(year),
        quarter=int(quarter[1]),
    ).first()
    return QuarterBalanceForm(data, instance=balance)


def _period_control_context(period_type, period):
    """Build the selected month or quarter's booking control."""
    period_range = _period_bounds(period_type, period)
    if period_range is None:
        return {
            "available": False,
            "period": "",
            "status": "",
            "status_label": "",
            "inconsistent_transactions": [],
        }

    start_date, end_date = period_range
    ready_statuses = BOOKING_READY_STATUSES
    ready_period_filter = BankTransaction.objects.filter(
        status__in=ready_statuses,
    ).filter(
        Q(booking_date__gte=start_date, booking_date__lte=end_date)
        | Q(
            booking_entries__payment_date__gte=start_date,
            booking_entries__payment_date__lte=end_date,
        )
    )
    ready_transactions = list(
        ready_period_filter.distinct()
        .prefetch_related(
            Prefetch(
                "booking_entries",
                queryset=BookingEntry.objects.order_by(
                    "payment_date", "created_at", "id"
                ),
                to_attr="quarter_control_booking_entries",
            )
        )
        .order_by("-booking_date", "id")
    )

    open_transactions = BankTransaction.objects.filter(
        status__in=(
            BankTransaction.Status.IMPORTED,
            BankTransaction.Status.MATCHED,
        ),
        booking_date__gte=start_date,
        booking_date__lte=end_date,
    ).count()
    bank_movement = BankTransaction.objects.filter(
        booking_date__gte=start_date,
        booking_date__lte=end_date,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    booking_entry_count = 0
    booking_entry_total = Decimal("0")
    bank_transaction_total = Decimal("0")
    ready_transaction_count = 0
    inconsistent_transactions = []
    for bank_transaction in ready_transactions:
        bank_transaction_total += bank_transaction.amount
        entries = getattr(bank_transaction, "quarter_control_booking_entries", ())
        entries_in_quarter = [
            entry
            for entry in entries
            if start_date <= entry.payment_date <= end_date
        ]
        has_entries_outside_quarter = any(
            not start_date <= entry.payment_date <= end_date
            for entry in entries
        )
        entry_total = sum(
            (entry.gross_amount for entry in entries_in_quarter),
            Decimal("0"),
        )
        entry_total = _quantize_money(entry_total)
        difference = _quantize_money(bank_transaction.amount - entry_total)
        booking_entry_count += len(entries_in_quarter)
        booking_entry_total += entry_total
        if entries_in_quarter:
            ready_transaction_count += 1

        if (
            not entries_in_quarter
            or difference != Decimal("0.00")
            or has_entries_outside_quarter
        ):
            inconsistent_transactions.append(
                {
                    "id": bank_transaction.pk,
                    "booking_date": bank_transaction.booking_date.strftime(
                        "%d.%m.%Y"
                    ),
                    "name": bank_transaction.partner_name or "–",
                    "bank_amount_value": _quantize_money(bank_transaction.amount),
                    "booking_total_value": entry_total,
                    "difference_value": difference,
                    "bank_amount": format_austrian_money(
                        bank_transaction.amount, "EUR"
                    ),
                    "booking_total": format_austrian_money(entry_total, "EUR"),
                    "difference": format_austrian_money(difference, "EUR"),
                    "edit_url": (
                        f"{reverse('bank_transaction_booking', kwargs={'pk': bank_transaction.pk})}"
                        f"?{urlencode({'status': BankTransaction.Status.REVIEWED, 'period': period, 'period_type': period_type})}"
                    ),
                }
            )

    manual_entries = list(
        ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
            payment_date__gte=start_date,
            payment_date__lte=end_date,
        ).select_related("manual_invoice")
    )
    manual_booking_entry_total = sum(
        (
            entry.gross_amount
            for entry in manual_entries
            if entry.gross_amount is not None
        ),
        Decimal("0"),
    )
    booking_entry_count += len(manual_entries)
    booking_entry_total += manual_booking_entry_total
    ready_transaction_count += len(
        {entry.manual_invoice_id for entry in manual_entries}
    )
    bank_booking_entry_total = _quantize_money(
        booking_entry_total - manual_booking_entry_total
    )

    bank_transaction_total = _quantize_money(bank_transaction_total)
    booking_entry_total = _quantize_money(booking_entry_total)
    manual_booking_entry_total = _quantize_money(manual_booking_entry_total)
    difference = _quantize_money(bank_transaction_total - bank_booking_entry_total)
    has_inconsistencies = bool(inconsistent_transactions) or difference != Decimal(
        "0.00"
    )
    if has_inconsistencies:
        status = "danger"
        status_label = "Buchungsdaten sind nicht konsistent"
    elif open_transactions:
        status = "warning"
        status_label = (
            "Monat noch nicht vollständig"
            if period_type == "month"
            else "Quartal noch nicht vollständig"
        )
    else:
        status = "success"
        status_label = (
            "Monat vollständig und buchhalterisch konsistent"
            if period_type == "month"
            else "Quartal vollständig und buchhalterisch konsistent"
        )

    statement = None
    statement_display = None
    if period_type == "month":
        statement = (
            BankStatement.objects.filter(booking_month=period)
            .order_by("-statement_date", "-id")
            .first()
        )
        if statement is not None:
            statement_display = display_bank_statement(statement)
        opening_balance = statement.opening_balance if statement else None
        closing_balance = statement.closing_balance if statement else None
    else:
        parsed_period = _parse_export_period(period)
        year, quarter = parsed_period.split("-", 1)
        balance = QuarterBalance.objects.filter(
            year=int(year),
            quarter=int(quarter[1]),
        ).first()
        opening_balance = balance.opening_balance if balance else None
        closing_balance = balance.closing_balance if balance else None
    bank_movement = _quantize_money(bank_movement)
    calculated_balance = (
        _quantize_money(opening_balance + bank_movement)
        if opening_balance is not None
        else None
    )
    balance_difference = (
        _quantize_money(closing_balance - calculated_balance)
        if closing_balance is not None and calculated_balance is not None
        else None
    )
    if period_type == "month" and statement is None:
        balance_mode = "missing_statement"
        balance_message = "Für diesen Monat wurde noch kein Kontoauszug importiert."
    elif opening_balance is None and closing_balance is None:
        balance_mode = "none"
        balance_message = "Bankkontostände sind optional und noch nicht eingetragen."
    elif opening_balance is not None and closing_balance is None:
        balance_mode = "opening_only"
        balance_message = "Zwischenstand anhand der aktuell importierten Transaktionen."
    elif opening_balance is None:
        balance_mode = "closing_only"
        balance_message = "Für eine vollständige Abstimmung fehlt der Anfangsstand."
    else:
        balance_mode = "complete"
        if balance_difference == Decimal("0.00"):
            balance_message = "Bankkonto stimmt überein"
        else:
            balance_message = (
                "Bankkonto weist eine Differenz von "
                f"{format_austrian_decimal(balance_difference)} EUR auf"
            )

    balance_context = {
        "opening_balance_value": opening_balance,
        "closing_balance_value": closing_balance,
        "opening_balance": format_austrian_money(opening_balance, "EUR"),
        "closing_balance": format_austrian_money(closing_balance, "EUR"),
        "bank_movement_value": bank_movement,
        "bank_movement": format_austrian_money(bank_movement, "EUR"),
        "calculated_balance_value": calculated_balance,
        "calculated_balance": format_austrian_money(calculated_balance, "EUR"),
        "balance_difference_value": balance_difference,
        "balance_difference": format_austrian_money(balance_difference, "EUR"),
        "mode": balance_mode,
        "message": balance_message,
        "calculated_label": (
            "Errechneter Zwischenstand"
            if balance_mode == "opening_only"
            else "Errechneter Endstand"
        ),
        "has_difference_warning": (
            balance_mode == "complete"
            and balance_difference != Decimal("0.00")
        ),
        "statement": statement_display,
        "statement_control": (
            json_control_for_statement(statement)
            if statement is not None
            else None
        ),
    }

    return {
        "available": True,
        "period": period,
        "status": status,
        "status_label": status_label,
        "open_transactions": open_transactions,
        "ready_transactions": ready_transaction_count,
        "ready_transaction_candidates": len(ready_transactions),
        "booking_entries": booking_entry_count,
        "bank_transaction_total_value": bank_transaction_total,
        "bank_transaction_total": format_austrian_money(
            bank_transaction_total, "EUR"
        ),
        "booking_entry_total_value": booking_entry_total,
        "booking_entry_total": format_austrian_money(booking_entry_total, "EUR"),
        "manual_booking_entries": len(manual_entries),
        "manual_booking_entry_total_value": manual_booking_entry_total,
        "manual_booking_entry_total": format_austrian_money(
            manual_booking_entry_total, "EUR"
        ),
        "manual_invoices": len(
            {entry.manual_invoice_id for entry in manual_entries}
        ),
        "bank_booking_entry_total_value": bank_booking_entry_total,
        "difference_value": difference,
        "difference": format_austrian_money(difference, "EUR"),
        "inconsistent_transactions": inconsistent_transactions,
        "has_inconsistencies": has_inconsistencies,
        "balance": balance_context,
        "period_type": period_type,
        "period_label": _period_label(period_type, period),
    }


def _quarter_control_context(period):
    """Backward-compatible wrapper for the quarterly control."""
    return _period_control_context("quarter", period)


def _export_selection(params, available_quarters):
    requested_period = params.get("period")
    parsed_period = _parse_export_period(requested_period)
    if parsed_period is not None:
        return parsed_period
    requested_year = params.get("export_year") or params.get("year")
    requested_quarter = params.get("export_quarter") or params.get("quarter")
    if quarter_bounds(requested_year, requested_quarter) is not None:
        return f"{int(requested_year)}-{str(requested_quarter).upper()}"
    if available_quarters:
        year, quarter = available_quarters[0]
        return f"{year}-{quarter}"
    return ""


def _overview_url(status, month=None, period=None, period_type=None):
    query = {"status": status}
    if month is not None:
        query["month"] = month
    if period is not None:
        query["period"] = period
    if period_type is not None:
        query["period_type"] = period_type
    return f"{reverse('bookkeeping_overview')}?{urlencode(query)}"


def _note_preview(note, max_length=90):
    normalized_note = " ".join(str(note or "").split())
    if len(normalized_note) <= max_length:
        return normalized_note, False
    return f"{normalized_note[: max_length - 1]}…", True


def _bookkeeping_navigation_context(request, filter_params=None):
    params = filter_params if filter_params is not None else request.GET
    requested_status = params.get("status")
    show_dashboard = (
        request.resolver_match.url_name == "bookkeeping_overview"
        and not requested_status
    )
    selected_status = (
        requested_status if requested_status in STATUS_VALUES else OPEN_FILTER
    )

    available_month_keys = sorted(
        {
            booking_date.strftime("%Y-%m")
            for booking_date in BankTransaction.objects.values_list(
                "booking_date", flat=True
            )
        },
        reverse=True,
    )
    if "month" in params and params.get("month") == "":
        selected_month = ""
    else:
        requested_month = params.get("month")
        selected_month = (
            requested_month
            if requested_month in available_month_keys and _parse_month(requested_month)
            else (available_month_keys[0] if available_month_keys else "")
        )
    count_query = BankTransaction.objects
    if selected_month:
        count_query = count_query.filter(**_month_filter(selected_month))
    counts_by_status = {
        row["status"]: row["count"]
        for row in count_query.values("status").annotate(count=Count("id"))
    }
    ready_count = sum(
        counts_by_status.get(status, 0) for status in BOOKING_READY_STATUSES
    )
    manual_ready_query = ManualInvoice.objects.filter(
        status=ManualInvoice.Status.READY,
    )
    if selected_month:
        month_bounds = _month_bounds(selected_month)
        manual_ready_query = manual_ready_query.filter(
            payment_date__gte=month_bounds[0],
            payment_date__lte=month_bounds[1],
        )
    ready_count += manual_ready_query.count()
    navigation_month = (
        selected_month
        if selected_month
        or (
            selected_status not in BOOKING_READY_STATUSES
            and available_month_keys
        )
        else None
    )
    status_navigation = [
        {
            **item,
            "count": (
                counts_by_status.get(BankTransaction.Status.IMPORTED, 0)
                + counts_by_status.get(BankTransaction.Status.MATCHED, 0)
                if item["value"] == OPEN_FILTER
                else ready_count
            ),
            "url": _overview_url(
                item["value"],
                navigation_month,
            ),
                "active": (
                    request.resolver_match.url_name
                in {
                    "bookkeeping_overview",
                    "bank_transaction_note",
                    "bank_transaction_booking",
                }
                and (
                    selected_status == item["value"]
                    or (
                        item["value"] == BankTransaction.Status.REVIEWED
                        and selected_status in BOOKING_READY_STATUSES
                    )
                    or (
                        item["value"] == OPEN_FILTER
                        and selected_status in {
                            BankTransaction.Status.IMPORTED,
                            BankTransaction.Status.MATCHED,
                        }
                    )
                )
            ),
        }
        for item in STATUS_NAVIGATION
    ]
    available_export_quarters = _available_export_quarters()
    export_period = _export_selection(
        params,
        available_export_quarters,
    )
    available_export_periods = [
        {
            "value": f"{year}-{quarter}",
            "label": f"{quarter} {year}",
        }
        for year, quarter in available_export_quarters
    ]
    ready_months = _available_ready_months()
    ready_quarters = [
        f"{year}-{quarter}" for year, quarter in available_export_quarters
    ]
    ready_period_type = params.get("period_type")
    ready_period = params.get("period")
    if ready_period_type not in PERIOD_TYPES:
        if _parse_export_period(ready_period):
            ready_period_type = "quarter"
        elif _parse_month(ready_period):
            ready_period_type = "month"
        elif _parse_month(params.get("month")):
            ready_period_type = "month"
            ready_period = params.get("month")
        else:
            ready_period_type = "month"
    ready_available_periods = (
        ready_months if ready_period_type == "month" else ready_quarters
    )
    ready_period = _period_value(ready_period_type, ready_period)
    if ready_period not in ready_available_periods:
        ready_period = (
            ready_available_periods[0] if ready_available_periods else ""
        )
    selected_status_details = STATUS_DETAILS[selected_status]
    month_suffix = f" für {_month_label(selected_month)}" if selected_month else ""
    return {
        "show_dashboard": show_dashboard,
        "selected_status": selected_status,
        "selected_status_label": selected_status_details["label"],
        "page_heading": selected_status_details["heading"],
        "selected_month": selected_month,
        "selected_month_label": _month_label(selected_month),
        "available_months": [
            {"value": month_key, "label": _month_label(month_key)}
            for month_key in available_month_keys
        ],
        "status_counts": {
            OPEN_FILTER: (
                counts_by_status.get(BankTransaction.Status.IMPORTED, 0)
                + counts_by_status.get(BankTransaction.Status.MATCHED, 0)
            ),
            BankTransaction.Status.REVIEWED: ready_count,
            BankTransaction.Status.BOOKED: counts_by_status.get(
                BankTransaction.Status.BOOKED,
                0,
            ),
        },
        "status_counts_by_code": counts_by_status,
        "status_navigation": status_navigation,
        "available_export_periods": available_export_periods,
        "export_period": export_period,
        "available_ready_months": [
            {"value": value, "label": _month_label(value)}
            for value in ready_months
        ],
        "available_ready_quarters": [
            {"value": value, "label": _period_label("quarter", value)}
            for value in ready_quarters
        ],
        "ready_period_type": ready_period_type,
        "ready_period": ready_period,
        "ready_period_label": _period_label(ready_period_type, ready_period),
        "empty_state_message": (
            (
                f"Keine offenen Transaktionen für {_month_label(selected_month)}."
                if selected_status in {
                    OPEN_FILTER,
                    BankTransaction.Status.IMPORTED,
                    BankTransaction.Status.MATCHED,
                }
                and selected_month
                else f"Keine {selected_status_details['empty_label']} Transaktionen"
                f"{month_suffix} vorhanden."
            )
        ),
    }


def _display_matching_rule(rule):
    expected_amount = (
        format_austrian_decimal(rule.expected_amount)
        if rule.expected_amount is not None
        else "–"
    )
    notes_preview, notes_truncated = _note_preview(rule.notes)
    next_version = MatchingRule.objects.filter(previous_version=rule).first()
    linked_transaction_count = getattr(rule, "_linked_transaction_count", None)
    if linked_transaction_count is None:
        linked_transaction_count = rule.transactions.count()
    return {
        "id": rule.pk,
        "name": rule.name,
        "display_name": f"{rule.name} – Version {rule.version_number}",
        "version_number": rule.version_number,
        "direction": rule.get_direction_display(),
        "direction_code": rule.direction,
        "match_type": rule.get_match_type_display(),
        "iban": rule.iban or "–",
        "expected_amount": expected_amount,
        "text_pattern": rule.text_pattern or "–",
        "active": rule.active,
        "status": "Aktiv" if rule.active else "Inaktiv",
        "notes": rule.notes,
        "notes_preview": notes_preview,
        "notes_truncated": notes_truncated,
        "booking_template_count": rule.booking_templates.count(),
        "linked_transaction_count": linked_transaction_count,
        "used": linked_transaction_count > 0,
        "previous_version_id": rule.previous_version_id,
        "next_version_id": next_version.pk if next_version else None,
    }


def _matching_template_initials(rule):
    return [
        {
            field_name: getattr(template, field_name)
            for field_name in (
                "position",
                "booking_text",
                "invoice_number",
                "partner_name",
                "gross_amount",
                "vat_symbol",
                "category",
            )
        }
        for template in rule.booking_templates.order_by("position", "id")
    ]


def _matching_template_formset(request, instance, initial=None):
    prefix = "templates"
    data = request.POST if f"{prefix}-TOTAL_FORMS" in request.POST else None
    formset = MatchingRuleBookingTemplateFormSet(
        data,
        instance=instance,
        prefix=prefix,
        initial=initial,
    )
    if initial:
        # A new version has no related template rows yet.  The copied rows
        # therefore have to be rendered as extra forms, not as existing rows.
        formset.extra = len(initial)
    return formset


def _matching_template_formset_is_valid(formset):
    return not formset.is_bound or formset.is_valid()


def _rule_is_used(rule):
    return BankTransaction.objects.filter(matched_rule=rule).exists()


def _matching_result_message(result):
    return (
        f"{result.auto_ready_count} automatisch buchungsfertig, "
        f"{result.incomplete_count} zugeordnet, aber Buchungsdaten "
        f"unvollständig, {result.unmatched_count} ohne Treffer, "
        f"{result.ambiguous_count} mehrdeutig."
    )


class AccountantPackageDownloadView(TemplateView):
    """Download endpoint for callers outside the overview form."""

    def get(self, request, *args, **kwargs):
        return self._download(request)

    def post(self, request, *args, **kwargs):
        return self._download(request)

    def _download(self, request):
        try:
            return _accountant_package_response(request)
        except AccountantPackageError as exc:
            messages.error(request, str(exc))
            period_type = request.POST.get("period_type") or request.GET.get(
                "period_type",
                "month",
            )
            period = request.POST.get("period") or request.GET.get("period", "")
            status = request.POST.get("status") or request.GET.get(
                "status",
                BankTransaction.Status.REVIEWED,
            )
            if status not in BOOKING_READY_STATUSES:
                status = BankTransaction.Status.REVIEWED
            return redirect(
                _overview_url(
                    status,
                    period=period,
                    period_type=period_type,
                )
            )


class BookkeepingOverviewView(TemplateView):
    template_name = "bookkeeping/overview.html"

    def get_context_data(self, **kwargs):
        filter_params = kwargs.pop("filter_params", None)
        quarter_balance_form = kwargs.pop("quarter_balance_form", None)
        bank_statement_form = kwargs.pop("bank_statement_form", None)
        context = super().get_context_data(**kwargs)
        navigation_context = _bookkeeping_navigation_context(
            self.request,
            filter_params=filter_params,
        )
        context.update(navigation_context)
        context["show_bank_import"] = (
            navigation_context["selected_status"] == BANK_IMPORT_FILTER
        )
        if navigation_context["show_dashboard"]:
            context.update(
                _dashboard_context(
                    filter_params if filter_params is not None else self.request.GET
                )
            )
            context["transactions"] = []
            context["show_preview"] = False
            context.setdefault("error_message", "")
            return context
        if context["show_bank_import"]:
            context.update(
                _bank_import_context(
                    filter_params if filter_params is not None else self.request.GET
                )
            )
            context["bank_statement_form"] = (
                bank_statement_form or BankStatementUploadForm()
            )
            context["transactions"] = []
            context["show_preview"] = False
            context.setdefault("error_message", "")
            return context

        ready_period_bounds = None
        if navigation_context["selected_status"] in BOOKING_READY_STATUSES:
            ready_period_bounds = _period_bounds(
                navigation_context["ready_period_type"],
                navigation_context["ready_period"],
            )
            context["quarter_control"] = _period_control_context(
                navigation_context["ready_period_type"],
                navigation_context["ready_period"],
            )
            context["quarter_control_available"] = context["quarter_control"][
                "available"
            ]
            if context["quarter_control"]["available"]:
                if quarter_balance_form is None:
                    if navigation_context["ready_period_type"] == "quarter":
                        quarter_balance_form = _quarter_balance_form(
                            navigation_context["ready_period"]
                        )
                context["quarter_balance_form"] = quarter_balance_form
            else:
                context["quarter_balance_form"] = None
            try:
                context["accountant_package"] = inspect_accountant_package(
                    period_type=navigation_context["ready_period_type"],
                    period=navigation_context["ready_period"],
                )
            except AccountantPackageError:
                context["accountant_package"] = None
        booking_entries_queryset = BookingEntry.objects.order_by(
            "created_at", "id"
        )
        if ready_period_bounds is not None:
            booking_entries_queryset = booking_entries_queryset.filter(
                payment_date__gte=ready_period_bounds[0],
                payment_date__lte=ready_period_bounds[1],
            )
        selected_transactions = BankTransaction.objects.select_related(
            "matched_rule"
        ).prefetch_related(
            Prefetch(
                "booking_entries",
                queryset=booking_entries_queryset,
                to_attr="booking_entries_for_display",
            ),
            Prefetch(
                "supporting_documents",
                queryset=SupportingDocument.objects.order_by("-created_at", "-id"),
                to_attr="supporting_documents_for_display",
            ),
        )
        if navigation_context["selected_status"] in {
            OPEN_FILTER,
            BANK_IMPORT_FILTER,
        }:
            selected_transactions = selected_transactions.filter(
                status__in=(
                    BankTransaction.Status.IMPORTED,
                    BankTransaction.Status.MATCHED,
                )
            )
        elif navigation_context["selected_status"] in BOOKING_READY_STATUSES:
            selected_transactions = selected_transactions.filter(
                status__in=BOOKING_READY_STATUSES
            )
            if ready_period_bounds is None:
                selected_transactions = selected_transactions.none()
            else:
                selected_transactions = selected_transactions.filter(
                    Q(
                        booking_date__gte=ready_period_bounds[0],
                        booking_date__lte=ready_period_bounds[1],
                    )
                    | Q(
                        booking_entries__payment_date__gte=ready_period_bounds[0],
                        booking_entries__payment_date__lte=ready_period_bounds[1],
                    )
                ).distinct()
        else:
            selected_transactions = selected_transactions.filter(
                status=navigation_context["selected_status"]
            )
        if (
            navigation_context["selected_month"]
            and navigation_context["selected_status"]
            not in BOOKING_READY_STATUSES
        ):
            selected_transactions = selected_transactions.filter(
                **_month_filter(navigation_context["selected_month"])
            )
        saved_transactions = list(
            selected_transactions.order_by("-booking_date", "-imported_at")
        )
        displayed_transactions = [
            self._display_saved_transaction(transaction)
            for transaction in saved_transactions
        ]
        if (
            navigation_context["selected_status"] in BOOKING_READY_STATUSES
            and ready_period_bounds is not None
        ):
            manual_invoice_queryset = ManualInvoice.objects.filter(
                status=ManualInvoice.Status.READY,
                payment_date__gte=ready_period_bounds[0],
                payment_date__lte=ready_period_bounds[1],
            ).prefetch_related(
                Prefetch(
                    "booking_entries",
                    queryset=ManualInvoiceEntry.objects.order_by(
                        "position", "created_at", "id"
                    ),
                    to_attr="booking_entries_for_display",
                )
            )
            displayed_transactions.extend(
                self._display_manual_invoice(invoice)
                for invoice in manual_invoice_queryset.order_by(
                    "-payment_date", "-updated_at", "-id"
                )
            )
            displayed_transactions.sort(
                key=lambda item: item["booking_date_sort"],
                reverse=True,
            )
        for transaction in displayed_transactions:
            transaction.pop("booking_date_sort", None)
        context["transactions"] = displayed_transactions
        context["show_preview"] = bool(displayed_transactions)
        context.setdefault("error_message", "")
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "export_csv":
            return self._export_csv(request)

        if request.POST.get("action") == "download_accountant_package":
            return self._download_accountant_package(request)

        if request.POST.get("action") == "save_quarter_balance":
            return self._save_quarter_balance(request)

        if request.POST.get("action") == "upload_bank_statement":
            return self._upload_bank_statement(request)

        if request.POST.get("action") == "retry_bank_statement":
            return self._retry_bank_statement(request)

        if request.POST.get("action") == "run_matching":
            matching_result = match_imported_transactions()
            messages.success(
                request,
                _matching_result_message(matching_result),
            )
            navigation_context = _bookkeeping_navigation_context(
                request,
                filter_params=request.POST,
            )
            return redirect(
                _overview_url(
                    navigation_context["selected_status"],
                    navigation_context["selected_month"],
                )
            )

        uploaded_file = request.FILES.get("json_file")
        if uploaded_file is None:
            return self.render_to_response(
                self.get_context_data(
                    error_message="Bitte eine JSON-Datei auswählen.",
                    filter_params=request.POST,
                )
            )

        try:
            payload = json.load(uploaded_file)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die Datei ist kein gültiges JSON.",
                    filter_params=request.POST,
                )
            )

        if not isinstance(payload, list):
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die JSON-Wurzel muss ein Array sein.",
                    filter_params=request.POST,
                )
            )

        try:
            import_payloads = [self._build_import_payload(item) for item in payload]
        except ValueError as exc:
            return self.render_to_response(
                self.get_context_data(
                    error_message=str(exc),
                    filter_params=request.POST,
                )
            )

        imported_count, existing_count = self._persist_transactions(import_payloads)
        matching_result = match_imported_transactions()
        messages.success(
            request,
            f"{imported_count} Transaktionen importiert, "
            f"{existing_count} bereits vorhanden.",
        )
        messages.info(
            request,
            _matching_result_message(matching_result),
        )
        newest_imported_month = max(
            (payload["booking_date"] for payload in import_payloads),
            default=None,
        )
        newest_imported_month_key = (
            newest_imported_month.strftime("%Y-%m")
            if newest_imported_month is not None
            else None
        )
        import_status = (
            BANK_IMPORT_FILTER
            if request.POST.get("status") == BANK_IMPORT_FILTER
            else OPEN_FILTER
        )
        return redirect(
            _overview_url(
                import_status,
                newest_imported_month_key,
            )
        )

    def _download_accountant_package(self, request):
        try:
            return _accountant_package_response(request)
        except AccountantPackageError as exc:
            return self.render_to_response(
                self.get_context_data(
                    error_message=str(exc),
                    filter_params=request.POST,
                )
            )
        except Exception:
            logger.exception("Accountant package creation failed")
            return self.render_to_response(
                self.get_context_data(
                    error_message="Das Übergabepaket konnte nicht erstellt werden.",
                    filter_params=request.POST,
                )
            )

    def _upload_bank_statement(self, request):
        form = BankStatementUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    filter_params=request.POST,
                    bank_statement_form=form,
                )
            )
        try:
            result = import_bank_statement(form.cleaned_data["pdf"])
        except (BankStatementParseError, BankStatementImportError) as exc:
            return self.render_to_response(
                self.get_context_data(
                    error_message=str(exc),
                    filter_params=request.POST,
                    bank_statement_form=form,
                )
            )
        if result.paperless_error:
            messages.error(
                request,
                "Kontoauszug gespeichert, aber die Übertragung zu Paperless ist "
                f"fehlgeschlagen: {result.paperless_error}",
            )
        else:
            messages.success(
                request,
                "Kontoauszug gespeichert. Übertragung zu Paperless läuft.",
            )
        return redirect(_overview_url(BANK_IMPORT_FILTER))

    def _retry_bank_statement(self, request):
        statement = get_object_or_404(
            BankStatement,
            pk=request.POST.get("statement_id"),
        )
        try:
            retry_bank_statement(statement)
        except BankStatementImportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Erneute Übertragung zu Paperless gestartet.")
        return redirect(_overview_url(BANK_IMPORT_FILTER))

    def _save_quarter_balance(self, request):
        period = _parse_export_period(request.POST.get("period", ""))
        if period is None:
            return self.render_to_response(
                self.get_context_data(
                    error_message="Bitte einen gültigen Zeitraum auswählen.",
                    filter_params=request.POST,
                )
            )

        form = _quarter_balance_form(period, request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    filter_params=request.POST,
                    quarter_balance_form=form,
                )
            )

        year, quarter = period.split("-", 1)
        QuarterBalance.objects.update_or_create(
            year=int(year),
            quarter=int(quarter[1]),
            defaults={
                "opening_balance": form.cleaned_data["opening_balance"],
                "closing_balance": form.cleaned_data["closing_balance"],
            },
        )
        messages.success(request, "Kontostände gespeichert.")
        selected_status = request.POST.get("status")
        if selected_status not in BOOKING_READY_STATUSES:
            selected_status = BankTransaction.Status.REVIEWED
        return redirect(_overview_url(selected_status, period=period))

    def _export_csv(self, request):
        requested_period = request.POST.get("period", "")
        if requested_period:
            export_period = _parse_export_period(requested_period) or ""
        else:
            export_year = request.POST.get("export_year") or request.POST.get(
                "year", ""
            )
            export_quarter = request.POST.get("export_quarter") or request.POST.get(
                "quarter", ""
            )
            if export_year or export_quarter:
                export_period = _export_selection(
                    request.POST,
                    [],
                )
            else:
                export_period = _export_selection(
                    request.POST,
                    _available_export_quarters(),
                )
        quarter_range = _export_period_bounds(export_period)
        if quarter_range is None:
            error_message = (
                "Bitte einen gültigen Zeitraum auswählen."
                if requested_period
                else "Bitte einen Zeitraum auswählen."
            )
            return self.render_to_response(
                self.get_context_data(
                    error_message=error_message,
                    filter_params=request.POST,
                )
            )

        quarter_control = _quarter_control_context(export_period)
        if quarter_control["has_inconsistencies"]:
            error_message = (
                "CSV-Export nicht möglich: Buchungsdaten sind nicht konsistent."
            )
            if quarter_control["booking_entries"] == 0:
                error_message += " Keine Buchungszeilen im ausgewählten Quartal."
            return self.render_to_response(
                self.get_context_data(
                    error_message=error_message,
                    filter_params=request.POST,
                )
            )

        try:
            content = export_reviewed_transactions_csv(
                start_date=quarter_range[0],
                end_date=quarter_range[1],
            )
        except CsvExportError as exc:
            return self.render_to_response(
                self.get_context_data(
                    error_message=str(exc),
                    filter_params=request.POST,
                )
            )
        except Exception:
            logger.exception("Bookkeeping CSV export failed")
            return self.render_to_response(
                self.get_context_data(
                    error_message="Die CSV-Datei konnte nicht erstellt werden.",
                    filter_params=request.POST,
                )
            )

        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        export_year, export_quarter = export_period.split("-", 1)
        response["Content-Disposition"] = (
            f'attachment; filename="Buchungszeilen_{int(export_year)}_'
            f'{str(export_quarter).upper()}.csv"'
        )
        return response

    @classmethod
    def _build_import_payload(cls, transaction):
        if not isinstance(transaction, dict):
            raise ValueError("Eine Transaktion ist ungültig.")

        booking_date = cls._parse_booking_date(transaction.get("booking"))
        if booking_date is None:
            raise ValueError("Eine Transaktion enthält kein gültiges Buchungsdatum.")
        value_date = cls._parse_booking_date(transaction.get("valuation"))

        amount = transaction.get("amount")
        if not isinstance(amount, dict):
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")
        converted_amount, direction = cls._parse_amount(amount)

        partner_account = transaction.get("partnerAccount")
        if not isinstance(partner_account, dict):
            partner_account = {}

        currency = cls._text_or_empty(amount.get("currency")) or "EUR"
        if len(currency) > 3:
            raise ValueError("Eine Transaktion enthält eine ungültige Währung.")

        reference = cls._text_or_empty(transaction.get("reference"))
        purpose = reference or cls._text_or_empty(transaction.get("receiverReference"))

        return {
            "source_hash": cls._source_hash(transaction),
            "booking_date": booking_date,
            "value_date": value_date or booking_date,
            "partner_name": cls._text_or_empty(transaction.get("partnerName")),
            "partner_iban": cls._text_or_empty(partner_account.get("iban")),
            "amount": converted_amount,
            "currency": currency,
            "purpose": purpose,
            "direction": direction,
            "source": BankTransaction.Source.BANK_IMPORT,
            "status": BankTransaction.Status.IMPORTED,
        }

    @classmethod
    def _persist_transactions(cls, import_payloads):
        imported_count = 0
        existing_count = 0
        source_hashes = [payload["source_hash"] for payload in import_payloads]

        with db_transaction.atomic():
            existing_transactions = {
                bank_transaction.source_hash: bank_transaction
                for bank_transaction in BankTransaction.objects.select_for_update().filter(
                    source_hash__in=source_hashes
                )
            }
            existing_hashes = set(existing_transactions)
            for payload in import_payloads:
                source_hash = payload["source_hash"]
                if source_hash in existing_hashes:
                    existing_count += 1
                    existing_transaction = existing_transactions[source_hash]
                    if (
                        existing_transaction.value_date is None
                        and payload["value_date"] is not None
                    ):
                        existing_transaction.value_date = payload["value_date"]
                        existing_transaction.save(update_fields=("value_date",))
                    continue
                existing_transactions[source_hash] = BankTransaction.objects.create(
                    **payload
                )
                existing_hashes.add(source_hash)
                imported_count += 1

        return imported_count, existing_count

    @staticmethod
    def _source_hash(transaction):
        serialized = json.dumps(
            transaction,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _parse_booking_date(cls, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = cls._text_or_empty(value)
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None

    @classmethod
    def _parse_amount(cls, amount):
        value = amount.get("value")
        if value is None:
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")
        try:
            precision = int(amount.get("precision") or 0)
            if precision < 0:
                raise ValueError
            converted = Decimal(str(value)) / (Decimal("10") ** precision)
            converted = converted.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.") from None

        if converted > 0:
            return converted, BankTransaction.Direction.INCOMING
        if converted < 0:
            return converted, BankTransaction.Direction.OUTGOING
        raise ValueError("Eine Transaktion enthält keinen gültigen Betrag.")

    @classmethod
    def _display_saved_transaction(cls, transaction):
        direction_labels = {
            BankTransaction.Direction.INCOMING: "Eingang",
            BankTransaction.Direction.OUTGOING: "Ausgang",
        }
        direction = direction_labels.get(transaction.direction, "–")
        direction_code = transaction.direction if direction != "–" else ""
        transaction_notes_preview, transaction_notes_truncated = _note_preview(
            transaction.notes
        )
        matching_rule_notes = (
            transaction.matched_rule.notes
            if transaction.matched_rule_id
            else ""
        )
        matching_rule_notes_preview, matching_rule_notes_truncated = _note_preview(
            matching_rule_notes
        )
        booking_entries = getattr(transaction, "booking_entries_for_display", ())
        supporting_documents = getattr(
            transaction,
            "supporting_documents_for_display",
            (),
        )
        booking_entry_data = [
            cls._display_booking_entry(entry, transaction.currency)
            for entry in booking_entries
        ]
        original_purpose = cls._text_or_empty(transaction.purpose)
        booking_entry_total = sum(
            (entry.gross_amount for entry in booking_entries),
            Decimal("0"),
        )
        return {
            "id": transaction.pk,
            "booking_date": transaction.booking_date.strftime("%d.%m.%Y"),
            "name": cls._text_or_dash(transaction.partner_name),
            "iban": cls._text_or_dash(transaction.partner_iban),
            "amount": cls._format_saved_amount(transaction.amount, transaction.currency),
            "direction_code": direction_code,
            "direction": direction,
            "purpose": cls._text_or_dash(transaction.purpose),
            "show_original_purpose": bool(
                original_purpose
                and not any(
                    original_purpose == cls._text_or_empty(entry.booking_text)
                    for entry in booking_entries
                )
            ),
            "status_code": transaction.status,
            "status": (
                "Buchungsfertig"
                if transaction.status in BOOKING_READY_STATUSES
                else transaction.get_status_display()
            ),
            "open_reason": (
                "Buchungsdaten unvollständig"
                if transaction.status == BankTransaction.Status.MATCHED
                else (
                    "Mehrdeutig"
                    if transaction.status == BankTransaction.Status.IMPORTED
                    and transaction.matched_rule_id
                    else "Kein Treffer"
                )
            ),
            "matched_rule": (
                str(transaction.matched_rule)
                if transaction.matched_rule_id
                else "–"
            ),
            "matched_rule_id": transaction.matched_rule_id,
            "matched_rule_url": (
                reverse(
                    "matching_rule_detail",
                    kwargs={"pk": transaction.matched_rule_id},
                )
                if transaction.matched_rule_id
                else ""
            ),
            "matching_rule_notes": matching_rule_notes,
            "matching_rule_notes_preview": matching_rule_notes_preview,
            "matching_rule_notes_truncated": matching_rule_notes_truncated,
            "notes": transaction.notes,
            "notes_preview": transaction_notes_preview,
            "notes_truncated": transaction_notes_truncated,
            "booking_data": booking_entry_data[0] if booking_entry_data else None,
            "booking_entries": booking_entry_data,
            "booking_entry_count": len(booking_entry_data),
            "booking_entry_total": (
                cls._format_saved_amount(
                    booking_entry_total,
                    transaction.currency,
                )
                if booking_entry_data
                else None
            ),
            "supporting_document_count": len(supporting_documents),
            "booking_date_sort": transaction.booking_date,
        }

    @classmethod
    def _display_manual_invoice(cls, invoice):
        booking_entries = getattr(invoice, "booking_entries_for_display", ())
        booking_entry_data = [
            cls._display_booking_entry(entry, "EUR") for entry in booking_entries
        ]
        booking_entry_total = sum(
            (
                entry.gross_amount
                for entry in booking_entries
                if entry.gross_amount is not None
            ),
            Decimal("0"),
        )
        return {
            "id": invoice.pk,
            "manual_invoice": True,
            "manual_invoice_url": reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            "manual_invoice_reset_url": reverse(
                "manual_invoice_reset_booking",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            "manual_invoice_delete_url": reverse(
                "manual_invoice_delete",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            "manual_invoice_paperless_delete_url": reverse(
                "manual_invoice_paperless_delete",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            "paperless_document_url": (
                PaperlessClient.document_url(invoice.paperless_document_id)
                if invoice.paperless_deleted_at is None
                else ""
            ),
            "paperless_can_delete": (
                invoice.paperless_deleted_at is None
                and (
                    bool(invoice.paperless_document_id)
                    or bool(invoice.paperless_task_id)
                    or invoice.paperless_status
                    in {
                        ManualInvoice.PaperlessStatus.COMPLETED,
                        ManualInvoice.PaperlessStatus.PENDING,
                        ManualInvoice.PaperlessStatus.FAILED,
                    }
                )
            ),
            "booking_date": (
                invoice.payment_date.strftime("%d.%m.%Y")
                if invoice.payment_date
                else "–"
            ),
            "booking_date_sort": invoice.payment_date or date.min,
            "name": cls._text_or_dash(invoice.partner_name),
            "iban": "–",
            "amount": format_austrian_money(invoice.gross_amount, "EUR"),
            "direction_code": "outgoing",
            "direction": "Ausgang",
            "purpose": "–",
            "show_original_purpose": False,
            "status_code": "manual",
            "status": "Buchungsfertig",
            "open_reason": "",
            "matched_rule": "–",
            "matched_rule_id": None,
            "matched_rule_url": "",
            "matching_rule_notes": "",
            "matching_rule_notes_preview": "",
            "matching_rule_notes_truncated": False,
            "notes": invoice.notes,
            "notes_preview": _note_preview(invoice.notes)[0],
            "notes_truncated": _note_preview(invoice.notes)[1],
            "booking_data": booking_entry_data[0] if booking_entry_data else None,
            "booking_entries": booking_entry_data,
            "booking_entry_count": len(booking_entry_data),
            "booking_entry_total": format_austrian_money(
                booking_entry_total, "EUR"
            ),
        }

    @classmethod
    def _display_booking_entry(cls, booking_entry, currency):
        if booking_entry is None:
            return None
        receipt_group = booking_entry.get_receipt_group_display()
        vat_symbol = booking_entry.get_vat_symbol_display()
        category = category_description(booking_entry.category)
        return {
            "receipt": " / ".join(
                part for part in (receipt_group, booking_entry.receipt_number)
                if part
            ) or "–",
            "payment_date": booking_entry.payment_date.strftime("%d.%m.%Y"),
            "booking_text": cls._text_or_dash(booking_entry.booking_text),
            "invoice_number": cls._text_or_dash(booking_entry.invoice_number),
            "partner_name": cls._text_or_dash(booking_entry.partner_name),
            "gross_amount": cls._format_saved_amount(
                booking_entry.gross_amount,
                currency,
            ),
            "vat_symbol": cls._text_or_dash(vat_symbol),
            "category": cls._text_or_dash(category),
        }

    @classmethod
    def _format_saved_amount(cls, amount, currency):
        return format_austrian_money(amount, cls._text_or_dash(currency))

    @staticmethod
    def _text_or_empty(value):
        text = str(value).strip() if value is not None else ""
        return text

    @classmethod
    def _text_or_dash(cls, value):
        return cls._text_or_empty(value) or "–"


class ManualInvoiceListView(TemplateView):
    template_name = "bookkeeping/manual_invoice_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        refresh_pending_manual_invoice_tasks()
        context.update(_bookkeeping_navigation_context(self.request))
        context["manual_invoice_upload_form"] = kwargs.pop(
            "manual_invoice_upload_form", ManualInvoiceUploadForm()
        )
        context["manual_invoices"] = [
            display_manual_invoice(invoice)
            for invoice in ManualInvoice.objects.filter(
                status=ManualInvoice.Status.DRAFT,
            ).order_by(
                "-updated_at", "-id"
            )
        ]
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "import_paperless_invoices":
            try:
                summary = import_paperless_invoices()
            except PaperlessInvoiceImportError as exc:
                messages.error(request, str(exc))
            except BookkeepingPaperlessError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    (
                        f"{summary.new_count} Beleg(e) übernommen, "
                        f"{summary.existing_count} bereits vorhanden, "
                        f"{summary.ocr_unavailable_count} ohne OCR, "
                        f"{summary.ai_suggestion_count} KI-Vorschlag/-Vorschläge erstellt."
                    ),
                )
                if summary.error_count:
                    messages.warning(
                        request,
                        f"{summary.error_count} Beleg(e) konnten nicht vollständig verarbeitet werden.",
                    )
                if summary.waiting_count:
                    messages.info(
                        request,
                        f"{summary.waiting_count} weitere(s) Dokument(e) warten auf den nächsten Lauf.",
                    )
            return redirect("manual_invoice_list")

        if request.POST.get("action") == "retry_manual_invoice":
            invoice = get_object_or_404(
                ManualInvoice,
                reference_uuid=request.POST.get("reference_uuid"),
            )
            try:
                retry_manual_invoice(invoice)
            except ManualInvoiceImportError as exc:
                messages.error(request, str(exc))
            except BookkeepingPaperlessError:
                pass
            else:
                messages.success(request, "Erneute Übertragung zu Paperless gestartet.")
            return redirect("manual_invoice_list")

        form = ManualInvoiceUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(manual_invoice_upload_form=form)
            )
        try:
            result = import_manual_invoice(form.cleaned_data["pdf"])
        except ManualInvoiceImportError as exc:
            form.add_error("pdf", str(exc))
            return self.render_to_response(
                self.get_context_data(manual_invoice_upload_form=form)
            )
        try:
            start_manual_invoice_upload(result.invoice)
        except BookkeepingPaperlessError:
            pass
        else:
            messages.success(request, "Rechnung hochgeladen. Paperless-OCR wird vorbereitet.")
        return redirect(
            "manual_invoice_edit",
            reference_uuid=result.invoice.reference_uuid,
        )


class ManualInvoiceEditView(TemplateView):
    template_name = "bookkeeping/manual_invoice_edit.html"
    formset_prefix = "entries"

    def _invoice(self):
        return get_object_or_404(
            ManualInvoice,
            reference_uuid=self.kwargs["reference_uuid"],
        )

    def _formset(self, invoice, data=None, final=False, initial=None):
        formset = ManualInvoiceEntryFormSet(
            data,
            instance=invoice,
            prefix=self.formset_prefix,
            initial=initial,
            form_kwargs={
                "manual_invoice": invoice,
                "final": final,
            },
            manual_invoice=invoice,
            final=final,
        )
        # A draft without entries still renders one visible input row.  Make
        # that row a real form (index 0), so its values are included in the
        # POST even when the user does not click "Buchungszeile hinzufügen".
        if data is None and not invoice.booking_entries.exists():
            formset.extra = max(1, len(initial or []))
        return formset

    def _context(self, invoice, form, formset, error_message=""):
        context = _bookkeeping_navigation_context(self.request)
        context.update(
            {
                "manual_invoice": invoice,
                "manual_invoice_form": form,
                "manual_invoice_formset": formset,
                "manual_invoice_error": error_message,
                "return_url": reverse("manual_invoice_list"),
                "manual_invoice_paperless_delete_url": reverse(
                    "manual_invoice_paperless_delete",
                    kwargs={"reference_uuid": invoice.reference_uuid},
                ),
            }
        )
        context.update(ai_ui_state(invoice))
        return context

    @staticmethod
    def _assign_manual_invoice_form(invoice, form):
        invoice.payment_date = form.cleaned_data.get("payment_date")
        invoice.invoice_number = form.cleaned_data.get("invoice_number", "")
        invoice.invoice_date = form.cleaned_data.get("invoice_date")
        invoice.partner_name = form.cleaned_data.get("partner_name", "")
        invoice.gross_amount = form.cleaned_data.get("gross_amount")
        invoice.notes = form.cleaned_data.get("notes", "")

    @staticmethod
    def _has_posted_booking_data(formset):
        for form in formset.forms:
            if any(
                str(form.data.get(form.add_prefix(field_name), "")).strip()
                for field_name in ("booking_text", "gross_amount", "category")
            ):
                return True
        return False

    def _analyze_post(self, request, invoice):
        form = ManualInvoiceForm(request.POST, instance=invoice, final=False)
        form_is_valid = form.is_valid()
        formset = self._formset(invoice, request.POST, final=False)
        has_posted_booking_data = self._has_posted_booking_data(formset)
        if form_is_valid:
            self._assign_manual_invoice_form(invoice, form)
            invoice.save()

        outcome = run_manual_invoice_analysis(invoice, force=True)
        invoice.refresh_from_db()
        if outcome.kind == "completed" and outcome.existing_data_untouched:
            messages.info(request, "Bestehende Buchungsdaten wurden nicht verändert.")
        elif outcome.kind == "failed" and outcome.message:
            messages.error(request, outcome.message)
        elif outcome.kind == "ocr_unavailable":
            messages.info(
                request,
                "OCR wird noch verarbeitet"
                if outcome.message == OCR_UNAVAILABLE_MESSAGE
                else outcome.message,
            )
        elif outcome.kind == "paperless_failed" and outcome.message:
            messages.error(request, outcome.message)
        elif outcome.kind in {"paperless_pending", "paperless_not_started"}:
            messages.info(request, outcome.message)

        if form_is_valid and not has_posted_booking_data:
            form = ManualInvoiceForm(instance=invoice)
            formset = self._formset(
                invoice,
                initial=formset_initial_from_analysis(invoice),
            )
        return self.render_to_response(self._context(invoice, form, formset))

    def get(self, request, *args, **kwargs):
        invoice = self._invoice()
        refresh_pending_manual_invoice_tasks()
        invoice.refresh_from_db()
        run_manual_invoice_analysis(invoice)
        invoice.refresh_from_db()
        return self.render_to_response(
            self._context(
                invoice,
                ManualInvoiceForm(instance=invoice),
                self._formset(
                    invoice,
                    initial=formset_initial_from_analysis(invoice),
                ),
            )
        )

    def post(self, request, *args, **kwargs):
        invoice = self._invoice()
        action = request.POST.get("action", "save_draft")
        if action == "retry_paperless":
            try:
                retry_manual_invoice(invoice)
            except ManualInvoiceImportError as exc:
                messages.error(request, str(exc))
            except BookkeepingPaperlessError:
                pass
            else:
                messages.success(request, "Paperless-Übertragung erneut gestartet.")
            return redirect(
                "manual_invoice_edit",
                reference_uuid=invoice.reference_uuid,
            )
        if action == "retry_paperless_dates":
            if invoice.status != ManualInvoice.Status.READY:
                return redirect(
                    "manual_invoice_edit",
                    reference_uuid=invoice.reference_uuid,
                )
            try:
                PaperlessClient.update_manual_invoice_dates(invoice)
            except BookkeepingPaperlessError as exc:
                invoice.paperless_error = (
                    "Paperless-Datumsfelder konnten nicht aktualisiert werden: "
                    f"{exc}"
                )[:500]
                invoice.save(update_fields=("paperless_error", "updated_at"))
            else:
                invoice.paperless_error = ""
                invoice.save(update_fields=("paperless_error", "updated_at"))
                messages.success(request, "Paperless-Datumsfelder aktualisiert.")
            return redirect(
                "manual_invoice_edit",
                reference_uuid=invoice.reference_uuid,
            )
        if action == "analyze_ai":
            return self._analyze_post(request, invoice)
        finalize = action == "finalize"
        form = ManualInvoiceForm(
            request.POST,
            instance=invoice,
            final=finalize,
        )
        form_is_valid = form.is_valid()
        candidate = form.save(commit=False) if form_is_valid else invoice
        formset = self._formset(candidate, request.POST, final=finalize)
        if action not in {"save_draft", "finalize"}:
            form.add_error(None, "Die gewünschte Aktion ist ungültig.")
            form_is_valid = False

        if form_is_valid and formset.is_valid():
            rounding_difference = formset.rounding_difference
            self._assign_manual_invoice_form(invoice, form)
            invoice.status = (
                ManualInvoice.Status.READY
                if finalize
                else ManualInvoice.Status.DRAFT
            )
            with db_transaction.atomic():
                invoice.save()
                formset.instance = invoice
                formset.manual_invoice = invoice
                if finalize:
                    formset.apply_rounding_difference()
                formset.save()

            warning = duplicate_manual_invoice_warning(invoice)
            if warning:
                messages.warning(request, warning)
            if finalize:
                if (
                    invoice.paperless_status
                    != ManualInvoice.PaperlessStatus.COMPLETED
                    or not invoice.paperless_document_id
                ):
                    paperless_error = (
                        invoice.paperless_error
                        or "Die Rechnung kann erst abgeschlossen werden, wenn sie in "
                        "Paperless abgelegt ist."
                    )
                    invoice.status = ManualInvoice.Status.DRAFT
                    invoice.paperless_error = paperless_error[:500]
                    invoice.save(
                        update_fields=("status", "paperless_error", "updated_at")
                    )
                    return redirect(
                        "manual_invoice_edit",
                        reference_uuid=invoice.reference_uuid,
                    )
                try:
                    PaperlessClient.update_manual_invoice_dates(invoice)
                except BookkeepingPaperlessError as exc:
                    paperless_error = (
                        "Paperless-Datumsfelder konnten nicht aktualisiert werden: "
                        f"{exc}"
                    )[:500]
                    invoice.paperless_error = paperless_error
                    invoice.save(
                        update_fields=("paperless_error", "updated_at")
                    )
                    return redirect(
                        "manual_invoice_edit",
                        reference_uuid=invoice.reference_uuid,
                    )
                invoice.paperless_error = ""
                invoice.save(update_fields=("paperless_error", "updated_at"))
                messages.success(request, "Rechnung geprüft und abgeschlossen.")
                if abs(rounding_difference) == Decimal("0.01"):
                    messages.warning(
                        request,
                        "Die Rundungsdifferenz von "
                        f"{format_austrian_decimal(rounding_difference)} EUR "
                        "wurde in der größten Buchungszeile ausgeglichen.",
                    )
                return redirect("manual_invoice_list")
            if not finalize:
                messages.success(request, "Rechnungsentwurf gespeichert.")
                return redirect(
                    "manual_invoice_edit",
                    reference_uuid=invoice.reference_uuid,
                )

        return self.render_to_response(
            self._context(invoice, form, formset)
        )


class BookingSetResetView(TemplateView):
    template_name = "bookkeeping/booking_set_reset_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("transaction_pk") is not None:
            self.owner_kind = "bank_transaction"
            self.owner = get_object_or_404(
                BankTransaction,
                pk=kwargs["transaction_pk"],
            )
        else:
            self.owner_kind = "manual_invoice"
            self.owner = get_object_or_404(
                ManualInvoice,
                reference_uuid=kwargs["reference_uuid"],
            )
        return super().dispatch(request, *args, **kwargs)

    def _entries(self):
        if self.owner_kind == "bank_transaction":
            return list(
                BookingEntry.objects.filter(
                    bank_transaction=self.owner
                ).order_by("created_at", "id")
            )
        return list(
            ManualInvoiceEntry.objects.filter(
                manual_invoice=self.owner
            ).order_by("position", "created_at", "id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = self._entries()
        if self.owner_kind == "bank_transaction":
            source_type = "Banktransaktion"
            source_name = self.owner.partner_name or "–"
            payment_date = self.owner.booking_date
            currency = self.owner.currency
        else:
            source_type = "Manueller Beleg"
            source_name = self.owner.partner_name or "–"
            payment_date = self.owner.payment_date
            currency = "EUR"
        total = sum(
            (entry.gross_amount for entry in entries if entry.gross_amount is not None),
            Decimal("0"),
        )
        context.update(
            {
                "owner_kind": self.owner_kind,
                "owner": self.owner,
                "source_type": source_type,
                "source_name": source_name,
                "payment_date": payment_date,
                "cancel_url": (
                    _overview_url(
                        OPEN_FILTER,
                        self.owner.booking_date.strftime("%Y-%m"),
                    )
                    if self.owner_kind == "bank_transaction"
                    else reverse("manual_invoice_list")
                ),
                "entry_count": len(entries),
                "entry_total": format_austrian_money(total, currency),
                "booking_texts": [
                    {
                        "text": entry.booking_text or "–",
                        "amount": format_austrian_money(
                            entry.gross_amount,
                            currency,
                        ),
                    }
                    for entry in entries
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        if self.owner_kind == "bank_transaction":
            reset_bank_transaction_booking(self.owner)
            messages.success(
                request,
                "Buchungssatz wurde zurückgesetzt. Quelldaten und Dokumente bleiben erhalten.",
            )
            return redirect(
                _overview_url(
                    OPEN_FILTER,
                    self.owner.booking_date.strftime("%Y-%m"),
                )
            )
        reset_manual_invoice_booking(self.owner)
        messages.success(
            request,
            "Buchungssatz wurde zurückgesetzt. Quelldaten und Dokumente bleiben erhalten.",
        )
        return redirect("manual_invoice_list")


class ManualInvoiceDeleteView(TemplateView):
    template_name = "bookkeeping/manual_invoice_delete_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(
            ManualInvoice,
            reference_uuid=kwargs["reference_uuid"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = list(
            ManualInvoiceEntry.objects.filter(
                manual_invoice=self.invoice
            ).order_by("position", "created_at", "id")
        )
        context.update(
            {
                "manual_invoice": self.invoice,
                "entry_count": len(entries),
                "entry_total": format_austrian_money(
                    sum(
                        (
                            entry.gross_amount
                            for entry in entries
                            if entry.gross_amount is not None
                        ),
                        Decimal("0"),
                    ),
                    "EUR",
                ),
                "paperless_document_id": self.invoice.paperless_document_id,
                "original_filename": (
                    os.path.basename(self.invoice.temporary_pdf.name)
                    if self.invoice.temporary_pdf
                    else "–"
                ),
                "booking_texts": [entry.booking_text or "–" for entry in entries],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        try:
            delete_manual_invoice_completely(self.invoice)
        except ManualInvoiceDeletionError as exc:
            messages.error(request, str(exc))
            return redirect(
                "manual_invoice_delete",
                reference_uuid=self.invoice.reference_uuid,
            )
        messages.success(request, "Manueller Beleg und Paperless-Dokument wurden gelöscht.")
        return redirect("manual_invoice_list")


class ManualInvoicePaperlessDeleteView(TemplateView):
    template_name = "bookkeeping/manual_invoice_paperless_delete_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(
            ManualInvoice,
            reference_uuid=kwargs["reference_uuid"],
        )
        self.return_url = self._return_url()
        return super().dispatch(request, *args, **kwargs)

    def _return_url(self):
        if self.invoice.status == ManualInvoice.Status.READY:
            month = (
                self.invoice.payment_date.strftime("%Y-%m")
                if self.invoice.payment_date
                else None
            )
            return _overview_url(
                BankTransaction.Status.REVIEWED,
                month=month,
            )
        return reverse("manual_invoice_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "manual_invoice": self.invoice,
                "paperless_document_id": self.invoice.paperless_document_id,
                "original_filename": (
                    os.path.basename(self.invoice.temporary_pdf.name)
                    if self.invoice.temporary_pdf
                    else "–"
                ),
                "return_url": self.return_url,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        try:
            delete_manual_invoice_from_paperless(self.invoice)
        except ManualInvoiceDeletionError as exc:
            messages.error(request, str(exc))
            return redirect(
                "manual_invoice_paperless_delete",
                reference_uuid=self.invoice.reference_uuid,
            )
        messages.success(request, "Das Paperless-Dokument wurde gelöscht. Der manuelle Beleg bleibt erhalten.")
        return redirect(self.return_url)


class BankTransactionNoteView(TemplateView):
    template_name = "bookkeeping/transaction_note.html"

    def _navigation_context(self):
        return _bookkeeping_navigation_context(self.request)

    def _context_for_transaction(self, bank_transaction, form, navigation_context):
        return {
            **navigation_context,
            "bank_transaction": bank_transaction,
            "form": form,
            "return_url": _overview_url(
                navigation_context["selected_status"],
                navigation_context["selected_month"],
            ),
        }

    def _reject_if_note_is_read_only(
        self,
        request,
        bank_transaction,
        navigation_context,
    ):
        if bank_transaction.status in NOTE_EDITABLE_STATUSES:
            return None
        messages.error(
            request,
            "Anmerkungen können nur bei zugeordneten oder buchungsfertigen "
            "Transaktionen bearbeitet werden.",
        )
        return redirect(
            _overview_url(
                navigation_context["selected_status"],
                navigation_context["selected_month"],
            )
        )

    def get(self, request, *args, **kwargs):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=kwargs["pk"],
        )
        navigation_context = self._navigation_context()
        rejection = self._reject_if_note_is_read_only(
            request,
            bank_transaction,
            navigation_context,
        )
        if rejection is not None:
            return rejection
        form = BankTransactionNoteForm(instance=bank_transaction)
        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                form,
                navigation_context,
            )
        )

    def post(self, request, *args, **kwargs):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=kwargs["pk"],
        )
        navigation_context = self._navigation_context()
        rejection = self._reject_if_note_is_read_only(
            request,
            bank_transaction,
            navigation_context,
        )
        if rejection is not None:
            return rejection
        form = BankTransactionNoteForm(
            request.POST,
            instance=bank_transaction,
        )
        if form.is_valid():
            bank_transaction.notes = form.cleaned_data["notes"]
            bank_transaction.save(update_fields=("notes",))
            messages.success(request, "Anmerkung gespeichert.")
            return redirect(
                _overview_url(
                    navigation_context["selected_status"],
                    navigation_context["selected_month"],
                )
            )
        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                form,
                navigation_context,
            )
        )


class BookingEntryView(TemplateView):
    template_name = "bookkeeping/booking_entry.html"
    formset_prefix = "entries"

    def _navigation_context(self):
        return _bookkeeping_navigation_context(self.request)

    @staticmethod
    def _existing_entries(bank_transaction):
        return list(
            bank_transaction.booking_entries.order_by("created_at", "id")
        )

    def _initial_rows(self, bank_transaction, existing_entries):
        if existing_entries:
            return None, None
        if (
            bank_transaction.status == BankTransaction.Status.MATCHED
            and bank_transaction.matched_rule_id
        ):
            snapshot, error = build_booking_entry_snapshot(bank_transaction)
            if snapshot is not None or error:
                return snapshot or [{}], error
        return [{}], None

    def _legacy_post_data(self, request, bank_transaction, existing_entries):
        if f"{self.formset_prefix}-TOTAL_FORMS" in request.POST:
            return request.POST

        data = request.POST.copy()
        data[f"{self.formset_prefix}-TOTAL_FORMS"] = "1"
        data[f"{self.formset_prefix}-INITIAL_FORMS"] = (
            "1" if existing_entries else "0"
        )
        if existing_entries:
            data[f"{self.formset_prefix}-0-id"] = str(existing_entries[0].pk)
        for field_name in BookingEntryForm.Meta.fields:
            if field_name in request.POST:
                data[f"{self.formset_prefix}-0-{field_name}"] = request.POST[
                    field_name
                ]
        return data

    def _formset(
        self,
        data,
        bank_transaction,
        final,
        initial,
    ):
        formset = BookingEntryFormSet(
            data,
            instance=bank_transaction,
            prefix=self.formset_prefix,
            initial=initial,
            form_kwargs={
                "bank_transaction": bank_transaction,
                "final": final,
            },
        )
        if initial:
            formset.extra = len(initial)
            formset.initial_row_count = len(initial)
            for form in formset.forms:
                form.empty_permitted = False
        return formset

    def _context_for_transaction(
        self,
        bank_transaction,
        formset,
        notes_form,
        navigation_context,
        snapshot_error="",
        supporting_document_form=None,
    ):
        if bank_transaction.status == BankTransaction.Status.MATCHED:
            page_heading = "Buchungsdaten ergänzen"
        elif bank_transaction.status in BOOKING_READY_STATUSES:
            page_heading = "Buchungsdaten bearbeiten"
        else:
            page_heading = "Buchung erfassen"
        first_form = formset.forms[0] if formset.forms else None
        return {
            **navigation_context,
            "bank_transaction": bank_transaction,
            "booking_entry": (
                first_form.instance if first_form and first_form.instance.pk else None
            ),
            "booking_entries": [
                form.instance for form in formset.forms if form.instance.pk
            ],
            "form": first_form,
            "formset": formset,
            "notes_form": notes_form,
            "page_heading": page_heading,
            "booking_snapshot_error": snapshot_error,
            "supporting_documents": [
                display_supporting_document(document)
                for document in SupportingDocument.objects.filter(
                    bank_transaction=bank_transaction
                ).select_related("matching_rule").order_by("-created_at", "-id")
            ],
            "supporting_document_form": (
                supporting_document_form or SupportingDocumentUploadForm()
            ),
            "return_url": _overview_url(
                navigation_context["selected_status"],
                navigation_context["selected_month"],
            ),
        }

    def _reject_if_booked(
        self,
        request,
        bank_transaction,
        navigation_context,
    ):
        return None

    def get(self, request, *args, **kwargs):
        refresh_pending_supporting_documents()
        bank_transaction = get_object_or_404(BankTransaction, pk=kwargs["pk"])
        navigation_context = self._navigation_context()
        rejection = self._reject_if_booked(
            request, bank_transaction, navigation_context
        )
        if rejection is not None:
            return rejection
        existing_entries = self._existing_entries(bank_transaction)
        initial, snapshot_error = self._initial_rows(
            bank_transaction, existing_entries
        )
        formset = self._formset(
            None, bank_transaction, final=False, initial=initial
        )
        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                formset,
                BankTransactionNoteForm(instance=bank_transaction),
                navigation_context,
                snapshot_error,
            )
        )

    def post(self, request, *args, **kwargs):
        bank_transaction = get_object_or_404(BankTransaction, pk=kwargs["pk"])
        navigation_context = self._navigation_context()
        action = request.POST.get("action", "save_draft")
        if action == "retry_supporting_document":
            document = get_object_or_404(
                SupportingDocument,
                bank_transaction=bank_transaction,
                reference_uuid=request.POST.get("reference_uuid"),
            )
            try:
                retry_supporting_document(document)
            except SupportingDocumentError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Erneute Übertragung zu Paperless gestartet.")
            return redirect(
                reverse(
                    "bank_transaction_booking",
                    kwargs={"pk": bank_transaction.pk},
                )
                + "?"
                + urlencode(
                    {
                        "status": navigation_context["selected_status"],
                        "month": navigation_context["selected_month"],
                    }
                )
            )
        if action == "upload_supporting_document":
            document_form = SupportingDocumentUploadForm(
                request.POST,
                request.FILES,
            )
            if document_form.is_valid():
                result = import_supporting_document(
                    document_form.cleaned_data["pdf"],
                    bank_transaction=bank_transaction,
                )
                if result.document.transfer_status == SupportingDocument.TransferStatus.FAILED:
                    messages.error(
                        request,
                        f"Beleg gespeichert, aber Paperless meldet einen Fehler: "
                        f"{result.document.transfer_error}",
                    )
                else:
                    messages.success(
                        request,
                        "Beleg gespeichert. Die Übertragung zu Paperless läuft.",
                    )
                return redirect(
                    reverse(
                        "bank_transaction_booking",
                        kwargs={"pk": bank_transaction.pk},
                    )
                    + "?"
                    + urlencode(
                        {
                            "status": navigation_context["selected_status"],
                            "month": navigation_context["selected_month"],
                        }
                    )
                )
            existing_entries = self._existing_entries(bank_transaction)
            initial, snapshot_error = self._initial_rows(
                bank_transaction, existing_entries
            )
            formset = self._formset(
                None, bank_transaction, final=False, initial=initial
            )
            return self.render_to_response(
                self._context_for_transaction(
                    bank_transaction,
                    formset,
                    BankTransactionNoteForm(instance=bank_transaction),
                    navigation_context,
                    snapshot_error,
                    document_form,
                )
            )
        rejection = self._reject_if_booked(
            request, bank_transaction, navigation_context
        )
        if rejection is not None:
            return rejection

        finalize = action == "finalize"
        existing_entries = self._existing_entries(bank_transaction)
        initial, snapshot_error = self._initial_rows(
            bank_transaction, existing_entries
        )
        data = self._legacy_post_data(request, bank_transaction, existing_entries)
        formset = self._formset(
            data, bank_transaction, final=finalize, initial=initial
        )
        notes_form = BankTransactionNoteForm(
            request.POST, instance=bank_transaction
        )
        if action not in {"save_draft", "finalize"}:
            notes_form.add_error(None, "Die gewünschte Aktion ist ungültig.")

        if formset.is_valid() and notes_form.is_valid():
            rounding_difference = formset.rounding_difference
            with db_transaction.atomic():
                locked_transaction = BankTransaction.objects.select_for_update().get(
                    pk=bank_transaction.pk
                )
                formset.instance = locked_transaction
                if finalize:
                    formset.apply_rounding_difference()
                formset.save()
                locked_transaction.notes = notes_form.cleaned_data["notes"]
                update_fields = ["notes"]
                if finalize and locked_transaction.status != BankTransaction.Status.BOOKED:
                    locked_transaction.status = BankTransaction.Status.REVIEWED
                    update_fields.append("status")
                locked_transaction.save(update_fields=update_fields)

            if finalize:
                messages.success(request, "Buchung geprüft und abgeschlossen.")
                if abs(rounding_difference) == Decimal("0.01"):
                    messages.warning(
                        request,
                        f"Rundungsdifferenz von "
                        f"{format_austrian_decimal(rounding_difference)} EUR "
                        "wurde in der größten Buchungszeile ausgeglichen.",
                    )
                if bank_transaction.status in BOOKING_READY_STATUSES:
                    return redirect(
                        _overview_url(
                            BankTransaction.Status.REVIEWED,
                            navigation_context["selected_month"],
                        )
                    )
                return redirect(
                    _overview_url(
                        OPEN_FILTER,
                        bank_transaction.booking_date.strftime("%Y-%m"),
                    )
                )
            messages.success(request, "Buchungsentwurf gespeichert.")
            return redirect(
                _overview_url(
                    navigation_context["selected_status"],
                    navigation_context["selected_month"],
                )
            )

        return self.render_to_response(
            self._context_for_transaction(
                bank_transaction,
                formset,
                notes_form,
                navigation_context,
                snapshot_error,
            )
        )


class MatchingRuleListView(TemplateView):
    template_name = "bookkeeping/matching_rules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        context["matching_rules"] = [
            _display_matching_rule(rule)
            for rule in MatchingRule.objects.annotate(
                _linked_transaction_count=Count("transactions", distinct=True)
            ).order_by("-created_at")
        ]
        context.setdefault("matching_rule_form", MatchingRuleForm())
        context.setdefault(
            "matching_rule_formset",
            MatchingRuleBookingTemplateFormSet(
                instance=MatchingRule(),
                prefix="templates",
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        matching_rule_form = MatchingRuleForm(request.POST)
        if matching_rule_form.is_valid():
            matching_rule = matching_rule_form.save(commit=False)
        else:
            matching_rule = MatchingRule()
        matching_template_formset = _matching_template_formset(
            request,
            matching_rule,
        )
        if matching_rule_form.is_valid() and _matching_template_formset_is_valid(
            matching_template_formset
        ):
            with db_transaction.atomic():
                matching_rule.save()
                matching_template_formset.instance = matching_rule
                matching_template_formset.save()
            messages.success(request, "Matching-Regel angelegt.")
            return redirect("matching_rule_list")
        return self.render_to_response(
            self.get_context_data(
                matching_rule_form=matching_rule_form,
                matching_rule_formset=matching_template_formset,
                matching_rule_error="Bitte prüfen Sie die Angaben zur Matching-Regel.",
            )
        )


class MatchingRuleEditView(UpdateView):
    model = MatchingRule
    form_class = MatchingRuleForm
    template_name = "bookkeeping/matching_rule_edit.html"
    success_url = reverse_lazy("matching_rule_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        context.setdefault(
            "matching_rule_formset",
            MatchingRuleBookingTemplateFormSet(
                instance=self.object,
                prefix="templates",
            ),
        )
        return context

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _rule_is_used(self.object):
            messages.error(
                request,
                "Diese Regel wurde bereits verwendet und ist daher "
                "schreibgeschützt.",
            )
            return redirect(
                "matching_rule_detail",
                pk=self.object.pk,
            )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        matching_template_formset = _matching_template_formset(
            request,
            self.object,
        )
        if form.is_valid() and _matching_template_formset_is_valid(
            matching_template_formset
        ):
            return self._save_valid_forms(form, matching_template_formset)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                matching_rule_formset=matching_template_formset,
            )
        )

    def _save_valid_forms(self, form, matching_template_formset):
        with db_transaction.atomic():
            self.object = form.save()
            matching_template_formset.instance = self.object
            matching_template_formset.save()
        messages.success(self.request, "Matching-Regel gespeichert.")
        return redirect(self.get_success_url())


class MatchingRuleDetailView(TemplateView):
    template_name = "bookkeeping/matching_rule_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(MatchingRule, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "upload_supporting_document":
            document_form = SupportingDocumentUploadForm(
                request.POST,
                request.FILES,
            )
            if document_form.is_valid():
                result = import_supporting_document(
                    document_form.cleaned_data["pdf"],
                    matching_rule=self.object,
                )
                if result.document.transfer_status == SupportingDocument.TransferStatus.FAILED:
                    messages.error(
                        request,
                        f"Nachweis gespeichert, aber Paperless meldet einen Fehler: "
                        f"{result.document.transfer_error}",
                    )
                else:
                    messages.success(
                        request,
                        "Nachweis gespeichert. Die Übertragung zu Paperless läuft.",
                    )
                return redirect("matching_rule_detail", pk=self.object.pk)
            return self.render_to_response(
                self.get_context_data(supporting_document_form=document_form)
            )
        if action == "retry_supporting_document":
            document = get_object_or_404(
                SupportingDocument,
                matching_rule=self.object,
                reference_uuid=request.POST.get("reference_uuid"),
            )
            try:
                retry_supporting_document(document)
            except SupportingDocumentError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Erneute Übertragung zu Paperless gestartet.")
            return redirect("matching_rule_detail", pk=self.object.pk)
        if action == "deactivate" and self.object.active:
            self.object.active = False
            self.object.save(update_fields=("active", "updated_at"))
            messages.success(request, "Matching-Regel deaktiviert.")
        return redirect("matching_rule_detail", pk=self.object.pk)

    def get_context_data(self, **kwargs):
        refresh_pending_supporting_documents()
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        context["object"] = self.object
        context["matching_rule"] = self.object
        context["booking_templates"] = self.object.booking_templates.order_by(
            "position", "id"
        )
        context["previous_version"] = self.object.previous_version
        context["next_version"] = MatchingRule.objects.filter(
            previous_version=self.object
        ).first()
        context["linked_transaction_count"] = self.object.linked_transaction_count
        context["supporting_documents"] = [
            display_supporting_document(document)
            for document in SupportingDocument.objects.filter(
                matching_rule=self.object
            ).select_related("matching_rule").order_by("-created_at", "-id")
        ]
        context.setdefault("supporting_document_form", SupportingDocumentUploadForm())
        return context


class SupportingDocumentActionView(TemplateView):
    template_name = "bookkeeping/supporting_document_confirm.html"
    action = "unlink"

    def dispatch(self, request, *args, **kwargs):
        self.owner_kind = "matching_rule" if kwargs.get("rule_pk") else "bank_transaction"
        owner_filter = (
            {"matching_rule_id": kwargs["rule_pk"]}
            if self.owner_kind == "matching_rule"
            else {"bank_transaction_id": kwargs["transaction_pk"]}
        )
        self.document = get_object_or_404(
            SupportingDocument.objects.select_related(
                "matching_rule",
                "bank_transaction",
            ),
            reference_uuid=kwargs["reference_uuid"],
            **owner_filter,
        )
        return super().dispatch(request, *args, **kwargs)

    def _owner_redirect(self):
        return redirect(supporting_document_owner_url(self.document))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document"] = display_supporting_document(self.document)
        context["document_object"] = self.document
        context["action"] = self.action
        context["owner_url"] = supporting_document_owner_url(self.document)
        context["owner"] = (
            self.document.matching_rule
            if self.owner_kind == "matching_rule"
            else self.document.bank_transaction
        )
        return context

    def post(self, request, *args, **kwargs):
        if self.action == "unlink":
            remove_supporting_document(self.document)
            messages.success(request, "Die Verknüpfung wurde aus Quintus entfernt.")
            return self._owner_redirect()
        try:
            delete_supporting_document_from_paperless(self.document)
        except BookkeepingPaperlessError as exc:
            messages.error(request, f"Paperless-Löschung fehlgeschlagen: {exc}")
            return redirect(request.path)
        messages.success(request, "Das Dokument wurde aus Quintus und Paperless gelöscht.")
        return self._owner_redirect()


class SupportingDocumentUnlinkView(SupportingDocumentActionView):
    action = "unlink"


class SupportingDocumentDeleteView(SupportingDocumentActionView):
    action = "delete"


class MatchingRuleVersionView(TemplateView):
    template_name = "bookkeeping/matching_rule_version.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(MatchingRule, pk=kwargs["pk"])
        if not _rule_is_used(self.object):
            messages.error(
                request,
                "Eine neue Version kann nur für eine bereits verwendete Regel "
                "angelegt werden.",
            )
            return redirect("matching_rule_edit", pk=self.object.pk)
        if self.object.has_successor:
            messages.info(
                request,
                "Für diese Regel besteht bereits eine Nachfolgeversion.",
            )
            return redirect("matching_rule_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def _build_new_rule(self, source=None):
        source = source or self.object
        return MatchingRule(
            name=source.name,
            direction=source.direction,
            match_type=source.match_type,
            iban=source.iban,
            expected_amount=source.expected_amount,
            text_pattern=source.text_pattern,
            notes=source.notes,
            active=True,
            previous_version=source,
            version_number=source.version_number + 1,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        context["source_rule"] = self.object
        context.setdefault(
            "matching_rule_form",
            MatchingRuleVersionForm(instance=self._build_new_rule()),
        )
        context.setdefault(
            "matching_rule_formset",
            _matching_template_formset(
                self.request,
                self._build_new_rule(),
                initial=_matching_template_initials(self.object),
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        new_rule = self._build_new_rule()
        form = MatchingRuleVersionForm(request.POST, instance=new_rule)
        matching_template_formset = _matching_template_formset(
            request,
            new_rule,
            initial=_matching_template_initials(self.object),
        )
        if not form.is_valid() or not _matching_template_formset_is_valid(
            matching_template_formset
        ):
            return self.render_to_response(
                self.get_context_data(
                    matching_rule_form=form,
                    matching_rule_formset=matching_template_formset,
                )
            )

        try:
            with db_transaction.atomic():
                source = MatchingRule.objects.select_for_update().get(
                    pk=self.object.pk
                )
                if not _rule_is_used(source):
                    messages.error(
                        request,
                        "Eine neue Version kann nur für eine bereits verwendete "
                        "Regel angelegt werden.",
                    )
                    return redirect("matching_rule_edit", pk=source.pk)
                if source.has_successor:
                    messages.info(
                        request,
                        "Für diese Regel besteht bereits eine Nachfolgeversion.",
                    )
                    return redirect("matching_rule_detail", pk=source.pk)

                new_rule = form.save(commit=False)
                new_rule.previous_version = source
                new_rule.version_number = source.version_number + 1
                new_rule.active = True
                source.active = False
                source.save(update_fields=("active", "updated_at"))
                new_rule.save()
                matching_template_formset.instance = new_rule
                matching_template_formset.save()
        except IntegrityError:
            messages.error(
                request,
                "Für diese Regel besteht bereits eine Nachfolgeversion.",
            )
            return redirect("matching_rule_detail", pk=self.object.pk)

        messages.success(request, "Neue Version der Matching-Regel angelegt.")
        return redirect("matching_rule_list")


class MatchingRuleDeleteView(DeleteView):
    model = MatchingRule
    template_name = "bookkeeping/matching_rule_delete.html"
    success_url = reverse_lazy("matching_rule_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_bookkeeping_navigation_context(self.request))
        return context

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _rule_is_used(self.object):
            messages.error(
                request,
                "Diese Regel wurde bereits verwendet und kann nicht gelöscht werden.",
            )
            return redirect("matching_rule_list")
        if self.object.has_successor:
            messages.error(
                request,
                "Diese Regel ist eine Vorgängerversion und kann nicht gelöscht "
                "werden.",
            )
            return redirect("matching_rule_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        rule_name = self.object.name
        with db_transaction.atomic():
            response = super().form_valid(form)
        messages.success(self.request, f'Matching-Regel „{rule_name}“ gelöscht.')
        return response
