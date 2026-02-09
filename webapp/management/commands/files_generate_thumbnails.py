import json
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q

from webapp.models import Datei
from webapp.storage_paths import build_deterministic_derived_upload_path


class Command(BaseCommand):
    help = (
        "Erzeugt Vorschaubilder für Bild-Dateien in uploads/_derived. "
        "Idempotent und sicher für Cron-Wiederholungen."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Erzeugt Vorschaubilder neu, auch wenn sie bereits existieren.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optionales Limit der zu verarbeitenden Dateien (0 = kein Limit).",
        )
        parser.add_argument(
            "--size",
            type=int,
            default=480,
            help="Maximale Kantenlänge des Vorschaubilds in Pixel (Default: 480).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Ausgabe als JSON.",
        )

    def handle(self, *args, **options):
        force = bool(options["force"])
        limit = int(options["limit"] or 0)
        size = max(int(options["size"]), 64)

        try:
            from PIL import Image
        except ImportError:
            message = {
                "status": "skipped",
                "reason": "Pillow ist nicht installiert. Thumbnails wurden nicht erzeugt.",
            }
            if options["json"]:
                self.stdout.write(json.dumps(message, ensure_ascii=False, indent=2))
            else:
                self.stdout.write(self.style.WARNING(message["reason"]))
            return

        queryset = (
            Datei.objects.filter(is_archived=False)
            .filter(
                Q(mime_type__startswith="image/")
                | Q(kategorie__in=[Datei.Kategorie.BILD, Datei.Kategorie.ZAEHLERFOTO])
            )
            .exclude(file="")
            .order_by("id")
        )
        if limit > 0:
            queryset = queryset[:limit]

        created = 0
        skipped_existing = 0
        skipped_missing = 0
        failed = 0

        for datei in queryset:
            source_path = (datei.file.name or "").strip()
            if not source_path or not datei.file.storage.exists(source_path):
                skipped_missing += 1
                continue

            target_path = build_deterministic_derived_upload_path(
                source_path,
                "thumb",
                extension=".jpg",
            )
            if not force and datei.file.storage.exists(target_path):
                skipped_existing += 1
                continue

            try:
                with datei.file.storage.open(source_path, "rb") as source_stream:
                    image = Image.open(source_stream)
                    image = image.convert("RGB")
                    image.thumbnail((size, size))

                    buffer = BytesIO()
                    image.save(buffer, format="JPEG", quality=85, optimize=True)
                    buffer.seek(0)

                    datei.file.storage.save(
                        target_path,
                        ContentFile(buffer.read()),
                    )
                    created += 1
            except Exception:
                failed += 1

        summary = {
            "status": "ok",
            "created": created,
            "skipped_existing": skipped_existing,
            "skipped_missing_source": skipped_missing,
            "failed": failed,
            "size": size,
            "force": force,
        }

        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write(
            self.style.NOTICE(
                "Thumbnail-Generierung abgeschlossen: "
                f"{created} erstellt, {skipped_existing} übersprungen (existiert), "
                f"{skipped_missing} ohne Quelldatei, {failed} Fehler."
            )
        )
