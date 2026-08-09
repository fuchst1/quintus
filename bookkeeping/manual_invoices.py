from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from .bank_statements import file_sha256
from .formatting import format_austrian_money
from .models import ManualInvoice, ManualInvoiceEntry
from .paperless import BookkeepingPaperlessError, PaperlessClient


logger = logging.getLogger(__name__)
PAPERLESS_NOT_FOUND_MESSAGE = "Paperless antwortet mit HTTP-Status 404."
PAPERLESS_PENDING_DELETE_MESSAGE = (
    "Die Paperless-Übertragung ist noch nicht eindeutig abgeschlossen. "
    "Bitte später erneut versuchen."
)


class ManualInvoiceDeletionError(ValueError):
    """Expected, user-facing error for complete manual-invoice deletion."""


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
    if invoice.paperless_deleted_at is not None:
        raise BookkeepingPaperlessError(
            "Das Paperless-Dokument wurde bewusst gelöscht und darf nicht erneut "
            "übertragen werden."
        )
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
    if invoice.paperless_deleted_at is not None:
        raise BookkeepingPaperlessError(
            "Das Paperless-Dokument wurde bewusst gelöscht. Eine erneute Übertragung "
            "ist nicht vorgesehen."
        )
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
    if invoice.paperless_deleted_at is not None:
        raise ManualInvoiceImportError(
            "Das Paperless-Dokument wurde bewusst gelöscht. Eine erneute Übertragung "
            "ist nicht vorgesehen."
        )
    if invoice.paperless_status not in {
        ManualInvoice.PaperlessStatus.NOT_STARTED,
        ManualInvoice.PaperlessStatus.FAILED,
    }:
        raise ManualInvoiceImportError(
            "Diese Rechnung kann derzeit nicht erneut übertragen werden."
        )
    return start_manual_invoice_upload(invoice, check_existing_reference=True)


def _paperless_reference_for_deletion(invoice: ManualInvoice) -> int | None:
    """Resolve a document only through the task and the invoice UUID."""
    if invoice.paperless_document_id:
        return int(invoice.paperless_document_id)

    if not invoice.paperless_task_id:
        if (
            invoice.paperless_status == ManualInvoice.PaperlessStatus.NOT_STARTED
            and not PaperlessClient.is_configured()
        ):
            return None
        try:
            result = PaperlessClient.find_document_by_reference(
                str(invoice.reference_uuid)
            )
        except BookkeepingPaperlessError as exc:
            raise ManualInvoiceDeletionError(str(exc)) from None
        if result["status"] == "completed" and result.get("document_id"):
            return int(result["document_id"])
        if result["status"] == "pending":
            # find_document_by_reference uses pending for an empty result set.
            return None
        raise ManualInvoiceDeletionError(
            str(result.get("message") or PAPERLESS_PENDING_DELETE_MESSAGE)
        )

    try:
        task_result = PaperlessClient.task_status(invoice.paperless_task_id)
    except BookkeepingPaperlessError:
        try:
            reference_result = PaperlessClient.find_document_by_reference(
                str(invoice.reference_uuid)
            )
        except BookkeepingPaperlessError as exc:
            if "mehrere Dokumente" in str(exc):
                raise ManualInvoiceDeletionError(str(exc)) from None
            raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE) from None
        if reference_result["status"] == "completed" and reference_result.get(
            "document_id"
        ):
            return int(reference_result["document_id"])
        raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE)

    if task_result["status"] == "completed" and task_result.get("document_id"):
        return int(task_result["document_id"])
    if task_result["status"] == "failed":
        try:
            reference_result = PaperlessClient.find_document_by_reference(
                str(invoice.reference_uuid)
            )
        except BookkeepingPaperlessError as exc:
            raise ManualInvoiceDeletionError(str(exc)) from None
        if reference_result["status"] == "completed" and reference_result.get(
            "document_id"
        ):
            return int(reference_result["document_id"])
        return None

    try:
        reference_result = PaperlessClient.find_document_by_reference(
            str(invoice.reference_uuid)
        )
    except BookkeepingPaperlessError as exc:
        if "mehrere Dokumente" in str(exc):
            raise ManualInvoiceDeletionError(str(exc)) from None
        raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE) from None
    if reference_result["status"] == "completed" and reference_result.get(
        "document_id"
    ):
        return int(reference_result["document_id"])
    # Pending, not-found-task and successful-without-id are intentionally
    # treated as ambiguous.  No local deletion is allowed in those states.
    if (
        task_result["status"] == "needs_fallback"
        and task_result.get("found") is False
    ):
        return None
    raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE)


def _delete_manual_invoice_paperless(invoice: ManualInvoice) -> None:
    if invoice.paperless_deleted_at is not None:
        return
    document_id = _paperless_reference_for_deletion(invoice)
    if document_id is None:
        return
    try:
        PaperlessClient.delete_document(document_id)
    except BookkeepingPaperlessError as exc:
        if str(exc) != PAPERLESS_NOT_FOUND_MESSAGE:
            raise ManualInvoiceDeletionError(str(exc)) from None
        try:
            replacement = PaperlessClient.find_document_by_reference(
                str(invoice.reference_uuid)
            )
        except BookkeepingPaperlessError as lookup_error:
            raise ManualInvoiceDeletionError(str(lookup_error)) from None
        if replacement["status"] != "completed" or not replacement.get("document_id"):
            return
        replacement_id = int(replacement["document_id"])
        if replacement_id == document_id:
            return
        try:
            PaperlessClient.delete_document(replacement_id)
        except BookkeepingPaperlessError as replacement_error:
            if str(replacement_error) != PAPERLESS_NOT_FOUND_MESSAGE:
                raise ManualInvoiceDeletionError(str(replacement_error)) from None


