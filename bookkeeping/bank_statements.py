from __future__ import annotations

import hashlib
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Count, Q, Sum

from .formatting import format_austrian_money
from .models import BankStatement, BankTransaction
from .paperless import BookkeepingPaperlessError, PaperlessClient
from .bank_statement_parser import (
    BankStatementParseError,
    ParsedBankStatement,
    parse_bank_statement,
)


class BankStatementImportError(ValueError):
    """Expected, user-facing import error."""


@dataclass(frozen=True)
class BankStatementImportResult:
    statement: BankStatement
    paperless_error: str = ""


def file_sha256(uploaded_file) -> str:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    digest = hashlib.sha256()
    while True:
        chunk = uploaded_file.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return digest.hexdigest()


def _month_bounds(month: str) -> tuple[date, date]:
    year, month_number = (int(value) for value in month.split("-"))
    return date(year, month_number, 1), date(
        year,
        month_number,
        monthrange(year, month_number)[1],
    )


def _zero() -> Decimal:
    return Decimal("0.00")


def json_control_for_statement(statement: BankStatement) -> dict:
    start_date, end_date = _month_bounds(statement.booking_month)
    aggregate = BankTransaction.objects.filter(
        value_date__gte=start_date,
        value_date__lte=end_date,
    ).aggregate(
        count=Count("id"),
        credits=Sum("amount", filter=Q(amount__gt=0)),
        negative_amounts=Sum("amount", filter=Q(amount__lt=0)),
    )
    transaction_count = aggregate["count"] or 0
    credits = aggregate["credits"] or _zero()
    negative_amounts = aggregate["negative_amounts"] or _zero()
    debits = abs(negative_amounts)
    net_movement = credits - debits
    calculated_closing = statement.opening_balance + net_movement
    credits_difference = credits - statement.total_credits
    debits_difference = debits - statement.total_debits
    closing_difference = calculated_closing - statement.closing_balance

    if transaction_count == 0:
        status = "warning"
        message = "Für diesen Monat sind noch keine JSON-Transaktionen vorhanden."
    elif (
        credits_difference == _zero()
        and debits_difference == _zero()
        and closing_difference == _zero()
    ):
        status = "success"
        message = "Kontoauszug und importierte Transaktionen stimmen überein."
    else:
        status = "danger"
        message = (
            "Abweichung: Gutschriften "
            f"{format_austrian_money(credits_difference, 'EUR')}, "
            "Belastungen "
            f"{format_austrian_money(debits_difference, 'EUR')}, "
            "Endstand "
            f"{format_austrian_money(closing_difference, 'EUR')}."
        )

    return {
        "status": status,
        "status_label": message,
        "message": message,
        "transaction_count": transaction_count,
        "credits_value": credits,
        "debits_value": debits,
        "net_movement_value": net_movement,
        "calculated_closing_value": calculated_closing,
        "credits": format_austrian_money(credits, "EUR"),
        "debits": format_austrian_money(debits, "EUR"),
        "net_movement": format_austrian_money(net_movement, "EUR"),
        "calculated_closing": format_austrian_money(calculated_closing, "EUR"),
        "credits_difference": format_austrian_money(credits_difference, "EUR"),
        "debits_difference": format_austrian_money(debits_difference, "EUR"),
        "closing_difference": format_austrian_money(closing_difference, "EUR"),
    }


def _has_temporary_pdf(statement: BankStatement) -> bool:
    if not statement.temporary_pdf:
        return False
    try:
        return statement.temporary_pdf.storage.exists(statement.temporary_pdf.name)
    except OSError:
        return False


def display_bank_statement(statement: BankStatement) -> dict:
    status_labels = dict(BankStatement.PaperlessStatus.choices)
    control = json_control_for_statement(statement)
    return {
        "id": statement.pk,
        "month": statement.booking_month,
        "quarter": statement.booking_quarter,
        "statement_number": f"{statement.statement_number:03d}/{statement.statement_year}",
        "opening_balance": format_austrian_money(statement.opening_balance, "EUR"),
        "credits": format_austrian_money(statement.total_credits, "EUR"),
        "debits": format_austrian_money(statement.total_debits, "EUR"),
        "closing_balance": format_austrian_money(statement.closing_balance, "EUR"),
        "json_control": control,
        "paperless_status": statement.paperless_status,
        "paperless_status_label": status_labels.get(
            statement.paperless_status,
            statement.paperless_status,
        ),
        "paperless_error": statement.paperless_error,
        "paperless_document_url": PaperlessClient.document_url(
            statement.paperless_document_id
        ),
        "can_retry": (
            statement.paperless_status == BankStatement.PaperlessStatus.FAILED
            and _has_temporary_pdf(statement)
        ),
    }


def _remove_temporary_pdf(statement: BankStatement) -> None:
    if statement.temporary_pdf:
        statement.temporary_pdf.delete(save=False)
    statement.temporary_pdf = None


