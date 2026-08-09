from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError

from .bank_statements import file_sha256
from .formatting import format_austrian_money
from .models import ManualInvoice
from .paperless import BookkeepingPaperlessError, PaperlessClient


class ManualInvoiceImportError(ValueError):
    """Expected, user-facing error for manual invoice handling."""


@dataclass(frozen=True)
class ManualInvoiceImportResult:
    invoice: ManualInvoice


def import_manual_invoice(uploaded_file) -> ManualInvoiceImportResult:
    file_hash = file_sha256(uploaded_file)
    if ManualInvoice.objects.filter(file_hash=file_hash).exists():
        raise ManualInvoiceImportError(
            "Diese Rechnung wurde bereits importiert. Ein zweites Dokument wird nicht angelegt."
        )
    try:
        invoice = ManualInvoice.objects.create(
            file_hash=file_hash,
            temporary_pdf=uploaded_file,
        )
    except IntegrityError:
        raise ManualInvoiceImportError(
            "Diese Rechnung wurde bereits importiert. Ein zweites Dokument wird nicht angelegt."
        ) from None
    return ManualInvoiceImportResult(invoice=invoice)


def _remove_temporary_pdf(invoice: ManualInvoice) -> None:
    if invoice.temporary_pdf:
        invoice.temporary_pdf.delete(save=False)
    invoice.temporary_pdf = None


def _has_temporary_pdf(invoice: ManualInvoice) -> bool:
    if not invoice.temporary_pdf:
        return False
    try:
        return invoice.temporary_pdf.storage.exists(invoice.temporary_pdf.name)
    except OSError:
        return False


def _complete_manual_invoice_paperless(invoice: ManualInvoice, document_id: int) -> str:
    invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
    invoice.paperless_document_id = document_id
    invoice.paperless_error = ""
    _remove_temporary_pdf(invoice)
    invoice.save(
        update_fields=(
            "temporary_pdf",
            "paperless_status",
            "paperless_document_id",
            "paperless_error",
            "updated_at",
        )
    )
    return str(document_id)


def _resolve_before_manual_invoice_upload(invoice: ManualInvoice) -> dict[str, object]:
    if invoice.paperless_document_id:
        return {
            "status": "completed",
            "document_id": int(invoice.paperless_document_id),
        }

    task_result = None
    if invoice.paperless_task_id:
        try:
            task_result = PaperlessClient.task_status(invoice.paperless_task_id)
        except BookkeepingPaperlessError as task_error:
            try:
                reference_result = PaperlessClient.find_document_by_reference(
                    str(invoice.reference_uuid)
                )
            except BookkeepingPaperlessError:
                raise task_error
            if reference_result["status"] == "completed":
                return reference_result
            raise task_error
        if task_result["status"] in {"pending", "completed"}:
            return task_result

    if not PaperlessClient.is_configured():
        return {"status": "not_found", "document_id": None}

    reference_result = PaperlessClient.find_document_by_reference(
        str(invoice.reference_uuid)
    )
    if reference_result["status"] == "completed":
        return reference_result

    if task_result is None:
        return {"status": "not_found", "document_id": None}
    if task_result["status"] == "failed":
        return task_result
    if not task_result.get("found", True):
        return {"status": "not_found", "document_id": None}

    # A successful task without a document ID is deliberately kept pending.
    # Re-uploading in this ambiguous state could create a duplicate document.
    return {
        "status": "pending",
        "document_id": None,
        "message": task_result.get("message") or "Paperless-Task wird geprüft.",
    }


def start_manual_invoice_upload(
    invoice: ManualInvoice,
    *,
    check_existing_reference: bool = False,
) -> str:
    if (
        invoice.paperless_document_id
        or invoice.paperless_task_id
        or check_existing_reference
        or invoice.paperless_status
        in {
            ManualInvoice.PaperlessStatus.FAILED,
            ManualInvoice.PaperlessStatus.COMPLETED,
        }
    ):
        resolved = _resolve_before_manual_invoice_upload(invoice)
    else:
        resolved = {"status": "not_found", "document_id": None}
    if resolved["status"] == "completed" and resolved.get("document_id"):
        return _complete_manual_invoice_paperless(
            invoice,
            int(resolved["document_id"]),
        )
    if resolved["status"] == "pending":
        invoice.paperless_status = ManualInvoice.PaperlessStatus.PENDING
        invoice.paperless_error = ""
        invoice.save(update_fields=("paperless_status", "paperless_error", "updated_at"))
        return invoice.paperless_task_id
    if not _has_temporary_pdf(invoice):
        raise BookkeepingPaperlessError(
            "Die ursprüngliche PDF ist nicht mehr verfügbar. "
            "Bitte laden Sie die Rechnung erneut hoch."
        )
    try:
        task_id = PaperlessClient.upload_manual_invoice(invoice)
    except BookkeepingPaperlessError as exc:
        invoice.paperless_status = ManualInvoice.PaperlessStatus.FAILED
        invoice.paperless_error = str(exc)
        invoice.save(
            update_fields=("paperless_status", "paperless_error", "updated_at")
        )
        raise
    invoice.paperless_task_id = task_id
    invoice.paperless_status = ManualInvoice.PaperlessStatus.PENDING
    invoice.paperless_error = ""
    invoice.save(
        update_fields=(
            "paperless_task_id",
            "paperless_status",
            "paperless_error",
            "updated_at",
        )
    )
    return task_id


