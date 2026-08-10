"""Read-only ZIP packages for the external bookkeeping hand-off."""

from __future__ import annotations

import csv
import io
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import BinaryIO

from django.db.models import Prefetch, Q

from .csv_export import (
    _build_csv_content,
    get_export_booking_entries,
    quarter_bounds,
)
from .formatting import format_austrian_decimal
from .models import (
    BankStatement,
    BankTransaction,
    BookingEntry,
    ManualInvoice,
    ManualInvoiceEntry,
    SupportingDocument,
)
from .paperless import BookkeepingPaperlessError, PaperlessClient


OVERVIEW_HEADERS = (
    "Typ",
    "Datum",
    "Referenz",
    "Name",
    "Betrag",
    "Status",
    "Dokument",
    "Paperless-ID",
    "Hinweis",
)
PERIOD_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])$")
QUARTER_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<quarter>Q[1-4])$", re.IGNORECASE)
SAFE_EXTENSION_PATTERN = re.compile(r"^[a-z0-9]{1,8}$")
SAFE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tif", "tiff"}
ZIP_DIRECTORIES = {
    "statement": "Kontoauszuege",
    "invoice": "Rechnungen",
    "bank": "Bankbelege",
    "matching": "Matching-Nachweise",
}


class AccountantPackageError(Exception):
    """Expected, user-facing errors while creating a package."""


class AccountantPackageTechnicalError(AccountantPackageError):
    """A Paperless or archive error that must abort the complete download."""


@dataclass(frozen=True)
class PackagePeriod:
    period_type: str
    value: str
    start_date: date
    end_date: date
    months: tuple[str, ...]

    @property
    def filename(self) -> str:
        return f"Buchhaltung_{self.value}.zip"

    @property
    def csv_filename(self) -> str:
        return f"Buchungszeilen_{self.value}.csv"

    @property
    def overview_filename(self) -> str:
        return f"Uebersicht_{self.value}.csv"


@dataclass
class _DocumentReference:
    kind: str
    directory: str
    display_date: date | None
    reference: str
    name: str
    amount: Decimal | None
    paperless_id: int | None
    source_status: str
    original_filename: str
    optional: bool = False
    status: str = "Nicht vorhanden"
    note: str = ""
    warning: bool = False
    zip_filename: str = ""

    @property
    def downloadable(self) -> bool:
        return (
            self.paperless_id is not None
            and self.source_status == "completed"
            and not self.warning
        )


@dataclass
class PackageInspection:
    period: PackagePeriod
    entries: list[BookingEntry | ManualInvoiceEntry]
    references: list[_DocumentReference] = field(default_factory=list)
    open_transactions: int = 0
    expected_statements: int = 0
    present_statements: int = 0
    consistent_booking_rows: bool = True

    @property
    def unique_document_references(self) -> list[_DocumentReference]:
        result = []
        seen_ids = set()
        for reference in self.references:
            if reference.paperless_id is None:
                continue
            if reference.paperless_id in seen_ids:
                continue
            seen_ids.add(reference.paperless_id)
            result.append(reference)
        return result

    @property
    def initial_warning_count(self) -> int:
        return (
            sum(reference.warning for reference in self.references)
            + bool(self.open_transactions)
            + bool(not self.entries)
            + bool(not self.consistent_booking_rows)
        )

    def preview(self) -> dict[str, object]:
        ready_invoices = {
            entry.manual_invoice_id
            for entry in self.entries
            if isinstance(entry, ManualInvoiceEntry)
        }
        ready_invoice_references = [
            reference
            for reference in self.references
            if reference.kind == "Manuelle Rechnung"
        ]
        complete = (
            bool(self.entries)
            and self.consistent_booking_rows
            and self.open_transactions == 0
            and self.present_statements == self.expected_statements
            and len(ready_invoice_references) == len(ready_invoices)
            and not any(reference.warning for reference in self.references)
        )
        return {
            "booking_entries": len(self.entries),
            "found_documents": len(self.unique_document_references),
            "statements_present": self.present_statements,
            "statements_expected": self.expected_statements,
            "open_transactions": self.open_transactions,
            "warnings": self.initial_warning_count,
            "warning_items": self.warning_items(),
            "complete": complete,
            "status_label": "Paket vollständig" if complete else f"{self.initial_warning_count} Hinweise",
            "csv_filename": self.period.csv_filename,
        }

    def warning_items(self) -> list[str]:
        items = [
            reference.note or reference.status
            for reference in self.references
            if reference.warning
        ]
        if self.open_transactions:
            items.append(
                f"{self.open_transactions} offene Banktransaktion(en) im Zeitraum"
            )
        if not self.entries:
            items.append("Keine Buchungszeilen im ausgewählten Zeitraum.")
        if not self.consistent_booking_rows:
            items.append("Die Buchungszeilen sind fachlich nicht konsistent.")
        return items


