from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from bookkeeping.services.chart_of_accounts import (
    ReferenceValidationError,
    validate_chart_of_accounts_workbook,
    validate_monthly_bank_json,
)


class Command(BaseCommand):
    help = "Prüft lokale Bookkeeping-Referenzdateien ohne Datenbank-Schreibzugriff."

    def add_arguments(self, parser):
        parser.add_argument("--xlsx", type=Path, required=True, help="Pfad zur Excel-Vorlage")
        parser.add_argument("--bank-json", type=Path, required=True, help="Pfad zur Monats-JSON-Datei")
        parser.add_argument(
            "--expected-transactions",
            type=int,
            help="Optionale erwartete Transaktionszahl für einen expliziten Abnahmelauf.",
        )

    def handle(self, *args, **options):
        xlsx_path: Path = options["xlsx"]
        json_path: Path = options["bank_json"]
        for path in (xlsx_path, json_path):
            if not path.is_file():
                raise CommandError(f"Datei nicht gefunden: {path}")
        try:
            workbook = validate_chart_of_accounts_workbook(xlsx_path.read_bytes())
            bank_json = validate_monthly_bank_json(
                json_path.read_bytes(), expected_transactions=options.get("expected_transactions")
            )
        except ReferenceValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Excel gültig: "
                f"{workbook['entry_count']} Kategorien, {workbook['input_max_column']} Spalten, "
                f"SHA-256 {workbook['sha256']}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Bank-JSON gültig: "
                f"{bank_json['transaction_count']} Transaktionen, Währung {', '.join(bank_json['currencies'])}, "
                f"Präzision {', '.join(str(item) for item in bank_json['amount_precisions'])}, "
                f"SHA-256 {bank_json['sha256']}"
            )
        )