def refresh_pending_paperless_tasks() -> None:
    for statement in BankStatement.objects.filter(
        paperless_status=BankStatement.PaperlessStatus.PENDING,
    ).exclude(paperless_task_id=""):
        try:
            result = PaperlessClient.task_status(statement.paperless_task_id)
        except BookkeepingPaperlessError as exc:
            result = {
                "status": "needs_fallback",
                "document_id": None,
                "message": str(exc),
            }
        if result["status"] == "pending":
            continue
        if result["status"] == "needs_fallback":
            try:
                result = PaperlessClient.find_document_by_reference(
                    str(statement.reference_uuid)
                )
            except BookkeepingPaperlessError as exc:
                statement.paperless_status = BankStatement.PaperlessStatus.FAILED
                statement.paperless_document_id = None
                statement.paperless_error = str(exc)
                statement.save(
                    update_fields=(
                        "paperless_status",
                        "paperless_document_id",
                        "paperless_error",
                        "updated_at",
                    )
                )
                continue
            if result["status"] == "pending":
                continue
        if result["status"] == "completed":
            statement.paperless_status = BankStatement.PaperlessStatus.COMPLETED
            statement.paperless_document_id = result["document_id"]
            statement.paperless_reference_synced = True
            statement.paperless_error = ""
            _remove_temporary_pdf(statement)
            statement.save(
                update_fields=(
                    "temporary_pdf",
                    "paperless_status",
                    "paperless_document_id",
                    "paperless_reference_synced",
                    "paperless_error",
                    "updated_at",
                )
            )
            continue
        statement.paperless_status = BankStatement.PaperlessStatus.FAILED
        statement.paperless_document_id = None
        statement.paperless_error = str(
            result.get("message") or "Paperless meldet einen Fehler beim Upload."
        )
        statement.save(
            update_fields=(
                "paperless_status",
                "paperless_document_id",
                "paperless_error",
                "updated_at",
            )
        )


def refresh_unsynced_completed_references() -> dict[int, str]:
    synchronization_errors = {}
    statements = BankStatement.objects.filter(
        paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        paperless_document_id__isnull=False,
        paperless_reference_synced=False,
    )
    for statement in statements:
        try:
            result = PaperlessClient.synchronize_statement_reference(statement)
        except BookkeepingPaperlessError as exc:
            synchronization_errors[statement.pk] = str(exc)
            continue
        if result["status"] != "synced":
            continue
        statement.paperless_reference_synced = True
        statement.paperless_error = ""
        statement.save(
            update_fields=(
                "paperless_reference_synced",
                "paperless_error",
                "updated_at",
            )
        )
    return synchronization_errors


def _statement_values(parsed: ParsedBankStatement, file_hash: str, uploaded_file) -> dict:
    return {
        "iban": parsed.iban,
        "statement_number": parsed.statement_number,
        "statement_year": parsed.statement_year,
        "statement_date": parsed.statement_date,
        "booking_month": parsed.booking_month,
        "booking_quarter": parsed.booking_quarter,
        "opening_balance": parsed.opening_balance,
        "total_credits": parsed.total_credits,
        "total_debits": parsed.total_debits,
        "closing_balance": parsed.closing_balance,
        "file_hash": file_hash,
        "temporary_pdf": uploaded_file,
        "paperless_status": BankStatement.PaperlessStatus.PENDING,
    }


def import_bank_statement(uploaded_file) -> BankStatementImportResult:
    file_hash = file_sha256(uploaded_file)
    existing_by_hash = BankStatement.objects.filter(file_hash=file_hash).first()
    if existing_by_hash is not None:
        raise BankStatementImportError(
            "Dieser Kontoauszug wurde bereits importiert. Ein zweites Paperless-Dokument wird nicht angelegt."
        )
    try:
        parsed = parse_bank_statement(uploaded_file)
    except BankStatementParseError:
        raise
    if BankStatement.objects.filter(
        iban=parsed.iban,
        statement_year=parsed.statement_year,
        statement_number=parsed.statement_number,
    ).exists():
        raise BankStatementImportError(
            "Dieser Kontoauszug mit IBAN, Jahr und Auszugsnummer ist bereits vorhanden."
        )

    try:
        statement = BankStatement.objects.create(
            **_statement_values(parsed, file_hash, uploaded_file)
        )
    except IntegrityError:
        raise BankStatementImportError(
            "Dieser Kontoauszug ist bereits vorhanden. Ein zweites Paperless-Dokument wird nicht angelegt."
        ) from None
    try:
        task_id = PaperlessClient.upload_bank_statement(statement)
    except BookkeepingPaperlessError as exc:
        statement.paperless_status = BankStatement.PaperlessStatus.FAILED
        statement.paperless_error = str(exc)
        statement.save(update_fields=("paperless_status", "paperless_error", "updated_at"))
        return BankStatementImportResult(statement=statement, paperless_error=str(exc))
    statement.paperless_task_id = task_id
    statement.paperless_status = BankStatement.PaperlessStatus.PENDING
    statement.paperless_error = ""
    statement.save(update_fields=("paperless_task_id", "paperless_status", "paperless_error", "updated_at"))
    return BankStatementImportResult(statement=statement)


def retry_bank_statement(statement: BankStatement) -> str:
    if statement.paperless_status != BankStatement.PaperlessStatus.FAILED:
        raise BankStatementImportError(
            "Dieser Kontoauszug kann derzeit nicht erneut übertragen werden."
        )
    if not _has_temporary_pdf(statement):
        raise BankStatementImportError(
            "Die temporäre PDF-Datei ist nicht mehr vorhanden. Ein erneuter Upload ist erforderlich."
        )
    try:
        task_id = PaperlessClient.upload_bank_statement(statement)
    except BookkeepingPaperlessError as exc:
        statement.paperless_error = str(exc)
        statement.save(update_fields=("paperless_error", "updated_at"))
        raise BankStatementImportError(str(exc)) from None
    statement.paperless_task_id = task_id
    statement.paperless_document_id = None
    statement.paperless_status = BankStatement.PaperlessStatus.PENDING
    statement.paperless_error = ""
    statement.save(
        update_fields=(
            "paperless_task_id",
            "paperless_document_id",
            "paperless_status",
            "paperless_error",
            "updated_at",
        )
    )
    return task_id
