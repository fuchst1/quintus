import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from webapp.models import Datei, DateiOperationLog, DateiZuordnung
from webapp.services.files import DateiService


class Command(BaseCommand):
    help = (
        "Findet verwaiste Dateien (ohne aktive Zuordnung) und archiviert sie optional "
        "idempotent für sichere Cron-Läufe."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archive",
            action="store_true",
            help="Archiviert gefundene Orphans. Ohne Flag nur Analyse (Dry-Run).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Ausgabe als JSON.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximale Anzahl Detaileinträge (Default: 200).",
        )

    def handle(self, *args, **options):
        archive_mode = bool(options["archive"])
        limit = max(int(options["limit"]), 1)

        active_datei_ids = set()
        assignments = DateiZuordnung.objects.select_related("content_type").order_by("id")
        for zuordnung in assignments.iterator():
            if zuordnung.content_object is None:
                continue
            active_datei_ids.add(zuordnung.datei_id)

        orphan_qs = (
            Datei.objects.filter(is_archived=False)
            .exclude(id__in=active_datei_ids)
            .order_by("id")
        )
        orphan_ids = list(orphan_qs.values_list("id", flat=True))

        archived_ids = []
        if archive_mode:
            now = timezone.now()
            for datei in orphan_qs:
                if datei.is_archived:
                    continue
                datei.is_archived = True
                datei.archived_at = now
                datei.archived_by = None
                datei.save(update_fields=["is_archived", "archived_at", "archived_by"])
                DateiService.log_operation(
                    operation=DateiOperationLog.Operation.DELETE,
                    actor=None,
                    datei=datei,
                    success=True,
                    detail="Archiviert durch files_cleanup_orphans.",
                )
                archived_ids.append(datei.pk)

        details = list(
            Datei.objects.filter(id__in=orphan_ids)
            .order_by("id")
            .values("id", "original_name", "file", "is_archived")[:limit]
        )

        summary = {
            "mode": "archive" if archive_mode else "dry-run",
            "orphans_count": len(orphan_ids),
            "archived_count": len(archived_ids),
            "orphans": details,
        }

        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        if archive_mode:
            self.stdout.write(
                self.style.NOTICE(
                    f"Orphan-Cleanup: {len(orphan_ids)} gefunden, {len(archived_ids)} archiviert."
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"Orphan-Cleanup Dry-Run: {len(orphan_ids)} verwaiste Dateien gefunden."
                )
            )
            self.stdout.write("Mit --archive werden diese Dateien archiviert.")

        for item in details:
            self.stdout.write(
                f"  - Datei #{item['id']} ({item['original_name'] or item['file']}) "
                f"{'[archiviert]' if item['is_archived'] else ''}"
            )
