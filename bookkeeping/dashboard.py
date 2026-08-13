"""Selectors and presentation data for the bookkeeping decision dashboard."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.urls import reverse

from .category_display import category_description
from .formatting import format_austrian_decimal, format_austrian_money
from .models import (
    BankStatement,
    BankTransaction,
    ManualInvoice,
    SupportingDocument,
)


DASHBOARD_PERIOD_TYPES = ("month", "quarter", "year")
READY_BANK_STATUSES = frozenset(
    {BankTransaction.Status.REVIEWED, BankTransaction.Status.BOOKED}
)
WORKFLOW_STATUS_GROUPS = {
    "completed": frozenset({BankTransaction.Status.REVIEWED, BankTransaction.Status.BOOKED}),
    "in_progress": frozenset({BankTransaction.Status.MATCHED}),
    "open": frozenset({BankTransaction.Status.IMPORTED}),
}
MANUAL_STATUS_GROUPS = {
    "completed": frozenset({ManualInvoice.Status.READY}),
    "in_progress": frozenset(),
    "open": frozenset({ManualInvoice.Status.DRAFT}),
}
MONEY_ZERO = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")


def parse_dashboard_period(period_type: str, value: str | None) -> str | None:
    value = str(value or "")
    if period_type == "month":
        try:
            year, month = (int(part) for part in value.split("-", 1))
            if len(value) == 7 and date(year, month, 1):
                return value
        except (TypeError, ValueError):
            return None
    elif period_type == "quarter":
        try:
            year, quarter = value.split("-", 1)
            if len(year) == 4 and quarter in {"Q1", "Q2", "Q3", "Q4"}:
                int(year)
                return value
        except (TypeError, ValueError):
            return None
    elif period_type == "year":
        try:
            if len(value) == 4 and int(value) > 0:
                return value
        except (TypeError, ValueError):
            return None
    return None


def dashboard_period_bounds(period_type: str, period: str) -> tuple[date, date] | None:
    normalized = parse_dashboard_period(period_type, period)
    if normalized is None:
        return None
    if period_type == "month":
        year, month = (int(part) for part in normalized.split("-"))
        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return start, end
    if period_type == "quarter":
        year, quarter = normalized.split("-")
        year_number = int(year)
        month = (int(quarter[1]) - 1) * 3 + 1
        start = date(year_number, month, 1)
        if month == 10:
            end = date(year_number + 1, 1, 1)
        else:
            end = date(year_number, month + 3, 1)
        return start, end
    year = int(normalized)
    return date(year, 1, 1), date(year + 1, 1, 1)


def dashboard_period_label(period_type: str, period: str) -> str:
    normalized = parse_dashboard_period(period_type, period)
    if normalized is None:
        return ""
    if period_type == "month":
        year, month = (int(part) for part in normalized.split("-"))
        months = (
            "Januar", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember",
        )
        return f"{months[month - 1]} {year}"
    if period_type == "quarter":
        year, quarter = normalized.split("-")
        return f"{quarter} {year}"
    return normalized


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _date_for_manual_invoice(invoice: ManualInvoice) -> date:
    return invoice.payment_date or invoice.invoice_date or invoice.created_at.date()


def _in_period(value: date | None, bounds: tuple[date, date]) -> bool:
    return value is not None and bounds[0] <= value < bounds[1]


def _period_key_from_date(value: date, period_type: str) -> str:
    if period_type == "month":
        return value.strftime("%Y-%m")
    if period_type == "quarter":
        return f"{value.year}-Q{((value.month - 1) // 3) + 1}"
    return str(value.year)


def _last_quarter_periods(available_quarters, count=8):
    """Return the latest contiguous calendar quarters in display order."""
    parsed = [
        parse_dashboard_period("quarter", value)
        for value in available_quarters
    ]
    parsed = [value for value in parsed if value is not None]
    if not parsed:
        return []
    latest_year, latest_quarter = parsed[0].split("-Q")
    latest_index = int(latest_year) * 4 + int(latest_quarter)
    return [
        f"{(latest_index - offset - 1) // 4}-Q{((latest_index - offset - 1) % 4) + 1}"
        for offset in range(count - 1, -1, -1)
    ]


def available_dashboard_periods() -> dict[str, list[str]]:
    dates = list(
        BankTransaction.objects.values_list("booking_date", flat=True)
    )
    dates += list(
        ManualInvoice.objects.values_list("payment_date", flat=True)
    )
    dates += list(
        ManualInvoice.objects.values_list("invoice_date", flat=True)
    )
    dates += list(
        BankStatement.objects.values_list("statement_date", flat=True)
    )
    dates = [value for value in dates if value is not None]
    return {
        "month": sorted({_period_key_from_date(value, "month") for value in dates}, reverse=True),
        "quarter": sorted({_period_key_from_date(value, "quarter") for value in dates}, reverse=True),
        "year": sorted({_period_key_from_date(value, "year") for value in dates}, reverse=True),
    }


def _source_amounts(bank_transactions, manual_invoices):
    """Use each source amount once; booking rows are only used for categories."""
    amounts = [
        transaction.amount
        for transaction in bank_transactions
        if transaction.amount is not None
    ]
    amounts.extend(
        invoice.gross_amount
        for invoice in manual_invoices
        if invoice.gross_amount is not None
    )
    income = sum((value for value in amounts if value > 0), MONEY_ZERO)
    expenses = sum((abs(value) for value in amounts if value < 0), MONEY_ZERO)
    return {
        "income_value": _money(income),
        "income": format_austrian_money(income, "EUR"),
        "expenses_value": _money(expenses),
        "expenses": format_austrian_money(expenses, "EUR"),
        "balance_value": _money(sum(amounts, MONEY_ZERO)),
        "balance": format_austrian_money(sum(amounts, MONEY_ZERO), "EUR"),
    }


def _category_totals(bank_transactions, manual_invoices):
    totals = {"income": defaultdict(Decimal), "expenses": defaultdict(Decimal)}
    for transaction in bank_transactions:
        for entry in transaction.booking_entries.all():
            if not entry.category or entry.gross_amount is None:
                continue
            target = "income" if entry.gross_amount > 0 else "expenses"
            totals[target][category_description(entry.category)] += abs(entry.gross_amount)
    for invoice in manual_invoices:
        for entry in invoice.booking_entries.all():
            if not entry.category or entry.gross_amount is None:
                continue
            target = "income" if entry.gross_amount > 0 else "expenses"
            totals[target][category_description(entry.category)] += abs(entry.gross_amount)
    result = {}
    for target, values in totals.items():
        ordered = sorted(values.items(), key=lambda item: (-item[1], item[0].casefold()))
        if len(ordered) > 8:
            ordered = ordered[:7] + [
                ("Sonstige", sum((value for _, value in ordered[7:]), MONEY_ZERO))
            ]
        maximum = max((value for _, value in ordered), default=MONEY_ZERO)
        result[target] = [
            {
                "label": label,
                "value": str(_money(value)),
                "amount": format_austrian_money(value, "EUR"),
                "width": str(int((value / maximum * 100).quantize(Decimal("1"))) if maximum else 0),
            }
            for label, value in ordered
        ]
    return result


def _year_chart(bank_transactions, manual_invoices, selected_year):
    by_year = defaultdict(lambda: {"income": MONEY_ZERO, "expenses": MONEY_ZERO})
    for transaction in bank_transactions:
        year = transaction.booking_date.year
        if transaction.amount > 0:
            by_year[year]["income"] += transaction.amount
        elif transaction.amount < 0:
            by_year[year]["expenses"] += abs(transaction.amount)
    for invoice in manual_invoices:
        year = _date_for_manual_invoice(invoice).year
        if invoice.gross_amount and invoice.gross_amount > 0:
            by_year[year]["income"] += invoice.gross_amount
        elif invoice.gross_amount and invoice.gross_amount < 0:
            by_year[year]["expenses"] += abs(invoice.gross_amount)
    maximum = max(
        (max(values["income"], values["expenses"]) for values in by_year.values()),
        default=MONEY_ZERO,
    )
    chart = []
    for year in sorted(by_year):
        values = by_year[year]
        balance = values["income"] - values["expenses"]
        chart.append(
            {
                "year": year,
                "income": str(_money(values["income"])),
                "expenses": str(_money(values["expenses"])),
                "income_amount": format_austrian_money(values["income"], "EUR"),
                "expenses_amount": format_austrian_money(values["expenses"], "EUR"),
                "balance_amount": format_austrian_money(balance, "EUR"),
                "income_height": str(int((values["income"] / maximum * 100).quantize(Decimal("1"))) if maximum else 0),
                "expenses_height": str(int((values["expenses"] / maximum * 100).quantize(Decimal("1"))) if maximum else 0),
                "selected": str(year) == str(selected_year),
            }
        )
    return chart


def _quarter_chart(bank_transactions, manual_invoices, quarter_periods):
    """Build an income/expense comparison for the latest eight quarters."""
    quarter_periods = tuple(quarter_periods or ())
    if not quarter_periods:
        return []
    by_quarter = {
        period: {"income": MONEY_ZERO, "expenses": MONEY_ZERO}
        for period in quarter_periods
    }
    for transaction in bank_transactions:
        quarter = _period_key_from_date(transaction.booking_date, "quarter")
        if quarter not in by_quarter:
            continue
        if transaction.amount > 0:
            by_quarter[quarter]["income"] += transaction.amount
        elif transaction.amount < 0:
            by_quarter[quarter]["expenses"] += abs(transaction.amount)
    for invoice in manual_invoices:
        invoice_date = _date_for_manual_invoice(invoice)
        quarter = _period_key_from_date(invoice_date, "quarter")
        if quarter not in by_quarter or invoice.gross_amount is None:
            continue
        if invoice.gross_amount > 0:
            by_quarter[quarter]["income"] += invoice.gross_amount
        elif invoice.gross_amount < 0:
            by_quarter[quarter]["expenses"] += abs(invoice.gross_amount)

    maximum = max(
        (max(values["income"], values["expenses"]) for values in by_quarter.values()),
        default=MONEY_ZERO,
    )
    if maximum == MONEY_ZERO:
        return []

    maximum_amount = format_austrian_money(maximum, "EUR")
    chart = []
    for quarter in quarter_periods:
        year, quarter_number = quarter.split("-Q")
        values = by_quarter[quarter]
        balance = values["income"] - values["expenses"]
        chart.append(
            {
                "quarter": quarter,
                "quarter_label": f"Q{quarter_number} {year}",
                "period_label": f"Q{quarter_number} {year}",
                "income": str(_money(values["income"])),
                "expenses": str(_money(values["expenses"])),
                "income_amount": format_austrian_money(values["income"], "EUR"),
                "expenses_amount": format_austrian_money(values["expenses"], "EUR"),
                "balance_amount": format_austrian_money(balance, "EUR"),
                "income_height": str(
                    int((values["income"] / maximum * 100).quantize(Decimal("1")))
                ),
                "expenses_height": str(
                    int((values["expenses"] / maximum * 100).quantize(Decimal("1")))
                ),
                "scale_max_amount": maximum_amount,
            }
        )
    return chart


def _statement_controls(statements):
    """Calculate month controls with one transaction query for the dashboard."""
    if not statements:
        return {}
    bounds = [
        dashboard_period_bounds("month", statement.booking_month)
        for statement in statements
    ]
    bounds = [item for item in bounds if item]
    if not bounds:
        return {}
    start = min(item[0] for item in bounds)
    end = max(item[1] for item in bounds)
    totals = defaultdict(lambda: {"count": 0, "credits": MONEY_ZERO, "debits": MONEY_ZERO})
    for value_date, amount in BankTransaction.objects.filter(
        value_date__gte=start,
        value_date__lt=end,
    ).values_list("value_date", "amount"):
        month = value_date.strftime("%Y-%m")
        totals[month]["count"] += 1
        if amount > 0:
            totals[month]["credits"] += amount
        elif amount < 0:
            totals[month]["debits"] += abs(amount)
    controls = {}
    for statement in statements:
        values = totals[statement.booking_month]
        calculated_closing = statement.opening_balance + values["credits"] - values["debits"]
        status = "warning"
        if values["count"] and (
            values["credits"] != statement.total_credits
            or values["debits"] != statement.total_debits
            or calculated_closing != statement.closing_balance
        ):
            status = "danger"
        elif values["count"]:
            status = "success"
        controls[statement.pk] = {"status": status}
    return controls


def _bank_reconciliation(statements, controls=None):
    if not statements:
        return {"status": "neutral", "label": "Noch keine Abstimmung möglich", "date": ""}
    controls = controls or _statement_controls(statements)
    statement_controls = [controls.get(statement.pk, {"status": "warning"}) for statement in statements]
    latest_date = max(statement.statement_date for statement in statements)
    if any(control["status"] == "danger" for control in statement_controls):
        return {
            "status": "danger",
            "label": f"Abweichung im {dashboard_period_label('month', latest_date.strftime('%Y-%m'))}",
            "date": latest_date.strftime("%d.%m.%Y"),
        }
    if all(control["status"] == "success" for control in statement_controls):
        return {
            "status": "success",
            "label": f"Stimmt bis {latest_date.strftime('%d.%m.%Y')}",
            "date": latest_date.strftime("%d.%m.%Y"),
        }
    return {"status": "warning", "label": "Noch keine Abstimmung möglich", "date": ""}


def _step(problem, operation, amount, action, url, priority, value_date):
    return {
        "problem": problem,
        "operation": operation,
        "amount": format_austrian_money(amount, "EUR"),
        "action": action,
        "url": url,
        "priority": priority,
        "date": value_date,
    }


def _next_steps(bank_transactions, manual_invoices, statements, period_label, statement_controls=None):
    steps = []
    bank_url = reverse("bookkeeping_overview") + "?status=bank_import#bank-import"
    for statement in statements:
        statement_url = reverse("bookkeeping_overview") + "?status=bank_import#bank-import"
        if statement.paperless_status in {
            BankStatement.PaperlessStatus.FAILED,
            BankStatement.PaperlessStatus.METADATA_INCOMPLETE,
        }:
            problem = (
                "Paperless-Metadaten unvollständig"
                if statement.paperless_status == BankStatement.PaperlessStatus.METADATA_INCOMPLETE
                else "Paperless-Upload fehlgeschlagen"
            )
            action = "Metadaten synchronisieren" if statement.paperless_status == BankStatement.PaperlessStatus.METADATA_INCOMPLETE else "Paperless erneut prüfen"
            steps.append(_step(problem, f"Kontoauszug {statement.booking_month}", MONEY_ZERO, action, statement_url, 10, statement.statement_date))
        control = (statement_controls or {}).get(statement.pk, {"status": "warning"})
        if control["status"] == "danger":
            steps.append(_step("Kontoauszug stimmt rechnerisch nicht überein", f"Kontoauszug {statement.booking_month}", MONEY_ZERO, "Kontoauszug öffnen", statement_url, 10, statement.statement_date))
    statement_months = {statement.booking_month for statement in statements}
    if bank_transactions and not statement_months:
        first_date = min(transaction.booking_date for transaction in bank_transactions)
        steps.append(_step("Kontoauszug fehlt", period_label, MONEY_ZERO, "Kontoauszug importieren", bank_url, 20, first_date))
    for transaction in bank_transactions:
        url = reverse("bank_transaction_booking", kwargs={"pk": transaction.pk}) + "?status=open"
        if transaction.status == BankTransaction.Status.IMPORTED and not transaction.matched_rule_id:
            steps.append(_step("Banktransaktion ohne Zuordnung", transaction.partner_name or "Banktransaktion", transaction.amount, "Zuordnen", url, 30, transaction.booking_date))
        elif transaction.status == BankTransaction.Status.MATCHED:
            steps.append(_step("Buchungsdaten unvollständig", transaction.partner_name or "Banktransaktion", transaction.amount, "Buchung ergänzen", url, 40, transaction.booking_date))
        elif transaction.status in READY_BANK_STATUSES and not transaction.booking_entries.exists():
            steps.append(_step("Buchungsdaten unvollständig", transaction.partner_name or "Banktransaktion", transaction.amount, "Buchung ergänzen", url, 40, transaction.booking_date))
        elif transaction.status == BankTransaction.Status.IMPORTED and transaction.matched_rule_id:
            steps.append(_step("Vorgang wartet auf Prüfung", transaction.partner_name or "Banktransaktion", transaction.amount, "Öffnen", url, 50, transaction.booking_date))
        for entry in transaction.booking_entries.all():
            if not entry.receipt_group or not entry.receipt_number:
                steps.append(_step("Erforderlicher Beleg fehlt", transaction.partner_name or "Bankbeleg", entry.gross_amount or transaction.amount, "Beleg hochladen", url, 20, entry.payment_date))
        for document in transaction.supporting_documents.all():
            if document.transfer_status == SupportingDocument.TransferStatus.FAILED:
                steps.append(_step("Paperless-Upload fehlgeschlagen", transaction.partner_name or "Bankbeleg", transaction.amount, "Paperless erneut prüfen", url, 10, transaction.booking_date))
    for invoice in manual_invoices:
        value_date = _date_for_manual_invoice(invoice)
        url = reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
        if invoice.status == ManualInvoice.Status.DRAFT:
            steps.append(_step("Manueller Beleg ist noch nicht fertig", invoice.partner_name or "Manueller Beleg", invoice.gross_amount or MONEY_ZERO, "Öffnen", url, 40, value_date))
        elif invoice.status == ManualInvoice.Status.READY and not invoice.booking_entries.exists():
            steps.append(_step("Buchungsdaten unvollständig", invoice.partner_name or "Manueller Beleg", invoice.gross_amount or MONEY_ZERO, "Buchung ergänzen", url, 40, value_date))
        for entry in invoice.booking_entries.all():
            if not entry.receipt_group or not entry.receipt_number:
                steps.append(_step("Erforderlicher Beleg fehlt", invoice.partner_name or "Manueller Beleg", entry.gross_amount or invoice.gross_amount or MONEY_ZERO, "Beleg hochladen", url, 20, entry.payment_date))
        if invoice.paperless_status == ManualInvoice.PaperlessStatus.FAILED:
            steps.append(_step("Paperless-Upload fehlgeschlagen", invoice.partner_name or "Manueller Beleg", invoice.gross_amount or MONEY_ZERO, "Paperless erneut prüfen", url, 10, value_date))
    return sorted(steps, key=lambda item: (item["priority"], item["date"], item["operation"]))


def build_dashboard_data(period_type: str, period: str) -> dict[str, object]:
    bounds = dashboard_period_bounds(period_type, period)
    if bounds is None:
        return {"empty": True, "period_bounds": None}
    available = available_dashboard_periods()
    all_ready_bank = list(
        BankTransaction.objects.filter(status__in=READY_BANK_STATUSES)
        .prefetch_related("booking_entries", "supporting_documents")
    )
    all_ready_manual = list(
        ManualInvoice.objects.filter(status=ManualInvoice.Status.READY)
        .prefetch_related("booking_entries")
    )
    selected_bank = list(
        BankTransaction.objects.filter(
            booking_date__gte=bounds[0], booking_date__lt=bounds[1]
        ).prefetch_related("booking_entries", "supporting_documents")
    )
    selected_manual = list(
        ManualInvoice.objects.filter(
            Q(payment_date__gte=bounds[0], payment_date__lt=bounds[1])
            | Q(payment_date__isnull=True, invoice_date__gte=bounds[0], invoice_date__lt=bounds[1])
        ).prefetch_related("booking_entries")
    )
    selected_ready_bank = [item for item in all_ready_bank if _in_period(item.booking_date, bounds)]
    selected_ready_manual = [item for item in all_ready_manual if _in_period(_date_for_manual_invoice(item), bounds)]
    statements = list(
        BankStatement.objects.filter(
            statement_date__gte=bounds[0], statement_date__lt=bounds[1]
        ).order_by("statement_date", "id")
    )
    totals = _source_amounts(selected_ready_bank, selected_ready_manual)
    statement_controls = _statement_controls(statements)
    workload = {key: 0 for key in ("completed", "in_progress", "open")}
    for transaction in selected_bank:
        for key, statuses in WORKFLOW_STATUS_GROUPS.items():
            if transaction.status in statuses:
                workload[key] += 1
                break
    for invoice in selected_manual:
        for key, statuses in MANUAL_STATUS_GROUPS.items():
            if invoice.status in statuses:
                workload[key] += 1
                break
    total_workflow = sum(workload.values())
    processed = (Decimal(workload["completed"]) * 100 / Decimal(total_workflow)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_workflow else MONEY_ZERO
    steps = _next_steps(
        selected_bank,
        selected_manual,
        statements,
        dashboard_period_label(period_type, period),
        statement_controls,
    )
    quarter_chart = _quarter_chart(
        all_ready_bank,
        all_ready_manual,
        _last_quarter_periods(available.get("quarter", [])),
    )
    # There is no separate ``receipt_required`` field in the current model.
    # A persisted booking row with an empty receipt group/number is therefore
    # the only reliable representation of a missing required receipt.
    missing_receipt_sources = set()
    for transaction in selected_bank:
        for entry in transaction.booking_entries.all():
            if not entry.receipt_group or not entry.receipt_number:
                missing_receipt_sources.add(("bank", transaction.pk))
    for invoice in selected_manual:
        for entry in invoice.booking_entries.all():
            if not entry.receipt_group or not entry.receipt_number:
                missing_receipt_sources.add(("manual", invoice.pk))
    return {
        "empty": not (selected_bank or selected_manual or statements),
        "available": available,
        "period_bounds": bounds,
        "totals": totals,
        "year_chart": _year_chart(all_ready_bank, all_ready_manual, period if period_type == "year" else period[:4]),
        "quarter_chart": quarter_chart,
        "quarter_chart_max": (
            quarter_chart[0]["scale_max_amount"] if quarter_chart else "0,00 EUR"
        ),
        "categories": _category_totals(selected_ready_bank, selected_ready_manual),
        "workload": {
            **workload,
            "total": total_workflow,
            "processed_value": str(processed),
            "processed": f"{format_austrian_decimal(processed)} %",
        },
        "next_steps": steps,
        "missing_receipts": len(missing_receipt_sources),
        "reconciliation": _bank_reconciliation(statements, statement_controls),
    }
