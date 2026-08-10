"""Import already stored Paperless invoices into the manual-invoice workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction

from .invoice_ai import OCR_UNAVAILABLE_MESSAGE, run_manual_invoice_analysis
from .models import ManualInvoice
from .paperless import BookkeepingPaperlessError, PaperlessClient


DEFAULT_IMPORT_LIMIT = 25
MAX_ERROR_LENGTH = 240


class PaperlessInvoiceImportError(ValueError):
    """Expected, safe error for the Paperless invoice import."""


@dataclass
class PaperlessInvoiceImportSummary:
    matched_count: int = 0
    processed_count: int = 0
    new_count: int = 0
    existing_count: int = 0
    ocr_unavailable_count: int = 0
    ai_suggestion_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    waiting_count: int = 0
    document_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def imported_count(self) -> int:
        return self.new_count

    def add_error(self, document_id: int | None, message: str) -> None:
        self.error_count += 1
        safe_message = " ".join(str(message or "").split())[:MAX_ERROR_LENGTH]
        if document_id is not None:
            self.errors.append(f"Dokument {document_id}: {safe_message}")
        else:
            self.errors.append(safe_message)


class PaperlessInvoiceImportService:
    def run(
        self,
        *,
        limit: int = DEFAULT_IMPORT_LIMIT,
        dry_run: bool = False,
    ) -> PaperlessInvoiceImportSummary:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise PaperlessInvoiceImportError(
                "Das Batch-Limit muss eine positive Zahl sein."
            ) from None
        if limit <= 0:
            raise PaperlessInvoiceImportError(
                "Das Batch-Limit muss eine positive Zahl sein."
            )

        master_data = PaperlessClient.paperless_invoice_import_master_data()
        import_tag_ids = master_data.get("import_tag_ids") or (
            master_data["import_tag_id"],
        )
        documents = PaperlessClient.documents_by_tag_id(import_tag_ids)
        summary = PaperlessInvoiceImportSummary(
            matched_count=len(documents),
            document_ids=[
                document_id
                for document_id in (
                    _document_id(document) for document in documents
                )
                if document_id is not None
            ],
            dry_run=dry_run,
        )
        batch = documents[:limit]
        summary.waiting_count = max(0, len(documents) - len(batch))
        if dry_run:
            self._classify_dry_run(
                batch,
                summary,
            )
            summary.skipped_count = summary.waiting_count
            return summary

        for document in batch:
            document_id = _document_id(document)
            summary.processed_count += 1
            try:
                self._process_document(
                    document,
                    document_id=document_id,
                    master_data=master_data,
                    summary=summary,
                )
            except (PaperlessInvoiceImportError, BookkeepingPaperlessError) as exc:
                summary.add_error(document_id, str(exc))
                if document_id is not None:
                    self._mark_error_without_replacing_other_tags(
                        document_id,
                        master_data,
                        summary,
                    )
            except Exception:
                summary.add_error(
                    document_id,
                    "Der Beleg konnte nicht übernommen werden.",
                )
                if document_id is not None:
                    self._mark_error_without_replacing_other_tags(
                        document_id,
                        master_data,
                        summary,
                    )
        return summary

    def _process_document(
        self,
        document: dict,
        *,
        document_id: int | None,
        master_data: dict[str, int],
        summary: PaperlessInvoiceImportSummary,
    ) -> None:
        if document_id is None:
            raise PaperlessInvoiceImportError(
                "Paperless-Dokument enthält keine gültige Dokument-ID."
            )

        invoice, created = self._get_or_create_invoice(
            document,
            document_id=document_id,
        )
        if created:
            summary.new_count += 1
        else:
            summary.existing_count += 1
            self._repair_local_paperless_state(invoice)

        try:
            PaperlessClient.update_invoice_import_markers(
                document_id,
                reference_uuid=str(invoice.reference_uuid),
                **master_data,
            )
        except (PaperlessInvoiceImportError, BookkeepingPaperlessError) as exc:
            summary.add_error(document_id, f"Paperless-Markierung: {exc}")

        try:
            outcome = run_manual_invoice_analysis(
                invoice,
                force=invoice.ai_error == OCR_UNAVAILABLE_MESSAGE,
            )
        except Exception:
            summary.add_error(
                document_id,
                "Die OCR-/KI-Verarbeitung konnte nicht durchgeführt werden.",
            )
            return
        if outcome.kind == "ocr_unavailable":
            summary.ocr_unavailable_count += 1
        elif outcome.kind == "completed":
            summary.ai_suggestion_count += 1
        elif outcome.kind == "failed":
            summary.add_error(document_id, outcome.message or "KI-Analyse fehlgeschlagen.")

    @staticmethod
    def _classify_dry_run(
        documents: list[dict],
        summary: PaperlessInvoiceImportSummary,
    ) -> None:
        for document in documents:
            document_id = _document_id(document)
            if document_id is None:
                summary.add_error(
                    None,
                    "Paperless-Dokument enthält keine gültige Dokument-ID.",
                )
            elif ManualInvoice.objects.filter(
                paperless_document_id=document_id,
            ).exists():
                summary.existing_count += 1
            else:
                summary.new_count += 1

    @staticmethod
    def _repair_local_paperless_state(invoice: ManualInvoice) -> None:
        if invoice.paperless_deleted_at is not None:
            return
        update_fields = []
        if invoice.paperless_status != ManualInvoice.PaperlessStatus.COMPLETED:
            invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
            update_fields.append("paperless_status")
        if invoice.paperless_task_id:
            invoice.paperless_task_id = ""
            update_fields.append("paperless_task_id")
        if invoice.paperless_error:
            invoice.paperless_error = ""
            update_fields.append("paperless_error")
        if update_fields:
            update_fields.append("updated_at")
            invoice.save(update_fields=tuple(update_fields))

    @staticmethod
    def _get_or_create_invoice(
        document: dict,
        *,
        document_id: int,
    ) -> tuple[ManualInvoice, bool]:
        defaults = {
            "file_hash": _paperless_file_hash(document_id),
            "status": ManualInvoice.Status.DRAFT,
            "paperless_task_id": "",
            "paperless_status": ManualInvoice.PaperlessStatus.COMPLETED,
            "paperless_error": "",
            "temporary_pdf": None,
            "notes": _paperless_source_note(document),
        }
        try:
            with transaction.atomic():
                return ManualInvoice.objects.get_or_create(
                    paperless_document_id=document_id,
                    defaults=defaults,
                )
        except IntegrityError:
            try:
                return (
                    ManualInvoice.objects.get(paperless_document_id=document_id),
                    False,
                )
            except ManualInvoice.DoesNotExist:
                raise PaperlessInvoiceImportError(
                    "Der lokale ManualInvoice konnte nicht sicher angelegt werden."
                ) from None

    @staticmethod
    def _mark_error_without_replacing_other_tags(
        document_id: int,
        master_data: dict[str, int],
        summary: PaperlessInvoiceImportSummary,
    ) -> None:
        try:
            PaperlessClient.update_invoice_import_error_tag(
                document_id,
                import_tag_id=master_data["import_tag_id"],
                imported_tag_id=master_data["imported_tag_id"],
                error_tag_id=master_data["error_tag_id"],
                import_tag_ids=master_data.get("import_tag_ids"),
            )
        except BookkeepingPaperlessError as exc:
            summary.add_error(document_id, f"Fehler-Tag: {exc}")


def import_paperless_invoices(
    *,
    limit: int = DEFAULT_IMPORT_LIMIT,
    dry_run: bool = False,
) -> PaperlessInvoiceImportSummary:
    return PaperlessInvoiceImportService().run(
        limit=limit,
        dry_run=dry_run,
    )


def _document_id(document: dict) -> int | None:
    if not isinstance(document, dict):
        return None
    try:
        document_id = int(document.get("id"))
    except (TypeError, ValueError):
        return None
    return document_id if document_id > 0 else None


def _paperless_file_hash(document_id: int) -> str:
    return hashlib.sha256(
        f"paperless-document:{document_id}".encode("ascii")
    ).hexdigest()


def _paperless_source_note(document: dict) -> str:
    title = " ".join(str(document.get("title") or "").split())
    original_name = " ".join(
        str(document.get("original_file_name") or "").split()
    )
    parts = []
    if title:
        parts.append(f"Paperless-Titel: {title}")
    if original_name and original_name != title:
        parts.append(f"Paperless-Dateiname: {original_name}")
    return "\n".join(parts)[:500]
