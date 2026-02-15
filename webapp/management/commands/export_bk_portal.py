from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from webapp.models import Abrechnungslauf
from webapp.services.annual_statement_portal_export_service import AnnualStatementPortalExportService


class Command(BaseCommand):
    help = "Erstellt ein statisches BK-Mieterportal als ZIP für einen BK-Lauf."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, help="ID des Abrechnungslaufs")
        parser.add_argument("--liegenschaft-id", type=int, help="Alternative Auswahl über Liegenschaft-ID")
        parser.add_argument("--jahr", type=int, help="Alternative Auswahl über Jahr")
        parser.add_argument("--output", type=str, help="Zielpfad für die ZIP-Datei")
        parser.add_argument("--base-url", type=str, help="Optionale Basis-URL für Portal-Links")

    def handle(self, *args, **options):
        run = self._resolve_run(options)
        service = AnnualStatementPortalExportService(run=run)
        base_url_override = (options.get("base_url") or "").strip() or None

        try:
            zip_bytes, summary = service.build_zip(base_url_override=base_url_override)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        output_path = self._resolve_output_path(service=service, output=options.get("output"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(zip_bytes)

        self.stdout.write(self.style.SUCCESS(f"Portal-Export erstellt: {output_path}"))
        self.stdout.write(
            f"Mieterseiten: {summary.get('tenant_count', 0)} | "
            f"Belege pro Seite: {summary.get('attachment_count', 0)} | "
            f"Kopierte Belegdateien gesamt: {summary.get('copied_attachment_files', 0)}"
        )

    @staticmethod
    def _resolve_output_path(*, service: AnnualStatementPortalExportService, output: str | None) -> Path:
        raw_path = (output or "").strip()
        if not raw_path:
            raw_path = service.build_zip_filename()
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    @staticmethod
    def _resolve_run(options) -> Abrechnungslauf:
        run_id = options.get("run_id")
        property_id = options.get("liegenschaft_id")
        year = options.get("jahr")

        if run_id:
            run = (
                Abrechnungslauf.objects.select_related("liegenschaft")
                .filter(pk=int(run_id))
                .first()
            )
            if run is None:
                raise CommandError(f"Abrechnungslauf mit ID {run_id} wurde nicht gefunden.")
            return run

        if not property_id or not year:
            raise CommandError("Bitte --run-id oder alternativ --liegenschaft-id und --jahr angeben.")

        run = (
            Abrechnungslauf.objects.select_related("liegenschaft")
            .filter(liegenschaft_id=int(property_id), jahr=int(year))
            .first()
        )
        if run is None:
            raise CommandError(
                f"Kein Abrechnungslauf für Liegenschaft {property_id} und Jahr {year} gefunden."
            )
        return run
