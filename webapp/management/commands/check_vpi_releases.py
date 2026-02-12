from __future__ import annotations

from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from webapp.models import VpiIndexValue
from webapp.services.vpi_adjustment_run_service import VpiAdjustmentRunService


class Command(BaseCommand):
    help = "Prüft freigegebene VPI-Indexwerte ohne Lauf und kann Draft-Läufe idempotent anlegen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-runs",
            action="store_true",
            help="Erzeugt für freigegebene Werte ohne Lauf automatisch einen Draft-Lauf.",
        )
        parser.add_argument(
            "--today",
            type=str,
            help="Bezugsdatum im Format YYYY-MM-DD (optional, für Tests).",
        )

    def handle(self, *args, **options):
        today = self._parse_today(options.get("today"))
        create_runs = bool(options.get("create_runs"))

        released_values = VpiIndexValue.objects.filter(is_released=True).order_by("month")
        pending_before = list(released_values.filter(adjustment_runs__isnull=True))

        created_runs = 0
        letters_prepared = 0
        if create_runs:
            for index_value in pending_before:
                run = VpiAdjustmentRunService.ensure_run(index_value=index_value, run_date=today)
                letters = VpiAdjustmentRunService(run=run).ensure_letters()
                created_runs += 1
                letters_prepared += len(letters)

        pending_after = list(released_values.filter(adjustment_runs__isnull=True))

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"VPI-Check abgeschlossen. Datum: {today.isoformat()}, "
                    f"freigegeben: {released_values.count()}, "
                    f"ohne Lauf: {len(pending_after)}, "
                    f"Läufe erstellt: {created_runs}, "
                    f"Zeilen vorbereitet: {letters_prepared}."
                )
            )
        )

        if pending_after:
            for index_value in pending_after:
                self.stdout.write(
                    f"- Offen: {index_value.month:%m/%Y} (Index {index_value.index_value})"
                )

    @staticmethod
    def _parse_today(value: str | None) -> date:
        if not value:
            return timezone.localdate()
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise CommandError("Ungültiges Datum. Erwartet: YYYY-MM-DD") from exc
