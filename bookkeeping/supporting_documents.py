from __future__ import annotations

import os
from dataclasses import dataclass

from django.db import IntegrityError

from .models import BankTransaction, MatchingRule, SupportingDocument
from .paperless import BookkeepingPaperlessError, PaperlessClient


MAX_SUPPORTING_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024


class SupportingDocumentError(ValueError):
    """Expected, user-facing error for supporting-document handling."""


@dataclass(frozen=True)
class SupportingDocumentImportResult:
    document: SupportingDocument


def _has_temporary_file(document: SupportingDocument) -> bool:
    if not document.temporary_file:
        return False
    try:
        return document.temporary_file.storage.exists(document.temporary_file.name)
    except OSError:
        return False


def _validate_pdf_file(uploaded_file) -> None:
    if uploaded_file.size > MAX_SUPPORTING_DOCUMENT_SIZE_BYTES:
        raise SupportingDocumentError("Die PDF-Datei darf höchstens 25 MB groß sein.")
    if not str(uploaded_file.name or "").lower().endswith(".pdf"):
        raise SupportingDocumentError("Bitte eine PDF-Datei auswählen.")
    if str(getattr(uploaded_file, "content_type", "") or "").lower() not in {
        "application/pdf",
        "application/x-pdf",
    }:
        raise SupportingDocumentError(
            "Die Datei muss den Content-Type application/pdf haben."
        )
    current_position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    file_header = uploaded_file.read(5)
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(current_position)
    if file_header != b"%PDF-":
        raise SupportingDocumentError("Die Datei ist kein gültiges PDF.")
def _remove_temporary_file(document: SupportingDocument) -> None:
    if document.temporary_file:
        document.temporary_file.delete(save=False)
    document.temporary_file = None


def _save_failure(document: SupportingDocument, message: str) -> None:
    document.transfer_status = SupportingDocument.TransferStatus.FAILED
    document.transfer_error = str(message).strip() or "Paperless meldet einen Fehler beim Upload."
    document.save(update_fields=("transfer_status", "transfer_error", "updated_at"))


def _complete(document: SupportingDocument, document_id: int) -> SupportingDocument:
    document.paperless_document_id = int(document_id)
    document.transfer_status = SupportingDocument.TransferStatus.COMPLETED
    document.transfer_error = ""
    _remove_temporary_file(document)
    document.save(
        update_fields=(
            "temporary_file",
            "paperless_document_id",
            "transfer_status",
            "transfer_error",
            "updated_at",
        )
    )
    return document


def _resolve_existing(document: SupportingDocument) -> dict[str, object]:
    if document.paperless_document_id:
        return {
            "status": "completed",
            "document_id": int(document.paperless_document_id),
        }

    task_result = None
    if document.paperless_task_id:
        task_result = PaperlessClient.task_status(document.paperless_task_id)
        if task_result["status"] == "completed" and task_result.get("document_id"):
            return task_result
        if task_result["status"] == "pending":
            return task_result
        if task_result["status"] == "failed":
            return task_result

    reference_result = PaperlessClient.find_document_by_reference(
        str(document.reference_uuid)
    )
    if reference_result["status"] == "completed":
        return reference_result
    if (
        task_result is not None
        and task_result["status"] in {"pending", "needs_fallback"}
        and reference_result["status"] == "pending"
    ):
        return reference_result
    if task_result is not None:
        return task_result
    return {"status": "not_found", "document_id": None}


def start_supporting_document_upload(
    document: SupportingDocument,
    *,
    check_existing_reference: bool = False,
) -> SupportingDocument:
    """Resolve known Paperless state before allowing one upload attempt."""
    if document.paperless_document_id:
        return _complete(document, int(document.paperless_document_id))
    if document.transfer_status == SupportingDocument.TransferStatus.COMPLETED:
        raise BookkeepingPaperlessError(
            "Dieser Beleg ist bereits als abgelegt markiert, aber ohne Dokument-ID."
        )

    should_resolve = bool(document.paperless_task_id or check_existing_reference)
    if should_resolve:
        try:
            resolved = _resolve_existing(document)
        except BookkeepingPaperlessError:
            # An unavailable/ambiguous API must not be followed by another upload.
            raise
        if resolved["status"] == "completed" and resolved.get("document_id"):
            return _complete(document, int(resolved["document_id"]))
        if resolved["status"] == "pending":
            document.transfer_status = SupportingDocument.TransferStatus.PENDING
            document.transfer_error = ""
            document.save(update_fields=("transfer_status", "transfer_error", "updated_at"))
            return document
        if document.paperless_task_id and resolved["status"] not in {"failed", "not_found"}:
            raise BookkeepingPaperlessError(
                str(resolved.get("message") or "Der Paperless-Status ist unklar.")
            )

    if not _has_temporary_file(document):
        raise BookkeepingPaperlessError(
            "Die ursprüngliche PDF ist nicht mehr verfügbar. Bitte den Beleg erneut hochladen."
        )
    try:
        task_id = PaperlessClient.upload_supporting_document(document)
    except BookkeepingPaperlessError as exc:
        _save_failure(document, str(exc))
        raise
    document.paperless_task_id = str(task_id)
    document.transfer_status = SupportingDocument.TransferStatus.PENDING
    document.transfer_error = ""
    document.save(
        update_fields=(
            "paperless_task_id",
            "transfer_status",
            "transfer_error",
            "updated_at",
        )
    )
    return document


