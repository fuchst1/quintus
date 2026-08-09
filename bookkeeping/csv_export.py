import csv
import io
from calendar import monthrange
from datetime import date

from .category_display import category_description
from .formatting import format_austrian_decimal
from .models import BankTransaction, BookingEntry, ManualInvoice, ManualInvoiceEntry


CSV_HEADERS = (
    "Belegkreis",
    "Belegnummer",
    "Zahlungsdatum",
    "Buchungstext",
    "Rechnungsnummer",
    "Lieferant/Kunde",
    "Bruttobetrag",
    "USt-Symbol",
    "Kategorie",
)


class CsvExportError(Exception):
    """Expected errors while creating a bookkeeping CSV export."""


QUARTER_VALUES = ("Q1", "Q2", "Q3", "Q4")


def quarter_bounds(year, quarter):
    if str(quarter or "").upper() not in QUARTER_VALUES:
        return None
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    quarter = str(quarter).upper()
    start_month = (int(quarter[1]) - 1) * 3 + 1
    try:
        start = date(year, start_month, 1)
    except ValueError:
        return None
    end_month = start_month + 2
    end = date(year, end_month, monthrange(year, end_month)[1])
    return start, end


def export_reviewed_transactions_csv(*, start_date, end_date):
    """Create a repeatable full-quarter report without changing any status."""
    booking_entries = list(
        BookingEntry.objects.filter(
            bank_transaction__status__in=(
                BankTransaction.Status.REVIEWED,
                BankTransaction.Status.BOOKED,
            ),
            payment_date__gte=start_date,
            payment_date__lte=end_date,
        )
        .select_related("bank_transaction")
        .order_by("payment_date", "bank_transaction_id", "id")
    )
    manual_entries = list(
        ManualInvoiceEntry.objects.filter(
            manual_invoice__status=ManualInvoice.Status.READY,
            payment_date__gte=start_date,
            payment_date__lte=end_date,
        ).order_by("payment_date", "manual_invoice_id", "position", "id")
    )
    all_entries = [*booking_entries, *manual_entries]
    all_entries.sort(
        key=lambda entry: (
            entry.payment_date,
            str(getattr(entry, "bank_transaction_id", "")),
            str(getattr(entry, "manual_invoice_id", "")),
            getattr(entry, "position", 0),
            str(entry.pk),
        )
    )
    if not all_entries:
        raise CsvExportError(
            "Keine Buchungszeilen im ausgewählten Quartal vorhanden."
        )

    try:
        return _build_csv_content(all_entries)
    except Exception as exc:
        raise CsvExportError(
            "Die CSV-Datei konnte nicht erstellt werden."
        ) from exc


def _build_csv_content(booking_entries):
    output = io.StringIO(newline="")
    writer = csv.writer(
        output,
        delimiter=";",
        lineterminator="\r\n",
    )
    writer.writerow(CSV_HEADERS)
    for booking_entry in booking_entries:
        writer.writerow(
            (
                booking_entry.receipt_group,
                booking_entry.receipt_number,
                booking_entry.payment_date.strftime("%d.%m.%Y"),
                booking_entry.booking_text,
                booking_entry.invoice_number,
                booking_entry.partner_name,
                _format_amount(booking_entry.gross_amount),
                booking_entry.vat_symbol,
                category_description(booking_entry.category),
            )
        )
    return output.getvalue().encode("utf-8-sig")


def _format_amount(value):
    return format_austrian_decimal(value)
