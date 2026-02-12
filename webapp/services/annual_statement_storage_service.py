from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone

from webapp.models import Abrechnungsschreiben, Datei, DateiZuordnung
from webapp.services.files import DateiService


class AnnualStatementStorageService:
    @staticmethod
    def _archive_existing_pdf(letter: Abrechnungsschreiben) -> None:
        existing = letter.pdf_datei
        if existing is None:
            return
        letter.pdf_datei = None
        letter.generated_at = None
        letter.save(update_fields=["pdf_datei", "generated_at", "updated_at"])
        if not existing.is_archived:
            DateiService.archive(user=None, datei=existing)

    @classmethod
    def persist_letter_pdf(
        cls,
        *,
        letter: Abrechnungsschreiben,
        filename: str,
        pdf_bytes: bytes,
    ) -> Datei:
        cls._archive_existing_pdf(letter)

        file_obj = ContentFile(pdf_bytes, name=filename)
        datei = Datei(
            file=file_obj,
            original_name=filename,
            kategorie=Datei.Kategorie.DOKUMENT,
            beschreibung=f"BK-Abrechnung {letter.lauf.jahr}",
            uploaded_by=None,
        )
        datei.set_upload_context(content_object=letter.mietervertrag)
        datei.full_clean()
        datei.save()

        DateiZuordnung.objects.create(
            datei=datei,
            content_type=ContentType.objects.get_for_model(letter.mietervertrag),
            object_id=letter.mietervertrag_id,
            created_by=None,
        )

        letter.pdf_datei = datei
        letter.generated_at = timezone.now()
        letter.save(update_fields=["pdf_datei", "generated_at", "updated_at"])
        return datei
