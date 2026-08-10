from django.core.management import BaseCommand, CommandError

from bookkeeping.paperless_invoice_import import (
    DEFAULT_IMPORT_LIMIT,
    PaperlessInvoiceImportError,
    import_paperless_invoices,
)


class Command(BaseCommand):
    help = "Übernimmt Eingangsrechnungen mit dem exakten Paperless-Import-Tag."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_IMPORT_LIMIT,
            help=f"Maximale Anzahl pro Lauf (Standard: {DEFAULT_IMPORT_LIMIT}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur passende Dokument-IDs und Anzahl prüfen.",
        )

    def handle(self, *args, **options):
        try:
            summary = import_paperless_invoices(
                limit=options["limit"],
                dry_run=options["dry_run"],
            )
        except PaperlessInvoiceImportError as exc:
            raise CommandError(str(exc)) from exc

        if summary.dry_run:
            self.stdout.write(
                "Dry-run: "
                f"{summary.matched_count} passende Dokument(e), "
                f"{len(summary.document_ids)} gültige ID(s), "
                f"{summary.new_count} neu importierbar, "
                f"{summary.existing_count} bereits vorhanden, "
                f"{summary.skipped_count} übersprungen, "
                f"{summary.error_count} Fehler."
            )
            if summary.document_ids:
                self.stdout.write(
                    "IDs: "
                    + ", ".join(str(document_id) for document_id in summary.document_ids)
                )
        else:
            self.stdout.write(
                f"{summary.new_count} Beleg(e) übernommen, "
                f"{summary.existing_count} bereits vorhanden, "
                f"{summary.ocr_unavailable_count} ohne OCR, "
                f"{summary.ai_suggestion_count} KI-Vorschlag/-Vorschläge erstellt, "
                f"{summary.error_count} Fehler."
            )
        if summary.waiting_count:
            self.stdout.write(
                f"{summary.waiting_count} weitere(s) Dokument(e) warten auf den nächsten Lauf."
            )
        for error in summary.errors:
            self.stderr.write(error)