def import_supporting_document(
    uploaded_file,
    *,
    matching_rule: MatchingRule | None = None,
    bank_transaction: BankTransaction | None = None,
) -> SupportingDocumentImportResult:
    _validate_pdf_file(uploaded_file)
    if (matching_rule is None) == (bank_transaction is None):
        raise SupportingDocumentError(
            "Ein Beleg muss genau einer Matching-Regel-Version oder einer Banktransaktion zugeordnet sein."
        )
    original_filename = os.path.basename(str(uploaded_file.name or "beleg.pdf"))[:255]
    try:
        document = SupportingDocument.objects.create(
            matching_rule=matching_rule,
            bank_transaction=bank_transaction,
            original_filename=original_filename,
            temporary_file=uploaded_file,
            transfer_status=SupportingDocument.TransferStatus.PENDING,
        )
    except IntegrityError:
        raise SupportingDocumentError(
            "Der Beleg konnte nicht gespeichert werden. Bitte erneut versuchen."
        ) from None
    try:
        start_supporting_document_upload(document)
    except BookkeepingPaperlessError:
        pass
    return SupportingDocumentImportResult(document=document)


def retry_supporting_document(document: SupportingDocument) -> SupportingDocument:
    if document.transfer_status != SupportingDocument.TransferStatus.FAILED:
        raise SupportingDocumentError(
            "Dieser Beleg kann derzeit nicht erneut übertragen werden."
        )
    try:
        return start_supporting_document_upload(
            document,
            check_existing_reference=True,
        )
    except BookkeepingPaperlessError as exc:
        raise SupportingDocumentError(str(exc)) from None


def refresh_pending_supporting_documents() -> None:
    for document in SupportingDocument.objects.filter(
        transfer_status=SupportingDocument.TransferStatus.PENDING,
    ).exclude(paperless_task_id=""):
        try:
            result = PaperlessClient.task_status(document.paperless_task_id)
            if result["status"] == "needs_fallback":
                result = PaperlessClient.find_document_by_reference(
                    str(document.reference_uuid)
                )
        except BookkeepingPaperlessError as exc:
            _save_failure(document, str(exc))
            continue
        if result["status"] == "pending":
            continue
        if result["status"] == "completed" and result.get("document_id"):
            _complete(document, int(result["document_id"]))
            continue
        _save_failure(
            document,
            str(result.get("message") or "Paperless meldet einen Fehler beim Upload."),
        )


def remove_supporting_document(document: SupportingDocument) -> None:
    _remove_temporary_file(document)
    document.delete()


def delete_supporting_document_from_paperless(document: SupportingDocument) -> None:
    if document.paperless_document_id:
        PaperlessClient.delete_document(document.paperless_document_id)
    remove_supporting_document(document)


def display_supporting_document(document: SupportingDocument) -> dict[str, object]:
    status_labels = dict(SupportingDocument.TransferStatus.choices)
    owner = document.matching_rule or document.bank_transaction
    if document.matching_rule_id:
        owner_label = (
            f"Matching-Nachweis {document.matching_rule.name} "
            f"– Version {document.matching_rule.version_number}"
        )
    else:
        if document.bank_transaction is None:
            owner_label = "Banktransaktion"
        else:
            transaction_date = (
                document.bank_transaction.value_date
                or document.bank_transaction.booking_date
            )
            owner_label = (
                f"Banktransaktion {transaction_date.isoformat()} – "
                f"{document.bank_transaction.partner_name or '–'}"
            )
    return {
        "id": document.pk,
        "reference_uuid": str(document.reference_uuid),
        "original_filename": document.original_filename,
        "created_at": document.created_at,
        "transfer_status": document.transfer_status,
        "transfer_status_label": status_labels.get(
            document.transfer_status,
            document.transfer_status,
        ),
        "transfer_error": document.transfer_error,
        "paperless_document_id": document.paperless_document_id,
        "paperless_document_url": PaperlessClient.document_url(
            document.paperless_document_id
        ),
        "owner_label": owner_label,
        "can_retry": document.transfer_status == SupportingDocument.TransferStatus.FAILED,
    }
