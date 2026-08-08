import hashlib
import json
import logging
import re
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Max, Prefetch, Q, Sum
from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import DeleteView, TemplateView, UpdateView

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
    BookingEntryForm,
    BookingEntryFormSet,
    MatchingRuleBookingTemplateFormSet,
    MatchingRuleForm,
    MatchingRuleVersionForm,
)
from .models import BankTransaction, BookingEntry, MatchingRule


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
logger = logging.getLogger(__name__)


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
    return sorted(
        {
            (
                payment_date.year,
                f"Q{((payment_date.month - 1) // 3) + 1}",
            )
            for payment_date in BookingEntry.objects.filter(
                bank_transaction__status__in=BOOKING_READY_STATUSES,
            ).values_list("payment_date", flat=True)
        },
        reverse=True,
    )


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


def _dashboard_period_selection(params, available_quarters):
    available_periods = {
        f"{year}-{quarter}" for year, quarter in available_quarters
    }
    requested_period = params.get("dashboard_period")
    parsed_period = _parse_export_period(requested_period)
    if parsed_period in available_periods:
        return parsed_period
    if available_quarters:
        year, quarter = available_quarters[0]
        return f"{year}-{quarter}"
    return ""


def _bank_import_dashboard_context(params):
    available_quarters = _available_transaction_quarters()
    dashboard_period = _dashboard_period_selection(
        params,
        available_quarters,
    )
    available_periods = [
        {
            "value": f"{year}-{quarter}",
            "label": f"{quarter} {year}",
        }
        for year, quarter in available_quarters
    ]
    context = {
        "available_dashboard_periods": available_periods,
        "dashboard_period": dashboard_period,
        "dashboard_has_data": False,
        "dashboard_total": 0,
        "dashboard_open": 0,
        "dashboard_ready": 0,
        "dashboard_processed_percentage": "0.00",
        "dashboard_processed_percent": "0,00 %",
        "dashboard_processed_width": "0",
        "dashboard_incoming": "0,00 EUR",
        "dashboard_outgoing": "0,00 EUR",
        "dashboard_balance": "0,00 EUR",
        "dashboard_auto_matched": 0,
        "dashboard_without_matching": 0,
        "dashboard_latest_booking_date": "–",
        "dashboard_active_matching_rules": 0,
    }
    period_range = _export_period_bounds(dashboard_period)
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
        ready_count=Count(
            "id",
            filter=Q(status__in=BOOKING_READY_STATUSES),
        ),
        incoming=Sum("amount", filter=Q(amount__gt=0)),
        outgoing=Sum("amount", filter=Q(amount__lt=0)),
        balance=Sum("amount"),
        auto_matched=Count("id", filter=Q(matched_rule__isnull=False)),
        without_matching=Count("id", filter=Q(matched_rule__isnull=True)),
        latest_booking_date=Max("booking_date"),
    )
    total = aggregate["total"] or 0
    ready_count = aggregate["ready_count"] or 0
    incoming = aggregate["incoming"] or Decimal("0")
    outgoing = aggregate["outgoing"] or Decimal("0")
    balance = aggregate["balance"] or Decimal("0")
    processed_percentage = (
        (Decimal(ready_count) * Decimal("100") / Decimal(total)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        if total
        else Decimal("0.00")
    )
    context.update(
        {
            "dashboard_has_data": total > 0,
            "dashboard_total": total,
            "dashboard_open": aggregate["open_count"] or 0,
            "dashboard_ready": ready_count,
            "dashboard_processed_percentage": str(processed_percentage),
            "dashboard_processed_percent": (
                f"{format_austrian_decimal(processed_percentage)} %"
            ),
            "dashboard_processed_width": str(processed_percentage),
            "dashboard_incoming": format_austrian_money(incoming, "EUR"),
            "dashboard_outgoing": format_austrian_money(abs(outgoing), "EUR"),
            "dashboard_balance": format_austrian_money(balance, "EUR"),
            "dashboard_auto_matched": aggregate["auto_matched"] or 0,
            "dashboard_without_matching": aggregate["without_matching"] or 0,
            "dashboard_latest_booking_date": (
                aggregate["latest_booking_date"].strftime("%d.%m.%Y")
                if aggregate["latest_booking_date"]
                else "–"
            ),
            "dashboard_active_matching_rules": MatchingRule.objects.filter(
                active=True
            ).count(),
        }
    )
    return context


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


def _overview_url(status, month=None):
    query = {"status": status}
    if month is not None:
        query["month"] = month
    return f"{reverse('bookkeeping_overview')}?{urlencode(query)}"


def _note_preview(note, max_length=90):
    normalized_note = " ".join(str(note or "").split())
    if len(normalized_note) <= max_length:
        return normalized_note, False
    return f"{normalized_note[: max_length - 1]}…", True


def _bookkeeping_navigation_context(request, filter_params=None):
    params = filter_params if filter_params is not None else request.GET
    requested_status = params.get("status")
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
    if selected_status in BOOKING_READY_STATUSES and "month" not in params:
        selected_month = ""

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
    selected_status_details = STATUS_DETAILS[selected_status]
    month_suffix = f" für {_month_label(selected_month)}" if selected_month else ""
    return {
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
        "empty_state_message": (
            f"Keine {selected_status_details['empty_label']} Transaktionen"
            f"{month_suffix} vorhanden."
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


class BookkeepingOverviewView(TemplateView):
    template_name = "bookkeeping/overview.html"

    def get_context_data(self, **kwargs):
        filter_params = kwargs.pop("filter_params", None)
        context = super().get_context_data(**kwargs)
        navigation_context = _bookkeeping_navigation_context(
            self.request,
            filter_params=filter_params,
        )
        context.update(navigation_context)
        context["show_bank_import"] = (
            navigation_context["selected_status"] == BANK_IMPORT_FILTER
        )
        if context["show_bank_import"]:
            context.update(
                _bank_import_dashboard_context(
                    filter_params if filter_params is not None else self.request.GET
                )
            )
            context["transactions"] = []
            context["show_preview"] = False
            context.setdefault("error_message", "")
            return context

        export_period_bounds = None
        if navigation_context["selected_status"] in BOOKING_READY_STATUSES:
            export_period_bounds = _export_period_bounds(
                navigation_context["export_period"]
            )
        booking_entries_queryset = BookingEntry.objects.order_by(
            "created_at", "id"
        )
        if export_period_bounds is not None:
            booking_entries_queryset = booking_entries_queryset.filter(
                payment_date__gte=export_period_bounds[0],
                payment_date__lte=export_period_bounds[1],
            )
        selected_transactions = BankTransaction.objects.select_related(
            "matched_rule"
        ).prefetch_related(
            Prefetch(
                "booking_entries",
                queryset=booking_entries_queryset,
                to_attr="booking_entries_for_display",
            )
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
            if export_period_bounds is None:
                selected_transactions = selected_transactions.none()
            else:
                selected_transactions = selected_transactions.filter(
                    booking_entries__payment_date__gte=export_period_bounds[0],
                    booking_entries__payment_date__lte=export_period_bounds[1],
                ).distinct()
        else:
            selected_transactions = selected_transactions.filter(
                status=navigation_context["selected_status"]
            )
        if navigation_context["selected_month"]:
            selected_transactions = selected_transactions.filter(
                **_month_filter(navigation_context["selected_month"])
            )
        saved_transactions = list(
            selected_transactions.order_by("-booking_date", "-imported_at")
        )
        context["transactions"] = [
            self._display_saved_transaction(transaction)
            for transaction in saved_transactions
        ]
        context["show_preview"] = bool(saved_transactions)
        context.setdefault("error_message", "")
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "export_csv":
            return self._export_csv(request)

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
        rejection = self._reject_if_booked(
            request, bank_transaction, navigation_context
        )
        if rejection is not None:
            return rejection

        action = request.POST.get("action", "save_draft")
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
        if request.POST.get("action") == "deactivate" and self.object.active:
            self.object.active = False
            self.object.save(update_fields=("active", "updated_at"))
            messages.success(request, "Matching-Regel deaktiviert.")
        return redirect("matching_rule_detail", pk=self.object.pk)

    def get_context_data(self, **kwargs):
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
        return context


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