def retry_manual_invoice(invoice: ManualInvoice) -> str:
    if invoice.paperless_status not in {
        ManualInvoice.PaperlessStatus.NOT_STARTED,
        ManualInvoice.PaperlessStatus.FAILED,
    }:
        raise ManualInvoiceImportError(
            "Diese Rechnung kann derzeit nicht erneut übertragen werden."
        )
    return start_manual_invoice_upload(invoice, check_existing_reference=True)


def refresh_pending_manual_invoice_tasks() -> None:
    invoices = ManualInvoice.objects.filter(
        paperless_status=ManualInvoice.PaperlessStatus.PENDING,
    ).exclude(paperless_task_id="")
    for invoice in invoices:
        try:
            result = PaperlessClient.task_status(invoice.paperless_task_id)
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
                    str(invoice.reference_uuid)
                )
            except BookkeepingPaperlessError as exc:
                invoice.paperless_status = ManualInvoice.PaperlessStatus.FAILED
                invoice.paperless_error = str(exc)
                invoice.save(
                    update_fields=(
                        "paperless_status",
                        "paperless_error",
                        "updated_at",
                    )
                )
                continue
            if result["status"] == "pending":
                continue
        if result["status"] == "completed":
            _complete_manual_invoice_paperless(
                invoice,
                int(result["document_id"]),
            )
            continue
        invoice.paperless_status = ManualInvoice.PaperlessStatus.FAILED
        invoice.paperless_error = str(
            result.get("message") or "Paperless meldet einen Fehler beim Upload."
        )
        invoice.save(
            update_fields=("paperless_status", "paperless_error", "updated_at")
        )


def duplicate_manual_invoice_warning(invoice: ManualInvoice) -> str:
    if not invoice.partner_name or invoice.gross_amount is None:
        return ""
    duplicate = ManualInvoice.objects.filter(
        partner_name__iexact=invoice.partner_name,
        invoice_number=invoice.invoice_number,
        gross_amount=invoice.gross_amount,
    ).exclude(pk=invoice.pk).first()
    if duplicate is None:
        return ""
    return (
        "Eine Rechnung mit gleichem Lieferanten, gleicher Rechnungsnummer und "
        f"gleichem Bruttobetrag ({format_austrian_money(invoice.gross_amount, 'EUR')}) "
        "ist bereits vorhanden."
    )


def display_manual_invoice(invoice: ManualInvoice) -> dict:
    status_labels = dict(ManualInvoice.PaperlessStatus.choices)
    return {
        "id": invoice.pk,
        "reference_uuid": str(invoice.reference_uuid),
        "invoice_number": invoice.invoice_number or "–",
        "invoice_date": invoice.invoice_date.strftime("%d.%m.%Y")
        if invoice.invoice_date
        else "–",
        "payment_date": invoice.payment_date.strftime("%d.%m.%Y")
        if invoice.payment_date
        else "–",
        "month": invoice.payment_date.strftime("%Y-%m")
        if invoice.payment_date
        else "–",
        "partner_name": invoice.partner_name or "–",
        "gross_amount": format_austrian_money(invoice.gross_amount, "EUR"),
        "status": invoice.get_status_display(),
        "status_code": invoice.status,
        "paperless_status": invoice.paperless_status,
        "paperless_status_label": status_labels.get(
            invoice.paperless_status,
            invoice.paperless_status,
        ),
        "paperless_error": invoice.paperless_error,
        "paperless_document_url": PaperlessClient.document_url(
            invoice.paperless_document_id
        ),
        "can_retry": invoice.paperless_status
        in {
            ManualInvoice.PaperlessStatus.NOT_STARTED,
            ManualInvoice.PaperlessStatus.FAILED,
        }
        and bool(invoice.temporary_pdf),
    }