def delete_manual_invoice_completely(invoice: ManualInvoice) -> None:
    """Delete Paperless first, then the local invoice and its entries."""
    _delete_manual_invoice_paperless(invoice)

    temporary_name = invoice.temporary_pdf.name if invoice.temporary_pdf else ""
    temporary_storage = invoice.temporary_pdf.storage if invoice.temporary_pdf else None
    try:
        with db_transaction.atomic():
            locked_invoice = ManualInvoice.objects.select_for_update().get(
                pk=invoice.pk
            )
            ManualInvoiceEntry.objects.filter(manual_invoice=locked_invoice).delete()
            locked_invoice.delete()
    except Exception as exc:
        logger.exception(
            "Lokale Löschung von ManualInvoice %s nach Paperless-Löschung fehlgeschlagen.",
            invoice.pk,
        )
        raise ManualInvoiceDeletionError(
            "Das Paperless-Dokument wurde behandelt, aber der lokale Beleg konnte "
            "nicht gelöscht werden. Bitte erneut versuchen."
        ) from exc

    if temporary_storage and temporary_name:
        try:
            temporary_storage.delete(temporary_name)
        except OSError:
            logger.exception(
                "Temporäre PDF-Datei %s konnte nach lokaler Löschung nicht entfernt werden.",
                os.path.basename(temporary_name),
            )


def _paperless_reference_for_paperless_only_delete(invoice: ManualInvoice) -> int:
    """Resolve a Paperless document without ever guessing its identity."""
    if invoice.paperless_document_id:
        return int(invoice.paperless_document_id)

    if invoice.paperless_task_id:
        try:
            task_result = PaperlessClient.task_status(invoice.paperless_task_id)
        except BookkeepingPaperlessError as task_error:
            try:
                reference_result = PaperlessClient.find_document_by_reference(
                    str(invoice.reference_uuid)
                )
            except BookkeepingPaperlessError as reference_error:
                if "mehrere Dokumente" in str(reference_error):
                    raise ManualInvoiceDeletionError(str(reference_error)) from None
                raise ManualInvoiceDeletionError(str(task_error)) from None
            if reference_result.get("status") == "completed" and reference_result.get(
                "document_id"
            ):
                return int(reference_result["document_id"])
            raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE)

        if task_result.get("status") == "completed" and task_result.get(
            "document_id"
        ):
            return int(task_result["document_id"])
        if task_result.get("status") == "pending":
            raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE)

    try:
        reference_result = PaperlessClient.find_document_by_reference(
            str(invoice.reference_uuid)
        )
    except BookkeepingPaperlessError as exc:
        raise ManualInvoiceDeletionError(str(exc)) from None
    if reference_result.get("status") == "completed" and reference_result.get(
        "document_id"
    ):
        return int(reference_result["document_id"])
    raise ManualInvoiceDeletionError(PAPERLESS_PENDING_DELETE_MESSAGE)


def delete_manual_invoice_from_paperless(invoice: ManualInvoice) -> None:
    """Delete only the remote invoice document and retain all local data."""
    if invoice.paperless_deleted_at is not None:
        raise ManualInvoiceDeletionError(
            "Das Paperless-Dokument wurde bereits bewusst gelöscht."
        )

    document_id = _paperless_reference_for_paperless_only_delete(invoice)
    try:
        PaperlessClient.delete_document(document_id)
    except BookkeepingPaperlessError as exc:
        raise ManualInvoiceDeletionError(str(exc)) from None

    try:
        with db_transaction.atomic():
            locked_invoice = ManualInvoice.objects.select_for_update().get(
                pk=invoice.pk
            )
            locked_invoice.paperless_deleted_at = timezone.now()
            locked_invoice.paperless_document_id = None
            locked_invoice.paperless_task_id = ""
            locked_invoice.paperless_status = ManualInvoice.PaperlessStatus.DELETED
            locked_invoice.paperless_error = ""
            locked_invoice.save(
                update_fields=(
                    "paperless_deleted_at",
                    "paperless_document_id",
                    "paperless_task_id",
                    "paperless_status",
                    "paperless_error",
                    "updated_at",
                )
            )
    except Exception as exc:
        logger.exception(
            "Paperless-Dokument von ManualInvoice %s wurde gelöscht, "
            "die lokale Löschmarkierung konnte aber nicht gespeichert werden.",
            invoice.pk,
        )
        raise ManualInvoiceDeletionError(
            "Das Paperless-Dokument wurde gelöscht, die lokale Löschmarkierung "
            "konnte aber nicht gespeichert werden. Bitte erneut prüfen."
        ) from exc


def refresh_pending_manual_invoice_tasks() -> None:
    invoices = ManualInvoice.objects.filter(
        paperless_status=ManualInvoice.PaperlessStatus.PENDING,
        paperless_deleted_at__isnull=True,
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
        "can_retry": invoice.paperless_status
        in {
            ManualInvoice.PaperlessStatus.NOT_STARTED,
            ManualInvoice.PaperlessStatus.FAILED,
        }
        and bool(invoice.temporary_pdf),
    }
