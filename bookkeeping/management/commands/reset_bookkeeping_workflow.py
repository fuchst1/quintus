"""Management command for a guarded, derived-data-only workflow reset."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from django.core.management import BaseCommand, CommandError
from django.db import connections

from bookkeeping.workflow_reset import (
    build_reset_selection,
    collect_reset_report,
    database_path,
    execute_workflow_reset,
)


CONFIRM_TOKEN = "RESET-BOOKKEEPING-WORKFLOW"
FINALIZED_CONFIRM_TOKEN = "DELETE-DERIVED-FINALIZED-BOOKINGS"


class Command(BaseCommand):
    help = "Setzt ausschließlich abgeleitete Bookkeeping-Buchungsdaten zurück."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur prüfen und anzeigen (Standard).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Reset tatsächlich ausführen; erfordert Bestätigung und Backup.",
        )
        parser.add_argument(
            "--confirm",
            default="",
            help=f"Exaktes Bestätigungstoken: {CONFIRM_TOKEN}",
        )
        parser.add_argument(
            "--include-finalized",
            action="store_true",
            help="Gebuchte/exportierte Vorgänge ausdrücklich einschließen.",
        )
        parser.add_argument(
            "--confirm-finalized",
            default="",
            help=f"Exaktes zweites Token: {FINALIZED_CONFIRM_TOKEN}",
        )
        parser.add_argument(
            "--backup-path",
            default="",
            help="Absoluter, noch nicht vorhandener SQLite-Backup-Pfad.",
        )

    def handle(self, *args, **options):
        if options["execute"] and options["dry_run"]:
            raise CommandError("--execute und --dry-run dürfen nicht gemeinsam verwendet werden.")

        using = "default"
        selection = build_reset_selection(using=using)
        report = collect_reset_report(selection, using=using)
        database = database_path(using=using)
        if database is None:
            if options["execute"]:
                raise CommandError(
                    "Die aktive Datenbank ist keine dateibasierte SQLite-Datenbank. "
                    "Für die echte Ausführung ist eine externe, konsistente Sicherung erforderlich."
                )
            self.stdout.write("Aktive Datenbank: nicht dateibasierte SQLite-Datenbank.")
        else:
            self.stdout.write(f"Aktive SQLite-Datenbank: {database}")

        self._write_report(report, dry_run=not options["execute"])
        finalized_count = report.details["booked_count"] + report.details["exported_count"]
        if finalized_count and not options["execute"]:
            self.stdout.write(
                "Hinweis: Gebuchte/exportierte Vorgänge blockieren eine echte Ausführung "
                "ohne --include-finalized und das zweite Bestätigungstoken."
            )

        if not options["execute"]:
            self._write_dry_run_next_steps(database)
            return

        self._validate_execution_options(options, database, finalized_count)
        backup_path = self._validate_backup_path(options["backup_path"], database)
        backup_metadata = self._create_and_verify_backup(database, backup_path)
        try:
            result = execute_workflow_reset(selection, using=using)
        except Exception as exc:
            raise CommandError(
                "Workflow-Reset fehlgeschlagen; die Datenbanktransaktion wurde vollständig "
                "zurückgerollt. Das Backup bleibt erhalten."
            ) from exc

        self.stdout.write(self.style.SUCCESS("Workflow-Reset erfolgreich ausgeführt."))
        self.stdout.write(f"Backup: {backup_metadata['path']}")
        self.stdout.write(f"Backup-Größe: {backup_metadata['size']} Bytes")
        self.stdout.write(f"Backup erstellt: {backup_metadata['created']}")
        self.stdout.write(
            "Zurückgesetzt: "
            f"{result.reset['Banktransaktionen']} Banktransaktion(en), "
            f"{result.reset['manuelle Belege auf Entwurf']} manuelle Belege, "
            f"{result.deleted['BookingEntry'] + result.deleted['ManualInvoiceEntry']} Buchungszeile(n)."
        )
        self.stdout.write(
            "Erhalten: "
            f"{result.kept['Matching-Regeln']} Regeln, "
            f"{result.kept['Paperless-Verknüpfungen']} Paperless-Verknüpfung(en), "
            f"{result.kept['Banktransaktionen']} Quelldatensatz/-sätze."
        )
        self.stdout.write(
            "Post-Reset-Prüfung: Quelldaten, Regelversionen, Paperless-Verknüpfungen, "
            "UUIDs und Ausgangsstatus wurden geprüft."
        )
        self.stdout.write(
            "Keine automatische Weiterverarbeitung: Matching, Buchungserzeugung, "
            "Paperless-Synchronisierung und Export wurden nicht gestartet."
        )

    def _write_report(self, report, *, dry_run):
        title = "DRY-RUN" if dry_run else "Vorschau vor Ausführung"
        self.stdout.write(f"Bookkeeping-Workflow-Reset ({title})")
        self.stdout.write("Behalten:")
        for label, count in report.kept.items():
            self.stdout.write(f"  - {label}: {count}")
        self.stdout.write("Zurücksetzen:")
        for label, count in report.reset.items():
            self.stdout.write(f"  - {label}: {count}")
        self.stdout.write("Aktuelle Statusverteilung Banktransaktionen:")
        for status, count in sorted(report.details["bank_status_counts"].items()):
            self.stdout.write(f"  - {status}: {count}")
        self.stdout.write("Statusverteilung manuelle Belege:")
        for status, count in sorted(
            report.details["manual_invoice_status_counts"].items()
        ):
            self.stdout.write(f"  - {status}: {count}")
        self.stdout.write("Löschen:")
        if report.deleted:
            for model_name, count in report.deleted.items():
                self.stdout.write(
                    f"  - {model_name}: {count} – abgeleitete Buchungsdaten, reproduzierbar."
                )
        else:
            self.stdout.write(
                "  - Keine Modellart im Dry-Run; in der echten Ausführung werden nur "
                "BookingEntry und ManualInvoiceEntry entfernt."
            )
        self.stdout.write("Warnungen:")
        if report.warnings:
            for warning in report.warnings:
                self.stdout.write(f"  - {warning}")
        else:
            self.stdout.write("  - Keine.")

    def _write_dry_run_next_steps(self, database):
        if database is not None:
            self.stdout.write(
                f"Vorgeschlagener Backup-Pfad (nicht erstellt): "
                f"{self._suggest_backup_path(database)}"
            )
        self.stdout.write(
            "Für eine echte Ausführung werden --execute, --confirm und ein neuer "
            "absoluter --backup-path benötigt."
        )

    @staticmethod
    def _suggest_backup_path(database: Path) -> Path:
        candidate = database.with_name(
            f"{database.stem}-before-workflow-reset{database.suffix or '.sqlite3'}"
        )
        counter = 2
        while os.path.lexists(candidate):
            candidate = database.with_name(
                f"{database.stem}-before-workflow-reset-{counter}"
                f"{database.suffix or '.sqlite3'}"
            )
            counter += 1
        return candidate

    @staticmethod
    def _validate_execution_options(options, database, finalized_count):
        if options["confirm"] != CONFIRM_TOKEN:
            raise CommandError(
                f"Echte Ausführung verweigert: --confirm muss exakt {CONFIRM_TOKEN} lauten."
            )
        if not options["backup_path"]:
            raise CommandError("Echte Ausführung erfordert --backup-path.")
        if finalized_count:
            if not options["include_finalized"]:
                raise CommandError(
                    f"{finalized_count} gebuchte/exportierte Vorgänge blockieren den Reset. "
                    "Zusätzlich --include-finalized verwenden."
                )
            if options["confirm_finalized"] != FINALIZED_CONFIRM_TOKEN:
                raise CommandError(
                    "Echte Ausführung gebuchter/exportierter Vorgänge erfordert das exakte "
                    f"Token {FINALIZED_CONFIRM_TOKEN}."
                )
        if database is None:
            raise CommandError("Für die echte Ausführung wird eine dateibasierte SQLite-Datenbank benötigt.")

    @staticmethod
    def _validate_backup_path(raw_path, database):
        raw_text = str(raw_path)
        separators = tuple(separator for separator in (os.sep, os.altsep) if separator)
        if raw_text.endswith(separators):
            raise CommandError("--backup-path muss auf eine konkrete Datei zeigen.")
        path = Path(raw_text).expanduser()
        if not path.is_absolute():
            raise CommandError("--backup-path muss absolut angegeben werden.")
        path = path.resolve(strict=False)
        if path == database:
            raise CommandError("--backup-path darf nicht auf die aktive Datenbank zeigen.")
        if not path.parent.exists() or not path.parent.is_dir():
            raise CommandError("Das übergeordnete Verzeichnis von --backup-path existiert nicht.")
        if os.path.lexists(path):
            raise CommandError("Der angegebene Backup-Pfad existiert bereits und wird nicht überschrieben.")
        if path.name in {"", ".", ".."}:
            raise CommandError("--backup-path muss auf eine konkrete Datei zeigen.")
        return path

    @staticmethod
    def _create_and_verify_backup(database, backup_path):
        if not database.exists() or not database.is_file():
            raise CommandError(f"Die aktive SQLite-Datenbank wurde nicht gefunden: {database}")
        if os.path.lexists(backup_path):
            raise CommandError(
                "Der angegebene Backup-Pfad existiert bereits und wird nicht überschrieben."
            )
        source = connections["default"]
        source.ensure_connection()
        target = None
        try:
            target = sqlite3.connect(str(backup_path))
            source.connection.backup(target)
            target.commit()
        except Exception as exc:
            raise CommandError(f"SQLite-Backup konnte nicht erstellt werden: {exc}") from exc
        finally:
            if target is not None:
                target.close()

        try:
            check = sqlite3.connect(str(backup_path))
            try:
                result = check.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise CommandError("Das erstellte SQLite-Backup ist nicht lesbar/integritätsgeprüft.")
            finally:
                check.close()
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f"Das erstellte SQLite-Backup konnte nicht geprüft werden: {exc}") from exc
        stat = backup_path.stat()
        return {
            "path": backup_path,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