@dataclass
class AccountantPackageResult:
    file: BinaryIO
    filename: str
    preview: dict[str, object]

    def close(self) -> None:
        self.file.close()


class _ZipNameAllocator:
    def __init__(self):
        self._used: set[str] = set()

    def allocate(self, directory: str, filename: str) -> str:
        safe_directory = directory.strip("/").replace("\\", "")
        safe_filename = _safe_component(filename)
        stem, dot, suffix = safe_filename.rpartition(".")
        if not dot:
            stem, suffix = safe_filename, ""
        candidate = f"{safe_directory}/{safe_filename}"
        counter = 2
        while candidate in self._used:
            numbered = f"{stem}_{counter}"
            if suffix:
                numbered = f"{numbered}.{suffix}"
            candidate = f"{safe_directory}/{numbered}"
            counter += 1
        self._used.add(candidate)
        return candidate


def normalize_period(period_type: str, value: str) -> PackagePeriod:
    """Normalize the only period inputs accepted by the package service."""
    period_type = str(period_type or "").strip().lower()
    value = str(value or "").strip().upper()
    if period_type == "month":
        match = PERIOD_PATTERN.fullmatch(value)
        if match is None:
            raise AccountantPackageError("Bitte einen gültigen Monat auswählen.")
        year = int(match.group("year"))
        month = int(match.group("month"))
        start = date(year, month, 1)
        end = date(year, month, _days_in_month(year, month))
        return PackagePeriod(period_type, value, start, end, (value,))
    if period_type == "quarter":
        match = QUARTER_PATTERN.fullmatch(value)
        if match is None:
            raise AccountantPackageError("Bitte ein gültiges Quartal auswählen.")
        year = match.group("year")
        quarter = match.group("quarter").upper()
        bounds = quarter_bounds(year, quarter)
        if bounds is None:
            raise AccountantPackageError("Bitte ein gültiges Quartal auswählen.")
        start, end = bounds
        first_month = start.month
        months = tuple(
            f"{start.year}-{month:02d}" for month in range(first_month, first_month + 3)
        )
        return PackagePeriod(period_type, f"{year}-{quarter}", start, end, months)
    raise AccountantPackageError("Bitte einen gültigen Zeitraum auswählen.")


def inspect_accountant_package(*, period_type: str, period: str) -> dict[str, object]:
    return AccountantPackageService.inspect(
        period_type=period_type,
        period=period,
    ).preview()


def build_accountant_package(*, period_type: str, period: str) -> AccountantPackageResult:
    return AccountantPackageService.build(
        period_type=period_type,
        period=period,
    )


