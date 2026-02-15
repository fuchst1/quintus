from __future__ import annotations

import csv
import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.text import slugify

from webapp.models import Abrechnungslauf, BetriebskostenBeleg, Datei, DateiZuordnung
from webapp.services.annual_statement_pdf_service import (
    AnnualStatementPdfGenerationError,
    AnnualStatementPdfService,
)
from webapp.services.annual_statement_run_service import AnnualStatementRunService
from webapp.services.annual_statement_storage_service import AnnualStatementStorageService
from webapp.services.files import ALLOWED_MIME_BY_EXTENSION


@dataclass(frozen=True)
class PortalAttachment:
    file_name: str
    content: bytes


class AnnualStatementPortalExportService:
    def __init__(self, *, run: Abrechnungslauf):
        self.run = run
        self.run_service = AnnualStatementRunService(run=run)
        self.period_start = self.run_service.period_start
        self.period_end = self.run_service.period_end

    def build_zip_filename(self) -> str:
        property_slug = slugify(self.run.liegenschaft.name) or f"liegenschaft-{self.run.liegenschaft_id}"
        return f"BK-Portal_{property_slug}_{self.run.jahr}.zip"

    def build_zip(
        self,
        *,
        base_url_override: str | None = None,
    ) -> tuple[bytes, dict[str, int]]:
        letters = self._ensure_letters_with_pdfs()
        if not letters:
            raise RuntimeError("Für diesen Lauf sind keine abrechenbaren Einheiten vorhanden.")

        attachments = self._collect_relevant_attachments()
        attachment_payloads = [
            PortalAttachment(file_name=self._safe_attachment_name(datei), content=self._read_file_bytes(datei))
            for datei in attachments
        ]

        manifest_rows: list[dict[str, str]] = []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("index.html", self._root_index_html())
            archive.writestr("robots.txt", "User-agent: *\nDisallow: /\n")
            archive.writestr("README_DEPLOY.txt", self._deploy_readme())

            for letter in letters:
                token = self.run_service.build_portal_token(letter=letter)
                rel_path = self.run_service.build_portal_relative_path(letter=letter).rstrip("/")
                portal_url = self.run_service.build_portal_url(
                    letter=letter,
                    base_url_override=base_url_override,
                )
                tenant_label = AnnualStatementRunService._tenant_names(letter)
                unit_label = self.run_service._unit_label(letter=letter)

                archive.writestr(
                    f"{rel_path}/index.html",
                    self._tenant_index_html(
                        tenant_label=tenant_label,
                        unit_label=unit_label,
                        portal_url=portal_url,
                        attachment_payloads=attachment_payloads,
                    ),
                )
                archive.writestr(f"{rel_path}/abrechnung.pdf", self._read_file_bytes(letter.pdf_datei))

                for item in attachment_payloads:
                    archive.writestr(f"{rel_path}/belege/{item.file_name}", item.content)

                manifest_rows.append(
                    {
                        "token": token,
                        "portal_url": portal_url,
                        "lauf_id": str(self.run.pk),
                        "jahr": str(self.run.jahr),
                        "liegenschaft": self.run.liegenschaft.name,
                        "mietvertrag_id": str(letter.mietervertrag_id),
                        "einheit": unit_label,
                        "mieter": tenant_label,
                        "beleg_count": str(len(attachment_payloads)),
                    }
                )

            archive.writestr("manifest.csv", self._manifest_csv(manifest_rows))

        summary = {
            "tenant_count": len(letters),
            "attachment_count": len(attachment_payloads),
            "copied_attachment_files": len(letters) * len(attachment_payloads),
        }
        return buffer.getvalue(), summary

    def _ensure_letters_with_pdfs(self):
        self.run_service.ensure_letters()
        letters = list(
            self.run.schreiben.select_related("mietervertrag", "einheit", "pdf_datei")
            .prefetch_related("mietervertrag__tenants")
            .order_by("einheit__door_number", "einheit__name", "mietervertrag_id")
        )
        sequence_numbers = self.run_service._sequence_numbers_for_letters(letters=letters)

        for letter in letters:
            sequence_number = sequence_numbers.get(letter.id)
            if sequence_number and letter.laufende_nummer != sequence_number:
                letter.laufende_nummer = sequence_number
                letter.save(update_fields=["laufende_nummer", "updated_at"])

            if letter.pdf_datei_id is not None:
                continue

            payload = self.run_service.payload_for_letter(letter=letter, sequence_number=sequence_number)
            filename = self.run_service.build_letter_filename(letter=letter, sequence_number=sequence_number)
            try:
                pdf_bytes = AnnualStatementPdfService.generate_letter_pdf(payload=payload)
            except AnnualStatementPdfGenerationError as exc:
                unit_label = payload.get("unit_label", "—")
                document_number = payload.get("document_number_display", "—")
                raise RuntimeError(
                    f"PDF-Erstellung fehlgeschlagen für Einheit {unit_label} (Nr. {document_number}): {exc}"
                ) from exc
            stored_file = AnnualStatementStorageService.persist_letter_pdf(
                letter=letter,
                filename=filename,
                pdf_bytes=pdf_bytes,
            )
            letter.pdf_datei = stored_file

        return letters

    def _collect_relevant_attachments(self) -> list[Datei]:
        beleg_ids = list(
            BetriebskostenBeleg.objects.filter(
                liegenschaft=self.run.liegenschaft,
                datum__gte=self.period_start,
                datum__lte=self.period_end,
            ).values_list("id", flat=True)
        )
        if not beleg_ids:
            return []

        beleg_content_type = ContentType.objects.get_for_model(BetriebskostenBeleg)
        assignments = (
            DateiZuordnung.objects.filter(
                content_type=beleg_content_type,
                object_id__in=beleg_ids,
                datei__is_archived=False,
            )
            .select_related("datei")
            .order_by("-datei__created_at", "-id")
        )

        result: list[Datei] = []
        seen_ids: set[int] = set()
        for assignment in assignments:
            datei = assignment.datei
            if datei is None or datei.pk in seen_ids:
                continue
            if not self._is_allowed_attachment(datei):
                continue
            seen_ids.add(datei.pk)
            result.append(datei)
        return result

    @staticmethod
    def _is_allowed_attachment(datei: Datei) -> bool:
        original_name = datei.original_name or os.path.basename(datei.file.name or "")
        extension = Path(original_name).suffix.lower()
        allowed_mimes = ALLOWED_MIME_BY_EXTENSION.get(extension)
        if not allowed_mimes:
            return False
        mime_type = (datei.mime_type or "").strip().lower()
        if not mime_type:
            return True
        return mime_type in allowed_mimes

    @staticmethod
    def _safe_attachment_name(datei: Datei) -> str:
        original_name = datei.original_name or os.path.basename(datei.file.name or "")
        extension = Path(original_name).suffix.lower()
        if extension not in ALLOWED_MIME_BY_EXTENSION:
            extension = ".pdf"
        base_name = slugify(Path(original_name).stem) or f"beleg-{datei.pk}"
        return f"{base_name}-{datei.pk}{extension}"

    @staticmethod
    def _read_file_bytes(datei: Datei) -> bytes:
        try:
            with datei.file.open("rb") as stream:
                return stream.read()
        except OSError as exc:
            readable_name = datei.original_name or os.path.basename(datei.file.name or "") or f"Datei #{datei.pk}"
            raise RuntimeError(f"Datei kann nicht gelesen werden: {readable_name}") from exc

    @staticmethod
    def _root_index_html() -> str:
        return """<!doctype html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Belegportal</title>
  <meta name=\"robots\" content=\"noindex,nofollow\">
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }
    .box { max-width: 760px; border: 1px solid #d1d5db; border-radius: 10px; padding: 1rem 1.25rem; }
  </style>
</head>
<body>
  <div class=\"box\">
    <h1>Belegportal</h1>
    <p>Diese Seite enthält keine öffentliche Übersicht. Bitte verwenden Sie den persönlichen Link oder den QR-Code aus Ihrer Abrechnung.</p>
  </div>
</body>
</html>
"""

    @staticmethod
    def _tenant_index_html(
        *,
        tenant_label: str,
        unit_label: str,
        portal_url: str,
        attachment_payloads: list[PortalAttachment],
    ) -> str:
        beleg_links = "".join(
            f'<li><a href="belege/{item.file_name}" target="_blank" rel="noopener">{item.file_name}</a></li>'
            for item in attachment_payloads
        )
        if not beleg_links:
            beleg_links = "<li>Keine Belege im Export enthalten.</li>"

        url_hint = (
            f"<p><small>Portal-Link: <a href=\"{portal_url}\">{portal_url}</a></small></p>"
            if portal_url
            else ""
        )

        today_display = timezone.localdate().strftime("%d.%m.%Y")
        return f"""<!doctype html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Betriebskostenbelege</title>
  <meta name=\"robots\" content=\"noindex,nofollow\">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #111827; }}
    .wrap {{ max-width: 860px; margin: 0 auto; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .meta {{ color: #4b5563; margin-bottom: 1rem; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1rem; }}
    .btn {{ display: inline-block; padding: 0.5rem 0.9rem; border: 1px solid #1d4ed8; border-radius: 6px; color: #1d4ed8; text-decoration: none; }}
    ul {{ margin-top: 0.75rem; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Betriebskostenbelege</h1>
    <div class=\"meta\">Einheit: {unit_label} · Mieter: {tenant_label} · Stand: {today_display}</div>

    <div class=\"card\">
      <h2>Ihre Abrechnung</h2>
      <p><a class=\"btn\" href=\"abrechnung.pdf\" target=\"_blank\" rel=\"noopener\">Abrechnung öffnen</a></p>
      {url_hint}
    </div>

    <div class=\"card\">
      <h2>Belege</h2>
      <ul>{beleg_links}</ul>
    </div>
  </div>
</body>
</html>
"""

    @staticmethod
    def _manifest_csv(rows: list[dict[str, str]]) -> str:
        output = io.StringIO()
        fieldnames = [
            "token",
            "portal_url",
            "lauf_id",
            "jahr",
            "liegenschaft",
            "mietvertrag_id",
            "einheit",
            "mieter",
            "beleg_count",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return output.getvalue()

    @staticmethod
    def _deploy_readme() -> str:
        return (
            "BK-Portal Export\n"
            "================\n\n"
            "Sicherheitshinweise:\n"
            "- Verzeichnislisting am Webserver deaktivieren.\n"
            "- Suchmaschinenindexierung deaktivieren (robots + Server-Header).\n"
            "- Token-URLs als geheim behandeln und nicht öffentlich veröffentlichen.\n"
            "- Bei Verdacht auf Leak: neuen Export erzeugen und alte Dateien entfernen.\n"
        )
