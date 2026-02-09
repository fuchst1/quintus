import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from webapp.models import Datei, DateiZuordnung


class Command(BaseCommand):
    help = "Prüft Dateien auf fehlende Binaries, hängende Zuordnungen und Checksum-Duplikate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Ausgabe als JSON.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximale Anzahl Detaileinträge pro Kategorie (Default: 200).",
        )

    def handle(self, *args, **options):
        limit = max(int(options["limit"]), 1)

        missing_files = self._collect_missing_files(limit=limit)
        dangling_assignments = self._collect_dangling_assignments(limit=limit)
        duplicate_groups = self._collect_checksum_duplicates(limit=limit)

        summary = {
            "missing_files_count": missing_files["count"],
            "dangling_assignments_count": dangling_assignments["count"],
            "duplicate_checksum_groups_count": duplicate_groups["count"],
            "duplicate_files_count": duplicate_groups["files_count"],
            "missing_files": missing_files["items"],
            "dangling_assignments": dangling_assignments["items"],
            "duplicate_checksum_groups": duplicate_groups["groups"],
        }

        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write(
            self.style.NOTICE(
                "Datei-Audit abgeschlossen: "
                f"{summary['missing_files_count']} fehlende Dateien, "
                f"{summary['dangling_assignments_count']} hängende Zuordnungen, "
                f"{summary['duplicate_checksum_groups_count']} Duplikatgruppen."
            )
        )

        if summary["missing_files"]:
            self.stdout.write(self.style.WARNING("Fehlende Binaries:"))
            for item in summary["missing_files"]:
                self.stdout.write(
                    f"  - Datei #{item['datei_id']} ({item['name']}) -> {item['path']}"
                )

        if summary["dangling_assignments"]:
            self.stdout.write(self.style.WARNING("Hängende Datei-Zuordnungen:"))
            for item in summary["dangling_assignments"]:
                self.stdout.write(
                    f"  - Zuordnung #{item['zuordnung_id']} zu Datei #{item['datei_id']} "
                    f"({item['content_type']}#{item['object_id']})"
                )

        if summary["duplicate_checksum_groups"]:
            self.stdout.write(self.style.WARNING("Checksum-Duplikatgruppen:"))
            for item in summary["duplicate_checksum_groups"]:
                self.stdout.write(
                    f"  - SHA256 {item['checksum']} -> Datei-IDs {item['datei_ids']}"
                )

    @staticmethod
    def _collect_missing_files(*, limit: int):
        count = 0
        items = []
        queryset = Datei.objects.exclude(file="").only("id", "file", "original_name")
        for datei in queryset.iterator():
            file_name = (datei.file.name or "").strip()
            if not file_name:
                count += 1
                if len(items) < limit:
                    items.append(
                        {
                            "datei_id": datei.pk,
                            "name": datei.original_name or "",
                            "path": "",
                        }
                    )
                continue
            if datei.file.storage.exists(file_name):
                continue
            count += 1
            if len(items) < limit:
                items.append(
                    {
                        "datei_id": datei.pk,
                        "name": datei.original_name or "",
                        "path": file_name,
                    }
                )
        return {"count": count, "items": items}

    @staticmethod
    def _collect_dangling_assignments(*, limit: int):
        count = 0
        items = []
        queryset = DateiZuordnung.objects.select_related("content_type", "datei").order_by("id")
        for zuordnung in queryset.iterator():
            if zuordnung.content_object is not None:
                continue
            count += 1
            if len(items) < limit:
                items.append(
                    {
                        "zuordnung_id": zuordnung.pk,
                        "datei_id": zuordnung.datei_id,
                        "content_type": zuordnung.content_type.model,
                        "object_id": zuordnung.object_id,
                    }
                )
        return {"count": count, "items": items}

    @staticmethod
    def _collect_checksum_duplicates(*, limit: int):
        groups = []
        files_count = 0
        duplicate_qs = (
            Datei.objects.exclude(checksum_sha256="")
            .values("checksum_sha256")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .order_by("-total", "checksum_sha256")
        )
        count = duplicate_qs.count()
        for group in duplicate_qs[:limit]:
            ids = list(
                Datei.objects.filter(checksum_sha256=group["checksum_sha256"])
                .order_by("id")
                .values_list("id", flat=True)
            )
            files_count += len(ids)
            groups.append(
                {
                    "checksum": group["checksum_sha256"],
                    "datei_ids": ids,
                }
            )
        return {"count": count, "groups": groups, "files_count": files_count}