class AccountantPackageService:
    @classmethod
    def inspect(cls, *, period_type: str, period: str) -> PackageInspection:
        package_period = normalize_period(period_type, period)
        entries = get_export_booking_entries(
            start_date=package_period.start_date,
            end_date=package_period.end_date,
        )
        inspection = PackageInspection(
            period=package_period,
            entries=entries,
            expected_statements=len(package_period.months),
        )
        cls._collect_manual_invoice_references(inspection)
        bank_transaction_ids = cls._collect_bank_document_references(inspection)
        cls._collect_matching_references(inspection, bank_transaction_ids)
        cls._collect_statement_references(inspection)
        inspection.open_transactions = BankTransaction.objects.filter(
            status__in=(
                BankTransaction.Status.IMPORTED,
                BankTransaction.Status.MATCHED,
            ),
            booking_date__gte=package_period.start_date,
            booking_date__lte=package_period.end_date,
        ).count()
        inspection.consistent_booking_rows = cls._booking_rows_are_consistent(
            inspection
        )
        return inspection

    @classmethod
    def build(cls, *, period_type: str, period: str) -> AccountantPackageResult:
        inspection = cls.inspect(period_type=period_type, period=period)
        if not inspection.entries:
            raise AccountantPackageError(
                "Keine Buchungszeilen im ausgewählten Zeitraum vorhanden."
            )

        try:
            csv_content = _build_csv_content(inspection.entries)
        except Exception as exc:
            raise AccountantPackageError(
                "Die Buchungszeilen konnten nicht in das Übergabepaket übernommen werden."
            ) from exc

        output = tempfile.SpooledTemporaryFile(
            max_size=8 * 1024 * 1024,
            mode="w+b",
        )
        try:
            allocator = _ZipNameAllocator()
            downloaded_ids: dict[int, str] = {}
            with zipfile.ZipFile(
                output,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                archive.writestr(inspection.period.csv_filename, csv_content)
                for reference in inspection.references:
                    if not reference.downloadable:
                        continue
                    document_id = reference.paperless_id
                    if document_id in downloaded_ids:
                        reference.zip_filename = downloaded_ids[document_id]
                        reference.status = "Enthalten"
                        reference.note = "Über eine weitere Beziehung bereits einmal im ZIP enthalten."
                        continue
                    try:
                        content = PaperlessClient.download_document(document_id)
                    except BookkeepingPaperlessError as exc:
                        if _is_paperless_404(exc):
                            reference.status = "Fehlend"
                            reference.warning = True
                            reference.note = (
                                "Das Dokument wurde mit der gespeicherten Paperless-ID "
                                "nicht gefunden."
                            )
                            continue
                        raise AccountantPackageTechnicalError(
                            f"Paperless-Dokument {document_id} konnte nicht geladen werden: {exc}"
                        ) from exc
                    if not isinstance(content, bytes) or not content:
                        raise AccountantPackageTechnicalError(
                            f"Paperless-Dokument {document_id} enthält keine gültige Binärdatei."
                        )
                    zip_filename = allocator.allocate(
                        reference.directory,
                        _filename_with_safe_extension(
                            reference.original_filename,
                            content,
                        ),
                    )
                    archive.writestr(zip_filename, content)
                    downloaded_ids[document_id] = zip_filename
                    reference.zip_filename = zip_filename
                    reference.status = "Enthalten"

                archive.writestr(
                    inspection.period.overview_filename,
                    _build_overview_csv(inspection),
                )
            output.seek(0)
            return AccountantPackageResult(
                file=output,
                filename=inspection.period.filename,
                preview=inspection.preview(),
            )
        except AccountantPackageError:
            output.close()
            raise
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            output.close()
            raise AccountantPackageTechnicalError(
                "Das Übergabepaket konnte technisch nicht erstellt werden."
            ) from exc
        except Exception:
            output.close()
            raise

    @staticmethod
    def _collect_manual_invoice_references(inspection: PackageInspection) -> None:
        invoices = {
            entry.manual_invoice_id: entry.manual_invoice
            for entry in inspection.entries
            if isinstance(entry, ManualInvoiceEntry)
        }
        for invoice in invoices.values():
            reference = _DocumentReference(
                kind="Manuelle Rechnung",
                directory=ZIP_DIRECTORIES["invoice"],
                display_date=invoice.payment_date or invoice.invoice_date,
                reference=invoice.invoice_number or str(invoice.reference_uuid)[:8],
                name=invoice.partner_name or "Diverse",
                amount=invoice.gross_amount,
                paperless_id=_positive_id(invoice.paperless_document_id),
                source_status=invoice.paperless_status,
                original_filename="rechnung.pdf",
            )
            if invoice.paperless_deleted_at is not None:
                reference.status = "Bewusst aus Paperless gelöscht"
                reference.warning = True
                reference.note = "Bewusst aus Paperless gelöscht."
            elif reference.paperless_id is None:
                reference.status = "Fehlendes Rechnungsdokument"
                reference.warning = True
                reference.note = "Die fertige Rechnung besitzt keine Paperless-Dokument-ID."
            elif invoice.paperless_status == ManualInvoice.PaperlessStatus.COMPLETED:
                reference.status = "Bereit"
            else:
                reference.status = invoice.get_paperless_status_display()
                reference.warning = True
                reference.note = (
                    f"Paperless-Status: {reference.status}."
                )
            reference.original_filename = _manual_invoice_filename(invoice)
            inspection.references.append(reference)

    @staticmethod
    def _collect_bank_document_references(
        inspection: PackageInspection,
    ) -> set[str]:
        transaction_ids = {
            str(entry.bank_transaction_id)
            for entry in inspection.entries
            if isinstance(entry, BookingEntry)
        }
        transactions = {
            str(transaction.pk): transaction
            for transaction in BankTransaction.objects.filter(
                pk__in=transaction_ids,
            )
        }
        documents = SupportingDocument.objects.filter(
            bank_transaction_id__in=transaction_ids,
        ).select_related("bank_transaction")
        for document in documents:
            transaction = transactions.get(str(document.bank_transaction_id))
            if transaction is None:
                continue
            document_date = transaction.value_date or transaction.booking_date
            reference = _DocumentReference(
                kind="Bankbeleg",
                directory=ZIP_DIRECTORIES["bank"],
                display_date=document_date,
                reference=str(transaction.pk)[:8],
                name=transaction.partner_name or "–",
                amount=transaction.amount,
                paperless_id=_positive_id(document.paperless_document_id),
                source_status=document.transfer_status,
                original_filename=document.original_filename,
            )
            if document.transfer_status == SupportingDocument.TransferStatus.COMPLETED:
                if reference.paperless_id is not None:
                    reference.status = "Bereit"
                else:
                    reference.status = "Fehlende Paperless-Dokument-ID"
                    reference.warning = True
                    reference.note = "Der fertige Bankbeleg besitzt keine Paperless-Dokument-ID."
            else:
                reference.status = document.get_transfer_status_display()
                reference.warning = True
                reference.note = f"Dokumentübertragung: {reference.status}."
            reference.original_filename = _bank_document_filename(
                transaction,
                document,
            )
            inspection.references.append(reference)
        return transaction_ids

    @staticmethod
    def _collect_matching_references(
        inspection: PackageInspection,
        bank_transaction_ids: set[str],
    ) -> None:
        rule_ids = set(
            str(rule_id)
            for rule_id in BankTransaction.objects.filter(
                pk__in=bank_transaction_ids,
            ).exclude(matched_rule_id=None).values_list("matched_rule_id", flat=True)
        )
        documents = SupportingDocument.objects.filter(
            matching_rule_id__in=rule_ids,
        ).select_related("matching_rule")
        for document in documents:
            rule = document.matching_rule
            reference = _DocumentReference(
                kind="Matching-Nachweis",
                directory=ZIP_DIRECTORIES["matching"],
                display_date=document.created_at.date(),
                reference=f"{rule.name} – Version {rule.version_number}",
                name=rule.name,
                amount=None,
                paperless_id=_positive_id(document.paperless_document_id),
                source_status=document.transfer_status,
                original_filename=_matching_document_filename(rule, document),
                optional=True,
            )
            if document.transfer_status == SupportingDocument.TransferStatus.COMPLETED:
                if reference.paperless_id is not None:
                    reference.status = "Bereit"
                else:
                    reference.status = "Optionale Paperless-ID fehlt"
                    reference.note = "Optionaler Nachweis ohne Paperless-Dokument-ID."
            else:
                reference.status = document.get_transfer_status_display()
                reference.warning = True
                reference.note = f"Dokumentübertragung: {reference.status}."
            inspection.references.append(reference)

    @staticmethod
    def _collect_statement_references(inspection: PackageInspection) -> None:
        for month in inspection.period.months:
            statements = list(
                BankStatement.objects.filter(
                    booking_month=month,
                ).order_by("statement_date", "statement_number", "id")
            )
            if not statements:
                inspection.references.append(
                    _DocumentReference(
                        kind="Kontoauszug",
                        directory=ZIP_DIRECTORIES["statement"],
                        display_date=_month_start(month),
                        reference=month,
                        name="–",
                        amount=None,
                        paperless_id=None,
                        source_status="missing",
                        original_filename=f"Kontoauszug_{month}.pdf",
                        status="Fehlend",
                        warning=True,
                        note=f"Für {month} fehlt der erwartete Kontoauszug.",
                    )
                )
                continue
            inspection.present_statements += sum(
                statement.paperless_status == BankStatement.PaperlessStatus.COMPLETED
                and _positive_id(statement.paperless_document_id) is not None
                for statement in statements
            )
            for statement in statements:
                reference = _DocumentReference(
                    kind="Kontoauszug",
                    directory=ZIP_DIRECTORIES["statement"],
                    display_date=statement.statement_date,
                    reference=f"{statement.statement_year}/{statement.statement_number}",
                    name=statement.iban,
                    amount=None,
                    paperless_id=_positive_id(statement.paperless_document_id),
                    source_status=statement.paperless_status,
                    original_filename=_statement_filename(statement),
                )
                if statement.paperless_status == BankStatement.PaperlessStatus.COMPLETED:
                    if reference.paperless_id is not None:
                        reference.status = "Bereit"
                    else:
                        reference.status = "Fehlende Paperless-Dokument-ID"
                        reference.warning = True
                        reference.note = "Der fertige Kontoauszug besitzt keine Paperless-Dokument-ID."
                else:
                    reference.status = statement.get_paperless_status_display()
                    reference.warning = True
                    reference.note = f"Kontoauszug: {reference.status}."
                inspection.references.append(reference)

    @staticmethod
    def _booking_rows_are_consistent(inspection: PackageInspection) -> bool:
        booking_entries = [
            entry for entry in inspection.entries if isinstance(entry, BookingEntry)
        ]
        entry_by_transaction: dict[str, list[BookingEntry]] = {}
        for entry in booking_entries:
            entry_by_transaction.setdefault(str(entry.bank_transaction_id), []).append(
                entry
            )
        transactions = BankTransaction.objects.filter(
            status__in=BOOKING_READY_STATUSES,
        ).filter(
            Q(
                booking_date__gte=inspection.period.start_date,
                booking_date__lte=inspection.period.end_date,
            )
            | Q(
                booking_entries__payment_date__gte=inspection.period.start_date,
                booking_entries__payment_date__lte=inspection.period.end_date,
            )
        ).distinct().prefetch_related(
            Prefetch(
                "booking_entries",
                queryset=BookingEntry.objects.only(
                    "id",
                    "bank_transaction_id",
                    "payment_date",
                    "gross_amount",
                ),
                to_attr="package_all_booking_entries",
            )
        )
        for transaction in transactions:
            selected = entry_by_transaction.get(str(transaction.pk), [])
            all_entries = getattr(transaction, "package_all_booking_entries", [])
            total = sum((entry.gross_amount for entry in selected), Decimal("0"))
            if (
                not selected
                or total.quantize(Decimal("0.01"))
                != transaction.amount.quantize(Decimal("0.01"))
                or any(
                    not inspection.period.start_date
                    <= entry.payment_date
                    <= inspection.period.end_date
                    for entry in all_entries
                )
            ):
                return False
        return True


def _build_overview_csv(inspection: PackageInspection) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(OVERVIEW_HEADERS)
    writer.writerow(
        (
            "CSV",
            "",
            inspection.period.csv_filename,
            "",
            "",
            "Enthalten",
            inspection.period.csv_filename,
            "",
            "Buchungsdatenbasis des Übergabepakets",
        )
    )
    for reference in inspection.references:
        writer.writerow(
            (
                reference.kind,
                _format_date(reference.display_date),
                reference.reference,
                reference.name,
                _format_amount(reference.amount),
                reference.status,
                reference.zip_filename,
                reference.paperless_id or "",
                reference.note,
            )
        )
    if inspection.open_transactions:
        writer.writerow(
            (
                "Offene Banktransaktionen",
                "",
                "",
                "",
                "",
                "Hinweis",
                "",
                "",
                f"{inspection.open_transactions} offene Banktransaktion(en) im Zeitraum.",
            )
        )

    contained_document_count = len(
        {
            reference.zip_filename
            for reference in inspection.references
            if reference.zip_filename
        }
    )
    warning_count = inspection.initial_warning_count
    summary = (
        ("Anzahl Buchungszeilen", len(inspection.entries)),
        (
            "Summe Buchungszeilen",
            _format_amount(
                sum(
                    (
                        entry.gross_amount or Decimal("0")
                        for entry in inspection.entries
                    ),
                    Decimal("0"),
                )
            ),
        ),
        (
            "Anzahl fertiger Banktransaktionen",
            len(
                {
                    entry.bank_transaction_id
                    for entry in inspection.entries
                    if isinstance(entry, BookingEntry)
                }
            ),
        ),
        (
            "Anzahl fertiger manueller Belege",
            len(
                {
                    entry.manual_invoice_id
                    for entry in inspection.entries
                    if isinstance(entry, ManualInvoiceEntry)
                }
            ),
        ),
        ("Anzahl enthaltener Dokumente", contained_document_count),
        ("Anzahl Warnungen", warning_count),
        ("Anzahl offener Transaktionen", inspection.open_transactions),
    )
    for label, value in summary:
        writer.writerow(
            (
                "Zusammenfassung",
                "",
                label,
                "",
                value if label == "Summe Buchungszeilen" else "",
                "Information",
                "",
                "",
                str(value) if label != "Summe Buchungszeilen" else "",
            )
        )
    return output.getvalue().encode("utf-8-sig")


def _format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value is not None else ""


def _format_amount(value: Decimal | None) -> str:
    return format_austrian_decimal(value) if value is not None else ""


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, month, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _month_start(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _positive_id(value) -> int | None:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _safe_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.replace("/", "_").replace("\\", "_")
    normalized = re.sub(r"\.{2,}", "_", normalized)
    normalized = re.sub(r"[^\w .,_-]+", "_", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", "_", normalized).strip(" ._")
    return normalized[:180] or "Dokument"


def _safe_original_filename(value: str) -> str:
    basename = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    return _safe_component(basename)


def _filename_with_safe_extension(filename: str, content: bytes) -> str:
    safe_name = _safe_original_filename(filename)
    stem, dot, extension = safe_name.rpartition(".")
    extension = extension.lower() if dot else ""
    if not SAFE_EXTENSION_PATTERN.fullmatch(extension or "") or extension not in SAFE_EXTENSIONS:
        extension = "pdf"
    if extension != "pdf" and not _content_has_plausible_extension(content, extension):
        extension = "pdf"
    if extension == "pdf" and not content.startswith(b"%PDF") and content[:4] not in {
        b"",
        b"PK\x03\x04",
    }:
        extension = "pdf"
    return f"{_safe_component(stem if dot else safe_name)}.{extension}"


def _content_has_plausible_extension(content: bytes, extension: str) -> bool:
    signatures = {
        "png": b"\x89PNG",
        "jpg": b"\xff\xd8\xff",
        "jpeg": b"\xff\xd8\xff",
        "tif": (b"II*\x00", b"MM\x00*"),
        "tiff": (b"II*\x00", b"MM\x00*"),
    }
    signature = signatures.get(extension)
    if signature is None:
        return True
    if isinstance(signature, tuple):
        return any(content.startswith(item) for item in signature)
    return content.startswith(signature)


def _manual_invoice_filename(invoice: ManualInvoice) -> str:
    document_date = invoice.payment_date or invoice.invoice_date
    date_part = document_date.isoformat() if document_date else "ohne-Datum"
    return _safe_component(
        f"{date_part}_{invoice.partner_name or 'Diverse'}_"
        f"{invoice.invoice_number or 'ohne-Rechnungsnummer'}.pdf"
    )


def _bank_document_filename(transaction: BankTransaction, document: SupportingDocument) -> str:
    document_date = transaction.value_date or transaction.booking_date
    short_uuid = str(transaction.pk).replace("-", "")[:8]
    return _safe_component(
        f"{document_date.isoformat()}_{transaction.partner_name or 'Unbekannt'}_"
        f"{format_austrian_decimal(transaction.amount)}_{short_uuid}_"
        f"{_safe_original_filename(document.original_filename)}"
    )


def _statement_filename(statement: BankStatement) -> str:
    return _safe_component(
        f"Kontoauszug_{statement.booking_month}_{statement.statement_number}.pdf"
    )


def _matching_document_filename(rule, document: SupportingDocument) -> str:
    return _safe_component(
        f"Matching-Regel_{rule.name}_Version-{rule.version_number}_"
        f"{_safe_original_filename(document.original_filename)}"
    )


def _is_paperless_404(error: BookkeepingPaperlessError) -> bool:
    return getattr(error, "status_code", None) == 404 or "404" in str(error)


BOOKING_READY_STATUSES = (
    BankTransaction.Status.REVIEWED,
    BankTransaction.Status.BOOKED,
)
