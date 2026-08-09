import csv
import importlib
import io
import json
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .choices import CATEGORY_CHOICES, RECEIPT_GROUP_BANK
from .category_display import category_description
from .csv_export import quarter_bounds
from .formatting import format_austrian_decimal
from . import invoice_ai
from .invoice_ai import (
    AI_INCONSISTENT_MESSAGE,
    AI_NOT_CONFIGURED_MESSAGE,
    InvoiceAIError,
    apply_analysis_to_invoice,
    formset_initial_from_analysis,
    run_manual_invoice_analysis,
    validate_analysis,
)
from .bank_statement_parser import ParsedBankStatement, parse_bank_statement
from .bank_statements import (
    BankStatementImportError,
    import_bank_statement,
    json_control_for_statement,
    refresh_pending_paperless_tasks,
    refresh_unsynced_completed_references,
    retry_bank_statement,
)
from .booking_resets import reset_bank_transaction_booking, reset_manual_invoice_booking
from .forms import (
    BookingEntryForm,
    ManualInvoiceEntryFormSet,
    ManualInvoiceForm,
    MatchingRuleBookingTemplateForm,
    MatchingRuleForm,
    SupportingDocumentUploadForm,
)
from .matching import match_imported_transactions
from .models import (
    BankStatement,
    BankTransaction,
    BookingEntry,
    MatchingRule,
    MatchingRuleBookingTemplate,
    ManualInvoice,
    ManualInvoiceEntry,
    QuarterBalance,
    SupportingDocument,
)
from .manual_invoices import (
    ManualInvoiceDeletionError,
    delete_manual_invoice_completely,
    delete_manual_invoice_from_paperless,
    refresh_pending_manual_invoice_tasks,
    retry_manual_invoice,
    start_manual_invoice_upload,
)
from .paperless import BookkeepingPaperlessError, PaperlessClient
from .supporting_documents import (
    SupportingDocumentError,
    import_supporting_document,
    refresh_pending_supporting_documents,
    retry_supporting_document,
)
from .views import BookkeepingOverviewView


class AustrianFormattingTests(TestCase):
    def test_decimal_display_uses_austrian_separators_and_two_places(self):
        self.assertEqual(format_austrian_decimal(Decimal("43.48")), "43,48")
        self.assertEqual(format_austrian_decimal(Decimal("1096.07")), "1.096,07")
        self.assertEqual(format_austrian_decimal(Decimal("-57.40")), "-57,40")
        self.assertEqual(format_austrian_decimal(Decimal("10000")), "10.000,00")

    def test_matching_rule_decimal_input_accepts_austrian_and_point_notation(self):
        for value in ("43,48", "1.096,07", "43.48"):
            form = MatchingRuleForm(
                {
                    "name": "Mietzahlung",
                    "direction": MatchingRule.Direction.INCOMING,
                    "match_type": MatchingRule.MatchType.EXACT,
                    "iban": "AT611904300234573201",
                    "expected_amount": value,
                    "active": "on",
                }
            )

            self.assertTrue(form.is_valid(), form.errors)
            self.assertIsInstance(form.cleaned_data["expected_amount"], Decimal)
            self.assertEqual(
                form.cleaned_data["expected_amount"],
                Decimal(value.replace(".", "").replace(",", "."))
                if value == "1.096,07"
                else Decimal(value.replace(",", ".")),
            )

    def test_booking_entry_decimal_input_preserves_decimal_value(self):
        bank_transaction = BankTransaction(
            booking_date=date(2026, 7, 15),
            partner_name="Lieferant",
            purpose="Büromaterial",
            amount=Decimal("1096.07"),
            direction=BankTransaction.Direction.OUTGOING,
        )
        form = BookingEntryForm(
            {"gross_amount": "1.096,07"},
            bank_transaction=bank_transaction,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsInstance(form.cleaned_data["gross_amount"], Decimal)
        self.assertEqual(form.cleaned_data["gross_amount"], Decimal("1096.07"))

    def test_decimal_input_is_preserved_after_validation_error(self):
        form = MatchingRuleForm(
            {
                "name": "Ungültige Regel",
                "direction": MatchingRule.Direction.INCOMING,
                "match_type": MatchingRule.MatchType.EXACT,
                "iban": "ungültig",
                "expected_amount": "1.096,07",
                "active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('value="1.096,07"', str(form["expected_amount"]))


class BookkeepingOverviewUploadTests(TestCase):
    url_name = "bookkeeping_overview"

    def upload(self, payload, filename="transactions.json"):
        if isinstance(payload, list):
            payload = [
                {
                    **item,
                    "booking": item.get("booking", "2026-01-01"),
                }
                if isinstance(item, dict)
                else item
                for item in payload
            ]
        content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        uploaded_file = SimpleUploadedFile(
            filename,
            content,
            content_type="application/json",
        )
        return self.client.post(
            reverse(self.url_name),
            {"json_file": uploaded_file},
            follow=True,
        )

    def test_import_area_is_only_rendered_in_bank_import_context(self):
        bank_import_response = self.client.get(
            reverse(self.url_name),
            {"status": "bank_import"},
        )
        open_response = self.client.get(
            reverse(self.url_name),
            {"status": "open"},
        )
        ready_response = self.client.get(
            reverse(self.url_name),
            {"status": "reviewed"},
        )
        rules_response = self.client.get(reverse("matching_rule_list"))

        for response in (bank_import_response,):
            self.assertContains(response, "Bankimport")
            self.assertContains(response, "Banktransaktionen")
            self.assertContains(response, "Kontoauszug")
            self.assertContains(response, 'name="json_file"')
            self.assertContains(response, "Matching ausführen")
            self.assertNotContains(response, "<table")
            self.assertNotContains(response, "Transaktionen angezeigt")
            self.assertNotContains(response, 'id="transaction-month"')
        for response in (open_response, ready_response, rules_response):
            self.assertNotContains(response, "Banktransaktionen")
            self.assertNotContains(response, 'name="json_file"')
            self.assertNotContains(response, 'name="pdf"')
            self.assertNotContains(response, "Matching ausführen")

    def test_valid_upload_displays_transactions_and_converts_positive_and_negative_amounts(self):
        response = self.upload(
            [
                {
                    "booking": "2026-03-15T13:14:15+01:00",
                    "partnerName": "Mieter Positiv",
                    "partnerAccount": {"iban": "AT111"},
                    "amount": {"value": 12345, "precision": 2, "currency": "EUR"},
                    "reference": "Miete März",
                },
                {
                    "booking": "2026-03-16",
                    "partnerName": "Mieter Negativ",
                    "partnerAccount": {"iban": "AT222"},
                    "amount": {"value": -750, "precision": 2, "currency": "EUR"},
                    "reference": "Rückzahlung",
                },
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "123,45 EUR")
        self.assertContains(response, "-7,50 EUR")
        self.assertContains(response, "Miete März")
        self.assertContains(response, "Mieter Positiv")
        self.assertContains(response, "Mieter Negativ")
        self.assertContains(response, "15.03.2026")
        self.assertContains(response, "16.03.2026")
        self.assertContains(response, "Eingang")
        self.assertContains(response, "Ausgang")
        self.assertContains(response, "Kein Treffer")
        self.assertContains(response, "2 Transaktionen angezeigt")
        self.assertContains(response, "2 Transaktionen importiert, 0 bereits vorhanden.")
        self.assertEqual(response.context["transactions"][0]["direction"], "Ausgang")
        self.assertEqual(response.context["transactions"][1]["direction"], "Eingang")
        self.assertEqual(BankTransaction.objects.count(), 2)
        saved_positive = BankTransaction.objects.get(amount=Decimal("123.45"))
        self.assertEqual(saved_positive.booking_date, date(2026, 3, 15))
        self.assertEqual(saved_positive.partner_name, "Mieter Positiv")
        self.assertEqual(saved_positive.partner_iban, "AT111")
        self.assertEqual(saved_positive.currency, "EUR")
        self.assertEqual(saved_positive.purpose, "Miete März")
        self.assertEqual(saved_positive.direction, BankTransaction.Direction.INCOMING)
        self.assertEqual(saved_positive.status, BankTransaction.Status.IMPORTED)
        self.assertEqual(saved_positive.source, BankTransaction.Source.BANK_IMPORT)
        self.assertEqual(len(saved_positive.source_hash), 64)
        self.assertLess(
            response.content.index("Mieter Negativ".encode()),
            response.content.index("Mieter Positiv".encode()),
        )

    def test_import_uses_valuation_as_value_date(self):
        self.upload(
            [
                {
                    "booking": "2026-07-15",
                    "valuation": "2026-07-17",
                    "partnerName": "Lieferant",
                    "amount": {"value": 100, "precision": 2, "currency": "EUR"},
                }
            ]
        )

        transaction = BankTransaction.objects.get()
        self.assertEqual(transaction.booking_date, date(2026, 7, 15))
        self.assertEqual(transaction.value_date, date(2026, 7, 17))

    def test_import_falls_back_to_booking_date_when_valuation_is_empty(self):
        self.upload(
            [
                {
                    "booking": "2026-07-15",
                    "valuation": "",
                    "partnerName": "Lieferant",
                    "amount": {"value": 100, "precision": 2, "currency": "EUR"},
                }
            ]
        )

        transaction = BankTransaction.objects.get()
        self.assertEqual(transaction.value_date, transaction.booking_date)

    def test_duplicate_import_fills_only_missing_value_date(self):
        payload = {
            "booking": "2026-07-15",
            "valuation": "2026-07-17",
            "partnerName": "Lieferant",
            "amount": {"value": 100, "precision": 2, "currency": "EUR"},
        }
        import_payload = BookkeepingOverviewView._build_import_payload(payload)
        transaction = BankTransaction.objects.create(
            **{**import_payload, "value_date": None}
        )
        source_hash = transaction.source_hash

        response = self.upload([payload])

        transaction.refresh_from_db()
        self.assertContains(response, "0 Transaktionen importiert, 1 bereits vorhanden.")
        self.assertEqual(transaction.value_date, date(2026, 7, 17))
        self.assertEqual(transaction.source_hash, source_hash)

        transaction.value_date = date(2026, 7, 18)
        transaction.save(update_fields=("value_date",))
        response = self.upload([payload])

        transaction.refresh_from_db()
        self.assertContains(response, "0 Transaktionen importiert, 1 bereits vorhanden.")
        self.assertEqual(transaction.value_date, date(2026, 7, 18))
        self.assertEqual(BankTransaction.objects.count(), 1)

    def test_preview_has_no_transaction_id_or_bank_reference_column(self):
        response = self.upload(
            [
                {
                    "transactionId": "json-transaction-id",
                    "referenceNumber": "bank-reference",
                    "amount": {"value": 100, "precision": 2, "currency": "EUR"},
                }
            ]
        )

        self.assertNotContains(response, "Transaktions-ID")
        self.assertNotContains(response, "Bankreferenz")
        self.assertNotContains(response, "json-transaction-id")
        self.assertNotContains(response, "bank-reference")

    def test_booking_date_is_formatted(self):
        response = self.upload(
            [
                {
                    "booking": "2026-07-09T08:30:00Z",
                    "amount": {"value": 1, "precision": 0, "currency": "EUR"},
                }
            ]
        )

        row = response.context["transactions"][0]
        self.assertEqual(row["booking_date"], "09.07.2026")

    def test_positive_amount_uses_incoming_direction(self):
        response = self.upload(
            [{"amount": {"value": 1, "precision": 2, "currency": "EUR"}}]
        )

        row = response.context["transactions"][0]
        self.assertEqual(row["direction_code"], "incoming")
        self.assertEqual(row["direction"], "Eingang")

    def test_negative_amount_uses_outgoing_direction(self):
        response = self.upload(
            [{"amount": {"value": -1, "precision": 2, "currency": "EUR"}}]
        )

        row = response.context["transactions"][0]
        self.assertEqual(row["direction_code"], "outgoing")
        self.assertEqual(row["direction"], "Ausgang")

    def test_preview_status_is_eingelesen(self):
        response = self.upload(
            [{"amount": {"value": 100, "precision": 2, "currency": "EUR"}}]
        )

        self.assertEqual(response.context["transactions"][0]["status"], "Eingelesen")

    def test_reference_falls_back_to_receiver_reference(self):
        response = self.upload(
            [
                {
                    "amount": {"value": 100, "precision": 2, "currency": "EUR"},
                    "reference": "   ",
                    "receiverReference": "Empfängertext",
                }
            ]
        )

        self.assertContains(response, "Empfängertext")
        self.assertEqual(
            BankTransaction.objects.get().purpose,
            "Empfängertext",
        )

    def test_reimporting_same_json_creates_no_duplicates(self):
        payload = [
            {
                "booking": "2026-04-01",
                "partnerName": "Mieter",
                "amount": {"value": 1250, "precision": 2, "currency": "EUR"},
                "reference": "April",
            }
        ]

        self.upload(payload)
        response = self.upload(payload)

        self.assertEqual(BankTransaction.objects.count(), 1)
        self.assertContains(response, "0 Transaktionen importiert, 1 bereits vorhanden.")

    def test_invalid_transaction_rolls_back_the_complete_import(self):
        response = self.upload(
            [
                {
                    "booking": "2026-05-01",
                    "amount": {"value": 100, "precision": 2, "currency": "EUR"},
                },
                {
                    "booking": "2026-05-02",
                    "amount": {"value": "ungültig", "precision": 2, "currency": "EUR"},
                },
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Eine Transaktion enthält keinen gültigen Betrag.")
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_missing_purpose_fields_display_dash(self):
        response = self.upload(
            [{"amount": {"value": 100, "precision": 2, "currency": "EUR"}}]
        )

        self.assertContains(response, "–")

    def test_missing_name_and_iban_display_dash(self):
        response = self.upload(
            [{"amount": {"value": 100, "precision": 2, "currency": "EUR"}}]
        )

        row = response.context["transactions"][0]
        self.assertEqual(row["name"], "–")
        self.assertEqual(row["iban"], "–")

    def test_invalid_json_displays_error(self):
        response = self.upload(b"not json")

        self.assertContains(response, "Die Datei ist kein gültiges JSON.")

    def test_non_array_root_displays_error(self):
        response = self.upload({"transactions": []})

        self.assertContains(response, "Die JSON-Wurzel muss ein Array sein.")

    def test_missing_file_displays_error(self):
        response = self.client.post(reverse(self.url_name), {})

        self.assertContains(response, "Bitte eine JSON-Datei auswählen.")


class BookkeepingOverviewFilteringTests(TestCase):
    def create_transaction(self, booking_date, status, partner_name):
        return BankTransaction.objects.create(
            booking_date=booking_date,
            partner_name=partner_name,
            amount=Decimal("10.00"),
            direction=BankTransaction.Direction.INCOMING,
            status=status,
        )

    def get_overview(self, **query):
        return self.client.get(reverse("bookkeeping_overview"), query)

    def test_default_overview_is_dashboard_for_newest_month(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Offen Juni"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Offen Juli"
        )
        self.create_transaction(
            date(2026, 7, 16), BankTransaction.Status.MATCHED, "Zugeordnet Juli"
        )

        response = self.get_overview()

        self.assertTrue(response.context["show_dashboard"])
        self.assertEqual(response.context["dashboard_period_type"], "month")
        self.assertEqual(response.context["dashboard_period"], "2026-07")
        self.assertContains(response, "Übersicht – Juli 2026")
        self.assertContains(response, "Transaktionen gesamt")
        self.assertNotContains(response, "Offen Juli")
        self.assertNotContains(response, "Zugeordnet Juli")

    def test_each_valid_status_filter_shows_only_that_status(self):
        transactions = {
            BankTransaction.Status.IMPORTED: "Offen",
            BankTransaction.Status.MATCHED: "Zugeordnet",
            BankTransaction.Status.REVIEWED: "Geprüft",
            BankTransaction.Status.BOOKED: "Gebucht intern",
        }
        for status, partner_name in transactions.items():
            transaction = self.create_transaction(
                date(2026, 7, 15), status, partner_name
            )
            if status in {
                BankTransaction.Status.REVIEWED,
                BankTransaction.Status.BOOKED,
            }:
                BookingEntry.objects.create(
                    bank_transaction=transaction,
                    receipt_group="BK",
                    payment_date=date(2026, 7, 15),
                    booking_text=partner_name,
                    partner_name=partner_name,
                    gross_amount=transaction.amount,
                    vat_symbol="20",
                    category="4851",
                )

        for status, partner_name in transactions.items():
            with self.subTest(status=status):
                response = self.get_overview(status=status, month="2026-07")
                self.assertEqual(response.context["selected_status"], status)
                names = {row["name"] for row in response.context["transactions"]}
                if status in {
                    BankTransaction.Status.REVIEWED,
                    BankTransaction.Status.BOOKED,
                }:
                    self.assertEqual(names, {"Geprüft", "Gebucht intern"})
                else:
                    self.assertEqual(names, {partner_name})

        booked_response = self.get_overview(
            status=BankTransaction.Status.BOOKED,
            month="2026-07",
        )
        self.assertContains(booked_response, "Buchungsfertig")
        self.assertContains(booked_response, "Geprüft")
        self.assertContains(booked_response, "Gebucht intern")
        self.assertNotContains(booked_response, ">Exportiert<")

    def test_open_filter_includes_imported_and_matched_but_not_completed(self):
        transactions = {
            BankTransaction.Status.IMPORTED: "Offen",
            BankTransaction.Status.MATCHED: "Unvollständig",
            BankTransaction.Status.REVIEWED: "Buchungsfertig",
            BankTransaction.Status.BOOKED: "Gebucht intern",
        }
        for status, partner_name in transactions.items():
            self.create_transaction(date(2026, 7, 15), status, partner_name)

        response = self.get_overview(status="open", month="2026-07")

        self.assertEqual(
            {row["name"] for row in response.context["transactions"]},
            {"Offen", "Unvollständig"},
        )

    def test_open_rows_show_reason_actions_and_matched_rule(self):
        rule = MatchingRule.objects.create(
            name="Unvollständige Regel",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.REGEX,
            text_pattern="Miete",
            notes="Regelerklärung",
        )
        no_match = self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Kein Treffer"
        )
        ambiguous = self.create_transaction(
            date(2026, 7, 16),
            BankTransaction.Status.IMPORTED,
            "Mehrdeutig",
        )
        ambiguous.matched_rule = rule
        ambiguous.save(update_fields=("matched_rule",))
        incomplete = self.create_transaction(
            date(2026, 7, 17),
            BankTransaction.Status.MATCHED,
            "Buchungsdaten fehlen",
        )
        incomplete.matched_rule = rule
        incomplete.save(update_fields=("matched_rule",))

        response = self.get_overview(status="open", month="2026-07")

        self.assertContains(response, "Kein Treffer")
        self.assertContains(response, "Mehrdeutig")
        self.assertContains(response, "Buchungsdaten unvollständig")
        self.assertContains(response, "Buchung erfassen")
        self.assertContains(response, "Buchungsdaten ergänzen")
        self.assertContains(response, "Unvollständige Regel")
        self.assertContains(response, "Regelerklärung")
        self.assertContains(
            response,
            f'href="/bookkeeping/transactions/{no_match.pk}/booking/?status=open&amp;month=2026-07"',
        )
        self.assertContains(
            response,
            f'href="/bookkeeping/transactions/{incomplete.pk}/booking/?status=open&amp;month=2026-07"',
        )

        no_match.refresh_from_db()
        ambiguous.refresh_from_db()
        incomplete.refresh_from_db()
        self.assertEqual(no_match.status, BankTransaction.Status.IMPORTED)
        self.assertEqual(ambiguous.status, BankTransaction.Status.IMPORTED)
        self.assertEqual(incomplete.status, BankTransaction.Status.MATCHED)

    def test_matched_filter_remains_compatible_and_only_shows_matched(self):
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Offen"
        )
        self.create_transaction(
            date(2026, 7, 16), BankTransaction.Status.MATCHED, "Zugeordnet"
        )

        response = self.get_overview(status="matched", month="2026-07")

        self.assertEqual(response.context["selected_status"], "matched")
        self.assertEqual(
            [row["name"] for row in response.context["transactions"]],
            ["Zugeordnet"],
        )

    def test_invalid_status_falls_back_to_open(self):
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Offen"
        )
        self.create_transaction(
            date(2026, 7, 16), BankTransaction.Status.MATCHED, "Zugeordnet"
        )

        response = self.get_overview(status="unknown", month="2026-07")

        self.assertEqual(response.context["selected_status"], "open")
        self.assertEqual(
            {row["name"] for row in response.context["transactions"]},
            {"Offen", "Zugeordnet"},
        )

    def test_month_filter(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Juni"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Juli"
        )

        response = self.get_overview(status="imported", month="2026-06")

        self.assertEqual(response.context["selected_month"], "2026-06")
        self.assertEqual([row["name"] for row in response.context["transactions"]], ["Juni"])
        self.assertContains(response, "Offene Transaktionen – Juni 2026")

    def test_all_months_filter(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Juni"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Juli"
        )

        response = self.get_overview(status="imported", month="")

        self.assertEqual(response.context["selected_month"], "")
        self.assertEqual(len(response.context["transactions"]), 2)
        self.assertContains(response, "Alle Monate")
        self.assertNotContains(response, "Offene Transaktionen –")

    def test_invalid_month_falls_back_to_newest_available_month(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Juni"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Juli"
        )

        response = self.get_overview(status="imported", month="2026-99")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_month"], "2026-07")
        self.assertEqual(
            [row["name"] for row in response.context["transactions"]], ["Juli"]
        )

    def test_status_counts_are_limited_to_selected_month(self):
        for status, name in (
            (BankTransaction.Status.IMPORTED, "Offen Juli"),
            (BankTransaction.Status.MATCHED, "Zugeordnet Juli"),
            (BankTransaction.Status.REVIEWED, "Geprüft Juli"),
            (BankTransaction.Status.BOOKED, "Exportiert Juli"),
        ):
            self.create_transaction(date(2026, 7, 15), status, name)
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Offen Juni"
        )

        response = self.get_overview(status="imported", month="2026-07")

        self.assertEqual(
            response.context["status_counts"],
            {"open": 2, "reviewed": 2, "booked": 1},
        )
        self.assertContains(response, 'aria-label="2 Transaktionen"')

    def test_status_counts_are_global_for_all_months(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Offen Juni"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Offen Juli"
        )
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.MATCHED, "Zugeordnet Juli"
        )

        response = self.get_overview(status="matched", month="")

        self.assertEqual(
            response.context["status_counts"],
            {"open": 3, "reviewed": 0, "booked": 0},
        )

    def test_reviewed_label_and_booking_entry_summary_are_user_facing(self):
        transaction = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.REVIEWED,
            "Buchungsfertige Zahlung",
        )
        transaction.amount = Decimal("1096.07")
        transaction.save(update_fields=("amount",))
        for position, gross_amount in enumerate(
            (Decimal("868.24"), Decimal("193.92"), Decimal("33.91")),
            start=1,
        ):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                receipt_number=str(position),
                payment_date=transaction.booking_date,
                booking_text=f"Zeile {position}",
                partner_name="Mieter",
                gross_amount=gross_amount,
                vat_symbol="20",
                category="7600",
            )

        response = self.get_overview(status="reviewed", month="2026-07")

        self.assertContains(response, "Buchungsfertig")
        self.assertContains(response, "Buchungsfertig")
        self.assertContains(response, "3 Zeilen")
        self.assertContains(response, "1.096,07 EUR")
        self.assertContains(response, "Zeile 1")
        self.assertContains(response, "Zeile 2")
        self.assertContains(response, "Zeile 3")

    def test_ready_table_shows_booking_texts_and_original_purpose(self):
        transaction = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.REVIEWED,
            "Lieferant",
        )
        transaction.purpose = "Originaler Banktext"
        transaction.save(update_fields=("purpose",))
        BookingEntry.objects.create(
            bank_transaction=transaction,
            receipt_group="BK",
            payment_date=transaction.booking_date,
            booking_text="Korrigierter Buchungstext",
            partner_name="Lieferant",
            gross_amount=transaction.amount,
            vat_symbol="20",
            category="4851",
        )

        response = self.get_overview(status="reviewed", period="2026-Q3")

        self.assertContains(response, '<th class="bookkeeping-purpose" scope="col">Buchungstext</th>', html=True)
        self.assertContains(response, "Korrigierter Buchungstext")
        self.assertContains(response, "Ursprünglicher Verwendungszweck")
        self.assertContains(response, "Original: Originaler Banktext")
        self.assertContains(response, "Weitere Details")
        self.assertContains(response, '<details class="bookkeeping-row-details">')

    def test_ready_table_shows_multiple_booking_texts_in_existing_order(self):
        transaction = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.REVIEWED,
            "Lieferant",
        )
        for booking_text in ("Erste Buchung", "Zweite Buchung"):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=transaction.booking_date,
                booking_text=booking_text,
                partner_name="Lieferant",
                gross_amount=Decimal("5.00"),
                vat_symbol="20",
                category="4851",
            )

        response = self.get_overview(status="reviewed", period="2026-Q3")
        body = response.content.decode()

        self.assertLess(body.index("Erste Buchung"), body.index("Zweite Buchung"))

    def test_ready_table_does_not_repeat_identical_original_purpose(self):
        transaction = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.REVIEWED,
            "Lieferant",
        )
        transaction.purpose = "Identischer Text"
        transaction.save(update_fields=("purpose",))
        BookingEntry.objects.create(
            bank_transaction=transaction,
            receipt_group="BK",
            payment_date=transaction.booking_date,
            booking_text="Identischer Text",
            partner_name="Lieferant",
            gross_amount=transaction.amount,
            vat_symbol="20",
            category="4851",
        )

        response = self.get_overview(status="reviewed", period="2026-Q3")

        self.assertNotContains(response, "Original: Identischer Text")

    def test_ready_table_displays_empty_booking_text_as_dash(self):
        transaction = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.REVIEWED,
            "Lieferant",
        )
        BookingEntry.objects.create(
            bank_transaction=transaction,
            receipt_group="BK",
            payment_date=transaction.booking_date,
            booking_text="",
            partner_name="Lieferant",
            gross_amount=transaction.amount,
            vat_symbol="20",
            category="4851",
        )

        response = self.get_overview(status="reviewed", period="2026-Q3")

        self.assertContains(response, "<div>–</div>", html=True)

    def test_open_and_bank_import_tables_keep_bank_purpose(self):
        imported = self.create_transaction(
            date(2026, 7, 15),
            BankTransaction.Status.IMPORTED,
            "Offen",
        )
        imported.purpose = "Bank-Verwendungszweck"
        imported.save(update_fields=("purpose",))

        for status in ("open",):
            with self.subTest(status=status):
                response = self.get_overview(status=status, month="2026-07")
                self.assertContains(response, "Verwendungszweck")
                self.assertContains(response, "Bank-Verwendungszweck")
                self.assertNotContains(response, "Buchungstext")

    def test_bank_import_has_no_dashboard_or_period_selector(self):
        response = self.get_overview(status="bank_import")

        self.assertFalse(response.context["show_dashboard"])
        self.assertTrue(response.context["show_bank_import"])
        self.assertContains(response, "Banktransaktionen")
        self.assertContains(response, "Kontoauszug")
        self.assertNotContains(response, 'id="dashboard-period"')
        self.assertNotContains(response, "bookkeeping-dashboard-grid")
        self.assertNotContains(response, "Transaktionen gesamt")

    def test_empty_bank_import_dashboard_is_neutral(self):
        response = self.get_overview(status="bank_import")

        self.assertContains(response, "Noch keine Kontoauszüge importiert.")
        self.assertNotContains(response, 'id="dashboard-period"')
        self.assertNotContains(response, "bookkeeping-dashboard-grid")

    def test_ready_status_combines_reviewed_and_booked_without_exported_menu(self):
        reviewed = self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.REVIEWED, "Geprüft"
        )
        booked = self.create_transaction(
            date(2026, 7, 16), BankTransaction.Status.BOOKED, "Gebucht intern"
        )
        for transaction in (reviewed, booked):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=transaction.booking_date,
                booking_text=transaction.partner_name,
                partner_name=transaction.partner_name,
                gross_amount=transaction.amount,
                vat_symbol="20",
                category="4851",
            )

        response = self.get_overview(status="reviewed")

        self.assertEqual(response.context["status_counts"]["reviewed"], 2)
        self.assertEqual(
            {row["name"] for row in response.context["transactions"]},
            {"Geprüft", "Gebucht intern"},
        )
        self.assertContains(response, "Buchungsfertig")
        self.assertNotContains(response, ">Exportiert<")
        self.assertNotContains(response, "bookkeeping-nav-link-booked")

    def test_ready_view_defaults_to_newest_month_with_ready_data(self):
        older = self.create_transaction(date(2026, 7, 15), BankTransaction.Status.REVIEWED, "Juli")
        newer = self.create_transaction(date(2026, 10, 1), BankTransaction.Status.BOOKED, "Oktober")
        for transaction in (older, newer):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=transaction.booking_date,
                booking_text=transaction.partner_name,
                partner_name=transaction.partner_name,
                gross_amount=transaction.amount,
                vat_symbol="20",
                category="4851",
            )

        response = self.get_overview(status="reviewed")

        self.assertEqual(response.context["ready_period_type"], "month")
        self.assertEqual(response.context["ready_period"], "2026-10")
        self.assertEqual(
            response.context["available_ready_months"],
            [
                {"value": "2026-10", "label": "Oktober 2026"},
                {"value": "2026-07", "label": "Juli 2026"},
            ],
        )
        self.assertContains(response, 'name="period"')
        self.assertContains(response, '<form method="get" class="bookkeeping-period-control">')
        self.assertContains(response, "Der CSV-Export erfolgt quartalsweise.")

    def test_ready_table_filters_transactions_by_selected_quarter(self):
        q3_transaction = self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.REVIEWED, "Q3 Zahlung"
        )
        q4_transaction = self.create_transaction(
            date(2026, 10, 1), BankTransaction.Status.BOOKED, "Q4 Zahlung"
        )
        for transaction in (q3_transaction, q4_transaction):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=transaction.booking_date,
                booking_text=transaction.partner_name,
                partner_name=transaction.partner_name,
                gross_amount=transaction.amount,
                vat_symbol="20",
                category="4851",
            )

        q3_response = self.get_overview(status="reviewed", period="2026-Q3")
        q4_response = self.get_overview(status="reviewed", period="2026-Q4")

        self.assertEqual(
            [row["name"] for row in q3_response.context["transactions"]],
            ["Q3 Zahlung"],
        )
        self.assertEqual(q3_response.context["export_period"], "2026-Q3")
        self.assertContains(q3_response, "1 Transaktionen angezeigt")
        self.assertNotContains(q3_response, "Q4 Zahlung")
        self.assertEqual(
            [row["name"] for row in q4_response.context["transactions"]],
            ["Q4 Zahlung"],
        )
        self.assertEqual(q4_response.context["export_period"], "2026-Q4")
        self.assertNotContains(q4_response, "Q3 Zahlung")

    def test_export_periods_include_available_quarters_from_new_years(self):
        for payment_date in (date(2025, 12, 31), date(2026, 1, 1)):
            transaction = self.create_transaction(
                payment_date,
                BankTransaction.Status.REVIEWED,
                payment_date.isoformat(),
            )
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=payment_date,
                booking_text=transaction.partner_name,
                partner_name=transaction.partner_name,
                gross_amount=transaction.amount,
                vat_symbol="20",
                category="4851",
            )

        response = self.get_overview(status="reviewed")

        self.assertEqual(
            response.context["available_export_periods"],
            [
                {"value": "2026-Q1", "label": "Q1 2026"},
                {"value": "2025-Q4", "label": "Q4 2025"},
            ],
        )

    def test_ready_page_without_booking_entries_shows_neutral_export_hint(self):
        response = self.get_overview(status="reviewed")

        self.assertEqual(response.context["available_export_periods"], [])
        self.assertContains(
            response,
            "Keine buchungsfertigen Buchungszeilen für einen Export vorhanden.",
        )
        self.assertNotContains(response, "CSV exportieren")
        self.assertNotContains(response, 'role="alert"')

    def test_sidebar_status_links_preserve_selected_month(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Offen Juni"
        )
        response = self.get_overview(status="matched", month="2026-06")

        self.assertContains(
            response,
            'href="/bookkeeping/?status=open&amp;month=2026-06"',
        )
        self.assertContains(
            response,
            'href="/bookkeeping/?status=open&amp;month=2026-06" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
        )
        self.assertNotContains(response, ">Zugeordnet<")

    def test_empty_state_message_uses_status_and_month(self):
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.MATCHED, "Zugeordnet"
        )

        response = self.get_overview(status="imported", month="2026-07")

        self.assertContains(response, "Keine offenen Transaktionen für Juli 2026.")

    def test_import_redirects_to_open_newest_import_month(self):
        payload = [
            {
                "booking": "2026-06-15",
                "partnerName": "Juni",
                "amount": {"value": 1000, "precision": 2, "currency": "EUR"},
            },
            {
                "booking": "2026-07-15",
                "partnerName": "Juli",
                "amount": {"value": 1000, "precision": 2, "currency": "EUR"},
            },
        ]
        uploaded_file = SimpleUploadedFile(
            "transactions.json",
            json.dumps(payload).encode(),
            content_type="application/json",
        )

        response = self.client.post(
            reverse("bookkeeping_overview"),
            {"json_file": uploaded_file},
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=open&month=2026-07",
        )

    def test_dashboard_supports_quarter_selection(self):
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Juli"
        )
        self.create_transaction(
            date(2026, 10, 15), BankTransaction.Status.IMPORTED, "Oktober"
        )

        response = self.get_overview(
            period_type="quarter",
            period="2026-Q3",
        )

        self.assertEqual(response.context["dashboard_period_type"], "quarter")
        self.assertEqual(response.context["dashboard_period"], "2026-Q3")
        self.assertEqual(response.context["dashboard_total"], 1)
        self.assertContains(response, "Übersicht – Q3 2026")

    def test_dashboard_empty_state_and_quick_actions_are_compact(self):
        response = self.get_overview(period_type="month", period="2026-07")

        self.assertContains(
            response,
            "Für diesen Zeitraum sind noch keine Buchhaltungsdaten vorhanden.",
        )
        self.assertContains(response, "Zum Bankimport")
        self.assertContains(response, "Offene Buchungen")

    def test_ready_view_filters_by_selected_month_and_keeps_quarter_view_available(self):
        july = self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.REVIEWED, "Juli"
        )
        august = self.create_transaction(
            date(2026, 8, 15), BankTransaction.Status.BOOKED, "August"
        )
        for transaction in (july, august):
            BookingEntry.objects.create(
                bank_transaction=transaction,
                receipt_group="BK",
                payment_date=transaction.booking_date,
                booking_text=transaction.partner_name,
                partner_name=transaction.partner_name,
                gross_amount=transaction.amount,
                vat_symbol="20",
                category="4851",
            )

        response = self.get_overview(
            status="reviewed",
            period_type="month",
            period="2026-07",
        )

        self.assertEqual(response.context["ready_period"], "2026-07")
        self.assertEqual([row["name"] for row in response.context["transactions"]], ["Juli"])
        self.assertContains(response, "Der CSV-Export erfolgt quartalsweise.")
        self.assertContains(response, "Monatskontrolle")
        self.assertNotContains(response, "CSV exportieren")

    def test_monthly_reconciliation_uses_statement_without_quarter_balance(self):
        transaction = self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.REVIEWED, "Juli"
        )
        BookingEntry.objects.create(
            bank_transaction=transaction,
            receipt_group="BK",
            payment_date=transaction.booking_date,
            booking_text="Juli",
            partner_name="Juli",
            gross_amount=transaction.amount,
            vat_symbol="20",
            category="4851",
        )
        BankStatement.objects.create(
            iban="AT822011184722039000",
            statement_number=7,
            statement_year=2026,
            statement_date=date(2026, 7, 31),
            booking_month="2026-07",
            booking_quarter="2026-Q3",
            opening_balance=Decimal("100.00"),
            total_credits=Decimal("10.00"),
            total_debits=Decimal("0.00"),
            closing_balance=Decimal("110.00"),
            file_hash="statement-ui-test",
        )

        response = self.get_overview(
            status="reviewed",
            period_type="month",
            period="2026-07",
        )

        balance = response.context["quarter_control"]["balance"]
        self.assertEqual(balance["statement"]["month"], "2026-07")
        self.assertContains(response, "Anfangsstand Kontoauszug")
        self.assertContains(response, "Endstand Kontoauszug")
        self.assertNotContains(response, "Kontostände speichern")

    def test_sidebar_starts_with_dashboard_and_has_requested_order(self):
        response = self.get_overview(status="open", month="2026-07")
        body = response.content.decode()
        labels = ("Dashboard", "Bankimport", "Offen", "Buchungsfertig", "Matching-Regeln")
        positions = [body.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))


class BookkeepingCsvExportTests(TestCase):
    def create_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "partner_name": "Mieter",
            "amount": Decimal("7.80"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.REVIEWED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def create_entry(self, bank_transaction, **overrides):
        values = {
            "bank_transaction": bank_transaction,
            "receipt_group": "BK",
            "receipt_number": "7",
            "payment_date": date(2026, 7, 20),
            "booking_text": "Miete",
            "invoice_number": "RE-7",
            "partner_name": "Mieter",
            "gross_amount": Decimal("7.80"),
            "vat_symbol": "20",
            "category": "7600",
        }
        values.update(overrides)
        return BookingEntry.objects.create(**values)

    def export(self, period="2026-Q3"):
        return self.client.post(
            reverse("bookkeeping_overview"),
            {
                "action": "export_csv",
                "status": BankTransaction.Status.REVIEWED,
                "period": period,
            },
        )

    def test_exports_one_row_per_booking_entry_with_austrian_csv_format(self):
        bank_transaction = self.create_transaction(amount=Decimal("7.80"))
        self.create_entry(
            bank_transaction,
            booking_text="Text; mit Semikolon",
            gross_amount=Decimal("12.30"),
            category="4851",
        )
        self.create_entry(
            bank_transaction,
            payment_date=date(2026, 7, 21),
            booking_text="Gutschrift",
            invoice_number="",
            gross_amount=Decimal("-4.50"),
            vat_symbol="10",
            category="7600",
        )

        response = self.export()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[:3], b"\xef\xbb\xbf")
        self.assertIn(b"\r\n", response.content)
        self.assertNotIn(b"\n", response.content.replace(b"\r\n", b""))
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="Buchungszeilen_2026_Q3.csv"',
        )
        rows = list(
            csv.reader(
                io.StringIO(response.content.decode("utf-8-sig"), newline=""),
                delimiter=";",
            )
        )
        self.assertEqual(
            rows,
            [
                [
                    "Belegkreis",
                    "Belegnummer",
                    "Zahlungsdatum",
                    "Buchungstext",
                    "Rechnungsnummer",
                    "Lieferant/Kunde",
                    "Bruttobetrag",
                    "USt-Symbol",
                    "Kategorie",
                ],
                [
                    "BK",
                    "7",
                    "20.07.2026",
                    "Text; mit Semikolon",
                    "RE-7",
                    "Mieter",
                    "12,30",
                    "20",
                    "Mieterlös Bahngasse 10%",
                ],
                [
                    "BK",
                    "7",
                    "21.07.2026",
                    "Gutschrift",
                    "",
                    "Mieter",
                    "-4,50",
                    "10",
                    "Büromaterial und Drucksorten",
                ],
            ],
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)

    def test_csv_exports_zero_vat_symbol_exactly_as_zero(self):
        bank_transaction = self.create_transaction()
        self.create_entry(bank_transaction, vat_symbol="0")

        response = self.export()
        rows = list(
            csv.reader(
                io.StringIO(response.content.decode("utf-8-sig"), newline=""),
                delimiter=";",
            )
        )

        self.assertEqual(rows[1][7], "0")

    def test_quarter_bounds_cover_exactly_q1_to_q4(self):
        self.assertEqual(
            quarter_bounds(2026, "Q1"),
            (date(2026, 1, 1), date(2026, 3, 31)),
        )
        self.assertEqual(
            quarter_bounds(2026, "Q2"),
            (date(2026, 4, 1), date(2026, 6, 30)),
        )
        self.assertEqual(
            quarter_bounds(2026, "Q3"),
            (date(2026, 7, 1), date(2026, 9, 30)),
        )
        self.assertEqual(
            quarter_bounds(2026, "Q4"),
            (date(2026, 10, 1), date(2026, 12, 31)),
        )

    def test_adjacent_quarter_rows_are_not_exported(self):
        in_q1 = self.create_transaction(partner_name="Q1")
        in_q2 = self.create_transaction(
            status=BankTransaction.Status.BOOKED,
            partner_name="Q2",
        )
        self.create_entry(
            in_q1,
            payment_date=date(2026, 1, 1),
            booking_text="Q1 Anfang",
        )
        self.create_entry(
            in_q1,
            payment_date=date(2026, 3, 31),
            booking_text="Q1 Ende",
        )
        self.create_entry(
            in_q2,
            payment_date=date(2026, 4, 1),
            booking_text="Q2 Anfang",
        )

        response = self.export(period="2026-Q1")
        body = response.content.decode("utf-8-sig")

        self.assertIn("Q1 Anfang", body)
        self.assertIn("Q1 Ende", body)
        self.assertNotIn("Q2 Anfang", body)
        in_q1.refresh_from_db()
        in_q2.refresh_from_db()
        self.assertEqual(in_q1.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(in_q2.status, BankTransaction.Status.BOOKED)

    def test_table_and_csv_use_the_same_selected_period(self):
        q3_transaction = self.create_transaction(partner_name="Nur Q3")
        q4_transaction = self.create_transaction(
            booking_date=date(2026, 10, 1),
            status=BankTransaction.Status.BOOKED,
            partner_name="Nur Q4",
        )
        self.create_entry(
            q3_transaction,
            payment_date=date(2026, 7, 1),
            booking_text="Nur Q3",
        )
        self.create_entry(
            q4_transaction,
            payment_date=date(2026, 10, 1),
            booking_text="Nur Q4",
        )

        table_response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "reviewed", "period": "2026-Q3"},
        )
        csv_response = self.export(period="2026-Q3")

        self.assertContains(table_response, "Nur Q3")
        self.assertEqual(
            [row["name"] for row in table_response.context["transactions"]],
            ["Nur Q3"],
        )
        self.assertContains(csv_response, "Nur Q3")
        self.assertNotContains(csv_response, "Nur Q4")

    def test_booking_entries_are_sorted_by_payment_date_and_ids(self):
        first_transaction = self.create_transaction(
            partner_name="Erste", amount=Decimal("15.60")
        )
        second_transaction = self.create_transaction(partner_name="Zweite")
        first_entry = self.create_entry(
            first_transaction,
            payment_date=date(2026, 7, 15),
            booking_text="Erste Zeile",
        )
        second_entry = self.create_entry(
            second_transaction,
            payment_date=date(2026, 7, 15),
            booking_text="Zweite Zeile",
        )
        latest_entry = self.create_entry(
            first_transaction,
            payment_date=date(2026, 9, 30),
            booking_text="Letzte Zeile",
        )

        response = self.export()
        rows = list(
            csv.reader(
                io.StringIO(response.content.decode("utf-8-sig"), newline=""),
                delimiter=";",
            )
        )[1:]
        expected_same_date = [
            entry.booking_text
            for _transaction, entry in sorted(
                (
                    (first_transaction, first_entry),
                    (second_transaction, second_entry),
                ),
                key=lambda item: (str(item[0].pk), str(item[1].pk)),
            )
        ]
        self.assertEqual(
            [row[3] for row in rows],
            [*expected_same_date, latest_entry.booking_text],
        )

    def test_unknown_and_empty_category_codes_are_exported_without_failure(self):
        bank_transaction = self.create_transaction()
        self.create_entry(bank_transaction, category="9999")
        self.create_entry(
            bank_transaction,
            category="",
            gross_amount=Decimal("0.00"),
        )

        response = self.export()

        rows = list(
            csv.reader(
                io.StringIO(response.content.decode("utf-8-sig"), newline=""),
                delimiter=";",
            )
        )
        self.assertEqual(sorted((rows[1][-1], rows[2][-1])), ["", "9999"])
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)

    def test_export_is_repeatable_and_does_not_change_status(self):
        reviewed = self.create_transaction(partner_name="Geprüft")
        booked = self.create_transaction(
            status=BankTransaction.Status.BOOKED,
            partner_name="Schon gebucht",
        )
        self.create_entry(reviewed, booking_text="Alt geprüft")
        corrected_entry = self.create_entry(booked, booking_text="Erster Stand")

        first_response = self.export()
        second_response = self.export()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.content, second_response.content)
        reviewed.refresh_from_db()
        booked.refresh_from_db()
        self.assertEqual(reviewed.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(booked.status, BankTransaction.Status.BOOKED)

        corrected_entry.booking_text = "Korrigierter Stand"
        corrected_entry.save(update_fields=("booking_text",))
        corrected_response = self.export()
        self.assertNotEqual(first_response.content, corrected_response.content)
        self.assertContains(corrected_response, "Korrigierter Stand")

    def test_missing_quarter_selection_uses_latest_quarter_without_status_change(self):
        bank_transaction = self.create_transaction()
        self.create_entry(bank_transaction)

        response = self.export(period="")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Buchungszeilen_2026_Q3.csv", response["Content-Disposition"])
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)

    def test_quarter_without_booking_entries_has_understandable_error(self):
        bank_transaction = self.create_transaction(booking_date=date(2026, 7, 15))
        self.create_entry(bank_transaction, payment_date=date(2026, 10, 1))

        response = self.export()

        self.assertContains(response, "Keine Buchungszeilen im ausgewählten Quartal")
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)

    def test_csv_creation_error_does_not_change_status(self):
        bank_transaction = self.create_transaction()
        self.create_entry(bank_transaction)

        with patch(
            "bookkeeping.csv_export._build_csv_content",
            side_effect=RuntimeError("Testfehler"),
        ):
            response = self.export()

        self.assertContains(response, "Die CSV-Datei konnte nicht erstellt werden.")
        self.assertEqual(response.context["export_period"], "2026-Q3")
        self.assertContains(response, 'value="2026-Q3" selected')
        self.assertContains(response, "Mieter")
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)


class QuarterControlTests(TestCase):
    period = "2026-Q3"

    def create_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "partner_name": "Quartal Zahlung",
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.REVIEWED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def create_entry(self, bank_transaction, **overrides):
        values = {
            "bank_transaction": bank_transaction,
            "receipt_group": "BK",
            "receipt_number": "7",
            "payment_date": date(2026, 7, 20),
            "booking_text": "Quartal Zahlung",
            "partner_name": bank_transaction.partner_name,
            "gross_amount": bank_transaction.amount,
            "vat_symbol": "20",
            "category": "7600",
        }
        values.update(overrides)
        return BookingEntry.objects.create(**values)

    def overview(self, period=None):
        return self.client.get(
            reverse("bookkeeping_overview"),
            {"status": BankTransaction.Status.REVIEWED, "period": period or self.period},
        )

    def save_balances(self, opening="", closing="", period=None, follow=True):
        return self.client.post(
            reverse("bookkeeping_overview"),
            {
                "action": "save_quarter_balance",
                "status": BankTransaction.Status.REVIEWED,
                "period": period or self.period,
                "opening_balance": opening,
                "closing_balance": closing,
            },
            follow=follow,
        )

    def export(self, period=None):
        return self.client.post(
            reverse("bookkeeping_overview"),
            {
                "action": "export_csv",
                "status": BankTransaction.Status.REVIEWED,
                "period": period or self.period,
            },
        )

    def test_consistent_quarter_is_green_and_uses_decimal_sums(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        response = self.overview()
        control = response.context["quarter_control"]

        self.assertEqual(control["status"], "success")
        self.assertEqual(control["open_transactions"], 0)
        self.assertEqual(control["ready_transactions"], 1)
        self.assertEqual(control["booking_entries"], 1)
        self.assertEqual(control["bank_transaction_total_value"], Decimal("100.00"))
        self.assertEqual(control["booking_entry_total_value"], Decimal("100.00"))
        self.assertEqual(control["difference_value"], Decimal("0.00"))
        self.assertContains(response, "Quartal vollständig und buchhalterisch konsistent")

    def test_open_transactions_make_status_yellow_without_blocking_export(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))
        self.create_transaction(
            status=BankTransaction.Status.IMPORTED,
            amount=Decimal("25.00"),
            partner_name="Noch offen",
        )

        response = self.overview()

        self.assertEqual(response.context["quarter_control"]["status"], "warning")
        self.assertContains(response, "Quartal noch nicht vollständig")
        self.assertEqual(self.export().status_code, 200)
        self.assertIn("Buchungszeilen_2026_Q3.csv", self.export()["Content-Disposition"])

    def test_individual_differences_are_detected_even_when_they_cancel(self):
        first = self.create_transaction(amount=Decimal("100.00"), partner_name="Erste")
        second = self.create_transaction(
            amount=Decimal("-100.00"),
            direction=BankTransaction.Direction.OUTGOING,
            partner_name="Zweite",
        )
        self.create_entry(first, gross_amount=Decimal("90.00"))
        self.create_entry(second, gross_amount=Decimal("-90.00"))

        response = self.overview()
        control = response.context["quarter_control"]

        self.assertEqual(control["difference_value"], Decimal("0.00"))
        self.assertEqual(control["status"], "danger")
        self.assertEqual(len(control["inconsistent_transactions"]), 2)
        self.assertContains(response, "Buchungsdaten sind nicht konsistent")
        self.assertContains(response, "Bearbeiten")

    def test_missing_booking_entries_are_inconsistent_and_block_csv(self):
        self.create_transaction(amount=Decimal("100.00"), partner_name="Ohne Zeile")

        response = self.overview()
        export_response = self.export()

        self.assertEqual(response.context["quarter_control"]["status"], "danger")
        self.assertEqual(response.context["quarter_control"]["booking_entries"], 0)
        self.assertContains(response, "Ohne Zeile")
        self.assertContains(export_response, "Buchungsdaten sind nicht konsistent")
        self.assertNotIn("Content-Disposition", export_response)

    def test_booking_entries_outside_quarter_are_inconsistent(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(
            transaction,
            payment_date=date(2026, 10, 1),
        )

        response = self.overview()

        self.assertEqual(response.context["quarter_control"]["status"], "danger")
        self.assertEqual(len(response.context["quarter_control"]["inconsistent_transactions"]), 1)

    def test_missing_balances_are_allowed_and_bank_movement_uses_all_statuses(self):
        ready = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(ready, gross_amount=Decimal("100.00"))
        self.create_transaction(
            status=BankTransaction.Status.IMPORTED,
            amount=Decimal("-30.00"),
            direction=BankTransaction.Direction.OUTGOING,
        )
        self.create_transaction(
            status=BankTransaction.Status.MATCHED,
            amount=Decimal("5.00"),
        )
        self.create_transaction(
            status=BankTransaction.Status.BOOKED,
            amount=Decimal("7.50"),
        )

        response = self.overview()
        control = response.context["quarter_control"]

        self.assertEqual(control["balance"]["mode"], "none")
        self.assertEqual(control["balance"]["bank_movement_value"], Decimal("82.50"))
        self.assertContains(response, "Bankkontostände sind optional und noch nicht eingetragen.")
        self.assertNotContains(response, "Bankkonto weist eine Differenz")

    def test_only_opening_balance_is_valid(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        self.save_balances(opening="1.000,00", closing="")
        control = self.overview().context["quarter_control"]

        self.assertEqual(control["balance"]["mode"], "opening_only")
        self.assertEqual(control["balance"]["calculated_balance_value"], Decimal("1100.00"))
        self.assertContains(self.overview(), "Zwischenstand anhand der aktuell importierten Transaktionen.")

    def test_only_closing_balance_is_valid(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        self.save_balances(opening="", closing="1.100,00")
        control = self.overview().context["quarter_control"]

        self.assertEqual(control["balance"]["mode"], "closing_only")
        self.assertContains(self.overview(), "Für eine vollständige Abstimmung fehlt der Anfangsstand.")

    def test_negative_balances_are_valid_and_quarter_is_retained_after_post(self):
        transaction = self.create_transaction(amount=Decimal("-100.00"))
        transaction.direction = BankTransaction.Direction.OUTGOING
        transaction.save(update_fields=("direction",))
        self.create_entry(transaction, gross_amount=Decimal("-100.00"))

        response = self.save_balances(
            opening="-1.000,00",
            closing="-1.100,00",
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("period=2026-Q3", response["Location"])
        balance = QuarterBalance.objects.get(year=2026, quarter=3)
        self.assertEqual(balance.opening_balance, Decimal("-1000.00"))
        self.assertEqual(balance.closing_balance, Decimal("-1100.00"))

    def test_both_balances_are_reconciled_and_difference_is_warning_only(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        self.save_balances(opening="1.000,00", closing="1.100,00")
        matching_control = self.overview().context["quarter_control"]
        self.assertEqual(
            matching_control["balance"]["balance_difference_value"],
            Decimal("0.00"),
        )
        self.assertContains(self.overview(), "Bankkonto stimmt überein")

        self.save_balances(opening="1.000,00", closing="1.150,00")
        response = self.overview()
        control = response.context["quarter_control"]
        self.assertEqual(control["balance"]["balance_difference_value"], Decimal("50.00"))
        self.assertContains(response, "Bankkonto weist eine Differenz von 50,00 EUR auf")
        export_response = self.export()
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("Content-Disposition", export_response)

    def test_quarter_balances_are_separate_and_update_without_duplicates(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        self.save_balances(opening="100,00", closing="200,00")
        self.save_balances(opening="150,00", closing="250,00")
        self.save_balances(
            opening="300,00",
            closing="400,00",
            period="2026-Q4",
        )

        self.assertEqual(QuarterBalance.objects.count(), 2)
        q3 = QuarterBalance.objects.get(year=2026, quarter=3)
        q4 = QuarterBalance.objects.get(year=2026, quarter=4)
        self.assertEqual(q3.opening_balance, Decimal("150.00"))
        self.assertEqual(q3.closing_balance, Decimal("250.00"))
        self.assertEqual(q4.opening_balance, Decimal("300.00"))

    def test_invalid_austrian_balance_input_is_shown_inline(self):
        transaction = self.create_transaction(amount=Decimal("100.00"))
        self.create_entry(transaction, gross_amount=Decimal("100.00"))

        response = self.save_balances(opening="kein Betrag", closing="")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte einen gültigen Kontostand eingeben")
        self.assertEqual(QuarterBalance.objects.count(), 0)


class BankStatementFeatureTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

    def parsed_statement(self):
        return ParsedBankStatement(
            iban="AT611904300234573201",
            statement_number=7,
            statement_year=2026,
            statement_date=date(2026, 1, 31),
            opening_balance=Decimal("1234.56"),
            total_credits=Decimal("2000.00"),
            total_debits=Decimal("500.00"),
            closing_balance=Decimal("2734.56"),
        )

    def create_statement(self, **overrides):
        values = {
            "iban": "AT611904300234573201",
            "statement_number": 7,
            "statement_year": 2026,
            "statement_date": date(2026, 1, 31),
            "booking_month": "2026-01",
            "booking_quarter": "2026-Q1",
            "opening_balance": Decimal("1234.56"),
            "total_credits": Decimal("1000.00"),
            "total_debits": Decimal("500.00"),
            "closing_balance": Decimal("1734.56"),
            "file_hash": (uuid.uuid4().hex * 2),
        }
        values.update(overrides)
        return BankStatement.objects.create(**values)

    def test_new_bank_statements_get_unique_noneditable_reference_uuids(self):
        first = self.create_statement()
        second = self.create_statement(
            statement_number=8,
            file_hash=(uuid.uuid4().hex * 2),
        )
        reference_field = BankStatement._meta.get_field("reference_uuid")

        self.assertNotEqual(first.reference_uuid, second.reference_uuid)
        self.assertTrue(reference_field.unique)
        self.assertFalse(reference_field.editable)
        self.assertIs(reference_field.default, uuid.uuid4)

    def test_reference_uuid_migration_assigns_different_uuids_per_existing_row(self):
        migration = importlib.import_module(
            "bookkeeping.migrations.0014_bankstatement_reference_uuid"
        )
        statements = [
            SimpleNamespace(pk=1, reference_uuid=None),
            SimpleNamespace(pk=2, reference_uuid=None),
        ]

        class Manager:
            def filter(self, **filters):
                self.filters = filters
                return self

            def only(self, *fields):
                self.fields = fields
                return statements

            def bulk_update(self, objects, fields, batch_size):
                self.updated = (objects, fields, batch_size)

        manager = Manager()

        class HistoricalBankStatement:
            objects = manager

        class Apps:
            def get_model(self, app_label, model_name):
                self.lookup = (app_label, model_name)
                return HistoricalBankStatement

        migration.assign_reference_uuids(Apps(), schema_editor=None)

        self.assertTrue(all(isinstance(item.reference_uuid, uuid.UUID) for item in statements))
        self.assertNotEqual(statements[0].reference_uuid, statements[1].reference_uuid)
        self.assertEqual(manager.filters, {"reference_uuid__isnull": True})
        self.assertEqual(manager.updated[1], ["reference_uuid"])

    def create_transaction(self, amount, value_date=date(2026, 1, 15)):
        return BankTransaction.objects.create(
            booking_date=value_date,
            value_date=value_date,
            partner_name="Kontrolle",
            amount=amount,
            direction=(
                BankTransaction.Direction.INCOMING
                if amount > 0
                else BankTransaction.Direction.OUTGOING
            ),
        )

    def parse_text(self, text, pages=None):
        page_texts = pages or [text]
        fake_pages = [
            type(
                "FakePage",
                (),
                {"extract_text": lambda self, page_text=page_text: page_text},
            )()
            for page_text in page_texts
        ]
        reader = type("FakeReader", (), {"pages": fake_pages})()
        uploaded_file = SimpleUploadedFile(
            "kontoauszug.pdf",
            b"%PDF-1.7\nTestinhalt",
            content_type="application/pdf",
        )
        with patch(
            "bookkeeping.bank_statement_parser.PdfReader",
            return_value=reader,
        ):
            return parse_bank_statement(uploaded_file)

    def test_pdf_parser_reads_austrian_amounts_and_trailing_minus(self):
        parsed = self.parse_text(
            "\n".join(
                (
                    "AT822011184722039000 31.07.2026 21:41 15 007 1",
                    "IBAN Datum/Date Uhrzeit/Time Belege(*)/Vouchers Auszug/Statement Seite/Page",
                    "Kontoauszug 007/2026",
                    "Alter Kontostand: 1.093,73",
                    "Gutschriften: 19.711,31",
                    "Belastungen: 8.987,79-",
                    "Neuer Kontostand: 11.817,25",
                )
            )
        )

        self.assertEqual(parsed.iban, "AT822011184722039000")
        self.assertEqual(parsed.statement_number, 7)
        self.assertEqual(parsed.statement_date, date(2026, 7, 31))
        self.assertEqual(parsed.opening_balance, Decimal("1093.73"))
        self.assertEqual(parsed.total_credits, Decimal("19711.31"))
        self.assertEqual(parsed.total_debits, Decimal("8987.79"))
        self.assertEqual(parsed.closing_balance, Decimal("11817.25"))
        self.assertEqual(parsed.booking_month, "2026-07")
        self.assertEqual(parsed.booking_quarter, "2026-Q3")

    def test_pdf_parser_accepts_english_translations_on_following_lines(self):
        parsed = self.parse_text(
            "\n".join(
                (
                    "AT822011184722039000 31.07.2026 21:41 15 007 1",
                    "Alter Kontostand",
                    "Old Balance",
                    "1.093,73",
                    "Gutschriften",
                    "Credits",
                    "19.711,31",
                    "Belastungen",
                    "Debits",
                    "8.987,79-",
                    "Neuer Kontostand",
                    "New Balance",
                    "11.817,25",
                )
            )
        )

        self.assertEqual(parsed.opening_balance, Decimal("1093.73"))
        self.assertEqual(parsed.total_credits, Decimal("19711.31"))
        self.assertEqual(parsed.total_debits, Decimal("8987.79"))
        self.assertEqual(parsed.closing_balance, Decimal("11817.25"))

    def test_pdf_parser_accepts_combined_labels_and_amounts(self):
        parsed = self.parse_text(
            "\n".join(
                (
                    "AT822011184722039000 31.07.2026 21:41 15 007 1",
                    "Alter Kontostand/Old Balance 1.093,73",
                    "Gutschriften/Credits 19.711,31",
                    "Belastungen/Debits 8.987,79-",
                    "Neuer Kontostand/New Balance 11.817,25",
                )
            )
        )

        self.assertEqual(parsed.closing_balance, Decimal("11817.25"))

    def test_pdf_parser_rejects_inconsistent_balance_equation(self):
        with self.assertRaisesMessage(
            ValueError,
            "Die Kontostandsrechnung stimmt nicht",
        ):
            self.parse_text(
                "\n".join(
                    (
                        "IBAN: AT611904300234573201",
                        "AT611904300234573201 31.01.2026 21:41 15 007 1",
                        "Kontoauszug 007/2026",
                        "Alter Kontostand: 1.234,56",
                        "Gutschriften: 2.000,00",
                        "Belastungen: 500,00-",
                        "Neuer Kontostand: 2.734,57",
                    )
                )
            )

    def test_pdf_parser_accepts_identical_footer_on_multiple_pages(self):
        footer = "AT822011184722039000 31.07.2026 21:41 15 007 1"
        page_text = "\n".join(
            (
                footer,
                "Alter Kontostand: 1.093,73",
                "Gutschriften: 19.711,31",
                "Belastungen: 8.987,79-",
                "Neuer Kontostand: 11.817,25",
            )
        )

        second_page = "\n".join(
            (
                footer,
                "Neuer Kontostand/New Balance 11.817,25",
            )
        )
        parsed = self.parse_text("", pages=[page_text, second_page])

        self.assertEqual(parsed.statement_date, date(2026, 7, 31))
        self.assertEqual(parsed.statement_number, 7)
        self.assertEqual(parsed.booking_month, "2026-07")
        self.assertEqual(parsed.booking_quarter, "2026-Q3")

    def test_pdf_parser_rejects_conflicting_footer_dates(self):
        page_one = "\n".join(
            (
                "AT822011184722039000 31.07.2026 21:41 15 007 1",
                "Kontoauszug 007/2026",
                "Alter Kontostand: 1.093,73",
                "Gutschriften: 19.711,31",
                "Belastungen: 8.987,79-",
                "Neuer Kontostand: 11.817,25",
            )
        )
        page_two = "\n".join(
            (
                "AT822011184722039000 01.08.2026 21:41 15 007 2",
                "Neuer Kontostand/New Balance 11.817,25",
            )
        )

        with self.assertRaisesMessage(
            ValueError,
            "Widersprüchliche Auszugsdaten",
        ):
            self.parse_text("", pages=[page_one, page_two])

    def test_pdf_parser_rejects_conflicting_new_balances(self):
        page_one = "\n".join(
            (
                "AT822011184722039000 31.07.2026 21:41 15 007 1",
                "Kontoauszug 007/2026",
                "Alter Kontostand: 1.093,73",
                "Gutschriften: 19.711,31",
                "Belastungen: 8.987,79-",
                "Neuer Kontostand: 11.817,25",
            )
        )
        page_two = "Neuer Kontostand/New Balance 11.817,26"

        with self.assertRaisesMessage(
            ValueError,
            "Im PDF wurden unterschiedliche Werte für den neuen Kontostand gefunden.",
        ):
            self.parse_text("", pages=[page_one, page_two])

    def test_pdf_parser_accepts_negative_opening_and_closing_balances(self):
        parsed = self.parse_text(
            "\n".join(
                (
                    "AT822011184722039000 31.07.2026 21:41 15 007 1",
                    "Kontoauszug 007/2026",
                    "Alter Kontostand: -1.000,00",
                    "Gutschriften: 0,00",
                    "Belastungen: 100,00-",
                    "Neuer Kontostand: -1.100,00",
                )
            )
        )

        self.assertEqual(parsed.opening_balance, Decimal("-1000.00"))
        self.assertEqual(parsed.closing_balance, Decimal("-1100.00"))

    def test_pdf_parser_rejects_label_without_amount(self):
        with self.assertRaisesMessage(
            ValueError,
            "Der alte Kontostand konnte im PDF nicht gefunden werden.",
        ):
            self.parse_text(
                "\n".join(
                    (
                        "AT822011184722039000 31.07.2026 21:41 15 007 1",
                        "Alter Kontostand",
                        "Old Balance",
                        "Keine Angabe",
                        "Gutschriften: 19.711,31",
                    )
                )
            )

    def test_pdf_parser_does_not_use_transaction_amount_as_balance(self):
        with self.assertRaisesMessage(
            ValueError,
            "Der alte Kontostand konnte im PDF nicht gefunden werden.",
        ):
            self.parse_text(
                "\n".join(
                    (
                        "AT822011184722039000 31.07.2026 21:41 15 007 1",
                        "Alter Kontostand",
                        "Old Balance",
                        "Buchung 01.08.2026 1.234,56",
                        "Gutschriften: 19.711,31",
                    )
                )
            )

    def test_pdf_parser_rejects_missing_footer(self):
        with self.assertRaisesMessage(
            ValueError,
            "Das Auszugsdatum konnte im PDF nicht gefunden werden",
        ):
            self.parse_text(
                "\n".join(
                    (
                        "IBAN: AT822011184722039000",
                        "Kontoauszug 007/2026",
                        "Auszugsdatum: 31.07.2026",
                        "Alter Kontostand: 1.093,73",
                        "Gutschriften: 19.711,31",
                        "Belastungen: 8.987,79-",
                        "Neuer Kontostand: 11.817,25",
                    )
                )
            )

    def test_json_control_is_green_for_exact_value_date_totals(self):
        statement = self.create_statement()
        self.create_transaction(Decimal("1000.00"))
        self.create_transaction(Decimal("-500.00"))

        control = json_control_for_statement(statement)

        self.assertEqual(control["status"], "success")
        self.assertEqual(control["calculated_closing_value"], Decimal("1734.56"))
        self.assertEqual(
            control["message"],
            "Kontoauszug und importierte Transaktionen stimmen überein.",
        )

    def test_json_control_is_yellow_when_month_has_no_json_transactions(self):
        control = json_control_for_statement(self.create_statement())

        self.assertEqual(control["status"], "warning")
        self.assertEqual(
            control["message"],
            "Für diesen Monat sind noch keine JSON-Transaktionen vorhanden.",
        )

    def test_json_control_is_red_for_mismatch_without_blocking(self):
        statement = self.create_statement()
        self.create_transaction(Decimal("1001.00"))
        self.create_transaction(Decimal("-500.00"))

        control = json_control_for_statement(statement)

        self.assertEqual(control["status"], "danger")
        self.assertIn("Abweichung", control["message"])
        self.assertEqual(control["credits_difference"], "1,00 EUR")

    def test_duplicate_hash_does_not_create_second_paperless_task(self):
        uploaded_content = b"%PDF-1.7\nidentischer Auszug"
        with patch(
            "bookkeeping.bank_statements.parse_bank_statement",
            return_value=self.parsed_statement(),
        ), patch(
            "bookkeeping.bank_statements.PaperlessClient.upload_bank_statement",
            return_value="task-1",
        ) as upload_mock:
            first = import_bank_statement(
                SimpleUploadedFile("erster.pdf", uploaded_content)
            )
            with self.assertRaisesMessage(
                BankStatementImportError,
                "bereits importiert",
            ):
                import_bank_statement(
                    SimpleUploadedFile("zweiter.pdf", uploaded_content)
                )

        self.assertEqual(BankStatement.objects.count(), 1)
        self.assertEqual(first.statement.paperless_task_id, "task-1")
        upload_mock.assert_called_once()

    def test_duplicate_statement_identity_is_rejected_for_new_file_hash(self):
        with patch(
            "bookkeeping.bank_statements.parse_bank_statement",
            return_value=self.parsed_statement(),
        ), patch(
            "bookkeeping.bank_statements.PaperlessClient.upload_bank_statement",
            return_value="task-1",
        ) as upload_mock:
            import_bank_statement(SimpleUploadedFile("erster.pdf", b"%PDF-1.7 eins"))
            with self.assertRaisesMessage(
                BankStatementImportError,
                "IBAN, Jahr und Auszugsnummer",
            ):
                import_bank_statement(
                    SimpleUploadedFile("zweiter.pdf", b"%PDF-1.7 zwei")
                )

        self.assertEqual(BankStatement.objects.count(), 1)
        upload_mock.assert_called_once()

    def test_completed_paperless_task_stores_document_and_removes_temporary_pdf(self):
        with patch(
            "bookkeeping.bank_statements.parse_bank_statement",
            return_value=self.parsed_statement(),
        ), patch(
            "bookkeeping.bank_statements.PaperlessClient.upload_bank_statement",
            return_value="task-1",
        ):
            result = import_bank_statement(
                SimpleUploadedFile("kontoauszug.pdf", b"%PDF-1.7 task")
            )
        self.assertTrue(result.statement.temporary_pdf.name)

        with patch(
            "bookkeeping.bank_statements.PaperlessClient.task_status",
            return_value={"status": "completed", "document_id": 42},
        ):
            refresh_pending_paperless_tasks()

        result.statement.refresh_from_db()
        self.assertEqual(
            result.statement.paperless_status,
            BankStatement.PaperlessStatus.COMPLETED,
        )
        self.assertEqual(result.statement.paperless_document_id, 42)
        self.assertTrue(result.statement.paperless_reference_synced)
        self.assertFalse(result.statement.temporary_pdf.name)
        with override_settings(PAPERLESS_BASE_URL="https://paperless.example"):
            self.assertEqual(
                PaperlessClient.document_url(42),
                "https://paperless.example/documents/42/",
            )

    def test_failed_upload_retains_pdf_and_can_be_retried(self):
        with patch(
            "bookkeeping.bank_statements.parse_bank_statement",
            return_value=self.parsed_statement(),
        ), patch(
            "bookkeeping.bank_statements.PaperlessClient.upload_bank_statement",
            side_effect=BookkeepingPaperlessError("Paperless nicht erreichbar"),
        ):
            result = import_bank_statement(
                SimpleUploadedFile("kontoauszug.pdf", b"%PDF-1.7 retry")
            )

        result.statement.refresh_from_db()
        stored_name = result.statement.temporary_pdf.name
        self.assertEqual(
            result.statement.paperless_status,
            BankStatement.PaperlessStatus.FAILED,
        )
        self.assertTrue(result.statement.temporary_pdf.storage.exists(stored_name))

        with patch(
            "bookkeeping.bank_statements.PaperlessClient.upload_bank_statement",
            return_value="task-2",
        ):
            retry_bank_statement(result.statement)

        result.statement.refresh_from_db()
        self.assertEqual(
            result.statement.paperless_status,
            BankStatement.PaperlessStatus.PENDING,
        )
        self.assertEqual(result.statement.paperless_task_id, "task-2")
        self.assertTrue(result.statement.temporary_pdf.storage.exists(stored_name))

    def pending_statement(self):
        statement = self.create_statement(paperless_task_id="task-existing")
        statement.temporary_pdf = SimpleUploadedFile(
            "pending.pdf",
            b"%PDF-1.7 pending",
            content_type="application/pdf",
        )
        statement.paperless_status = BankStatement.PaperlessStatus.PENDING
        statement.save()
        return statement

    def test_task_status_supports_old_list_paginated_and_single_object(self):
        responses = (
            [{"id": "task-1", "status": "SUCCESS", "related_document": 101}],
            {"count": 1, "results": [{"task_id": "task-1", "status": "COMPLETED", "document_id": 102}]},
            {"id": "task-1", "status": "SUCCESS", "document": 103},
        )

        for payload, expected_document_id in zip(responses, (101, 102, 103)):
            with self.subTest(payload_type=type(payload).__name__), patch.object(
                PaperlessClient,
                "_request_json",
                return_value=payload,
            ):
                result = PaperlessClient.task_status("task-1")

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["document_id"], expected_document_id)

    def test_task_status_accepts_case_insensitive_running_states(self):
        for status in ("PENDING", "STARTED", "RETRY", "RUNNING"):
            with self.subTest(status=status), patch.object(
                PaperlessClient,
                "_request_json",
                return_value=[{"id": "task-1", "status": status}],
            ):
                result = PaperlessClient.task_status("task-1")

            self.assertEqual(result["status"], "pending")

    def test_task_status_reads_document_id_from_json_result(self):
        payload = {
            "task_id": "task-1",
            "status": "success",
            "result": '{"document_id": 104}',
        }

        with patch.object(PaperlessClient, "_request_json", return_value=payload):
            result = PaperlessClient.task_status("task-1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["document_id"], 104)

    def test_task_status_reads_integer_result_as_document_id(self):
        payload = {"task_id": "task-1", "status": "COMPLETED", "result": 105}

        with patch.object(PaperlessClient, "_request_json", return_value=payload):
            result = PaperlessClient.task_status("task-1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["document_id"], 105)

    def test_successful_task_without_document_id_requests_fallback(self):
        payload = {"task_id": "task-1", "status": "SUCCESS", "result": "done"}

        with patch.object(PaperlessClient, "_request_json", return_value=payload):
            result = PaperlessClient.task_status("task-1")

        self.assertEqual(result["status"], "needs_fallback")
        self.assertIsNone(result["document_id"])

    def test_missing_task_requests_fallback(self):
        payload = [{"task_id": "another-task", "status": "SUCCESS"}]

        with patch.object(PaperlessClient, "_request_json", return_value=payload):
            result = PaperlessClient.task_status("task-1")

        self.assertEqual(result["status"], "needs_fallback")
        self.assertFalse(result["found"])

    def test_reference_fallback_sends_json_custom_field_query(self):
        with patch.object(
            PaperlessClient,
            "_request_json",
            return_value={"count": 1, "results": [{"id": 106}]},
        ) as request_json:
            result = PaperlessClient.find_document_by_reference("1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["document_id"], 106)
        query = request_json.call_args.kwargs["query"]
        self.assertEqual(
            query["custom_field_query"],
            '["q_bookkeeping_referenz","exact","1"]',
        )

    def test_pending_statement_uses_reference_fallback_after_task_error(self):
        statement = self.pending_statement()
        with patch.object(
            PaperlessClient,
            "task_status",
            side_effect=BookkeepingPaperlessError("Zugriff abgelehnt"),
        ), patch.object(
            PaperlessClient,
            "find_document_by_reference",
            return_value={"status": "completed", "document_id": 107},
        ) as find_document, patch.object(
            PaperlessClient, "upload_bank_statement"
        ) as upload:
            refresh_pending_paperless_tasks()

        self.assertEqual(
            find_document.call_args.args[0],
            str(statement.reference_uuid),
        )

        statement.refresh_from_db()
        self.assertEqual(
            statement.paperless_status,
            BankStatement.PaperlessStatus.COMPLETED,
        )
        self.assertEqual(statement.paperless_document_id, 107)
        self.assertFalse(statement.temporary_pdf.name)
        upload.assert_not_called()

    def test_missing_reference_document_keeps_statement_pending_and_pdf(self):
        statement = self.pending_statement()
        stored_name = statement.temporary_pdf.name
        with patch.object(
            PaperlessClient,
            "task_status",
            return_value={"status": "needs_fallback", "document_id": None},
        ), patch.object(
            PaperlessClient,
            "find_document_by_reference",
            return_value={"status": "pending", "document_id": None},
        ):
            refresh_pending_paperless_tasks()

        statement.refresh_from_db()
        self.assertEqual(
            statement.paperless_status,
            BankStatement.PaperlessStatus.PENDING,
        )
        self.assertTrue(statement.temporary_pdf.storage.exists(stored_name))

    def test_multiple_reference_documents_fail_without_deleting_pdf(self):
        statement = self.pending_statement()
        stored_name = statement.temporary_pdf.name
        with patch.object(
            PaperlessClient,
            "task_status",
            return_value={"status": "needs_fallback", "document_id": None},
        ), patch.object(
            PaperlessClient,
            "find_document_by_reference",
            side_effect=BookkeepingPaperlessError(
                "In Paperless wurden mehrere Dokumente mit derselben "
                "Bookkeeping-Referenz gefunden."
            ),
        ):
            refresh_pending_paperless_tasks()

        statement.refresh_from_db()
        self.assertEqual(
            statement.paperless_status,
            BankStatement.PaperlessStatus.FAILED,
        )
        self.assertIn("mehrere Dokumente", statement.paperless_error)
        self.assertTrue(statement.temporary_pdf.storage.exists(stored_name))

    def test_bank_import_page_contains_statement_upload(self):
        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "bank_import"},
        )

        self.assertContains(response, "Banktransaktionen")
        self.assertContains(response, "Importierte Kontoauszüge")
        self.assertContains(response, "Kontoauszug hochladen")
        self.assertContains(response, "nach Buchungsmonat oder Quartal filtern")

    def test_bank_import_contains_two_import_cards_without_dashboard(self):
        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "bank_import"},
        )
        content = response.content.decode()

        self.assertEqual(content.count("bookkeeping-import-card"), 2)
        self.assertNotIn('class="bookkeeping-dashboard"', content)
        self.assertNotContains(response, "Transaktionen angezeigt")

    def test_imported_statement_table_keeps_paperless_link_and_compact_columns(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
            paperless_reference_synced=True,
        )
        with override_settings(PAPERLESS_BASE_URL="https://paperless.example"):
            response = self.client.get(
                reverse("bookkeeping_overview"),
                {"status": "bank_import"},
            )

        content = response.content.decode()
        self.assertContains(response, "Importierte Kontoauszüge")
        self.assertContains(response, "In Paperless öffnen")
        self.assertContains(response, "Abgelegt")
        self.assertIn(
            'href="https://paperless.example/documents/256/"',
            content,
        )
        self.assertIn('target="_blank"', content)
        self.assertIn('rel="noopener noreferrer"', content)
        self.assertEqual(content.count('title="In Paperless öffnen"'), 1)
        self.assertEqual(content.count('aria-label="In Paperless öffnen"'), 1)
        self.assertNotIn("bookkeeping-paperless-link", content)
        self.assertLess(
            content.index('href="https://paperless.example/documents/256/"'),
            content.index('<td class="bookkeeping-statement-month">'),
        )
        self.assertNotContains(response, "<th>Quartal</th>")
        self.assertLess(
            content.index('<th class="bookkeeping-actions" scope="col">Aktionen</th>'),
            content.index("<th scope=\"col\">Monat</th>"),
        )
        self.assertIn(str(statement.pk), content)

    def test_failed_statement_without_document_id_keeps_retry_action_without_link(self):
        statement = self.pending_statement()
        statement.paperless_status = BankStatement.PaperlessStatus.FAILED
        statement.paperless_document_id = None
        statement.save(update_fields=("paperless_status", "paperless_document_id"))

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "bank_import"},
        )

        self.assertContains(response, "Erneut übertragen")
        self.assertNotContains(response, "In Paperless öffnen")
        self.assertNotContains(response, "/documents/")

    def test_new_upload_uses_reference_uuid_in_paperless_custom_field(self):
        statement = self.pending_statement()
        with override_settings(
            PAPERLESS_BASE_URL="https://paperless.example",
            PAPERLESS_API_TOKEN="test-token",
        ), patch.object(
            PaperlessClient,
            "_require_named",
            side_effect=(1, 2, 3, 4),
        ), patch.object(
            PaperlessClient,
            "_require_storage_path",
            return_value=5,
        ), patch.object(
            PaperlessClient,
            "_require_custom_field",
            side_effect=(6, 7, 8, 9),
        ), patch.object(
            PaperlessClient,
            "_request_multipart",
            return_value={"task_id": "task-new"},
        ) as upload:
            task_id = PaperlessClient.upload_bank_statement(statement)

        self.assertEqual(task_id, "task-new")
        fields = dict(upload.call_args.kwargs["form_fields"])
        custom_fields = json.loads(fields["custom_fields"])
        self.assertEqual(
            custom_fields["6"],
            str(statement.reference_uuid),
        )
        self.assertNotEqual(custom_fields["6"], str(statement.pk))

    def reference_document(self, statement, reference, extra_fields=None):
        custom_fields = {
            "11": reference,
            "12": "2026-01-31",
            "13": "2026-01",
            "14": "2026-Q1",
        }
        custom_fields.update(extra_fields or {})
        return {
            "id": statement.paperless_document_id,
            "title": "Kontoauszug 2026-01",
            "tags": ["Buchhaltung", "Immo-Fuchs KG"],
            "custom_fields": custom_fields,
        }

    def reference_lookup_response(self):
        return {"results": [{"id": 11, "name": "q_bookkeeping_referenz"}]}

    def test_existing_document_reference_is_updated_without_changing_metadata(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=False,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        old_reference = str(statement.pk)
        document = self.reference_document(statement, old_reference, {"99": "keep"})
        with patch.object(
            PaperlessClient,
            "_request_json",
            side_effect=(document, self.reference_lookup_response(), {}),
        ) as request_json, patch.object(
            PaperlessClient,
            "upload_bank_statement",
        ) as upload:
            refresh_unsynced_completed_references()

        statement.refresh_from_db()
        self.assertTrue(statement.paperless_reference_synced)
        self.assertEqual(statement.paperless_error, "")
        self.assertEqual(request_json.call_count, 3)
        patch_call = request_json.call_args_list[2]
        self.assertEqual(patch_call.kwargs["method"], "PATCH")
        self.assertEqual(patch_call.kwargs["endpoint"], "documents/256/")
        updated_fields = patch_call.kwargs["payload"]["custom_fields"]
        self.assertEqual(updated_fields["11"], str(statement.reference_uuid))
        self.assertEqual(updated_fields["12"], "2026-01-31")
        self.assertEqual(updated_fields["13"], "2026-01")
        self.assertEqual(updated_fields["14"], "2026-Q1")
        self.assertEqual(updated_fields["99"], "keep")
        upload.assert_not_called()

    def test_existing_correct_uuid_is_accepted_without_patch(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=False,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        document = self.reference_document(statement, str(statement.reference_uuid))
        with patch.object(
            PaperlessClient,
            "_request_json",
            side_effect=(document, self.reference_lookup_response()),
        ) as request_json:
            refresh_unsynced_completed_references()

        statement.refresh_from_db()
        self.assertTrue(statement.paperless_reference_synced)
        self.assertEqual(request_json.call_count, 2)

    def test_unexpected_existing_reference_is_not_overwritten(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=False,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        document = self.reference_document(statement, "unexpected-reference")
        with patch.object(
            PaperlessClient,
            "_request_json",
            side_effect=(document, self.reference_lookup_response()),
        ) as request_json:
            errors = refresh_unsynced_completed_references()

        statement.refresh_from_db()
        self.assertFalse(statement.paperless_reference_synced)
        self.assertIn("stimmt weder", errors[statement.pk])
        self.assertEqual(statement.paperless_error, "")
        self.assertEqual(request_json.call_count, 2)

    def test_reference_api_error_keeps_local_sync_state_unchanged(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=False,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        with patch.object(
            PaperlessClient,
            "_request_json",
            side_effect=BookkeepingPaperlessError("Paperless ist nicht erreichbar"),
        ):
            refresh_unsynced_completed_references()

        statement.refresh_from_db()
        self.assertFalse(statement.paperless_reference_synced)
        self.assertEqual(statement.paperless_status, BankStatement.PaperlessStatus.COMPLETED)
        self.assertEqual(statement.paperless_error, "")

    def test_reference_sync_error_is_displayed_without_local_mutation(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=False,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        with patch.object(
            PaperlessClient,
            "synchronize_statement_reference",
            side_effect=BookkeepingPaperlessError(
                "Die bestehende Paperless-Referenz stimmt weder mit der alten "
                "noch mit der neuen Bookkeeping-Referenz überein."
            ),
        ):
            response = self.client.get(
                reverse("bookkeeping_overview"),
                {"status": "bank_import"},
            )

        self.assertContains(
            response,
            "Die bestehende Paperless-Referenz stimmt weder mit der alten",
        )
        statement.refresh_from_db()
        self.assertFalse(statement.paperless_reference_synced)
        self.assertEqual(statement.paperless_error, "")

    def test_completed_synced_statement_is_not_queried_again(self):
        statement = self.create_statement(
            paperless_document_id=256,
            paperless_reference_synced=True,
            paperless_status=BankStatement.PaperlessStatus.COMPLETED,
        )
        with patch.object(
            PaperlessClient,
            "synchronize_statement_reference",
        ) as synchronize:
            refresh_unsynced_completed_references()

        statement.refresh_from_db()
        self.assertTrue(statement.paperless_reference_synced)
        synchronize.assert_not_called()

    def test_paperless_metadata_names_are_fixed(self):
        self.assertEqual(PaperlessClient.CORRESPONDENT_NAME, "Erste Bank")
        self.assertEqual(PaperlessClient.DOCUMENT_TYPE_NAME, "Kontoauszug")
        self.assertEqual(PaperlessClient.TAG_NAMES, ("Buchhaltung", "Immo-Fuchs KG"))
        self.assertEqual(PaperlessClient.STORAGE_PATH_NAME, "IFKG Kontoauszüge")
        self.assertEqual(
            PaperlessClient.CUSTOM_FIELDS,
            {
                "q_bookkeeping_referenz": "string",
                "q_buchungsdatum": "date",
                "q_buchungsmonat": "string",
                "q_buchungsquartal": "string",
            },
        )

    def test_missing_paperless_metadata_is_reported_without_creation(self):
        with patch.object(
            PaperlessClient,
            "_find_exact_name",
            return_value=None,
        ), patch.object(PaperlessClient, "_request_json") as request_json:
            with self.assertRaisesMessage(
                BookkeepingPaperlessError,
                "Paperless-Objekt 'Erste Bank' fehlt",
            ):
                PaperlessClient._require_named("correspondents/", "Erste Bank")

            with self.assertRaisesMessage(
                BookkeepingPaperlessError,
                "Paperless-Custom-Field 'q_buchungsmonat'",
            ):
                PaperlessClient._require_custom_field("q_buchungsmonat", "string")

            with self.assertRaisesMessage(
                BookkeepingPaperlessError,
                "Paperless-Speicherpfad 'IFKG Kontoauszüge' fehlt",
            ):
                PaperlessClient._require_storage_path()

        request_json.assert_not_called()


class BookkeepingNoteTests(TestCase):
    def create_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "partner_name": "Mieter",
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.MATCHED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def note_url(self, bank_transaction, status="matched", month="2026-07"):
        return (
            f"{reverse('bank_transaction_note', kwargs={'pk': bank_transaction.pk})}"
            f"?status={status}&month={month}"
        )

    def note_href(self, bank_transaction, status="matched", month="2026-07"):
        return self.note_url(bank_transaction, status, month).replace("&", "&amp;")

    def test_transaction_note_can_be_created_edited_and_removed(self):
        bank_transaction = self.create_transaction()
        note_url = self.note_url(bank_transaction)

        response = self.client.post(note_url, {"notes": "Erste Anmerkung"})

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=matched&month=2026-07",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Erste Anmerkung")

        self.client.post(note_url, {"notes": "Geänderte Anmerkung"})
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Geänderte Anmerkung")

        self.client.post(note_url, {"notes": ""})
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "")

    def test_actions_is_the_first_transaction_table_column(self):
        bank_transaction = self.create_transaction()

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "matched", "month": "2026-07"},
        )
        content = response.content.decode()

        actions_header = '<th class="bookkeeping-actions" scope="col">Aktionen</th>'
        date_header = '<th class="bookkeeping-date" scope="col">Buchungsdatum</th>'
        self.assertContains(response, actions_header)
        self.assertLess(content.index(actions_header), content.index(date_header))
        self.assertContains(response, f'href="{self.note_href(bank_transaction)}"')

    def test_imported_transactions_hide_note_and_assignment_columns(self):
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.IMPORTED,
            notes="Nur intern sichtbar",
        )

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "imported", "month": "2026-07"},
        )

        self.assertContains(response, '<th class="bookkeeping-actions" scope="col">Aktionen</th>')
        self.assertContains(response, "Buchung erfassen")
        self.assertNotContains(response, "Anmerkung")
        self.assertNotContains(response, "Nur intern sichtbar")
        self.assertNotContains(response, "Matching-Erklärung")
        self.assertNotContains(
            response,
            '<th class="bookkeeping-matching-rule" scope="col">Matching-Regel</th>',
        )

    def test_reviewed_transactions_allow_note_editing(self):
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.REVIEWED,
        )
        BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Prüfung",
            partner_name=bank_transaction.partner_name,
            gross_amount=bank_transaction.amount,
            vat_symbol="20",
            category="4851",
        )

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "reviewed", "month": "2026-07"},
        )

        self.assertContains(response, "Matching-Erklärung")
        self.assertContains(
            response,
            f'href="{self.note_href(bank_transaction, "reviewed")}"',
        )

        self.client.post(
            self.note_url(bank_transaction, "reviewed"),
            {"notes": "Prüfhinweis"},
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Prüfhinweis")

    def test_booked_transactions_allow_note_editing(self):
        rule = MatchingRule.objects.create(
            name="Exportregel",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
            notes="Erklärung für den Export.",
        )
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.BOOKED,
            matched_rule=rule,
            notes="Exportnotiz",
        )
        BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Export",
            partner_name=bank_transaction.partner_name,
            gross_amount=bank_transaction.amount,
            vat_symbol="20",
            category="4851",
        )

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "booked", "month": "2026-07"},
        )

        self.assertContains(response, "Exportnotiz")
        self.assertContains(response, "Erklärung für den Export.")
        self.assertContains(response, rule.name)
        self.assertContains(
            response,
            f'href="{self.note_href(bank_transaction, "booked")}"',
        )

        self.client.post(
            self.note_url(bank_transaction, "booked"),
            {"notes": "Geänderte Gebucht-Notiz"},
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Geänderte Gebucht-Notiz")

    def test_imported_note_update_is_rejected_without_changing_note(self):
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.IMPORTED,
            notes="Bestehende Offen-Notiz",
        )

        response = self.client.post(
            self.note_url(bank_transaction, "imported"),
            {"notes": "Unzulässige Änderung"},
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=imported&month=2026-07",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Bestehende Offen-Notiz")

    def test_booked_note_update_is_allowed_without_status_change(self):
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.BOOKED,
            notes="Bestehende Exportnotiz",
        )

        response = self.client.post(
            self.note_url(bank_transaction, "booked"),
            {"notes": "Unzulässige Änderung"},
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=booked&month=2026-07",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "Unzulässige Änderung")
        self.assertEqual(bank_transaction.status, BankTransaction.Status.BOOKED)

    def test_transaction_note_changes_only_the_selected_transaction(self):
        first = self.create_transaction(partner_name="Erste Transaktion")
        second = self.create_transaction(partner_name="Zweite Transaktion")

        response = self.client.post(
            self.note_url(first),
            {"notes": "Nur erste Transaktion"},
        )

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.notes, "Nur erste Transaktion")
        self.assertEqual(second.notes, "")

    def test_used_matching_rule_note_is_historical_and_not_editable(self):
        rule = MatchingRule.objects.create(
            name="Mietzahlung",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
            notes="Regelnotiz alt",
        )
        bank_transaction = self.create_transaction(matched_rule=rule)

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "matched", "month": "2026-07"},
        )

        self.assertContains(response, "Matching-Erklärung")
        self.assertContains(response, "Regelnotiz alt")
        self.assertContains(response, rule.name)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.notes, "")

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": rule.name,
                "direction": rule.direction,
                "match_type": rule.match_type,
                "iban": rule.iban,
                "expected_amount": "100.00",
                "text_pattern": "",
                "notes": "Regelnotiz neu",
                "active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(bank_transaction.notes, "")
        self.assertContains(response, "Regelnotiz alt")
        self.assertNotContains(response, "Regelnotiz neu")


class BookingEntryTests(TestCase):
    def create_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "partner_name": "Lieferant",
            "purpose": "Büromaterial",
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.OUTGOING,
            "status": BankTransaction.Status.IMPORTED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def booking_url(self, bank_transaction, status=None, month="2026-07"):
        status = status or bank_transaction.status
        return (
            f"{reverse('bank_transaction_booking', kwargs={'pk': bank_transaction.pk})}"
            f"?status={status}&month={month}"
        )

    def complete_data(self, bank_transaction, **overrides):
        values = {
            "action": "finalize",
            "receipt_group": RECEIPT_GROUP_BANK,
            "receipt_number": "42",
            "payment_date": (
                bank_transaction.value_date or bank_transaction.booking_date
            ).isoformat(),
            "booking_text": "Büromaterial",
            "invoice_number": "RE-42",
            "partner_name": bank_transaction.partner_name,
            "gross_amount": str(bank_transaction.amount),
            "vat_symbol": "20",
            "category": "7600",
            "notes": "Beleg geprüft",
        }
        values.update(overrides)
        return values

    def create_rule_with_templates(
        self,
        amount,
        templates,
        direction=BankTransaction.Direction.OUTGOING,
    ):
        rule = MatchingRule.objects.create(
            name="Vorlage Buchungszeilen",
            direction=direction,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=abs(amount),
        )
        for position, template_values in enumerate(templates, start=1):
            MatchingRuleBookingTemplate.objects.create(
                matching_rule=rule,
                position=position,
                **template_values,
            )
        return rule

    def entry_formset_data(
        self,
        bank_transaction,
        rows,
        action="save_draft",
        initial_forms=0,
        notes="",
    ):
        payment_date = bank_transaction.value_date or bank_transaction.booking_date
        data = {
            "action": action,
            "entries-TOTAL_FORMS": str(len(rows)),
            "entries-INITIAL_FORMS": str(initial_forms),
            "entries-MIN_NUM_FORMS": "0",
            "entries-MAX_NUM_FORMS": "1000",
            "notes": notes,
        }
        for index, row in enumerate(rows):
            values = {
                "receipt_group": RECEIPT_GROUP_BANK,
                "receipt_number": str(payment_date.month),
                "payment_date": payment_date.isoformat(),
                "booking_text": bank_transaction.purpose,
                "invoice_number": "",
                "partner_name": bank_transaction.partner_name,
                "gross_amount": str(bank_transaction.amount),
                "vat_symbol": "20",
                "category": "7600",
            }
            values.update(row)
            for field_name in BookingEntryForm.Meta.fields:
                if field_name in values:
                    value = values[field_name]
                    if isinstance(value, Decimal):
                        value = str(value)
                    elif isinstance(value, date):
                        value = value.isoformat()
                    data[f"entries-{index}-{field_name}"] = value
            if row.get("id"):
                data[f"entries-{index}-id"] = str(row["id"])
            if row.get("delete"):
                data[f"entries-{index}-DELETE"] = "on"
        return data

    @staticmethod
    def booking_table_body(response):
        content = response.content.decode()
        return content.split('<tbody id="booking-entry-rows">', 1)[1].split(
            "</tbody>", 1
        )[0]

    def test_form_defaults_are_taken_from_bank_transaction(self):
        bank_transaction = self.create_transaction(
            notes="Vorhandene Transaktionsnotiz"
        )

        response = self.client.get(self.booking_url(bank_transaction))

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["payment_date"], bank_transaction.booking_date)
        self.assertEqual(form.initial["partner_name"], bank_transaction.partner_name)
        self.assertEqual(form.initial["booking_text"], bank_transaction.purpose)
        self.assertEqual(form.initial["gross_amount"], bank_transaction.amount)
        self.assertEqual(
            form.initial["notes"],
            "Vorhandene Transaktionsnotiz",
        )
        self.assertContains(response, "Originale Banktransaktion")
        self.assertContains(response, "Anmerkung")

    def test_booking_form_uses_full_width_layout_and_compact_optional_note(self):
        bank_transaction = self.create_transaction()

        response = self.client.get(self.booking_url(bank_transaction))
        content = response.content.decode()

        self.assertContains(response, 'class="bookkeeping-entry-form"')
        self.assertContains(response, 'class="bookkeeping-entry-rows-section"')
        self.assertContains(response, 'class="bookkeeping-entry-table-wrap"')
        self.assertContains(response, 'class="bookkeeping-entry-form-actions"')
        self.assertContains(response, "Anmerkung (optional)")
        self.assertIn('name="notes"', content)
        self.assertIn('rows="3"', content)

    def test_booking_entries_render_as_compact_table_rows_in_requested_order(self):
        bank_transaction = self.create_transaction()
        for booking_text, gross_amount, category in (
            ("Erste Zeile", Decimal("60.00"), "7600"),
            ("Zweite Zeile", Decimal("40.00"), "7380"),
        ):
            BookingEntry.objects.create(
                bank_transaction=bank_transaction,
                receipt_group="BK",
                payment_date=bank_transaction.booking_date,
                booking_text=booking_text,
                partner_name=bank_transaction.partner_name,
                gross_amount=gross_amount,
                vat_symbol="20",
                category=category,
            )

        response = self.client.get(self.booking_url(bank_transaction))
        content = response.content.decode()
        table = content.split('<table class="table table-sm bookkeeping-entry-table">', 1)[1]
        header = table.split("</thead>", 1)[0]
        expected_columns = (
            "Aktionen",
            "Belegkreis",
            "Belegnummer",
            "Zahlungsdatum",
            "Buchungstext",
            "Rechnungsnummer",
            "Lieferant/Kunde",
            "Bruttobetrag",
            "USt",
            "Kategorie",
        )
        positions = [header.index(column) for column in expected_columns]

        self.assertEqual(positions, sorted(positions))
        body = self.booking_table_body(response)
        self.assertEqual(body.count('<tr class="bookkeeping-entry-row'), 2)
        self.assertNotIn("bookkeeping-entry-row-title", body)
        self.assertLess(
            body.index('<td class="bookkeeping-entry-actions">'),
            body.index("<td>", body.index('<td class="bookkeeping-entry-actions">') + 1),
        )
        self.assertContains(response, "Buchungszeile hinzufügen")

    def test_booking_table_uses_single_line_text_input_and_preserves_formset_controls(self):
        bank_transaction = self.create_transaction()

        response = self.client.get(self.booking_url(bank_transaction))
        body = self.booking_table_body(response)

        self.assertIn('name="entries-0-booking_text"', body)
        self.assertIn('type="text" name="entries-0-booking_text"', body)
        self.assertNotIn("<textarea", body)
        self.assertIn('class="bi bi-trash"', body)
        self.assertIn('aria-label="Löschen"', body)
        self.assertIn("entries-TOTAL_FORMS", response.content.decode())
        self.assertIn("insertAdjacentHTML", response.content.decode())
        self.assertIn("entries-0-DELETE", body)
        self.assertIn("entries-__prefix__-DELETE", response.content.decode())
        self.assertContains(response, "Büromaterial und Drucksorten")
        self.assertNotContains(response, "7600 – Büromaterial und Drucksorten")

    def test_read_only_bank_values_have_hidden_submitted_values(self):
        bank_transaction = self.create_transaction(value_date=date(2026, 7, 20))

        response = self.client.get(self.booking_url(bank_transaction))
        body = self.booking_table_body(response)

        self.assertIn(
            'name="entries-0-receipt_group" value="BK"',
            body,
        )
        self.assertIn(
            'name="entries-0-receipt_number" value="7"',
            body,
        )
        self.assertIn(
            'name="entries-0-payment_date" value="2026-07-20"',
            body,
        )
        self.assertIn('value="20.07.2026"', body)

    def test_booking_table_keeps_field_errors_in_their_row_cells(self):
        bank_transaction = self.create_transaction(amount=Decimal("-100.00"))
        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {
                        "booking_text": "",
                        "partner_name": "",
                        "vat_symbol": "",
                        "category": "",
                        "gross_amount": Decimal("-60.00"),
                    },
                    {
                        "booking_text": "Zweite Zeile",
                        "gross_amount": Decimal("-40.00"),
                    },
                ],
                action="finalize",
            ),
        )

        self.assertEqual(response.status_code, 200)
        body = self.booking_table_body(response)
        first_row, second_row = body.split('<tr class="bookkeeping-entry-row', 2)[1:]
        self.assertIn("id_entries-0-booking_text_error", first_row)
        self.assertNotIn("id_entries-1-booking_text_error", second_row)
        self.assertContains(response, "Bitte korrigieren Sie die markierten Felder.")

    def test_bank_form_uses_bk_and_read_only_month_based_receipt_values(self):
        bank_transaction = self.create_transaction(
            value_date=date(2026, 7, 20)
        )

        response = self.client.get(self.booking_url(bank_transaction))

        form = response.context["form"]
        self.assertEqual(form.initial["receipt_group"], RECEIPT_GROUP_BANK)
        self.assertEqual(form.initial["receipt_number"], "7")
        self.assertEqual(form.initial["payment_date"], date(2026, 7, 20))
        self.assertTrue(form.fields["receipt_group"].disabled)
        self.assertTrue(form.fields["receipt_number"].disabled)
        self.assertTrue(form.fields["payment_date"].disabled)
        self.assertContains(response, "BK – Bank")
        self.assertContains(response, 'name="entries-0-receipt_number" value="7"')
        self.assertContains(response, 'name="entries-0-payment_date" value="20.07.2026"')

        self.client.post(
            self.booking_url(bank_transaction),
            {
                "action": "save_draft",
                "receipt_group": "PR",
                "receipt_number": "99",
                "payment_date": "2026-01-01",
                "category": "7600",
            },
        )

        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.receipt_group, RECEIPT_GROUP_BANK)
        self.assertEqual(entry.receipt_number, "7")
        self.assertEqual(entry.payment_date, date(2026, 7, 20))

    def test_belegnummer_uses_unpadded_payment_month(self):
        for payment_date, expected_receipt_number in (
            (date(2026, 1, 15), "1"),
            (date(2026, 7, 15), "7"),
            (date(2026, 12, 15), "12"),
        ):
            bank_transaction = self.create_transaction(
                booking_date=payment_date,
                value_date=payment_date,
            )

            response = self.client.get(
                self.booking_url(
                    bank_transaction,
                    month=payment_date.strftime("%Y-%m"),
                )
            )

            self.assertEqual(
                response.context["form"].initial["receipt_number"],
                expected_receipt_number,
            )

    def test_saved_booking_payment_date_is_not_overwritten(self):
        bank_transaction = self.create_transaction(
            value_date=date(2026, 7, 20)
        )
        self.client.post(
            self.booking_url(bank_transaction),
            {
                "action": "save_draft",
                "category": "7600",
            },
        )
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        entry.payment_date = date(2026, 7, 21)
        entry.save(update_fields=("payment_date",))

        response = self.client.get(self.booking_url(bank_transaction))

        self.assertEqual(
            response.context["form"].initial["payment_date"],
            date(2026, 7, 21),
        )
        self.assertEqual(response.context["form"].initial["receipt_number"], "7")

        self.client.post(
            self.booking_url(bank_transaction),
            {
                "action": "save_draft",
                "payment_date": "2026-01-01",
                "category": "7600",
            },
        )
        entry.refresh_from_db()
        self.assertEqual(entry.payment_date, date(2026, 7, 21))

    def test_vat_and_category_choices_use_central_codes_and_defaults(self):
        bank_transaction = self.create_transaction()
        response = self.client.get(self.booking_url(bank_transaction))
        form = response.context["form"]

        self.assertEqual(form.initial["vat_symbol"], "20")
        self.assertEqual(
            [value for value, _label in form.fields["vat_symbol"].choices],
            ["", "0", "10", "13", "20", "IG"],
        )
        expected_category_choices = sorted(
            [
                (value, category_description(value))
                for value, _label in CATEGORY_CHOICES
            ],
            key=lambda item: item[1].casefold(),
        )
        self.assertEqual(
            list(form.fields["category"].choices),
            [("", ""), *expected_category_choices],
        )
        self.assertContains(response, "Büromaterial und Drucksorten")
        self.assertNotContains(response, "7600 – Büromaterial und Drucksorten")

        self.client.post(
            self.booking_url(bank_transaction),
            {
                "action": "save_draft",
                "vat_symbol": "13",
                "category": "7600",
            },
        )
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.vat_symbol, "13")
        self.assertEqual(entry.category, "7600")

    def test_vat_zero_can_be_created_edited_and_added_dynamically(self):
        bank_transaction = self.create_transaction()

        get_response = self.client.get(self.booking_url(bank_transaction))
        self.assertContains(get_response, '<option value="0">0</option>')
        self.assertIn(
            ("0", "0"),
            get_response.context["form"].fields["vat_symbol"].choices,
        )

        create_response = self.client.post(
            self.booking_url(bank_transaction),
            self.complete_data(bank_transaction, vat_symbol="0"),
        )

        self.assertEqual(create_response.status_code, 302)
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.vat_symbol, "0")

        bank_transaction.refresh_from_db()
        edit_response = self.client.post(
            self.booking_url(bank_transaction, status="reviewed"),
            self.complete_data(bank_transaction, vat_symbol="0"),
        )

        self.assertEqual(edit_response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.vat_symbol, "0")

    def test_empty_vat_symbol_remains_invalid_on_final_review(self):
        bank_transaction = self.create_transaction()

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.complete_data(bank_transaction, vat_symbol=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte korrigieren Sie die markierten Felder.")
        self.assertFalse(
            BookingEntry.objects.filter(bank_transaction=bank_transaction).exists()
        )

    def test_final_review_rejects_invalid_vat_choice(self):
        bank_transaction = self.create_transaction()

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.complete_data(bank_transaction, vat_symbol="99"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookingEntry.objects.filter(bank_transaction=bank_transaction).exists())
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_draft_saves_and_updates_one_booking_entry_without_duplicates(self):
        bank_transaction = self.create_transaction()
        url = self.booking_url(bank_transaction)

        response = self.client.post(
            url,
            {
                "action": "save_draft",
                "receipt_group": "BK",
                "category": "7600",
                "notes": "Erster Entwurf",
            },
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=imported&month=2026-07",
        )
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 1)
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.receipt_group, "BK")
        self.assertEqual(entry.category, "7600")
        self.assertEqual(entry.booking_text, bank_transaction.purpose)
        self.assertEqual(entry.gross_amount, bank_transaction.amount)

        self.client.post(
            url,
            {
                "action": "save_draft",
                "receipt_group": "BK",
                "category": "7380",
                "notes": "Geänderter Entwurf",
            },
        )

        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 1)
        entry.refresh_from_db()
        bank_transaction.refresh_from_db()
        self.assertEqual(entry.category, "7380")
        self.assertEqual(bank_transaction.notes, "Geänderter Entwurf")
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_final_review_moves_unmatched_transaction_directly_to_reviewed(self):
        bank_transaction = self.create_transaction()

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.complete_data(bank_transaction),
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=open&month=2026-07",
        )
        followed_response = self.client.get(response["Location"])
        self.assertContains(followed_response, "Buchung geprüft und abgeschlossen.")
        self.assertNotContains(followed_response, bank_transaction.purpose)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertIsNone(bank_transaction.matched_rule_id)
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 1)

    def test_final_review_redirects_to_open_month_and_keeps_other_open_transactions(self):
        completed_transaction = self.create_transaction(
            booking_date=date(2026, 6, 15),
            purpose="Abgeschlossene Transaktion",
        )
        other_open_transaction = self.create_transaction(
            booking_date=date(2026, 6, 20),
            purpose="Weitere offene Transaktion",
        )
        different_month_transaction = self.create_transaction(
            booking_date=date(2026, 7, 1),
            purpose="Andere offene Transaktion",
        )

        response = self.client.post(
            self.booking_url(completed_transaction, month="2026-06"),
            self.complete_data(completed_transaction),
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=open&month=2026-06",
        )
        followed_response = self.client.get(response["Location"])
        self.assertContains(followed_response, "Buchung geprüft und abgeschlossen.")
        self.assertContains(followed_response, "Weitere offene Transaktion")
        self.assertNotContains(followed_response, "Abgeschlossene Transaktion")
        self.assertNotContains(followed_response, "Andere offene Transaktion")
        self.assertEqual(
            followed_response.context["selected_month"],
            "2026-06",
        )
        different_month_transaction.refresh_from_db()
        self.assertEqual(
            different_month_transaction.status,
            BankTransaction.Status.IMPORTED,
        )

    def test_final_review_keeps_automatic_matching_rule(self):
        rule = MatchingRule.objects.create(
            name="Bürobedarf",
            direction=MatchingRule.Direction.OUTGOING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
        )
        bank_transaction = self.create_transaction(
            partner_iban=rule.iban,
        )
        match_imported_transactions()
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)

        response = self.client.post(
            self.booking_url(bank_transaction, status="matched"),
            self.complete_data(bank_transaction),
        )

        self.assertEqual(response.status_code, 302)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)

    def test_final_review_requires_the_required_booking_fields(self):
        bank_transaction = self.create_transaction()
        response = self.client.post(
            self.booking_url(bank_transaction),
            {
                "action": "finalize",
                "receipt_group": "",
                "payment_date": "",
                "booking_text": "",
                "partner_name": "",
                "gross_amount": "",
                "category": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte korrigieren Sie die markierten Felder.")
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertFalse(BookingEntry.objects.filter(bank_transaction=bank_transaction).exists())

    def test_final_review_requires_exact_signed_transaction_amount(self):
        bank_transaction = self.create_transaction(amount=Decimal("-100.00"))
        response = self.client.post(
            self.booking_url(bank_transaction),
            self.complete_data(bank_transaction, gross_amount="100.00"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Buchungszeilen: 100,00 EUR · Banktransaktion: -100,00 EUR · "
            "Differenz: -200,00 EUR",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertFalse(BookingEntry.objects.filter(bank_transaction=bank_transaction).exists())

    def test_draft_preserves_status_and_month(self):
        bank_transaction = self.create_transaction(status=BankTransaction.Status.MATCHED)

        response = self.client.post(
            self.booking_url(bank_transaction, status="matched", month="2026-07"),
            {"action": "save_draft", "category": "7600"},
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=matched&month=2026-07",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)

    def test_reviewed_booking_data_is_read_only_in_queue_and_editable_via_action(self):
        bank_transaction = self.create_transaction(status=BankTransaction.Status.REVIEWED)
        BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Büromaterial",
            partner_name=bank_transaction.partner_name,
            gross_amount=bank_transaction.amount,
            category="7600",
        )

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "reviewed", "month": "2026-07"},
        )

        self.assertContains(response, "Buchungszeilen")
        self.assertContains(response, "Büromaterial und Drucksorten")
        self.assertNotContains(response, "7600 – Büromaterial und Drucksorten")
        self.assertContains(response, "Bearbeiten")
        self.assertContains(
            response,
            f'href="{self.booking_url(bank_transaction, "reviewed").replace("&", "&amp;")}"',
        )

    def test_booked_transactions_allow_booking_data_editing(self):
        bank_transaction = self.create_transaction(status=BankTransaction.Status.BOOKED)
        BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Vorhanden",
            partner_name=bank_transaction.partner_name,
            gross_amount=bank_transaction.amount,
            category="7600",
        )

        get_response = self.client.get(
            self.booking_url(bank_transaction, status="booked")
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Buchungsdaten bearbeiten")

        response = self.client.post(
            self.booking_url(bank_transaction, status="booked"),
            self.complete_data(bank_transaction, category="7380"),
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=reviewed&month=2026-07",
        )
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.category, "7380")
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.BOOKED)

    def test_booking_action_changes_only_the_selected_transaction(self):
        first = self.create_transaction(partner_name="Erste")
        second = self.create_transaction(partner_name="Zweite")

        self.client.post(
            self.booking_url(first),
            {"action": "save_draft", "category": "7600"},
        )

        self.assertTrue(BookingEntry.objects.filter(bank_transaction=first).exists())
        self.assertFalse(BookingEntry.objects.filter(bank_transaction=second).exists())

    def test_automatic_matching_does_not_overwrite_booking_data(self):
        rule = MatchingRule.objects.create(
            name="Bürobedarf",
            direction=MatchingRule.Direction.OUTGOING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
        )
        bank_transaction = self.create_transaction(partner_iban=rule.iban)
        entry = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=date(2026, 7, 16),
            booking_text="Eigener Buchungstext",
            partner_name="Eigener Partner",
            gross_amount=bank_transaction.amount,
            category="7600",
        )

        match_imported_transactions()

        entry.refresh_from_db()
        bank_transaction.refresh_from_db()
        self.assertEqual(entry.booking_text, "Eigener Buchungstext")
        self.assertEqual(entry.category, "7600")
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)

    def test_matching_templates_prepare_signed_unsaved_booking_rows(self):
        rule = self.create_rule_with_templates(
            Decimal("1096.07"),
            [
                {
                    "booking_text": "Miete",
                    "invoice_number": "RG-1",
                    "partner_name": "Hausverwaltung",
                    "gross_amount": Decimal("868.24"),
                    "vat_symbol": "20",
                    "category": "4850",
                },
                {
                    "booking_text": "Betriebskosten",
                    "invoice_number": "RG-2",
                    "partner_name": "Hausverwaltung",
                    "gross_amount": Decimal("193.92"),
                    "vat_symbol": "10",
                    "category": "4851",
                },
                {
                    "booking_text": "Rest",
                    "invoice_number": "",
                    "partner_name": "Hausverwaltung",
                    "gross_amount": None,
                    "vat_symbol": "20",
                    "category": "4852",
                },
            ],
        )
        bank_transaction = self.create_transaction(
            amount=Decimal("-1096.07"),
            value_date=date(2026, 7, 20),
            matched_rule=rule,
            status=BankTransaction.Status.MATCHED,
        )

        response = self.client.get(self.booking_url(bank_transaction, status="matched"))

        self.assertEqual(response.status_code, 200)
        forms = response.context["formset"].forms
        self.assertEqual(len(forms), 3)
        self.assertEqual(
            [form.initial["gross_amount"] for form in forms],
            [Decimal("-868.24"), Decimal("-193.92"), Decimal("-33.91")],
        )
        self.assertEqual(forms[0].initial["receipt_group"], "BK")
        self.assertEqual(forms[0].initial["receipt_number"], "7")
        self.assertEqual(forms[0].initial["payment_date"], date(2026, 7, 20))
        self.assertEqual(forms[1].initial["booking_text"], "Betriebskosten")
        self.assertEqual(forms[2].initial["category"], "4852")
        self.assertEqual(BookingEntry.objects.count(), 0)
        self.assertContains(response, "Buchungszeilen")
        self.assertContains(response, "Buchungszeile hinzufügen")

    def test_saved_template_snapshot_creates_independent_booking_entries(self):
        rule = self.create_rule_with_templates(
            Decimal("100.00"),
            [
                {
                    "booking_text": "Teil 1",
                    "invoice_number": "RG-1",
                    "partner_name": "Lieferant 1",
                    "gross_amount": Decimal("60.00"),
                    "vat_symbol": "20",
                    "category": "7600",
                },
                {
                    "booking_text": "Teil 2",
                    "invoice_number": "RG-2",
                    "partner_name": "Lieferant 2",
                    "gross_amount": Decimal("40.00"),
                    "vat_symbol": "20",
                    "category": "7380",
                },
            ],
        )
        bank_transaction = self.create_transaction(
            amount=Decimal("-100.00"),
            matched_rule=rule,
            status=BankTransaction.Status.MATCHED,
        )

        response = self.client.post(
            self.booking_url(bank_transaction, status="matched"),
            self.entry_formset_data(
                bank_transaction,
                [
                    {
                        "booking_text": "Teil 1",
                        "invoice_number": "RG-1",
                        "partner_name": "Lieferant 1",
                        "gross_amount": Decimal("-60.00"),
                        "category": "7600",
                    },
                    {
                        "booking_text": "Teil 2",
                        "invoice_number": "RG-2",
                        "partner_name": "Lieferant 2",
                        "gross_amount": Decimal("-40.00"),
                        "category": "7380",
                    },
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(
            set(
                BookingEntry.objects.filter(bank_transaction=bank_transaction)
                .values_list("booking_text", "invoice_number", "gross_amount")
            ),
            {
                ("Teil 1", "RG-1", Decimal("-60.00")),
                ("Teil 2", "RG-2", Decimal("-40.00")),
            },
        )

        response = self.client.get(self.booking_url(bank_transaction, status="matched"))

        self.assertEqual(
            set(
                form.initial["booking_text"]
                for form in response.context["formset"].forms
            ),
            {"Teil 1", "Teil 2"},
        )

    def test_matching_template_snapshot_uses_transaction_fallbacks(self):
        rule = self.create_rule_with_templates(
            Decimal("100.00"),
            [
                {
                    "booking_text": "",
                    "invoice_number": "",
                    "partner_name": "",
                    "gross_amount": Decimal("100.00"),
                    "vat_symbol": "20",
                    "category": "7600",
                }
            ],
            direction=BankTransaction.Direction.INCOMING,
        )
        bank_transaction = self.create_transaction(
            amount=Decimal("100.00"),
            direction=BankTransaction.Direction.INCOMING,
            value_date=None,
            matched_rule=rule,
            purpose="Mietzahlung Juli",
            partner_name="Mieter",
            booking_date=date(2026, 7, 15),
            status=BankTransaction.Status.MATCHED,
        )

        response = self.client.get(self.booking_url(bank_transaction, status="matched"))

        form = response.context["formset"].forms[0]
        self.assertEqual(form.initial["booking_text"], "Mietzahlung Juli")
        self.assertEqual(form.initial["invoice_number"], "")
        self.assertEqual(form.initial["partner_name"], "Mieter")
        self.assertEqual(form.initial["gross_amount"], Decimal("100.00"))
        self.assertEqual(form.initial["payment_date"], date(2026, 7, 15))

    def test_invalid_template_snapshot_shows_error_and_allows_manual_rows(self):
        rule = self.create_rule_with_templates(
            Decimal("100.00"),
            [
                {
                    "booking_text": "Zu klein",
                    "invoice_number": "",
                    "partner_name": "Lieferant",
                    "gross_amount": Decimal("60.00"),
                    "vat_symbol": "20",
                    "category": "7600",
                }
            ],
        )
        bank_transaction = self.create_transaction(
            matched_rule=rule,
            status=BankTransaction.Status.MATCHED,
        )

        response = self.client.get(self.booking_url(bank_transaction, status="matched"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nicht verwendbar")
        self.assertEqual(response.context["formset"].total_form_count(), 1)
        self.assertFalse(BookingEntry.objects.exists())

        response = self.client.post(
            self.booking_url(bank_transaction, status="matched"),
            self.complete_data(bank_transaction, gross_amount="100.00"),
        )

        self.assertEqual(response.status_code, 302)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(
            BookingEntry.objects.get(bank_transaction=bank_transaction).gross_amount,
            Decimal("100.00"),
        )

    def test_draft_updates_adds_and_deletes_booking_rows_without_duplicates(self):
        bank_transaction = self.create_transaction()
        existing = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Alt",
            partner_name=bank_transaction.partner_name,
            gross_amount=Decimal("60.00"),
            vat_symbol="20",
            category="7600",
        )

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"id": existing.pk, "booking_text": "Geändert", "gross_amount": Decimal("60.00")},
                    {"booking_text": "Neu", "gross_amount": Decimal("40.00")},
                ],
                initial_forms=1,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 2)
        existing.refresh_from_db()
        self.assertEqual(existing.booking_text, "Geändert")
        new_entry = BookingEntry.objects.exclude(pk=existing.pk).get(
            bank_transaction=bank_transaction
        )

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"id": existing.pk, "delete": True},
                    {"id": new_entry.pk, "booking_text": "Neu gespeichert", "gross_amount": Decimal("40.00")},
                ],
                initial_forms=2,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(BookingEntry.objects.filter(pk=existing.pk).exists())
        new_entry.refresh_from_db()
        self.assertEqual(new_entry.booking_text, "Neu gespeichert")
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 1)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_unmatched_transaction_can_be_finalized_with_multiple_manual_rows(self):
        bank_transaction = self.create_transaction(amount=Decimal("-100.00"))

        response = self.client.get(self.booking_url(bank_transaction))

        self.assertEqual(response.context["formset"].total_form_count(), 1)
        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"booking_text": "Teil 1", "gross_amount": Decimal("-60.00")},
                    {"booking_text": "Teil 2", "gross_amount": Decimal("-40.00")},
                ],
                action="finalize",
                notes="Mehrzeilige Prüfung",
            ),
        )

        self.assertEqual(response.status_code, 302)
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertIsNone(bank_transaction.matched_rule_id)
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 2)

    def test_rounding_difference_of_positive_one_cent_is_added_to_largest_row(self):
        bank_transaction = self.create_transaction(amount=Decimal("100.01"))

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("60.00")},
                    {"gross_amount": Decimal("40.00")},
                ],
                action="finalize",
            ),
            follow=True,
        )

        self.assertContains(
            response,
            "Rundungsdifferenz von 0,01 EUR wurde in der größten "
            "Buchungszeile ausgeglichen.",
        )
        entries = list(
            BookingEntry.objects.filter(bank_transaction=bank_transaction)
            .order_by("created_at", "id")
            .values_list("gross_amount", flat=True)
        )
        self.assertEqual(entries, [Decimal("60.01"), Decimal("40.00")])
        self.assertEqual(sum(entries, Decimal("0")), bank_transaction.amount)

        csv_response = self.client.post(
            reverse("bookkeeping_overview"),
            {
                "action": "export_csv",
                "status": BankTransaction.Status.REVIEWED,
                "period": "2026-Q3",
            },
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("60,01", csv_response.content.decode("utf-8-sig"))

    def test_rounding_difference_of_negative_one_cent_is_added_to_negative_rows(self):
        bank_transaction = self.create_transaction(amount=Decimal("-100.01"))

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("-60.00")},
                    {"gross_amount": Decimal("-40.00")},
                ],
                action="finalize",
            ),
            follow=True,
        )

        self.assertContains(
            response,
            "Rundungsdifferenz von -0,01 EUR wurde in der größten "
            "Buchungszeile ausgeglichen.",
        )
        entries = list(
            BookingEntry.objects.filter(bank_transaction=bank_transaction)
            .order_by("created_at", "id")
            .values_list("gross_amount", flat=True)
        )
        self.assertEqual(entries, [Decimal("-60.01"), Decimal("-40.00")])
        self.assertEqual(sum(entries, Decimal("0")), bank_transaction.amount)

    def test_rounding_difference_uses_first_row_when_absolute_amounts_tie(self):
        bank_transaction = self.create_transaction(amount=Decimal("100.01"))

        self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("50.00")},
                    {"gross_amount": Decimal("50.00")},
                ],
                action="finalize",
            ),
        )

        entries = list(
            BookingEntry.objects.filter(bank_transaction=bank_transaction)
            .order_by("created_at", "id")
            .values_list("gross_amount", flat=True)
        )
        self.assertEqual(entries, [Decimal("50.01"), Decimal("50.00")])

    def test_two_cent_difference_is_rejected_with_concrete_amounts(self):
        bank_transaction = self.create_transaction(amount=Decimal("100.02"))

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("60.00")},
                    {"gross_amount": Decimal("40.00")},
                ],
                action="finalize",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Buchungszeilen: 100,00 EUR · Banktransaktion: 100,02 EUR · "
            "Differenz: 0,02 EUR",
        )
        self.assertFalse(BookingEntry.objects.exists())
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_draft_save_does_not_apply_rounding_difference(self):
        bank_transaction = self.create_transaction(amount=Decimal("100.01"))

        self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("60.00")},
                    {"gross_amount": Decimal("40.00")},
                ],
                action="save_draft",
            ),
        )

        entries = list(
            BookingEntry.objects.filter(bank_transaction=bank_transaction)
            .order_by("created_at", "id")
            .values_list("gross_amount", flat=True)
        )
        self.assertEqual(entries, [Decimal("60.00"), Decimal("40.00")])
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_finalization_rejects_wrong_signed_sum_for_multiple_rows(self):
        bank_transaction = self.create_transaction(amount=Decimal("-100.00"))

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"gross_amount": Decimal("-60.00")},
                    {"gross_amount": Decimal("-30.00")},
                ],
                action="finalize",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Differenz: -10,00 EUR")
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertFalse(BookingEntry.objects.exists())

    def test_reviewed_transaction_loads_and_edits_all_saved_booking_rows(self):
        rule = self.create_rule_with_templates(
            Decimal("100.00"),
            [
                {
                    "booking_text": "Vorlage 1",
                    "invoice_number": "",
                    "partner_name": "Lieferant",
                    "gross_amount": Decimal("60.00"),
                    "vat_symbol": "20",
                    "category": "7600",
                },
                {
                    "booking_text": "Vorlage 2",
                    "invoice_number": "",
                    "partner_name": "Lieferant",
                    "gross_amount": Decimal("40.00"),
                    "vat_symbol": "20",
                    "category": "7380",
                },
            ],
        )
        bank_transaction = self.create_transaction(
            status=BankTransaction.Status.REVIEWED,
            matched_rule=rule,
        )
        first = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Gespeichert 1",
            partner_name="Eigener Partner",
            gross_amount=Decimal("60.00"),
            vat_symbol="20",
            category="7600",
        )
        second = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Gespeichert 2",
            partner_name="Eigener Partner",
            gross_amount=Decimal("40.00"),
            vat_symbol="20",
            category="7380",
        )

        response = self.client.get(self.booking_url(bank_transaction, status="reviewed"))

        self.assertEqual(len(response.context["formset"].forms), 2)
        self.assertEqual(
            sorted(
                form.initial["booking_text"]
                for form in response.context["formset"].forms
            ),
            ["Gespeichert 1", "Gespeichert 2"],
        )
        response = self.client.post(
            self.booking_url(bank_transaction, status="reviewed"),
            self.entry_formset_data(
                bank_transaction,
                [
                    {"id": first.pk, "booking_text": "Bearbeitet 1", "gross_amount": Decimal("60.00")},
                    {"id": second.pk, "booking_text": "Bearbeitet 2", "gross_amount": Decimal("40.00")},
                ],
                initial_forms=2,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 2)
        self.assertEqual(
            sorted(
                BookingEntry.objects.filter(bank_transaction=bank_transaction)
                .order_by("created_at", "id")
                .values_list("booking_text", flat=True)
            ),
            ["Bearbeitet 1", "Bearbeitet 2"],
        )

    def test_booking_formset_rejects_entry_from_another_transaction(self):
        bank_transaction = self.create_transaction()
        other_transaction = self.create_transaction(partner_name="Andere Transaktion")
        other_entry = BookingEntry.objects.create(
            bank_transaction=other_transaction,
            receipt_group="BK",
            payment_date=other_transaction.booking_date,
            booking_text="Fremde Zeile",
            partner_name=other_transaction.partner_name,
            gross_amount=other_transaction.amount,
            vat_symbol="20",
            category="7600",
        )

        response = self.client.post(
            self.booking_url(bank_transaction),
            self.entry_formset_data(
                bank_transaction,
                [{"id": other_entry.pk, "gross_amount": bank_transaction.amount}],
                initial_forms=1,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookingEntry.objects.filter(bank_transaction=bank_transaction).exists())
        other_entry.refresh_from_db()
        self.assertEqual(other_entry.booking_text, "Fremde Zeile")


class BankTransactionModelTests(TestCase):
    def build_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 1, 1),
            "amount": Decimal("12.34"),
            "direction": BankTransaction.Direction.INCOMING,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def test_default_status_is_imported(self):
        transaction = self.build_transaction()

        self.assertEqual(transaction.status, BankTransaction.Status.IMPORTED)

    def test_status_choices(self):
        self.assertEqual(
            dict(BankTransaction.Status.choices),
            {
                "imported": "Eingelesen",
                "matched": "Zugeordnet",
                "reviewed": "Geprüft",
                "booked": "Gebucht",
            },
        )

    def test_direction_choices(self):
        self.assertEqual(
            dict(BankTransaction.Direction.choices),
            {"incoming": "Eingang", "outgoing": "Ausgang"},
        )

    def test_positive_and_negative_amounts_are_supported(self):
        positive = self.build_transaction(
            amount=Decimal("123.45"),
        )
        negative = self.build_transaction(
            amount=Decimal("-67.89"),
            direction=BankTransaction.Direction.OUTGOING,
        )

        self.assertEqual(positive.amount, Decimal("123.45"))
        self.assertEqual(negative.amount, Decimal("-67.89"))

    def test_uuid_is_generated_automatically(self):
        transaction = self.build_transaction()

        self.assertIsInstance(transaction.id, uuid.UUID)
        self.assertFalse(BankTransaction._meta.get_field("id").editable)

    def test_transactions_receive_different_uuids(self):
        first = self.build_transaction()
        second = self.build_transaction()

        self.assertNotEqual(first.id, second.id)

    def test_default_source_is_bank_import(self):
        transaction = self.build_transaction()

        self.assertEqual(transaction.source, BankTransaction.Source.BANK_IMPORT)

    def test_manual_source_is_supported(self):
        transaction = self.build_transaction(source=BankTransaction.Source.MANUAL)

        self.assertEqual(transaction.source, BankTransaction.Source.MANUAL)


class TransactionMatchingTests(TestCase):
    iban = "AT611904300234573201"

    def create_transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 1, 1),
            "partner_iban": self.iban,
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.IMPORTED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def create_rule(self, **overrides):
        values = {
            "name": "Mietzahlung",
            "direction": MatchingRule.Direction.INCOMING,
            "iban": self.iban,
            "expected_amount": Decimal("100.00"),
        }
        values.update(overrides)
        return MatchingRule.objects.create(**values)

    def add_template(self, rule, **overrides):
        values = {
            "matching_rule": rule,
            "position": 1,
            "booking_text": "Automatische Buchung",
            "invoice_number": "RG-1",
            "partner_name": "Automatischer Partner",
            "gross_amount": Decimal("100.00"),
            "vat_symbol": "20",
            "category": "7600",
        }
        values.update(overrides)
        return MatchingRuleBookingTemplate.objects.create(**values)

    def upload(self, payload):
        content = json.dumps(payload).encode()
        uploaded_file = SimpleUploadedFile(
            "transactions.json",
            content,
            content_type="application/json",
        )
        return self.client.post(
            reverse("bookkeeping_overview"),
            {"json_file": uploaded_file},
            follow=True,
        )

    def test_one_exact_active_rule_matches_transaction(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)

    def test_successful_exact_match_creates_template_rows_and_is_booking_ready(self):
        rule = self.create_rule()
        self.add_template(rule)
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(result.auto_ready_count, 1)
        self.assertEqual(result.incomplete_count, 0)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertEqual(entry.booking_text, "Automatische Buchung")
        self.assertEqual(entry.gross_amount, Decimal("100.00"))

        second_result = match_imported_transactions()

        self.assertEqual(second_result, (0, 0, 0))
        self.assertEqual(
            BookingEntry.objects.filter(bank_transaction=bank_transaction).count(),
            1,
        )

    def test_successful_regex_match_creates_template_rows(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="EVN",
            iban="",
        )
        self.add_template(rule, gross_amount=None)
        bank_transaction = self.create_transaction(
            partner_name="EVN Vertrieb GmbH",
            amount=Decimal("12.34"),
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(result.auto_ready_count, 1)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(entry.gross_amount, Decimal("12.34"))

    def test_automatic_snapshot_calculates_signed_fixed_and_rest_rows(self):
        rule = self.create_rule(
            expected_amount=Decimal("100.00"),
            direction=BankTransaction.Direction.OUTGOING,
        )
        self.add_template(rule, gross_amount=Decimal("60.00"), position=1)
        self.add_template(
            rule,
            position=2,
            booking_text="Restbetrag",
            invoice_number="",
            gross_amount=None,
            category="7380",
        )
        bank_transaction = self.create_transaction(
            amount=Decimal("-100.00"),
            direction=BankTransaction.Direction.OUTGOING,
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        entries = list(
            BookingEntry.objects.filter(bank_transaction=bank_transaction)
            .order_by("created_at", "id")
            .values_list("gross_amount", flat=True)
        )
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(entries, [Decimal("-60.00"), Decimal("-40.00")])
        self.assertEqual(sum(entries, Decimal("0")), bank_transaction.amount)

    def test_missing_templates_leave_successful_match_manual(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result.auto_ready_count, 0)
        self.assertEqual(result.incomplete_count, 1)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertFalse(BookingEntry.objects.exists())

    def test_invalid_runtime_template_leaves_no_partial_rows(self):
        rule = self.create_rule()
        self.add_template(rule, gross_amount=Decimal("60.00"))
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result.auto_ready_count, 0)
        self.assertEqual(result.incomplete_count, 1)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertFalse(BookingEntry.objects.exists())

    def test_existing_booking_draft_is_not_overwritten_or_finalized(self):
        rule = self.create_rule()
        self.add_template(rule)
        bank_transaction = self.create_transaction()
        entry = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            receipt_group="BK",
            payment_date=bank_transaction.booking_date,
            booking_text="Manueller Entwurf",
            partner_name="Eigener Partner",
            gross_amount=Decimal("100.00"),
            vat_symbol="13",
            category="7380",
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(result.auto_ready_count, 0)
        self.assertEqual(result.incomplete_count, 1)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(entry.booking_text, "Manueller Entwurf")
        self.assertEqual(entry.category, "7380")

    def test_exact_matching_uses_the_stored_decimal_amount(self):
        rule = self.create_rule(expected_amount=Decimal("1096.07"))
        bank_transaction = self.create_transaction(amount=Decimal("1096.07"))

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(bank_transaction.amount, Decimal("1096.07"))
        self.assertEqual(rule.expected_amount, Decimal("1096.07"))
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_different_amount_does_not_match(self):
        self.create_rule(expected_amount=Decimal("872.03"))
        bank_transaction = self.create_transaction(amount=Decimal("46.46"))

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_different_iban_does_not_match(self):
        self.create_rule()
        bank_transaction = self.create_transaction(
            partner_iban="DE89370400440532013000"
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_different_direction_does_not_match(self):
        self.create_rule(direction=MatchingRule.Direction.INCOMING)
        bank_transaction = self.create_transaction(
            amount=Decimal("-100.00"),
            direction=BankTransaction.Direction.OUTGOING,
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_rule_without_expected_amount_does_not_match(self):
        self.create_rule(expected_amount=None)
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_transaction_iban_is_normalized_for_matching(self):
        self.create_rule(iban="at61 1904 3002 3457 3201")
        bank_transaction = self.create_transaction(
            partner_iban=" at61 1904 3002 3457 3201 "
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)

    def test_regex_matches_partner_name(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern=r"\bEVN\b",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_name="EVN Vertrieb GmbH",
            amount=Decimal("872.03"),
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_regex_matches_purpose(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern=r"Bahngasse 14",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_name="Versorger",
            purpose="Bahngasse 14 ABR 716050222013",
            amount=Decimal("12.34"),
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_regex_matching_is_case_insensitive(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="evn vertrieb",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_name="EVN VERTRIEB GMBH",
            amount=Decimal("999.99"),
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_regex_rule_may_omit_iban(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="EVN",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_iban="DE89370400440532013000",
            partner_name="EVN",
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_filled_regex_iban_must_match(self):
        self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="EVN",
            iban="DE89370400440532013000",
        )
        bank_transaction = self.create_transaction(partner_name="EVN")

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_regex_direction_must_match(self):
        self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            direction=MatchingRule.Direction.OUTGOING,
            expected_amount=None,
            text_pattern="EVN",
            iban="",
        )
        bank_transaction = self.create_transaction(partner_name="EVN")

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_regex_ignores_amount(self):
        rule = self.create_rule(
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="EVN",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_name="EVN",
            amount=Decimal("0.01"),
        )

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)

    def test_exact_rule_has_priority_over_regex_rule(self):
        exact_rule = self.create_rule(name="Exakt", expected_amount=Decimal("100.00"))
        self.create_rule(
            name="Regex",
            match_type=MatchingRule.MatchType.REGEX,
            expected_amount=None,
            text_pattern="Miete",
            iban="",
        )
        bank_transaction = self.create_transaction(
            partner_name="Miete",
            amount=Decimal("100.00"),
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (1, 0, 0))
        self.assertEqual(bank_transaction.matched_rule_id, exact_rule.id)

    def test_multiple_regex_rules_remain_ambiguous(self):
        for name in ("Regex 1", "Regex 2"):
            self.create_rule(
                name=name,
                match_type=MatchingRule.MatchType.REGEX,
                expected_amount=None,
                text_pattern="EVN",
                iban="",
            )
        bank_transaction = self.create_transaction(partner_name="EVN")

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 0, 1))
        self.assertIsNone(bank_transaction.matched_rule_id)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_no_matching_rule_keeps_imported_status(self):
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(bank_transaction.matched_rule_id)

    def test_inactive_rule_is_ignored(self):
        self.create_rule(active=False)
        bank_transaction = self.create_transaction()

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_wrong_direction_rule_is_ignored(self):
        self.create_rule(direction=MatchingRule.Direction.OUTGOING)
        bank_transaction = self.create_transaction()

        match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)

    def test_multiple_matching_rules_remain_ambiguous(self):
        self.create_rule(name="Regel 1")
        self.create_rule(name="Regel 2")
        bank_transaction = self.create_transaction()

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 0, 1))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(bank_transaction.matched_rule_id)

    def test_reviewed_and_booked_transactions_remain_unchanged(self):
        rule = self.create_rule()
        reviewed = self.create_transaction(status=BankTransaction.Status.REVIEWED)
        booked = self.create_transaction(status=BankTransaction.Status.BOOKED)

        result = match_imported_transactions()

        reviewed.refresh_from_db()
        booked.refresh_from_db()
        self.assertEqual(result, (0, 0, 0))
        self.assertEqual(reviewed.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(booked.status, BankTransaction.Status.BOOKED)
        self.assertIsNone(reviewed.matched_rule_id)
        self.assertIsNone(booked.matched_rule_id)
        self.assertEqual(rule.transactions.count(), 0)

    def test_rematching_does_not_re_evaluate_matched_transactions(self):
        rule = self.create_rule(expected_amount=Decimal("872.03"))
        bank_transaction = self.create_transaction(
            amount=Decimal("46.46"),
            status=BankTransaction.Status.MATCHED,
            matched_rule=rule,
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 0, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)

    def test_transactions_are_not_aggregated_for_matching(self):
        self.create_rule(expected_amount=Decimal("100.00"))
        first = self.create_transaction(amount=Decimal("50.00"))
        second = self.create_transaction(amount=Decimal("50.00"))

        result = match_imported_transactions()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(result, (0, 2, 0))
        self.assertEqual(first.status, BankTransaction.Status.IMPORTED)
        self.assertEqual(second.status, BankTransaction.Status.IMPORTED)

    def test_import_runs_matching_automatically(self):
        rule = self.create_rule()
        self.add_template(rule)
        response = self.upload(
            [
                {
                    "booking": "2026-02-01",
                    "partnerName": "Mieter",
                    "partnerAccount": {"iban": " at61 1904 3002 3457 3201 "},
                    "amount": {
                        "value": 10000,
                        "precision": 2,
                        "currency": "EUR",
                    },
                }
            ]
        )

        bank_transaction = BankTransaction.objects.get()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertContains(
            response,
            "1 automatisch buchungsfertig, 0 zugeordnet, aber Buchungsdaten "
            "unvollständig, 0 ohne Treffer, 0 mehrdeutig.",
        )
        matched_response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": BankTransaction.Status.REVIEWED, "month": "2026-02"},
        )
        self.assertContains(matched_response, "Matching-Regel")
        self.assertContains(matched_response, rule.name)

    def test_manual_matching_button_matches_existing_transactions(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction()

        response = self.client.post(
            reverse("bookkeeping_overview"),
            {"action": "run_matching"},
            follow=True,
        )

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.id)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertContains(
            response,
            "0 automatisch buchungsfertig, 1 zugeordnet, aber Buchungsdaten "
            "unvollständig, 0 ohne Treffer, 0 mehrdeutig.",
        )


class MatchingRuleTests(TestCase):
    url_name = "matching_rule_list"
    iban = "AT611904300234573201"

    def post_rule(self, **overrides):
        values = {
            "action": "create_matching_rule",
            "name": "Mietzahlung",
            "direction": MatchingRule.Direction.INCOMING,
            "match_type": MatchingRule.MatchType.EXACT,
            "iban": self.iban,
            "expected_amount": "850.00",
            "active": "on",
        }
        values.update(overrides)
        return self.client.post(reverse(self.url_name), values)

    def test_rule_creation_normalizes_iban_and_redirects_to_section(self):
        response = self.post_rule(iban=" at61 1904 3002 3457 3201 ")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/bookkeeping/matching-rules/")
        rule = MatchingRule.objects.get()
        self.assertEqual(rule.iban, self.iban)
        self.assertEqual(rule.name, "Mietzahlung")
        self.assertEqual(rule.direction, MatchingRule.Direction.INCOMING)
        self.assertEqual(rule.match_type, MatchingRule.MatchType.EXACT)
        self.assertTrue(rule.active)

    def test_rule_note_can_be_created_and_edited(self):
        response = self.post_rule(notes="Für Mietzahlungen im Voraus.")

        self.assertEqual(response.status_code, 302)
        rule = MatchingRule.objects.get()
        self.assertEqual(rule.notes, "Für Mietzahlungen im Voraus.")

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": rule.name,
                "direction": rule.direction,
                "match_type": rule.match_type,
                "iban": rule.iban,
                "expected_amount": "850.00",
                "text_pattern": "",
                "notes": "Geänderte Regelnotiz.",
                "active": "on",
            },
            follow=True,
        )

        rule.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rule.notes, "Geänderte Regelnotiz.")
        self.assertContains(response, "Geänderte Regelnotiz.")

    def test_rule_note_survives_validation_errors(self):
        response = self.post_rule(
            iban="not-an-iban",
            notes="Hinweis trotz Fehler",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(response, "Hinweis trotz Fehler")
        self.assertContains(response, 'id="id_notes"')

    def test_invalid_iban_is_rejected(self):
        response = self.post_rule(iban="not-an-iban")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Bitte eine IBAN mit 15 bis 34 alphanumerischen Zeichen eingeben.",
        )

    def test_invalid_iban_error_is_rendered_once_with_invalid_field_state(self):
        response = self.post_rule(iban="not-an-iban", name="Eingetragene Regel")
        content = response.content.decode()
        message = "Bitte eine IBAN mit 15 bis 34 alphanumerischen Zeichen eingeben."

        self.assertEqual(content.count(message), 1)
        self.assertContains(response, 'id="id_iban_error"')
        self.assertContains(response, 'name="iban"')
        self.assertContains(response, 'class="form-control is-invalid"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="Eingetragene Regel"')
        self.assertContains(response, "Bitte korrigieren Sie die markierten Felder.")

    def test_missing_expected_amount_error_is_rendered_once_and_value_is_preserved(self):
        response = self.post_rule(expected_amount="", iban="AT611904300234573201")
        content = response.content.decode()
        message = "Für exakte Regeln ist ein erwarteter Betrag erforderlich."

        self.assertEqual(content.count(message), 1)
        self.assertContains(response, 'id="id_expected_amount_error"')
        self.assertContains(response, 'name="expected_amount"')
        self.assertContains(response, 'class="form-control is-invalid"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="AT611904300234573201"')

    def test_expected_amount_is_required(self):
        response = self.post_rule(expected_amount="")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Für exakte Regeln ist ein erwarteter Betrag erforderlich.",
        )

    def test_expected_amount_must_be_positive(self):
        response = self.post_rule(expected_amount="-10.00")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Der erwartete Betrag muss positiv sein.",
        )

    def test_invalid_regex_is_rejected(self):
        response = self.post_rule(
            match_type=MatchingRule.MatchType.REGEX,
            iban="",
            expected_amount="",
            text_pattern="[ungueltig",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Das Textmuster ist kein gültiger regulärer Ausdruck.",
        )

    def test_regex_rule_form_allows_empty_iban_and_amount(self):
        response = self.post_rule(
            match_type=MatchingRule.MatchType.REGEX,
            iban="",
            expected_amount="",
            text_pattern=r"\bEVN\b",
        )

        self.assertEqual(response.status_code, 302)
        rule = MatchingRule.objects.get()
        self.assertEqual(rule.match_type, MatchingRule.MatchType.REGEX)
        self.assertEqual(rule.iban, "")
        self.assertIsNone(rule.expected_amount)

    def test_duplicate_ibans_are_allowed(self):
        self.post_rule(name="Regel 1")
        self.post_rule(name="Regel 2", direction=MatchingRule.Direction.OUTGOING)

        self.assertEqual(MatchingRule.objects.count(), 2)

    def test_rules_appear_on_bookkeeping_page(self):
        MatchingRule.objects.create(
            name="Miete",
            direction=MatchingRule.Direction.INCOMING,
            iban=self.iban,
            expected_amount=Decimal("1250.00"),
        )

        response = self.client.get(reverse(self.url_name))

        self.assertContains(response, "Miete")
        self.assertContains(response, self.iban)
        self.assertContains(response, "1.250,00")
        self.assertContains(response, "Eingang")
        self.assertContains(response, "Aktiv")

    def test_rules_table_displays_match_type_and_pattern(self):
        MatchingRule.objects.create(
            name="EVN",
            direction=MatchingRule.Direction.OUTGOING,
            match_type=MatchingRule.MatchType.REGEX,
            iban="",
            expected_amount=None,
            text_pattern=r"\bEVN\b",
        )

        response = self.client.get(reverse(self.url_name))

        self.assertContains(response, "Regeltyp")
        self.assertContains(response, "Textmuster")
        self.assertContains(response, "Exakter Betrag")
        self.assertContains(response, "\\bEVN\\b")

    def test_bookkeeping_page_has_no_matching_rule_form(self):
        response = self.client.get(reverse("bookkeeping_overview"))

        self.assertNotContains(response, "Erwarteter Betrag")
        self.assertNotContains(response, "Textmuster")
        self.assertNotContains(response, 'href="#matching-rules"')

    def test_sidebar_links_and_active_highlighting(self):
        overview_response = self.client.get(reverse("bookkeeping_overview"))
        rules_response = self.client.get(reverse("matching_rule_list"))

        for response in (overview_response, rules_response):
            self.assertContains(response, 'href="/bookkeeping/"')
            self.assertContains(
                response,
                'href="/bookkeeping/?status=bank_import#bank-import"',
            )
            self.assertContains(response, "Offen")
            self.assertNotContains(response, ">Zugeordnet<")
            self.assertContains(response, "Buchungsfertig")
            self.assertNotContains(response, ">Exportiert<")
            self.assertContains(response, 'href="/bookkeeping/matching-rules/"')
        self.assertContains(
            overview_response,
            'href="/bookkeeping/?status=open" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
        )
        self.assertContains(
            rules_response,
            'href="/bookkeeping/matching-rules/" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
        )


class MatchingRuleManagementTests(TestCase):
    iban = "AT611904300234573201"

    def create_rule(self, **overrides):
        values = {
            "name": "Mietzahlung",
            "direction": MatchingRule.Direction.INCOMING,
            "match_type": MatchingRule.MatchType.EXACT,
            "iban": self.iban,
            "expected_amount": Decimal("100.00"),
        }
        values.update(overrides)
        return MatchingRule.objects.create(**values)

    def create_transaction(self, rule, **overrides):
        values = {
            "booking_date": date(2026, 1, 1),
            "partner_iban": self.iban,
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.MATCHED,
            "matched_rule": rule,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def test_matching_rules_page_displays_form_and_rule_list(self):
        rule = self.create_rule()

        response = self.client.get(reverse("matching_rule_list"))

        self.assertContains(response, "Matching-Regeln")
        self.assertContains(response, "Regeln für die automatische Zuordnung")
        self.assertContains(response, "Bezeichnung")
        self.assertContains(response, rule.name)
        self.assertContains(response, "Aktionen")
        self.assertContains(response, "Bearbeiten")
        self.assertContains(response, "Löschen")
        self.assertContains(response, "Zurück zu den Transaktionen")

    def test_edit_prefills_and_saves_rule(self):
        rule = self.create_rule()

        response = self.client.get(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Mietzahlung"')
        self.assertContains(response, 'value="100,00"')

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": "Geänderte Regel",
                "direction": MatchingRule.Direction.OUTGOING,
                "match_type": MatchingRule.MatchType.EXACT,
                "iban": self.iban,
                "expected_amount": "250.00",
                "text_pattern": "",
                "active": "on",
            },
            follow=True,
        )

        rule.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matching-Regel gespeichert.")
        self.assertEqual(rule.name, "Geänderte Regel")
        self.assertEqual(rule.direction, MatchingRule.Direction.OUTGOING)
        self.assertEqual(rule.expected_amount, Decimal("250.00"))

    def test_edit_validation_is_preserved(self):
        rule = self.create_rule()

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": "Regex-Regel",
                "direction": MatchingRule.Direction.INCOMING,
                "match_type": MatchingRule.MatchType.REGEX,
                "iban": "",
                "expected_amount": "",
                "text_pattern": "[ungueltig",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "kein gültiger regulärer Ausdruck")

    def test_edit_validation_uses_the_same_inline_error_presentation(self):
        rule = self.create_rule()

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": "Geänderte Regel",
                "direction": MatchingRule.Direction.INCOMING,
                "match_type": MatchingRule.MatchType.EXACT,
                "iban": "not-an-iban",
                "expected_amount": "100.00",
                "text_pattern": "",
                "active": "on",
            },
        )

        content = response.content.decode()
        message = "Bitte eine IBAN mit 15 bis 34 alphanumerischen Zeichen eingeben."
        self.assertEqual(content.count(message), 1)
        self.assertContains(response, 'id="id_iban_error"')
        self.assertContains(response, 'class="form-control is-invalid"')
        self.assertContains(response, "Bitte korrigieren Sie die markierten Felder.")
        self.assertContains(response, 'value="Geänderte Regel"')

    def test_used_rule_cannot_be_edited_and_keeps_linked_matched_transactions(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction(rule)

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                "name": rule.name,
                "direction": rule.direction,
                "match_type": rule.match_type,
                "iban": rule.iban,
                "expected_amount": "200.00",
                "text_pattern": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
        )
        bank_transaction.refresh_from_db()
        rule.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(rule.expected_amount, Decimal("100.00"))

    def test_edit_is_blocked_for_reviewed_or_booked_transactions(self):
        rule = self.create_rule()
        self.create_transaction(rule, status=BankTransaction.Status.REVIEWED)

        response = self.client.get(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            follow=True,
        )

        self.assertContains(response, "bereits verwendet")
        self.assertContains(response, "schreibgeschützt")

    def test_delete_get_shows_confirmation_without_deleting(self):
        rule = self.create_rule()

        response = self.client.get(
            reverse("matching_rule_delete", kwargs={"pk": rule.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matching-Regel „Mietzahlung“ wirklich löschen?")
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())

    def test_used_rule_cannot_be_deleted_and_keeps_matched_transactions(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction(rule)
        delete_url = reverse("matching_rule_delete", kwargs={"pk": rule.pk})

        self.client.get(delete_url)
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())

        response = self.client.post(delete_url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertContains(response, "bereits verwendet")

    def test_delete_is_blocked_for_reviewed_or_booked_transactions(self):
        rule = self.create_rule()
        self.create_transaction(rule, status=BankTransaction.Status.BOOKED)

        response = self.client.post(
            reverse("matching_rule_delete", kwargs={"pk": rule.pk}),
            follow=True,
        )

        self.assertContains(response, "kann nicht gelöscht werden")
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())

    def test_edit_and_delete_pages_have_cancel_links(self):
        rule = self.create_rule()

        edit_response = self.client.get(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk})
        )
        delete_response = self.client.get(
            reverse("matching_rule_delete", kwargs={"pk": rule.pk})
        )

        list_url = reverse("matching_rule_list")
        self.assertContains(edit_response, f'href="{list_url}"')
        self.assertContains(delete_response, f'href="{list_url}"')


class MatchingRuleBookingTemplateTests(TestCase):
    iban = "AT611904300234573201"

    def parent_data(self, **overrides):
        values = {
            "name": "Mietzahlung",
            "direction": MatchingRule.Direction.INCOMING,
            "match_type": MatchingRule.MatchType.EXACT,
            "iban": self.iban,
            "expected_amount": "100,00",
            "text_pattern": "",
            "active": "on",
        }
        values.update(overrides)
        return values

    def template_data(self, rows, initial_forms=0):
        values = {
            "templates-TOTAL_FORMS": str(len(rows)),
            "templates-INITIAL_FORMS": str(initial_forms),
            "templates-MIN_NUM_FORMS": "0",
            "templates-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for field, value in row.items():
                values[f"templates-{index}-{field}"] = value
        return values

    def test_template_form_accepts_austrian_decimal_input(self):
        form = MatchingRuleBookingTemplateForm(
            {
                "position": "1",
                "booking_text": "Büromaterial",
                "invoice_number": "RG-1",
                "partner_name": "Lieferant",
                "gross_amount": "1.096,07",
                "vat_symbol": "20",
                "category": "300",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsInstance(form.cleaned_data["gross_amount"], Decimal)
        self.assertEqual(form.cleaned_data["gross_amount"], Decimal("1096.07"))

    def test_template_category_choices_are_description_only_sorted_and_dynamic(self):
        form = MatchingRuleBookingTemplateForm()
        expected_choices = sorted(
            [
                (value, category_description(value))
                for value, _label in CATEGORY_CHOICES
            ],
            key=lambda item: item[1].casefold(),
        )

        self.assertEqual(
            list(form.fields["category"].choices),
            [("", ""), *expected_choices],
        )
        self.assertEqual(form.fields["category"].choices[0], ("", ""))
        self.assertEqual(
            form.fields["category"].choices[
                next(
                    index
                    for index, (value, _label) in enumerate(
                        form.fields["category"].choices
                    )
                    if value == "4856"
                )
            ][1],
            "Betriebskostenerlös Bahngasse 10%",
        )

        response = self.client.get(reverse("matching_rule_list"))

        self.assertContains(
            response,
            '<option value="4856">Betriebskostenerlös Bahngasse 10%</option>',
        )
        self.assertNotContains(
            response,
            "4856 – Betriebskostenerlös Bahngasse 10%",
        )

    def test_template_submission_keeps_the_category_code(self):
        response = self.client.post(
            reverse("matching_rule_list"),
            {
                **self.parent_data(),
                **self.template_data(
                    [
                        {
                            "position": "1",
                            "booking_text": "Betriebskosten",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "100,00",
                            "vat_symbol": "20",
                            "category": "4856",
                        }
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MatchingRuleBookingTemplate.objects.get().category,
            "4856",
        )

    def test_template_submission_accepts_zero_vat_symbol(self):
        response = self.client.post(
            reverse("matching_rule_list"),
            {
                **self.parent_data(),
                **self.template_data(
                    [
                        {
                            "position": "1",
                            "booking_text": "Steuerfrei",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "100,00",
                            "vat_symbol": "0",
                            "category": "300",
                        }
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MatchingRuleBookingTemplate.objects.get().vat_symbol,
            "0",
        )

    def test_matching_rule_detail_displays_category_description(self):
        rule = MatchingRule.objects.create(
            name="Betriebskostenregel",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban=self.iban,
            expected_amount=Decimal("100.00"),
        )
        MatchingRuleBookingTemplate.objects.create(
            matching_rule=rule,
            position=1,
            booking_text="Betriebskosten",
            partner_name="Lieferant",
            gross_amount=Decimal("100.00"),
            vat_symbol="20",
            category="4856",
        )

        response = self.client.get(
            reverse("matching_rule_detail", kwargs={"pk": rule.pk})
        )

        self.assertContains(response, "Betriebskostenerlös Bahngasse 10%")
        self.assertNotContains(
            response,
            "4856 – Betriebskostenerlös Bahngasse 10%",
        )

    def test_create_normalizes_positions_and_shows_template_count(self):
        response = self.client.post(
            reverse("matching_rule_list"),
            {
                **self.parent_data(),
                **self.template_data(
                    [
                        {
                            "position": "8",
                            "booking_text": "Fixbetrag",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "60,00",
                            "vat_symbol": "20",
                            "category": "300",
                        },
                        {
                            "position": "2",
                            "booking_text": "Rest",
                            "invoice_number": "",
                            "partner_name": "",
                            "gross_amount": "",
                            "vat_symbol": "20",
                            "category": "300",
                        },
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        rule = MatchingRule.objects.get()
        templates = list(
            MatchingRuleBookingTemplate.objects.filter(matching_rule=rule)
            .order_by("position")
        )
        self.assertEqual([template.position for template in templates], [1, 2])
        self.assertEqual(templates[0].gross_amount, Decimal("60.00"))
        self.assertIsNone(templates[1].gross_amount)

        response = self.client.get(reverse("matching_rule_list"))
        self.assertContains(response, "Excel-Zeilen")
        self.assertEqual(
            response.context["matching_rules"][0]["booking_template_count"],
            2,
        )

    def test_exact_templates_without_rest_must_sum_to_expected_amount(self):
        response = self.client.post(
            reverse("matching_rule_list"),
            {
                **self.parent_data(),
                **self.template_data(
                    [
                        {
                            "position": "1",
                            "booking_text": "Zu viel",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "60,00",
                            "vat_symbol": "20",
                            "category": "300",
                        }
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Die Summe der Ergebniszeilen muss dem erwarteten Betrag entsprechen.",
        )
        self.assertContains(response, 'value="60,00"')

    def test_regex_templates_require_exactly_one_rest_amount(self):
        response = self.client.post(
            reverse("matching_rule_list"),
            {
                **self.parent_data(
                    match_type=MatchingRule.MatchType.REGEX,
                    iban="",
                    expected_amount="",
                    text_pattern="EVN",
                ),
                **self.template_data(
                    [
                        {
                            "position": "1",
                            "booking_text": "Fix",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "10,00",
                            "vat_symbol": "20",
                            "category": "300",
                        }
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MatchingRule.objects.count(), 0)
        self.assertContains(
            response,
            "Textmuster-Regeln benötigen genau eine Ergebniszeile mit Restbetrag.",
        )

    def test_used_rule_templates_are_read_only(self):
        rule = MatchingRule.objects.create(
            name="Mietzahlung",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban=self.iban,
            expected_amount=Decimal("100.00"),
        )
        template = MatchingRuleBookingTemplate.objects.create(
            matching_rule=rule,
            position=1,
            booking_text="Alt",
            partner_name="Lieferant",
            gross_amount=Decimal("100.00"),
            vat_symbol="20",
            category="300",
        )
        transaction = BankTransaction.objects.create(
            booking_date=date(2026, 1, 1),
            partner_iban=self.iban,
            amount=Decimal("100.00"),
            direction=BankTransaction.Direction.INCOMING,
            status=BankTransaction.Status.MATCHED,
            matched_rule=rule,
        )

        response = self.client.post(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            {
                **self.parent_data(),
                **self.template_data(
                    [
                        {
                            "id": str(template.pk),
                            "position": "1",
                            "booking_text": "Neu",
                            "invoice_number": "",
                            "partner_name": "Lieferant",
                            "gross_amount": "100,00",
                            "vat_symbol": "20",
                            "category": "300",
                        }
                    ],
                    initial_forms=1,
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        transaction.refresh_from_db()
        template.refresh_from_db()
        self.assertEqual(transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(transaction.matched_rule_id, rule.pk)
        self.assertEqual(template.booking_text, "Alt")


class MatchingRuleVersionTests(TestCase):
    iban = "AT611904300234573201"

    def create_rule(self, **overrides):
        values = {
            "name": "Mietzahlung",
            "direction": MatchingRule.Direction.INCOMING,
            "match_type": MatchingRule.MatchType.EXACT,
            "iban": self.iban,
            "expected_amount": Decimal("100.00"),
            "notes": "Alte Erklärung",
            "active": True,
        }
        values.update(overrides)
        return MatchingRule.objects.create(**values)

    def create_used_rule(self):
        rule = self.create_rule()
        first_template = MatchingRuleBookingTemplate.objects.create(
            matching_rule=rule,
            position=1,
            booking_text="Fixbetrag alt",
            invoice_number="RG-1",
            partner_name="Lieferant alt",
            gross_amount=Decimal("60.00"),
            vat_symbol="20",
            category="300",
        )
        second_template = MatchingRuleBookingTemplate.objects.create(
            matching_rule=rule,
            position=2,
            booking_text="Restbetrag alt",
            partner_name="Lieferant alt",
            gross_amount=None,
            vat_symbol="20",
            category="300",
        )
        bank_transaction = BankTransaction.objects.create(
            booking_date=date(2026, 1, 1),
            partner_iban=self.iban,
            amount=Decimal("100.00"),
            direction=BankTransaction.Direction.INCOMING,
            status=BankTransaction.Status.MATCHED,
            matched_rule=rule,
        )
        booking_entry = BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            payment_date=date(2026, 1, 1),
            booking_text="Bestehende Buchung",
            partner_name="Lieferant",
            gross_amount=Decimal("100.00"),
            vat_symbol="20",
            category="300",
        )
        return rule, (first_template, second_template), bank_transaction, booking_entry

    def template_data(self, rows, initial_forms=0):
        values = {
            "templates-TOTAL_FORMS": str(len(rows)),
            "templates-INITIAL_FORMS": str(initial_forms),
            "templates-MIN_NUM_FORMS": "0",
            "templates-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for field, value in row.items():
                values[f"templates-{index}-{field}"] = value
        return values

    def version_data(self, rule, templates, **overrides):
        values = {
            "name": rule.name,
            "direction": rule.direction,
            "match_type": rule.match_type,
            "iban": rule.iban,
            "expected_amount": "120,00",
            "text_pattern": "",
            "notes": "Neue Erklärung",
            "change_reason": "IBAN und Betrag angepasst",
            "active": "on",
        }
        values.update(overrides)
        values.update(
            self.template_data(
                templates,
                initial_forms=0,
            )
        )
        return values

    def test_existing_rules_default_to_version_one(self):
        rule = self.create_rule(change_reason="")

        self.assertEqual(rule.version_number, 1)
        self.assertIsNone(rule.previous_version_id)
        self.assertEqual(rule.change_reason, "")

    def test_used_rule_fields_and_templates_are_immutable(self):
        rule, templates, _, _ = self.create_used_rule()

        rule.notes = "Neue Erklärung"
        with self.assertRaises(ValidationError):
            rule.save()
        templates[0].booking_text = "Neu"
        with self.assertRaises(ValidationError):
            templates[0].save()
        with self.assertRaises(ValidationError):
            templates[1].delete()

    def test_version_form_prefills_all_copied_values(self):
        rule, _, _, _ = self.create_used_rule()

        response = self.client.get(
            reverse("matching_rule_version", kwargs={"pk": rule.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Mietzahlung"')
        self.assertContains(response, 'value="100,00"')
        self.assertContains(response, "Alte Erklärung")
        self.assertContains(response, "Fixbetrag alt")
        self.assertContains(response, "Restbetrag alt")
        self.assertContains(response, "Änderungsgrund")

    def test_version_requires_change_reason(self):
        rule, _, _, _ = self.create_used_rule()

        response = self.client.post(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            self.version_data(
                rule,
                [
                    {
                        "position": "1",
                        "booking_text": "Fixbetrag alt",
                        "invoice_number": "RG-1",
                        "partner_name": "Lieferant alt",
                        "gross_amount": "60,00",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                    {
                        "position": "2",
                        "booking_text": "Restbetrag alt",
                        "invoice_number": "",
                        "partner_name": "Lieferant alt",
                        "gross_amount": "",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                ],
                change_reason="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte einen Änderungsgrund angeben.")
        self.assertEqual(MatchingRule.objects.count(), 1)
        rule.refresh_from_db()
        self.assertTrue(rule.active)

    def test_version_form_accepts_zero_vat_symbol_in_template_rows(self):
        rule, _, _, _ = self.create_used_rule()

        response = self.client.post(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            self.version_data(
                rule,
                [
                    {
                        "position": "1",
                        "booking_text": "Steuerfrei",
                        "invoice_number": "RG-2",
                        "partner_name": "Lieferant",
                        "gross_amount": "100,00",
                        "vat_symbol": "0",
                        "category": "300",
                    },
                    {
                        "position": "2",
                        "booking_text": "Rest",
                        "invoice_number": "",
                        "partner_name": "Lieferant",
                        "gross_amount": "20,00",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                ],
                expected_amount="120,00",
            ),
        )

        self.assertEqual(response.status_code, 302)
        new_rule = MatchingRule.objects.get(previous_version=rule)
        self.assertEqual(
            new_rule.booking_templates.order_by("position").first().vat_symbol,
            "0",
        )

    def test_new_version_copies_templates_atomically_and_preserves_history(self):
        rule, templates, bank_transaction, booking_entry = self.create_used_rule()
        original_booking_entry_id = booking_entry.pk

        response = self.client.post(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            self.version_data(
                rule,
                [
                    {
                        "position": "1",
                        "booking_text": "Fixbetrag neu",
                        "invoice_number": "RG-2",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "80,00",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                    {
                        "position": "2",
                        "booking_text": "Restbetrag neu",
                        "invoice_number": "",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MatchingRule.objects.count(), 2)
        new_rule = MatchingRule.objects.get(previous_version=rule)
        rule.refresh_from_db()
        bank_transaction.refresh_from_db()
        booking_entry.refresh_from_db()
        new_templates = list(
            new_rule.booking_templates.order_by("position", "id")
        )
        self.assertEqual(new_rule.version_number, 2)
        self.assertEqual(new_rule.change_reason, "IBAN und Betrag angepasst")
        self.assertEqual(new_rule.notes, "Neue Erklärung")
        self.assertTrue(new_rule.active)
        self.assertFalse(rule.active)
        self.assertEqual([template.position for template in new_templates], [1, 2])
        self.assertEqual(new_templates[0].booking_text, "Fixbetrag neu")
        self.assertEqual(new_templates[1].gross_amount, None)
        self.assertEqual(templates[0].booking_text, "Fixbetrag alt")
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(booking_entry.pk, original_booking_entry_id)
        self.assertEqual(booking_entry.booking_text, "Bestehende Buchung")

    def test_detail_page_navigates_previous_and_next_versions(self):
        rule, _, _, _ = self.create_used_rule()
        self.client.post(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            self.version_data(
                rule,
                [
                    {
                        "position": "1",
                        "booking_text": "Fixbetrag neu",
                        "invoice_number": "RG-2",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "80,00",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                    {
                        "position": "2",
                        "booking_text": "Restbetrag neu",
                        "invoice_number": "",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                ],
            ),
        )
        new_rule = MatchingRule.objects.get(previous_version=rule)

        old_response = self.client.get(
            reverse("matching_rule_detail", kwargs={"pk": rule.pk})
        )
        new_response = self.client.get(
            reverse("matching_rule_detail", kwargs={"pk": new_rule.pk})
        )

        self.assertContains(old_response, "Version 1")
        self.assertContains(old_response, "Inaktiv")
        self.assertContains(old_response, "Nachfolgeversion: Version 2")
        self.assertContains(new_response, "Vorgängerversion: Version 1")
        self.assertContains(new_response, "Neue Erklärung")

    def test_existing_successor_prevents_a_second_branch(self):
        rule, _, _, _ = self.create_used_rule()
        first_response = self.client.post(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            self.version_data(
                rule,
                [
                    {
                        "position": "1",
                        "booking_text": "Fixbetrag neu",
                        "invoice_number": "RG-2",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "80,00",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                    {
                        "position": "2",
                        "booking_text": "Restbetrag neu",
                        "invoice_number": "",
                        "partner_name": "Lieferant neu",
                        "gross_amount": "",
                        "vat_symbol": "20",
                        "category": "300",
                    },
                ],
            ),
        )
        self.assertEqual(first_response.status_code, 302)

        response = self.client.get(
            reverse("matching_rule_version", kwargs={"pk": rule.pk}),
            follow=True,
        )

        self.assertContains(response, "Nachfolgeversion: Version 2")
        self.assertEqual(MatchingRule.objects.count(), 2)

    def test_used_rule_can_be_deactivated_without_changing_history(self):
        rule, _, bank_transaction, _ = self.create_used_rule()

        response = self.client.post(
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
            {"action": "deactivate"},
        )

        bank_transaction.refresh_from_db()
        rule.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(rule.active)
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)


class InvoiceAITests(TestCase):
    def analysis_payload(self, *, total="19.32", lines=None):
        return {
            "supplier": "Spusu",
            "invoice_number": "RG-42",
            "invoice_date": "2026-07-10",
            "payment_date": None,
            "currency": "EUR",
            "total_gross": total,
            "summary": "Mobilfunkrechnung",
            "warnings": [],
            "booking_lines": lines or [
                {
                    "booking_text": "Mobilfunk Juli",
                    "gross_amount": total,
                    "vat_code": "20",
                    "category_code": "7600",
                }
            ],
        }

    def invoice(self, **overrides):
        values = {
            "file_hash": uuid.uuid4().hex * 2,
            "paperless_document_id": 256,
            "paperless_status": ManualInvoice.PaperlessStatus.COMPLETED,
        }
        values.update(overrides)
        return ManualInvoice.objects.create(**values)

    def openai_client(self, payload):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="message",
                    status="completed",
                    content=[
                        SimpleNamespace(
                            type="output_text",
                            text=json.dumps(payload),
                        )
                    ],
                )
            ],
        )
        return client

    def test_structured_outputs_configuration_and_schema_constraints(self):
        payload = self.analysis_payload()
        client = self.openai_client(payload)
        with override_settings(BOOKKEEPING_OPENAI_API_KEY="test-secret"), patch.object(
            invoice_ai, "OpenAI", return_value=client
        ):
            result, model_name = invoice_ai.analyze_ocr_text("OCR")

        self.assertEqual(result["total_gross"], "19.32")
        self.assertEqual(model_name, invoice_ai.AI_MODEL_FALLBACK)
        request_format = client.responses.create.call_args.kwargs["text"]["format"]
        self.assertEqual(request_format["type"], "json_schema")
        self.assertTrue(request_format["strict"])
        self.assertEqual(request_format["name"], "invoice_analysis")
        schema = request_format["schema"]
        self.assertEqual(
            schema["required"],
            [
                "supplier",
                "invoice_number",
                "invoice_date",
                "payment_date",
                "currency",
                "total_gross",
                "summary",
                "warnings",
                "booking_lines",
            ],
        )
        self.assertEqual(
            schema["properties"]["booking_lines"]["items"]["required"],
            ["booking_text", "gross_amount", "vat_code", "category_code"],
        )
        self.assertEqual(
            schema["properties"]["booking_lines"]["items"]["properties"]["vat_code"]["enum"],
            ["0", "10", "13", "20", "IG", "unknown"],
        )
        self.assertEqual(
            schema["properties"]["booking_lines"]["items"]["properties"]["category_code"]["anyOf"][0]["enum"],
            sorted(invoice_ai.ALLOWED_CATEGORY_CODES),
        )
        self.assertEqual(
            schema["properties"]["total_gross"]["anyOf"][0]["type"],
            "string",
        )
        self.assertEqual(
            schema["properties"]["booking_lines"]["items"]["properties"]["gross_amount"]["type"],
            "string",
        )

        def assert_closed_objects(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object":
                self.assertIs(node.get("additionalProperties"), False)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    assert_closed_objects(value)

        assert_closed_objects(schema)

    def test_response_must_be_completed_structured_output(self):
        valid_payload = self.analysis_payload()
        responses = (
            SimpleNamespace(status="completed", output=[]),
            SimpleNamespace(
                status="completed",
                output=[
                    SimpleNamespace(
                        type="message",
                        status="completed",
                        content=[
                            SimpleNamespace(
                                type="refusal",
                                refusal="Nicht möglich",
                            )
                        ],
                    )
                ],
            ),
            SimpleNamespace(status="incomplete", output=[]),
            SimpleNamespace(
                status="completed",
                output=[
                    SimpleNamespace(
                        type="message",
                        status="completed",
                        content=[
                            SimpleNamespace(type="output_text", text="{\"extra\": true}")
                        ],
                    )
                ],
            ),
            SimpleNamespace(status="completed", output_text=json.dumps(valid_payload)),
        )
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaisesRegex(
                    InvoiceAIError, invoice_ai.AI_INVALID_RESPONSE_MESSAGE
                ):
                    invoice_ai._response_json(response)

    def test_paperless_ocr_text_is_loaded_from_document_content(self):
        with patch.object(
            PaperlessClient,
            "_request_json",
            return_value={"id": 256, "content": "OCR-Rechnungstext"},
        ) as request_json:
            content = PaperlessClient.document_ocr_text(256)

        self.assertEqual(content, "OCR-Rechnungstext")
        request_json.assert_called_once_with(endpoint="documents/256/")

    def test_validate_one_line_per_vat_rate_for_20_10_and_zero_percent(self):
        cases = (
            (
                [
                    {
                        "booking_text": "20 Prozent",
                        "gross_amount": "19.32",
                        "vat_code": "20",
                        "category_code": "7600",
                    }
                ],
                "19.32",
            ),
            (
                [
                    {
                        "booking_text": "10 Prozent",
                        "gross_amount": "10.00",
                        "vat_code": "10",
                        "category_code": "7600",
                    },
                    {
                        "booking_text": "20 Prozent",
                        "gross_amount": "9.32",
                        "vat_code": "20",
                        "category_code": "7600",
                    },
                ],
                "19.32",
            ),
            (
                [
                    {
                        "booking_text": "Steuerfreie Leistung",
                        "gross_amount": "19.32",
                        "vat_code": "0",
                        "category_code": None,
                    }
                ],
                "19.32",
            ),
        )
        for lines, total in cases:
            with self.subTest(lines=lines):
                result = validate_analysis(
                    self.analysis_payload(total=total, lines=lines)
                )
                self.assertEqual(len(result["booking_lines"]), len(lines))

    def test_unknown_vat_and_invalid_category_are_not_prefilled(self):
        result = validate_analysis(
            self.analysis_payload(
                lines=[
                    {
                        "booking_text": "Unklare Rechnung",
                        "gross_amount": "19.32",
                        "vat_code": "unknown",
                        "category_code": "erfunden",
                    }
                ]
            )
        )

        line = result["booking_lines"][0]
        self.assertEqual(line["vat_code"], "unknown")
        self.assertIsNone(line["category_code"])
        self.assertIn("USt-Satz konnte nicht eindeutig vorgeschlagen werden.", result["warnings"])
        self.assertIn("Kategorie konnte nicht eindeutig vorgeschlagen werden.", result["warnings"])

        invoice = self.invoice(ai_result=result)
        initial = formset_initial_from_analysis(invoice)
        self.assertEqual(initial[0]["vat_symbol"], "")
        self.assertEqual(initial[0]["category"], "")

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="test-secret",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_credit_note_does_not_receive_an_automatic_pr_sign(self):
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        client = self.openai_client(self.analysis_payload())
        with patch.object(
            PaperlessClient,
            "document_ocr_text",
            return_value="Gutschrift 19,32 EUR",
        ), patch.object(invoice_ai, "OpenAI", return_value=client):
            outcome = run_manual_invoice_analysis(invoice)

        invoice.refresh_from_db()
        self.assertEqual(outcome.kind, "completed")
        self.assertIsNone(invoice.gross_amount)
        self.assertEqual(formset_initial_from_analysis(invoice), [])
        self.assertIn(
            invoice_ai.DIRECTION_UNCLEAR_MESSAGE,
            invoice.ai_result["warnings"],
        )

    def test_exact_and_one_cent_difference_are_accepted_but_larger_difference_is_rejected(self):
        exact = validate_analysis(self.analysis_payload(total="19.32"))
        one_cent = validate_analysis(self.analysis_payload(total="19.33"))
        self.assertEqual(exact["total_gross"], "19.32")
        self.assertEqual(one_cent["total_gross"], "19.33")

        with self.assertRaisesRegex(InvoiceAIError, AI_INCONSISTENT_MESSAGE):
            validate_analysis(
                self.analysis_payload(
                    total="19.34",
                    lines=[
                        {
                            "booking_text": "Mobilfunk Juli",
                            "gross_amount": "19.32",
                            "vat_code": "20",
                            "category_code": "7600",
                        }
                    ],
                )
            )

    def test_missing_ocr_keeps_invoice_available_for_manual_entry(self):
        invoice = self.invoice()
        with patch.object(PaperlessClient, "document_ocr_text", return_value=""):
            outcome = run_manual_invoice_analysis(invoice)

        invoice.refresh_from_db()
        self.assertEqual(outcome.kind, "ocr_unavailable")
        self.assertEqual(invoice.ai_status, ManualInvoice.AIStatus.NOT_STARTED)
        self.assertEqual(invoice.ai_error, "OCR noch nicht verfügbar")

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_missing_openai_key_is_safe_and_manual_workflow_remains_available(self):
        invoice = self.invoice()
        with patch.object(PaperlessClient, "document_ocr_text", return_value="OCR"):
            outcome = run_manual_invoice_analysis(invoice)

        invoice.refresh_from_db()
        self.assertEqual(outcome.kind, "failed")
        self.assertEqual(invoice.ai_error, AI_NOT_CONFIGURED_MESSAGE)
        self.assertNotIn("BOOKKEEPING_OPENAI_API_KEY", invoice.ai_error)

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="test-secret",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_timeout_and_invalid_structured_response_are_safe_failures(self):
        timeout_client = Mock()
        timeout_client.responses.create.side_effect = TimeoutError()
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        with patch.object(PaperlessClient, "document_ocr_text", return_value="OCR"), patch.object(
            invoice_ai, "OpenAI", return_value=timeout_client
        ):
            outcome = run_manual_invoice_analysis(invoice)
        self.assertEqual(outcome.kind, "failed")
        invoice.refresh_from_db()
        self.assertEqual(invoice.ai_error, invoice_ai.AI_REQUEST_ERROR_MESSAGE)

        invalid_client = Mock()
        invalid_client.responses.create.return_value = SimpleNamespace(
            output_text="kein JSON"
        )
        second_invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        with patch.object(PaperlessClient, "document_ocr_text", return_value="OCR"), patch.object(
            invoice_ai, "OpenAI", return_value=invalid_client
        ):
            outcome = run_manual_invoice_analysis(second_invoice)
        self.assertEqual(outcome.kind, "failed")
        second_invoice.refresh_from_db()
        self.assertEqual(second_invoice.ai_error, invoice_ai.AI_INVALID_RESPONSE_MESSAGE)

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="test-secret",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_successful_analysis_prefills_without_payment_date_or_auto_completion(self):
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        client = self.openai_client(self.analysis_payload())
        with patch.object(
            PaperlessClient,
            "document_ocr_text",
            return_value="OCR-only",
        ) as ocr, patch.object(
            invoice_ai, "OpenAI", return_value=client
        ):
            response = self.client.get(
                reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
            )
            second_response = self.client.get(
                reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
            )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoice.ai_status, ManualInvoice.AIStatus.COMPLETED)
        self.assertEqual(invoice.partner_name, "Spusu")
        self.assertEqual(invoice.invoice_number, "RG-42")
        self.assertEqual(invoice.invoice_date, date(2026, 7, 10))
        self.assertEqual(invoice.gross_amount, Decimal("-19.32"))
        self.assertIsNone(invoice.payment_date)
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertFalse(invoice.booking_entries.exists())
        self.assertContains(response, "Vorschlag erstellt")
        self.assertContains(response, "Rechnungsdatum")
        self.assertContains(response, "Zahlungsdatum")
        self.assertContains(response, "Die vorausgefüllten Werte sind KI-Vorschläge")
        self.assertContains(response, "Mobilfunk Juli")
        self.assertNotContains(response, "OCR-only")
        self.assertNotContains(response, "test-secret")
        self.assertEqual(second_response.status_code, 200)
        self.assertIsNotNone(invoice.ai_analyzed_at)
        self.assertEqual(invoice.ai_model_used, "test-model")
        self.assertNotIn("OCR-only", json.dumps(invoice.ai_result))
        request_input = json.dumps(client.responses.create.call_args.kwargs["input"])
        self.assertIn("OCR-only", request_input)
        self.assertNotIn("%PDF", request_input)
        ocr.assert_called_once_with(256)
        client.responses.create.assert_called_once()
        self.assertEqual(
            client.responses.create.call_args.kwargs["model"],
            "test-model",
        )

    def test_payment_date_is_validated_prefilled_and_used_for_receipt_number(self):
        payload = self.analysis_payload()
        payload["payment_date"] = "2026-08-15"
        payload["warnings"] = [
            "Zahlungsdatum wurde aus dem Rechnungsdatum übernommen."
        ]

        result = validate_analysis(payload)
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        invoice_ai.apply_analysis_to_invoice(invoice, result, "test-model")
        invoice.refresh_from_db()

        self.assertEqual(result["payment_date"], "2026-08-15")
        self.assertEqual(
            invoice.payment_date,
            date(2026, 8, 15),
        )
        self.assertIn(
            "Zahlungsdatum wurde aus dem Rechnungsdatum übernommen.",
            invoice.ai_result["warnings"],
        )
        initial = formset_initial_from_analysis(invoice)
        self.assertEqual(initial[0]["payment_date"], date(2026, 8, 15))
        self.assertEqual(initial[0]["receipt_number"], "8")

    def test_unknown_payment_date_remains_null(self):
        payload = self.analysis_payload()
        payload["payment_date"] = None
        result = validate_analysis(payload)
        self.assertIsNone(result["payment_date"])

        invalid = self.analysis_payload()
        invalid["payment_date"] = "not-a-date"
        with self.assertRaisesRegex(InvoiceAIError, "KI-Zahlungsdatum ist ungültig"):
            validate_analysis(invalid)

    def test_payment_date_warning_is_displayed_as_neutral_hint(self):
        invoice = self.invoice(
            file_hash=uuid.uuid4().hex * 2,
            ai_status=ManualInvoice.AIStatus.COMPLETED,
            ai_result={
                "warnings": [
                    "Zahlungsdatum wurde aus dem Rechnungsdatum übernommen."
                ]
            },
        )
        response = self.client.get(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            )
        )

        self.assertContains(
            response,
            "Hinweis: Zahlungsdatum wurde aus dem Rechnungsdatum übernommen. Bitte prüfen.",
        )
        self.assertContains(response, "bookkeeping-ai-warnings")
        self.assertNotContains(response, "bookkeeping-formset-errors")

    def test_draft_hides_stale_date_metadata_error_and_retry(self):
        invoice = self.invoice(
            file_hash=uuid.uuid4().hex * 2,
            ai_status=ManualInvoice.AIStatus.COMPLETED,
            ai_result={"warnings": []},
            paperless_error=(
                "Paperless-Datumsfelder konnten nicht aktualisiert werden: "
                "altes Fehlersignal"
            ),
        )
        response = self.client.get(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            )
        )

        self.assertNotContains(response, "altes Fehlersignal")
        self.assertNotContains(response, "Paperless-Datumsfelder erneut aktualisieren")

    @override_settings(BOOKKEEPING_OPENAI_API_KEY="test-secret")
    @patch.object(PaperlessClient, "update_manual_invoice_dates")
    @patch.object(PaperlessClient, "document_ocr_text", return_value="OCR")
    @patch.object(invoice_ai, "OpenAI")
    def test_analysis_and_editing_never_update_paperless_dates(
        self, openai, ocr, date_update
    ):
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        openai.return_value = self.openai_client(self.analysis_payload())

        response = self.client.get(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            )
        )

        self.assertEqual(response.status_code, 200)
        date_update.assert_not_called()

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="test-secret",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_manual_analysis_button_keeps_workflow_editable(self):
        invoice = self.invoice(file_hash=uuid.uuid4().hex * 2)
        client = self.openai_client(self.analysis_payload())
        data = {
            "action": "analyze_ai",
            "invoice_number": "",
            "invoice_date": "",
            "payment_date": "",
            "partner_name": "",
            "gross_amount": "",
            "notes": "",
            "entries-TOTAL_FORMS": "1",
            "entries-INITIAL_FORMS": "0",
            "entries-MIN_NUM_FORMS": "0",
            "entries-MAX_NUM_FORMS": "1000",
            "entries-0-position": "",
            "entries-0-receipt_group": "PR",
            "entries-0-receipt_number": "",
            "entries-0-payment_date": "",
            "entries-0-booking_text": "",
            "entries-0-invoice_number": "",
            "entries-0-partner_name": "",
            "entries-0-gross_amount": "",
            "entries-0-vat_symbol": "20",
            "entries-0-category": "",
        }
        with patch.object(PaperlessClient, "document_ocr_text", return_value="OCR"), patch.object(
            invoice_ai, "OpenAI", return_value=client
        ):
            response = self.client.post(
                reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
                data,
            )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoice.ai_status, ManualInvoice.AIStatus.COMPLETED)
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertEqual(invoice.booking_entries.count(), 0)
        self.assertContains(response, "Mobilfunk Juli")

    @override_settings(
        BOOKKEEPING_OPENAI_API_KEY="test-secret",
        BOOKKEEPING_OPENAI_MODEL="test-model",
    )
    def test_existing_fields_and_booking_lines_are_not_overwritten(self):
        invoice = self.invoice(
            file_hash=uuid.uuid4().hex * 2,
            partner_name="Bestehender Lieferant",
            invoice_number="ALT-1",
            invoice_date=date(2026, 6, 1),
            payment_date=date(2026, 7, 15),
            gross_amount=Decimal("-19.32"),
        )
        entry = ManualInvoiceEntry.objects.create(
            manual_invoice=invoice,
            payment_date=invoice.payment_date,
            booking_text="Bestehende Buchung",
            partner_name="Bestehender Lieferant",
            gross_amount=Decimal("-19.32"),
            vat_symbol="20",
            category="7600",
        )
        client = self.openai_client(self.analysis_payload())
        with patch.object(PaperlessClient, "document_ocr_text", return_value="OCR"), patch.object(
            invoice_ai, "OpenAI", return_value=client
        ):
            outcome = run_manual_invoice_analysis(invoice)

        invoice.refresh_from_db()
        entry.refresh_from_db()
        self.assertTrue(outcome.existing_data_untouched)
        self.assertEqual(invoice.partner_name, "Bestehender Lieferant")
        self.assertEqual(invoice.invoice_number, "ALT-1")
        self.assertEqual(invoice.invoice_date, date(2026, 6, 1))
        self.assertEqual(invoice.gross_amount, Decimal("-19.32"))
        self.assertEqual(entry.booking_text, "Bestehende Buchung")
        self.assertEqual(invoice.booking_entries.count(), 1)


class ManualInvoiceTests(TestCase):
    def setUp(self):
        super().setUp()
        self.paperless_date_update = patch.object(
            PaperlessClient,
            "update_manual_invoice_dates",
            return_value=None,
        )
        self.paperless_date_update_mock = self.paperless_date_update.start()
        self.addCleanup(self.paperless_date_update.stop)

    def upload_invoice(self, content=b"%PDF- manual invoice"):
        uploaded_file = SimpleUploadedFile(
            "rechnung.pdf",
            content,
            content_type="application/pdf",
        )
        return self.client.post(
            reverse("manual_invoice_list"),
            {"pdf": uploaded_file},
        )

    def finalize_data(self, amount="100,00", rows=None, invoice_amount="100,00"):
        rows = [
            {
                "booking_text": "Büromaterial",
                "invoice_number": "RG-7",
                "partner_name": "Lieferant",
                "gross_amount": amount,
                "vat_symbol": "20",
                "category": "7600",
            }
        ] if rows is None else rows
        data = {
            "action": "finalize",
            "invoice_number": "RG-7",
            "invoice_date": "2026-07-10",
            "payment_date": "2026-07-15",
            "partner_name": "Lieferant",
            "gross_amount": invoice_amount,
            "notes": "Privat bezahlt",
            "entries-TOTAL_FORMS": str(len(rows)),
            "entries-INITIAL_FORMS": "0",
            "entries-MIN_NUM_FORMS": "0",
            "entries-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            data.update(
                {
                    f"entries-{index}-position": str(index + 1),
                    f"entries-{index}-receipt_group": "PR",
                    f"entries-{index}-receipt_number": "7",
                    f"entries-{index}-payment_date": "2026-07-15",
                    f"entries-{index}-booking_text": row["booking_text"],
                    f"entries-{index}-invoice_number": row.get("invoice_number", ""),
                    f"entries-{index}-partner_name": row["partner_name"],
                    f"entries-{index}-gross_amount": row["gross_amount"],
                    f"entries-{index}-vat_symbol": row["vat_symbol"],
                    f"entries-{index}-category": row["category"],
                }
            )
        return data

    def uploaded_invoice(self, *, paperless_ready=True):
        with patch.object(
            PaperlessClient,
            "upload_manual_invoice",
            return_value="initial-task",
        ):
            response = self.upload_invoice()
        self.assertEqual(response.status_code, 302)
        invoice = ManualInvoice.objects.get()
        self.assertEqual(invoice.paperless_task_id, "initial-task")
        if paperless_ready:
            invoice.paperless_document_id = 256
            invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
            invoice.save(
                update_fields=(
                    "paperless_document_id",
                    "paperless_status",
                    "updated_at",
                )
            )
        return invoice

    def test_manual_invoice_worklist_contains_only_drafts(self):
        draft = ManualInvoice.objects.create(
            file_hash="d" * 64,
            invoice_number="ENTWURF-1",
            partner_name="Offener Lieferant",
        )
        ready = ManualInvoice.objects.create(
            file_hash="r" * 64,
            status=ManualInvoice.Status.READY,
            invoice_number="FERTIG-1",
            partner_name="Fertiger Lieferant",
        )

        response = self.client.get(reverse("manual_invoice_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Offene manuelle Belege")
        self.assertContains(response, draft.invoice_number)
        self.assertNotContains(response, ready.invoice_number)
        self.assertNotContains(response, ready.partner_name)

    def test_empty_manual_invoice_worklist_has_compact_message(self):
        response = self.client.get(reverse("manual_invoice_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keine offenen manuellen Belege vorhanden.")

    def test_manual_invoice_without_paperless_does_not_show_ocr_as_root_cause(self):
        invoice = self.uploaded_invoice(paperless_ready=False)

        with patch.object(
            PaperlessClient,
            "task_status",
            return_value={"status": "pending", "document_id": None},
        ):
            response = self.client.get(
                reverse(
                    "manual_invoice_edit",
                    kwargs={"reference_uuid": invoice.reference_uuid},
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Übertragung läuft")
        self.assertContains(response, "Nicht gestartet")
        self.assertNotContains(response, "OCR noch nicht verfügbar")

    def test_completed_invoice_leaves_worklist_and_remains_available(self):
        invoice = self.uploaded_invoice()
        original_uuid = invoice.reference_uuid
        invoice.paperless_document_id = 256
        invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
        invoice.save(
            update_fields=(
                "paperless_document_id",
                "paperless_status",
                "updated_at",
            )
        )

        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        invoice.refresh_from_db()
        worklist_response = self.client.get(response["Location"])
        self.assertContains(worklist_response, "Rechnung geprüft und abgeschlossen.")
        self.assertNotContains(worklist_response, invoice.invoice_number)
        self.assertNotContains(worklist_response, invoice.partner_name)

        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertEqual(invoice.paperless_document_id, 256)
        self.assertEqual(invoice.reference_uuid, original_uuid)

        ready_response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": "reviewed",
                "period_type": "month",
                "period": "2026-07",
            },
        )
        self.assertContains(ready_response, "Büromaterial")
        self.assertContains(
            ready_response,
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
        )
        edit_response = self.client.get(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, "Büromaterial")

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example")
    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_ready_manual_invoice_shows_paperless_link_in_month_and_quarter_views(
        self, upload
    ):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(),
        )
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        invoice.paperless_document_id = 256
        invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
        invoice.save(
            update_fields=(
                "paperless_document_id",
                "paperless_status",
                "updated_at",
            )
        )

        bank_transaction = BankTransaction.objects.create(
            booking_date=date(2026, 7, 20),
            partner_name="Normale Banktransaktion",
            amount=Decimal("50.00"),
            direction=BankTransaction.Direction.OUTGOING,
            status=BankTransaction.Status.REVIEWED,
        )
        BookingEntry.objects.create(
            bank_transaction=bank_transaction,
            payment_date=bank_transaction.booking_date,
            booking_text="Normale Bankbuchung",
            partner_name=bank_transaction.partner_name,
            gross_amount=bank_transaction.amount,
            vat_symbol="20",
            category="7600",
        )

        for period_params in (
            {"period_type": "month", "period": "2026-07"},
            {"period_type": "quarter", "period": "2026-Q3"},
        ):
            ready_response = self.client.get(
                reverse("bookkeeping_overview"),
                {"status": "reviewed", **period_params},
            )
            content = ready_response.content.decode()
            self.assertContains(ready_response, "Bearbeiten")
            self.assertContains(ready_response, "In Paperless öffnen")
            self.assertIn(
                'href="https://paperless.example/documents/256/"',
                content,
            )
            self.assertIn('target="_blank"', content)
            self.assertIn('rel="noopener noreferrer"', content)
            self.assertEqual(
                content.count('href="https://paperless.example/documents/256/"'),
                1,
            )
            self.assertContains(ready_response, "Normale Banktransaktion")

        upload.assert_not_called()

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example")
    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_ready_manual_invoice_without_paperless_id_has_no_link(self, upload):
        invoice = self.uploaded_invoice()
        invoice.paperless_document_id = None
        invoice.paperless_status = ManualInvoice.PaperlessStatus.NOT_STARTED
        invoice.save(
            update_fields=(
                "paperless_document_id",
                "paperless_status",
                "updated_at",
            )
        )
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(),
        )

        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        invoice.status = ManualInvoice.Status.READY
        invoice.save(update_fields=("status", "updated_at"))
        ready_response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": "reviewed",
                "period_type": "month",
                "period": "2026-07",
            },
        )
        self.assertContains(ready_response, "Bearbeiten")
        self.assertNotContains(ready_response, "In Paperless öffnen")
        self.assertNotContains(ready_response, "/documents/")
        upload.assert_not_called()

    def test_initial_visible_line_is_submitted_with_negative_amount(self):
        invoice = self.uploaded_invoice(paperless_ready=False)
        response = self.client.get(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="entries-TOTAL_FORMS" value="1"')
        self.assertContains(response, 'name="entries-0-booking_text"')
        self.assertContains(response, 'name="entries-0-gross_amount"')
        self.assertContains(response, 'name="entries-__prefix__-booking_text"')

        invoice.paperless_document_id = 256
        invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
        invoice.save(
            update_fields=(
                "paperless_document_id",
                "paperless_status",
                "updated_at",
            )
        )

        with patch.object(
            PaperlessClient,
            "upload_manual_invoice",
            return_value="task-manual",
        ) as upload:
            data = self.finalize_data(
                amount="-19,32",
                invoice_amount="-19,32",
            )
            # This is the value sent by the visible initial form row.  The
            # server must calculate the position before saving the instance.
            data["entries-0-position"] = ""
            response = self.client.post(
                reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
                data,
            )

        invoice.refresh_from_db()
        entry = invoice.booking_entries.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertEqual(entry.booking_text, "Büromaterial")
        self.assertEqual(entry.gross_amount, Decimal("-19.32"))
        self.assertEqual(entry.vat_symbol, "20")
        self.assertEqual(entry.category, "7600")
        upload.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_invoice_with_one_line_is_ready_with_private_receipt_defaults(self, upload):
        invoice = self.uploaded_invoice()

        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(),
        )

        invoice.refresh_from_db()
        entry = invoice.booking_entries.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        self.assertEqual(entry.receipt_group, "PR")
        self.assertEqual(entry.receipt_number, "7")
        self.assertEqual(entry.payment_date, date(2026, 7, 15))
        upload.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-draft")
    def test_payment_date_alone_starts_paperless_before_manual_completion(self, upload):
        invoice = self.uploaded_invoice()
        data = self.finalize_data()
        data.update(
            {
                "action": "save_draft",
                "partner_name": "",
                "gross_amount": "",
            }
        )

        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            data,
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        self.assertEqual(invoice.paperless_task_id, "initial-task")
        self.paperless_date_update_mock.assert_not_called()
        upload.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_multiple_vat_rates_and_negative_line_are_supported(self, upload):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(
                rows=[
                    {
                        "booking_text": "Nettozeile",
                        "invoice_number": "RG-7",
                        "partner_name": "Lieferant",
                        "gross_amount": "120,00",
                        "vat_symbol": "20",
                        "category": "7600",
                    },
                    {
                        "booking_text": "Korrektur",
                        "invoice_number": "RG-7",
                        "partner_name": "Lieferant",
                        "gross_amount": "-20,00",
                        "vat_symbol": "0",
                        "category": "4830",
                    },
                ]
            ),
        )

        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.booking_entries.count(), 2)
        self.assertEqual(
            list(invoice.booking_entries.values_list("vat_symbol", flat=True)),
            ["20", "0"],
        )
        self.assertEqual(
            sum(invoice.booking_entries.values_list("gross_amount", flat=True)),
            Decimal("100.00"),
        )
        upload.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_rounding_tolerance_is_applied_to_largest_line(self, upload):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(amount="99,99"),
        )

        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.booking_entries.count(), 1)
        self.assertEqual(invoice.booking_entries.get().gross_amount, Decimal("100.00"))

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_larger_sum_difference_blocks_completion(self, upload):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(amount="90,00"),
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Differenz")
        self.assertContains(response, "Büromaterial")
        self.assertContains(response, 'value="90,00"')
        self.assertContains(response, 'value="7600"')
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertFalse(invoice.booking_entries.exists())
        upload.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_deleted_line_is_not_counted(self, upload):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(
                rows=[
                    {
                        "booking_text": "Nicht speichern",
                        "invoice_number": "RG-7",
                        "partner_name": "Lieferant",
                        "gross_amount": "100,00",
                        "vat_symbol": "20",
                        "category": "7600",
                    },
                    {
                        "booking_text": "Übrige Zeile",
                        "invoice_number": "RG-7",
                        "partner_name": "Lieferant",
                        "gross_amount": "100,00",
                        "vat_symbol": "0",
                        "category": "4830",
                    },
                ]
            )
            | {"entries-0-DELETE": "on"},
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertEqual(invoice.booking_entries.count(), 1)
        self.assertEqual(invoice.booking_entries.get().booking_text, "Übrige Zeile")
        upload.assert_not_called()

    def test_empty_formset_still_requires_a_booking_line(self):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(rows=[]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mindestens eine Buchungszeile ist erforderlich.")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertFalse(invoice.booking_entries.exists())

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-immediate")
    def test_finalization_updates_dates_without_a_second_upload(self, upload):
        response = self.upload_invoice(content=b"%PDF- finalize dates")
        invoice = ManualInvoice.objects.get()
        invoice.paperless_document_id = 256
        invoice.paperless_status = ManualInvoice.PaperlessStatus.COMPLETED
        invoice.save(
            update_fields=(
                "paperless_document_id",
                "paperless_status",
                "updated_at",
            )
        )

        response = self.client.post(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            self.finalize_data(),
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.paperless_date_update_mock.assert_called_once_with(invoice)
        upload.assert_called_once_with(invoice)

    def test_failed_date_update_keeps_completed_booking_data_and_does_not_upload(self):
        invoice = self.uploaded_invoice()
        self.paperless_date_update_mock.side_effect = BookkeepingPaperlessError(
            "Paperless vorübergehend nicht erreichbar."
        )

        response = self.client.post(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            self.finalize_data(),
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertTrue(invoice.booking_entries.exists())
        self.assertIn("Paperless-Datumsfelder konnten nicht aktualisiert werden", invoice.paperless_error)
        self.assertEqual(invoice.paperless_document_id, 256)
        with patch.object(PaperlessClient, "document_ocr_text", return_value=""):
            status_response = self.client.get(response["Location"])
        status_content = status_response.content.decode()
        self.assertEqual(
            status_content.count("Paperless-Datumsfelder konnten nicht aktualisiert werden"),
            1,
        )

    def test_draft_cannot_trigger_paperless_date_retry(self):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
            {"action": "retry_paperless_dates"},
        )

        self.assertEqual(response.status_code, 302)
        self.paperless_date_update_mock.assert_not_called()

    def test_identical_file_hash_is_rejected_without_second_invoice(self):
        with patch.object(
            PaperlessClient,
            "upload_manual_invoice",
            return_value="initial-task",
        ) as upload:
            first = self.upload_invoice()
            upload.assert_called_once()
        self.assertEqual(first.status_code, 302)
        second = self.upload_invoice()

        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Diese Rechnung wurde bereits importiert.")
        self.assertEqual(ManualInvoice.objects.count(), 1)

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-immediate")
    def test_pdf_upload_starts_paperless_without_payment_date_and_uses_uuid_url(
        self, upload
    ):
        response = self.upload_invoice(content=b"%PDF- immediate upload")
        invoice = ManualInvoice.objects.get()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": invoice.reference_uuid},
            ),
        )
        self.assertIsNone(invoice.payment_date)
        self.assertEqual(invoice.paperless_task_id, "task-immediate")
        self.assertNotIn(f"/{invoice.pk}/edit/", response["Location"])
        upload.assert_called_once_with(invoice)

    @override_settings(
        PAPERLESS_BASE_URL="https://paperless.example",
        PAPERLESS_API_TOKEN="test-token",
    )
    @patch.object(PaperlessClient, "_find_exact_name", return_value=5)
    @patch.object(PaperlessClient, "_require_named", side_effect=(1, 2, 3, 4))
    @patch.object(PaperlessClient, "_require_custom_field", side_effect=(6, 7, 8, 9))
    @patch.object(PaperlessClient, "_request_multipart", return_value={"task_id": "task-manual"})
    def test_paperless_metadata_uses_manual_invoice_names_and_uuid(
        self, multipart, custom_fields, named, find_name
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="a" * 64,
            invoice_date=date(2026, 7, 10),
            invoice_number="RG-7",
            partner_name="Lieferant",
            gross_amount=Decimal("100.00"),
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )

        task_id = PaperlessClient.upload_manual_invoice(invoice)

        self.assertEqual(task_id, "task-manual")
        fields = dict(multipart.call_args.kwargs["form_fields"])
        custom_values = json.loads(fields["custom_fields"])
        self.assertEqual(custom_values["6"], str(invoice.reference_uuid))
        self.assertNotIn("7", custom_values)
        self.assertNotIn("8", custom_values)
        self.assertNotIn("9", custom_values)
        self.assertEqual(fields["document_type"], "2")
        self.assertEqual(fields["correspondent"], "1")
        self.assertEqual(fields["storage_path"], "5")
        self.assertEqual(fields["created"], "2026-07-10")

    @patch.object(PaperlessClient, "_require_custom_field", side_effect=(7, 8, 9))
    @patch.object(
        PaperlessClient,
        "_request_json",
        side_effect=[
            {
                "id": 256,
                "custom_fields": {
                    "6": "existing-uuid",
                    "99": "unknown-field-value",
                },
                "tags": [1, 2],
                "title": "Originaltitel",
            },
            {},
        ],
    )
    def test_manual_invoice_date_update_preserves_all_existing_custom_fields(
        self, request_json, custom_fields
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="u" * 64,
            paperless_document_id=256,
            paperless_status=ManualInvoice.PaperlessStatus.COMPLETED,
            payment_date=date(2026, 7, 15),
        )

        self.paperless_date_update.stop()
        try:
            PaperlessClient.update_manual_invoice_dates(invoice)
        finally:
            self.paperless_date_update_mock = self.paperless_date_update.start()

        self.assertEqual(request_json.call_count, 2)
        patch_call = request_json.call_args_list[1]
        self.assertEqual(patch_call.kwargs["method"], "PATCH")
        self.assertEqual(patch_call.kwargs["endpoint"], "documents/256/")
        self.assertEqual(
            patch_call.kwargs["payload"]["custom_fields"],
            {
                "6": "existing-uuid",
                "7": "2026-07-15",
                "8": "2026-07",
                "9": "2026-Q3",
                "99": "unknown-field-value",
            },
        )
        self.assertEqual(custom_fields.call_count, 3)

    @patch.object(
        PaperlessClient,
        "_require_custom_field",
        side_effect=BookkeepingPaperlessError(
            "Das Paperless-Custom-Field 'q_buchungsdatum' fehlt."
        ),
    )
    @patch.object(
        PaperlessClient,
        "_request_json",
        return_value={"custom_fields": {"6": "existing-uuid"}},
    )
    def test_global_missing_custom_field_is_a_clear_error(
        self, request_json, custom_field
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="v" * 64,
            paperless_document_id=256,
            paperless_status=ManualInvoice.PaperlessStatus.COMPLETED,
            payment_date=date(2026, 7, 15),
        )

        self.paperless_date_update.stop()
        try:
            with self.assertRaisesRegex(
                BookkeepingPaperlessError,
                "q_buchungsdatum.*fehlt",
            ):
                PaperlessClient.update_manual_invoice_dates(invoice)
        finally:
            self.paperless_date_update_mock = self.paperless_date_update.start()

        request_json.assert_called_once_with(endpoint="documents/256/")
        custom_field.assert_called_once()

    @override_settings(
        PAPERLESS_BASE_URL="https://paperless.example",
        PAPERLESS_API_TOKEN="test-token",
    )
    @patch.object(PaperlessClient, "_require_named", side_effect=(1, 2, 3, 4))
    @patch.object(PaperlessClient, "_find_exact_name", return_value=None)
    def test_missing_manual_invoice_storage_path_is_reported_without_creation(
        self, find_name, named
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="m" * 64,
            payment_date=date(2026, 7, 15),
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )

        with self.assertRaisesRegex(
            BookkeepingPaperlessError,
            "IFKG Eingangsrechnungen",
        ):
            PaperlessClient.upload_manual_invoice(invoice)

    @patch.object(
        PaperlessClient,
        "task_status",
        return_value={"status": "pending", "document_id": None, "found": True},
    )
    @patch.object(PaperlessClient, "upload_manual_invoice")
    def test_pending_manual_invoice_task_is_not_uploaded_again(self, upload, task_status):
        invoice = ManualInvoice.objects.create(
            file_hash="p" * 64,
            paperless_task_id="task-running",
            paperless_status=ManualInvoice.PaperlessStatus.PENDING,
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )

        task_id = start_manual_invoice_upload(invoice, check_existing_reference=True)

        self.assertEqual(task_id, "task-running")
        upload.assert_not_called()
        task_status.assert_called_once_with("task-running")

    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "completed", "document_id": 321},
    )
    @patch.object(
        PaperlessClient,
        "task_status",
        return_value={
            "status": "needs_fallback",
            "document_id": None,
            "found": True,
        },
    )
    @patch.object(PaperlessClient, "upload_manual_invoice")
    def test_successful_task_without_document_id_links_reference_document(
        self, upload, task_status, find_document
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="f" * 64,
            paperless_task_id="task-success",
            paperless_status=ManualInvoice.PaperlessStatus.PENDING,
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )

        document_id = start_manual_invoice_upload(
            invoice,
            check_existing_reference=True,
        )

        invoice.refresh_from_db()
        self.assertEqual(document_id, "321")
        self.assertEqual(invoice.paperless_document_id, 321)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        upload.assert_not_called()
        task_status.assert_called_once_with("task-success")
        find_document.assert_called_once_with(str(invoice.reference_uuid))

    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "completed", "document_id": 654},
    )
    @patch.object(PaperlessClient, "upload_manual_invoice")
    @patch.object(PaperlessClient, "is_configured", return_value=True)
    def test_existing_reference_document_prevents_retry_upload(
        self, is_configured, upload, find_document
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="e" * 64,
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
            paperless_error="Vorheriger Fehler",
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )

        document_id = retry_manual_invoice(invoice)

        invoice.refresh_from_db()
        self.assertEqual(document_id, "654")
        self.assertEqual(invoice.paperless_document_id, 654)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        upload.assert_not_called()
        find_document.assert_called_once_with(str(invoice.reference_uuid))

    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "pending", "document_id": None},
    )
    @patch.object(PaperlessClient, "upload_manual_invoice")
    @patch.object(PaperlessClient, "is_configured", return_value=True)
    def test_retry_without_pdf_returns_reupload_instruction(
        self, is_configured, upload, find_document
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="n" * 64,
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )

        with self.assertRaisesRegex(
            BookkeepingPaperlessError,
            "ursprüngliche PDF ist nicht mehr verfügbar",
        ):
            retry_manual_invoice(invoice)

        upload.assert_not_called()
        find_document.assert_called_once_with(str(invoice.reference_uuid))

    @patch.object(PaperlessClient, "upload_manual_invoice", side_effect=BookkeepingPaperlessError("Upload fehlgeschlagen"))
    @patch.object(invoice_ai, "OpenAI")
    def test_failed_paperless_upload_does_not_start_openai(self, openai, upload):
        response = self.upload_invoice(content=b"%PDF- failed upload")
        invoice = ManualInvoice.objects.get()

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.FAILED)
        openai.assert_not_called()
        upload.assert_called_once_with(invoice)

    @patch.object(PaperlessClient, "document_ocr_text", return_value="")
    @patch.object(invoice_ai, "OpenAI")
    def test_completed_paperless_document_with_empty_ocr_waits_without_openai(
        self, openai, ocr
    ):
        invoice = ManualInvoice.objects.create(
            file_hash="o" * 64,
            paperless_document_id=256,
            paperless_status=ManualInvoice.PaperlessStatus.COMPLETED,
        )

        response = self.client.get(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abgelegt")
        self.assertContains(response, "Nicht verfügbar")
        self.assertContains(response, "Nicht gestartet")
        self.assertNotContains(response, "OCR noch nicht verfügbar")
        self.assertEqual(invoice.ai_status, ManualInvoice.AIStatus.NOT_STARTED)
        openai.assert_not_called()
        ocr.assert_called_once_with(256)

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example")
    @patch.object(PaperlessClient, "document_ocr_text", return_value="")
    def test_paperless_link_is_visible_after_document_association(self, ocr):
        invoice = ManualInvoice.objects.create(
            file_hash="l" * 64,
            paperless_document_id=256,
            paperless_status=ManualInvoice.PaperlessStatus.COMPLETED,
        )

        response = self.client.get(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid})
        )

        self.assertContains(response, "In Paperless öffnen")
        self.assertContains(response, 'href="https://paperless.example/documents/256/"')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        ocr.assert_called_once_with(256)

    @patch.object(PaperlessClient, "upload_manual_invoice", side_effect=BookkeepingPaperlessError("Paperless nicht erreichbar."))
    @patch.object(PaperlessClient, "find_document_by_reference", return_value={"status": "pending", "document_id": None})
    def test_paperless_error_keeps_draft_and_booking_data_and_retry_is_possible(self, find_document, upload):
        response = self.upload_invoice(content=b"%PDF- retryable upload")
        invoice = ManualInvoice.objects.get()

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertContains(
            self.client.get(response["Location"]),
            "Paperless nicht erreichbar.",
        )
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.FAILED)

        upload.side_effect = None
        upload.return_value = "retry-task"
        retry_response = self.client.post(
            reverse("manual_invoice_list"),
            {
                "action": "retry_manual_invoice",
                "reference_uuid": str(invoice.reference_uuid),
            },
        )

        invoice.refresh_from_db()
        self.assertEqual(retry_response.status_code, 302)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.PENDING)
        self.assertEqual(invoice.paperless_task_id, "retry-task")
        self.assertEqual(upload.call_count, 2)

    @patch.object(
        PaperlessClient,
        "task_status",
        return_value={"status": "completed", "document_id": 256},
    )
    def test_completed_task_sets_document_id_and_removes_temporary_pdf(self, task_status):
        invoice = ManualInvoice.objects.create(
            file_hash="b" * 64,
            payment_date=date(2026, 7, 15),
            paperless_task_id="task-manual",
            paperless_status=ManualInvoice.PaperlessStatus.PENDING,
            temporary_pdf=SimpleUploadedFile("rechnung.pdf", b"%PDF- test"),
        )
        stored_name = invoice.temporary_pdf.name

        refresh_pending_manual_invoice_tasks()

        invoice.refresh_from_db()
        self.assertEqual(invoice.paperless_document_id, 256)
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        self.assertFalse(invoice.temporary_pdf)
        self.assertFalse(invoice.temporary_pdf.storage.exists(stored_name))
        task_status.assert_called_once_with("task-manual")

    @patch.object(PaperlessClient, "upload_manual_invoice", return_value="task-manual")
    def test_ready_manual_entries_are_in_period_control_and_csv(self, upload):
        invoice = self.uploaded_invoice()
        response = self.client.post(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": invoice.reference_uuid}),
            self.finalize_data(),
        )
        self.assertEqual(response.status_code, 302)

        ready_response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": "reviewed",
                "period_type": "month",
                "period": "2026-07",
            },
        )
        self.assertContains(ready_response, "Lieferant")
        self.assertEqual(ready_response.context["quarter_control"]["manual_booking_entries"], 1)
        self.assertContains(ready_response, "Manuelle Buchungszeilen")

        from .csv_export import export_reviewed_transactions_csv

        csv_content = export_reviewed_transactions_csv(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        ).decode("utf-8-sig")
        self.assertIn("PR;7;15.07.2026;Büromaterial", csv_content)
        upload.assert_not_called()


class SupportingDocumentTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

    def rule(self, name="Miete"):
        return MatchingRule.objects.create(
            name=name,
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
        )

    def transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "value_date": date(2026, 7, 14),
            "partner_name": "Mieter GmbH",
            "amount": Decimal("100.00"),
            "direction": BankTransaction.Direction.INCOMING,
            "status": BankTransaction.Status.REVIEWED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def pdf(self, name="beleg.pdf", content=b"%PDF-1.7\nbeleg"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def create_document(self, **overrides):
        values = {
            "matching_rule": self.rule(),
            "original_filename": "nachweis.pdf",
            "temporary_file": self.pdf(),
            "transfer_status": SupportingDocument.TransferStatus.FAILED,
        }
        values.update(overrides)
        return SupportingDocument.objects.create(**values)

    def test_document_requires_exactly_one_owner(self):
        with self.assertRaises(ValidationError):
            SupportingDocument.objects.create(original_filename="leer.pdf")
        with self.assertRaises(ValidationError):
            SupportingDocument.objects.create(
                matching_rule=self.rule(),
                bank_transaction=self.transaction(),
                original_filename="zwei.pdf",
            )

    def test_documents_for_two_rule_versions_are_separate(self):
        first = self.rule("Miete")
        second = MatchingRule.objects.create(
            name="Miete",
            direction=first.direction,
            match_type=first.match_type,
            iban=first.iban,
            expected_amount=first.expected_amount,
            previous_version=first,
            version_number=2,
            change_reason="Neue Kondition",
        )
        first_document = self.create_document(matching_rule=first)
        second_document = self.create_document(matching_rule=second)

        self.assertEqual(first.supporting_documents.count(), 1)
        self.assertEqual(second.supporting_documents.count(), 1)
        self.assertNotEqual(first_document.reference_uuid, second_document.reference_uuid)

    def test_each_document_gets_a_unique_non_editable_uuid(self):
        first = self.create_document()
        second = self.create_document()

        self.assertNotEqual(first.reference_uuid, second.reference_uuid)
        self.assertFalse(SupportingDocument._meta.get_field("reference_uuid").editable)

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "_request_multipart", return_value={"task_id": "task-fallback"})
    @patch.object(PaperlessClient, "_require_custom_field", side_effect=lambda name, data_type: {
        "q_bookkeeping_referenz": 10,
        "q_buchungsdatum": 11,
        "q_buchungsmonat": 12,
        "q_buchungsquartal": 13,
    }[name])
    @patch.object(PaperlessClient, "_require_storage_path", return_value=14)
    @patch.object(PaperlessClient, "_require_named", return_value=15)
    def test_bank_metadata_falls_back_to_booking_date(
        self, require_named, require_storage, require_field, multipart
    ):
        transaction = self.transaction(value_date=None, booking_date=date(2026, 8, 3))
        document = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
            transfer_status=SupportingDocument.TransferStatus.PENDING,
        )
        PaperlessClient.upload_supporting_document(document)

        fields = dict(multipart.call_args.kwargs["form_fields"])
        self.assertEqual(fields["title"], "Buchungsbeleg 2026-08-03 – Mieter GmbH – 100.00")
        self.assertEqual(json.loads(fields["custom_fields"])["11"], "2026-08-03")
        self.assertEqual(json.loads(fields["custom_fields"])["12"], "2026-08")
        self.assertEqual(json.loads(fields["custom_fields"])["13"], "2026-Q3")

    def test_pdf_form_rejects_extension_content_type_and_signature(self):
        for uploaded_file in (
            self.pdf("beleg.txt"),
            SimpleUploadedFile("beleg.pdf", b"kein pdf", content_type="text/plain"),
            SimpleUploadedFile("beleg.pdf", b"kein pdf", content_type="application/pdf"),
        ):
            form = SupportingDocumentUploadForm(files={"pdf": uploaded_file})
            self.assertFalse(form.is_valid())

    def test_import_service_rejects_non_pdf_even_without_form(self):
        with self.assertRaises(SupportingDocumentError):
            import_supporting_document(
                SimpleUploadedFile(
                    "beleg.pdf",
                    b"kein pdf",
                    content_type="application/pdf",
                ),
                matching_rule=self.rule(),
            )

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="task-1")
    def test_upload_to_matching_rule_uses_same_uuid_and_keeps_pending_file(self, upload):
        rule = self.rule()
        result = import_supporting_document(self.pdf(), matching_rule=rule)

        document = result.document
        self.assertEqual(document.transfer_status, SupportingDocument.TransferStatus.PENDING)
        self.assertEqual(document.paperless_task_id, "task-1")
        self.assertTrue(document.temporary_file)
        upload.assert_called_once_with(document)

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="task-bank")
    def test_upload_to_bank_transaction_does_not_change_status(self, upload):
        transaction = self.transaction(status=BankTransaction.Status.BOOKED)
        result = import_supporting_document(self.pdf(), bank_transaction=transaction)

        transaction.refresh_from_db()
        self.assertEqual(transaction.status, BankTransaction.Status.BOOKED)
        self.assertEqual(result.document.bank_transaction_id, transaction.pk)
        upload.assert_called_once()

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "_request_multipart", return_value={"task_id": "task-rule"})
    @patch.object(PaperlessClient, "_require_custom_field", return_value=17)
    @patch.object(PaperlessClient, "_require_storage_path", return_value=18)
    @patch.object(PaperlessClient, "_require_named", return_value=19)
    def test_matching_metadata_uses_required_names_and_only_reference_field(
        self, require_named, require_storage, require_field, multipart
    ):
        document = self.create_document(
            transfer_status=SupportingDocument.TransferStatus.PENDING
        )
        task_id = PaperlessClient.upload_supporting_document(document)

        self.assertEqual(task_id, "task-rule")
        fields = dict(multipart.call_args.kwargs["form_fields"])
        custom_fields = json.loads(fields["custom_fields"])
        self.assertEqual(custom_fields, {"17": str(document.reference_uuid)})
        require_storage.assert_called_once_with("IFKG Matching-Nachweise")
        names = [call.args[1] for call in require_named.call_args_list]
        self.assertIn("Buchungsbeleg", names)
        self.assertIn("Diverse", names)
        self.assertIn("Buchhaltung", names)
        self.assertIn("Immo-Fuchs KG", names)
        self.assertEqual(require_field.call_args.args[0], "q_bookkeeping_referenz")

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "_request_multipart", return_value={"task_id": "task-bank"})
    @patch.object(PaperlessClient, "_require_custom_field", side_effect=lambda name, data_type: {
        "q_bookkeeping_referenz": 10,
        "q_buchungsdatum": 11,
        "q_buchungsmonat": 12,
        "q_buchungsquartal": 13,
    }[name])
    @patch.object(PaperlessClient, "_require_storage_path", return_value=14)
    @patch.object(PaperlessClient, "_require_named", return_value=15)
    def test_bank_metadata_prefers_value_date_and_sets_period_fields(
        self, require_named, require_storage, require_field, multipart
    ):
        transaction = self.transaction(value_date=date(2026, 7, 14))
        document = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
            transfer_status=SupportingDocument.TransferStatus.PENDING,
        )
        PaperlessClient.upload_supporting_document(document)

        fields = dict(multipart.call_args.kwargs["form_fields"])
        self.assertEqual(fields["title"], "Buchungsbeleg 2026-07-14 – Mieter GmbH – 100.00")
        self.assertEqual(
            json.loads(fields["custom_fields"]),
            {
                "10": str(document.reference_uuid),
                "11": "2026-07-14",
                "12": "2026-07",
                "13": "2026-Q3",
            },
        )
        require_storage.assert_called_once_with("IFKG Buchungsbelege")

    @patch.object(PaperlessClient, "task_status", return_value={"status": "completed", "document_id": 321})
    @patch.object(PaperlessClient, "upload_supporting_document")
    def test_completed_task_stores_document_id_and_removes_file(self, upload, task_status):
        document = self.create_document(
            paperless_task_id="task-completed",
            transfer_status=SupportingDocument.TransferStatus.PENDING,
        )
        stored_name = document.temporary_file.name

        refresh_pending_supporting_documents()

        document.refresh_from_db()
        self.assertEqual(document.paperless_document_id, 321)
        self.assertEqual(document.transfer_status, SupportingDocument.TransferStatus.COMPLETED)
        self.assertFalse(document.temporary_file)
        self.assertFalse(document.temporary_file.storage.exists(stored_name))
        upload.assert_not_called()
        task_status.assert_called_once_with("task-completed")

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="retry-task")
    @patch.object(PaperlessClient, "find_document_by_reference", return_value={"status": "pending", "document_id": None})
    def test_retry_uses_same_document_and_does_not_create_duplicate(self, find_document, upload):
        document = self.create_document()

        retry_supporting_document(document)

        document.refresh_from_db()
        self.assertEqual(document.paperless_task_id, "retry-task")
        self.assertEqual(SupportingDocument.objects.count(), 1)
        find_document.assert_called_once_with(str(document.reference_uuid))
        upload.assert_called_once_with(document)

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="task-no-ocr")
    @patch("bookkeeping.paperless.PaperlessClient.document_ocr_text")
    @patch("bookkeeping.invoice_ai.run_manual_invoice_analysis")
    def test_bank_transaction_document_never_calls_ocr_or_openai(
        self, run_openai, ocr, upload
    ):
        result = import_supporting_document(
            self.pdf(),
            bank_transaction=self.transaction(),
        )

        self.assertEqual(result.document.transfer_status, SupportingDocument.TransferStatus.PENDING)
        ocr.assert_not_called()
        run_openai.assert_not_called()
        upload.assert_called_once()

    @patch.object(PaperlessClient, "task_status", side_effect=BookkeepingPaperlessError("unklar"))
    @patch.object(PaperlessClient, "upload_supporting_document")
    def test_unclear_task_state_does_not_start_second_upload(self, upload, task_status):
        document = self.create_document(paperless_task_id="task-unclear")

        with self.assertRaises(SupportingDocumentError):
            retry_supporting_document(document)

        upload.assert_not_called()
        task_status.assert_called_once_with("task-unclear")

    @patch.object(PaperlessClient, "upload_supporting_document")
    def test_existing_document_id_is_reused_without_upload(self, upload):
        document = self.create_document(paperless_document_id=459)

        retry_supporting_document(document)

        document.refresh_from_db()
        self.assertEqual(document.transfer_status, SupportingDocument.TransferStatus.COMPLETED)
        upload.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_local_delete_without_document_id_does_not_call_paperless(self, delete):
        document = self.create_document(paperless_document_id=None)
        url = reverse(
            "matching_rule_document_delete",
            kwargs={
                "rule_pk": document.matching_rule_id,
                "reference_uuid": document.reference_uuid,
            },
        )

        self.client.post(url)

        delete.assert_not_called()
        self.assertFalse(SupportingDocument.objects.filter(pk=document.pk).exists())

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="task-rule-ui")
    def test_matching_rule_upload_ui_creates_document_for_that_version(self, upload):
        rule = self.rule()
        response = self.client.post(
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
            {"action": "upload_supporting_document", "pdf": self.pdf()},
        )

        self.assertEqual(response.status_code, 302)
        document = SupportingDocument.objects.get()
        self.assertEqual(document.matching_rule_id, rule.pk)
        self.assertEqual(document.transfer_status, SupportingDocument.TransferStatus.PENDING)
        upload.assert_called_once_with(document)

    def test_open_and_ready_overview_shows_compact_document_count(self):
        transaction = self.transaction(status=BankTransaction.Status.REVIEWED)
        self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
            transfer_status=SupportingDocument.TransferStatus.PENDING,
        )

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": BankTransaction.Status.REVIEWED, "period_type": "month", "period": "2026-07"},
        )

        self.assertContains(response, "1 Belege")
        self.assertContains(response, reverse("bank_transaction_booking", kwargs={"pk": transaction.pk}))

    @patch.object(PaperlessClient, "delete_document")
    def test_unlink_get_does_not_call_paperless_delete_and_post_removes_local_only(self, delete):
        rule = self.rule()
        document = self.create_document(matching_rule=rule)
        url = reverse(
            "matching_rule_document_remove",
            kwargs={"rule_pk": rule.pk, "reference_uuid": document.reference_uuid},
        )

        self.client.get(url)
        self.assertTrue(SupportingDocument.objects.filter(pk=document.pk).exists())
        delete.assert_not_called()
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
        )
        self.assertFalse(SupportingDocument.objects.filter(pk=document.pk).exists())
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_confirmation_cancel_uses_actual_owner_url_for_matching_and_bank(self, delete):
        rule = self.rule()
        matching_document = self.create_document(matching_rule=rule)
        matching_url = reverse(
            "matching_rule_document_remove",
            kwargs={"rule_pk": rule.pk, "reference_uuid": matching_document.reference_uuid},
        )
        matching_response = self.client.get(matching_url)

        self.assertEqual(
            matching_response.context["owner_url"],
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
        )
        self.assertNotIn(str(matching_document.reference_uuid), matching_response.context["owner_url"])
        self.assertContains(matching_response, matching_response.context["owner_url"])
        self.assertTrue(SupportingDocument.objects.filter(pk=matching_document.pk).exists())

        transaction = self.transaction()
        bank_document = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
        )
        bank_url = reverse(
            "bank_transaction_document_remove",
            kwargs={"transaction_pk": transaction.pk, "reference_uuid": bank_document.reference_uuid},
        )
        bank_response = self.client.get(bank_url)

        self.assertEqual(
            bank_response.context["owner_url"],
            reverse("bank_transaction_booking", kwargs={"pk": transaction.pk}),
        )
        self.assertNotIn(str(bank_document.reference_uuid), bank_response.context["owner_url"])
        self.assertContains(bank_response, bank_response.context["owner_url"])
        self.assertTrue(SupportingDocument.objects.filter(pk=bank_document.pk).exists())
        delete.assert_not_called()

    def test_delete_confirmation_cancel_uses_actual_owner_url(self):
        rule = self.rule()
        matching_document = self.create_document(matching_rule=rule)
        matching_response = self.client.get(
            reverse(
                "matching_rule_document_delete",
                kwargs={"rule_pk": rule.pk, "reference_uuid": matching_document.reference_uuid},
            )
        )
        self.assertEqual(
            matching_response.context["owner_url"],
            reverse("matching_rule_detail", kwargs={"pk": rule.pk}),
        )

        transaction = self.transaction()
        bank_document = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
        )
        bank_response = self.client.get(
            reverse(
                "bank_transaction_document_delete",
                kwargs={"transaction_pk": transaction.pk, "reference_uuid": bank_document.reference_uuid},
            )
        )
        self.assertEqual(
            bank_response.context["owner_url"],
            reverse("bank_transaction_booking", kwargs={"pk": transaction.pk}),
        )

    @patch.object(PaperlessClient, "delete_document")
    def test_successful_paperless_delete_removes_local_document(self, delete):
        document = self.create_document(paperless_document_id=456)
        url = reverse(
            "matching_rule_document_delete",
            kwargs={
                "rule_pk": document.matching_rule_id,
                "reference_uuid": document.reference_uuid,
            },
        )

        self.client.get(url)
        self.assertTrue(SupportingDocument.objects.filter(pk=document.pk).exists())
        response = self.client.post(url)

        delete.assert_called_once_with(456)
        self.assertEqual(
            response["Location"],
            reverse("matching_rule_detail", kwargs={"pk": document.matching_rule_id}),
        )
        self.assertFalse(SupportingDocument.objects.filter(pk=document.pk).exists())

    @patch.object(PaperlessClient, "delete_document")
    def test_successful_bank_document_unlink_returns_to_actual_transaction(self, delete):
        transaction = self.transaction(status=BankTransaction.Status.BOOKED)
        document = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
        )
        url = reverse(
            "bank_transaction_document_remove",
            kwargs={"transaction_pk": transaction.pk, "reference_uuid": document.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(
            response["Location"],
            reverse("bank_transaction_booking", kwargs={"pk": transaction.pk}),
        )
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, BankTransaction.Status.BOOKED)
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document", side_effect=BookkeepingPaperlessError("API-Fehler"))
    def test_failed_paperless_delete_keeps_local_document(self, delete):
        document = self.create_document(paperless_document_id=457)
        url = reverse(
            "matching_rule_document_delete",
            kwargs={
                "rule_pk": document.matching_rule_id,
                "reference_uuid": document.reference_uuid,
            },
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], url)
        self.assertTrue(SupportingDocument.objects.filter(pk=document.pk).exists())
        delete.assert_called_once_with(457)

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example")
    def test_booking_page_shows_paperless_link_only_for_existing_document(self):
        transaction = self.transaction()
        completed = self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
            transfer_status=SupportingDocument.TransferStatus.COMPLETED,
            paperless_document_id=458,
        )
        response = self.client.get(
            reverse("bank_transaction_booking", kwargs={"pk": transaction.pk})
        )

        self.assertContains(response, "In Paperless öffnen")
        self.assertContains(response, PaperlessClient.document_url(458))
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "Belege")
        self.assertEqual(completed.transfer_status, SupportingDocument.TransferStatus.COMPLETED)

    def test_booking_page_does_not_show_link_without_document_id(self):
        transaction = self.transaction()
        self.create_document(
            matching_rule=None,
            bank_transaction=transaction,
            transfer_status=SupportingDocument.TransferStatus.PENDING,
            paperless_document_id=None,
        )
        response = self.client.get(
            reverse("bank_transaction_booking", kwargs={"pk": transaction.pk})
        )

        self.assertNotContains(response, "In Paperless öffnen")

    @patch.object(PaperlessClient, "upload_supporting_document", return_value="task-ui")
    def test_bank_upload_ui_keeps_transaction_status_and_supports_multiple_documents(self, upload):
        transaction = self.transaction(status=BankTransaction.Status.BOOKED)
        url = reverse("bank_transaction_booking", kwargs={"pk": transaction.pk})
        first_response = self.client.post(
            url,
            {"action": "upload_supporting_document", "pdf": self.pdf("eins.pdf")},
        )
        second_response = self.client.post(
            url,
            {"action": "upload_supporting_document", "pdf": self.pdf("zwei.pdf")},
        )

        transaction.refresh_from_db()
        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(transaction.status, BankTransaction.Status.BOOKED)
        self.assertEqual(transaction.supporting_documents.count(), 2)
        self.assertEqual(upload.call_count, 2)


class BookingSetResetAndManualDeletionTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

    def rule(self):
        return MatchingRule.objects.create(
            name="BHG14_1",
            direction=MatchingRule.Direction.OUTGOING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
        )

    def transaction(self, **overrides):
        values = {
            "booking_date": date(2026, 7, 15),
            "value_date": date(2026, 7, 14),
            "partner_name": "BHG14_1",
            "partner_iban": "AT611904300234573201",
            "amount": Decimal("-100.00"),
            "currency": "EUR",
            "purpose": "Buchungstext original",
            "direction": BankTransaction.Direction.OUTGOING,
            "status": BankTransaction.Status.REVIEWED,
        }
        values.update(overrides)
        return BankTransaction.objects.create(**values)

    def invoice(self, **overrides):
        values = {
            "file_hash": uuid.uuid4().hex * 2,
            "status": ManualInvoice.Status.READY,
            "invoice_number": "INV-14",
            "invoice_date": date(2026, 7, 10),
            "payment_date": date(2026, 7, 15),
            "partner_name": "BHG14_1",
            "gross_amount": Decimal("100.00"),
            "notes": "Originale Anmerkung",
            "paperless_task_id": "task-existing",
            "paperless_document_id": 812,
            "paperless_status": ManualInvoice.PaperlessStatus.COMPLETED,
            "ai_status": ManualInvoice.AIStatus.COMPLETED,
            "ai_model_used": "test-model",
            "ai_result": {"invoice_number": "INV-14"},
            "ai_error": "",
            "temporary_pdf": SimpleUploadedFile(
                "rechnung-14.pdf",
                b"%PDF-1.7\nrechnung",
                content_type="application/pdf",
            ),
        }
        values.update(overrides)
        return ManualInvoice.objects.create(**values)

    def bank_entry(self, transaction, text="Bankbuchung"):
        return BookingEntry.objects.create(
            bank_transaction=transaction,
            payment_date=date(2026, 7, 15),
            booking_text=text,
            partner_name="BHG14_1",
            gross_amount=Decimal("-100.00"),
        )

    def manual_entry(self, invoice, text="Manuelle Buchung"):
        return ManualInvoiceEntry.objects.create(
            manual_invoice=invoice,
            payment_date=date(2026, 7, 15),
            booking_text=text,
            partner_name="BHG14_1",
            gross_amount=Decimal("100.00"),
        )

    @patch.object(PaperlessClient, "delete_document")
    def test_bank_reset_get_is_read_only_and_post_keeps_source_and_supporting_document(self, delete):
        rule = self.rule()
        transaction = self.transaction(matched_rule=rule)
        entry = self.bank_entry(transaction)
        supporting_document = SupportingDocument.objects.create(
            bank_transaction=transaction,
            original_filename="bankbeleg.pdf",
            transfer_status=SupportingDocument.TransferStatus.COMPLETED,
            paperless_document_id=813,
        )
        url = reverse(
            "bank_transaction_reset_booking",
            kwargs={"transaction_pk": transaction.pk},
        )

        get_response = self.client.get(url)
        self.assertContains(get_response, "Buchungssatz zurücksetzen")
        self.assertTrue(BookingEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(SupportingDocument.objects.filter(pk=supporting_document.pk).exists())
        delete.assert_not_called()

        post_response = self.client.post(url)

        transaction.refresh_from_db()
        self.assertEqual(post_response.status_code, 302)
        self.assertIn("status=open", post_response["Location"])
        self.assertIn("month=2026-07", post_response["Location"])
        self.assertTrue(BankTransaction.objects.filter(pk=transaction.pk).exists())
        self.assertEqual(transaction.status, BankTransaction.Status.MATCHED)
        self.assertEqual(transaction.purpose, "Buchungstext original")
        self.assertFalse(BookingEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(SupportingDocument.objects.filter(pk=supporting_document.pk).exists())
        delete.assert_not_called()

    def test_unmatched_bank_reset_returns_to_imported_without_matching(self):
        transaction = self.transaction(
            matched_rule=None,
            status=BankTransaction.Status.BOOKED,
        )
        self.bank_entry(transaction)

        reset_bank_transaction_booking(transaction)

        transaction.refresh_from_db()
        self.assertEqual(transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(transaction.matched_rule_id)
        self.assertEqual(transaction.booking_entries.count(), 0)

    def test_bank_reset_only_deletes_entries_of_selected_transaction(self):
        selected = self.transaction()
        other = self.transaction(partner_name="Andere Quelle")
        selected_entry = self.bank_entry(selected, text="Ausgewählt")
        other_entry = self.bank_entry(other, text="Andere Transaktion")

        reset_bank_transaction_booking(selected)

        self.assertFalse(BookingEntry.objects.filter(pk=selected_entry.pk).exists())
        self.assertTrue(BookingEntry.objects.filter(pk=other_entry.pk).exists())
        self.assertTrue(BankTransaction.objects.filter(pk=selected.pk).exists())
        self.assertTrue(BankTransaction.objects.filter(pk=other.pk).exists())

    def test_bank_reset_requires_post_with_csrf(self):
        transaction = self.transaction()
        entry = self.bank_entry(transaction)
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse(
                "bank_transaction_reset_booking",
                kwargs={"transaction_pk": transaction.pk},
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(BookingEntry.objects.filter(pk=entry.pk).exists())

    def test_manual_reset_get_and_post_keep_invoice_paperless_and_ai_data(self):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        document_name = invoice.temporary_pdf.name
        original_reference = invoice.reference_uuid
        url = reverse(
            "manual_invoice_reset_booking",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        with patch.object(PaperlessClient, "delete_document") as delete, patch(
            "bookkeeping.invoice_ai.run_manual_invoice_analysis"
        ) as analyze:
            get_response = self.client.get(url)
            self.assertContains(get_response, "BHG14_1")
            self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
            delete.assert_not_called()
            analyze.assert_not_called()

            post_response = self.client.post(url)

        invoice.refresh_from_db()
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response["Location"], reverse("manual_invoice_list"))
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertEqual(invoice.reference_uuid, original_reference)
        self.assertEqual(invoice.paperless_document_id, 812)
        self.assertEqual(invoice.paperless_task_id, "task-existing")
        self.assertEqual(invoice.ai_status, ManualInvoice.AIStatus.COMPLETED)
        self.assertEqual(invoice.ai_result, {"invoice_number": "INV-14"})
        self.assertTrue(invoice.temporary_pdf)
        self.assertTrue(invoice.temporary_pdf.storage.exists(document_name))
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    def test_manual_reset_without_entries_is_controlled_and_returns_to_draft(self):
        invoice = self.invoice()

        reset_manual_invoice_booking(invoice)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())

    def test_manual_reset_rolls_back_when_entry_deletion_fails(self):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)

        with patch(
            "bookkeeping.booking_resets.ManualInvoiceEntry.objects.filter",
            side_effect=RuntimeError("DB-Fehler"),
        ), self.assertRaises(RuntimeError):
            reset_manual_invoice_booking(invoice)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @patch.object(PaperlessClient, "delete_document")
    def test_manual_delete_get_is_read_only_and_shows_relevant_data(self, delete):
        invoice = self.invoice()
        self.manual_entry(invoice, text="Löschen prüfen")
        url = reverse(
            "manual_invoice_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.get(url)

        self.assertContains(response, "INV-14")
        self.assertContains(response, "BHG14_1")
        self.assertContains(response, "812")
        self.assertContains(response, "rechnung-14.pdf")
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_manual_delete_uses_saved_paperless_id_then_deletes_local_data(self, delete):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        document_name = invoice.temporary_pdf.name
        transaction = self.transaction()
        supporting_document = SupportingDocument.objects.create(
            bank_transaction=transaction,
            original_filename="bankbeleg.pdf",
            transfer_status=SupportingDocument.TransferStatus.COMPLETED,
            paperless_document_id=814,
        )
        url = reverse(
            "manual_invoice_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        delete.assert_called_once_with(812)
        self.assertFalse(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        self.assertFalse(invoice.temporary_pdf.storage.exists(document_name))
        self.assertTrue(SupportingDocument.objects.filter(pk=supporting_document.pk).exists())
        self.assertTrue(BankTransaction.objects.filter(pk=transaction.pk).exists())

    @patch.object(PaperlessClient, "delete_document", side_effect=BookkeepingPaperlessError("Paperless-Fehler"))
    def test_manual_delete_paperless_error_keeps_invoice_entries_and_file(self, delete):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        document_name = invoice.temporary_pdf.name
        url = reverse(
            "manual_invoice_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], url)
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(invoice.temporary_pdf.storage.exists(document_name))
        delete.assert_called_once_with(812)

    @patch.object(PaperlessClient, "delete_document")
    def test_manual_delete_rolls_back_local_data_when_database_delete_fails(self, delete):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)

        with patch(
            "bookkeeping.manual_invoices.ManualInvoiceEntry.objects.filter",
            side_effect=RuntimeError("DB-Fehler"),
        ), self.assertRaises(ManualInvoiceDeletionError):
            delete_manual_invoice_completely(invoice)

        delete.assert_called_once_with(812)
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "completed", "document_id": 815},
    )
    def test_missing_document_id_resolves_one_uuid_match_and_deletes_it(
        self, find_document, delete
    ):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )
        url = reverse(
            "manual_invoice_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        self.client.post(url)

        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_called_once_with(815)
        self.assertFalse(ManualInvoice.objects.filter(pk=invoice.pk).exists())

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        side_effect=BookkeepingPaperlessError(
            "In Paperless wurden mehrere Dokumente mit derselben Bookkeeping-Referenz gefunden."
        ),
    )
    def test_multiple_uuid_matches_block_local_delete(self, find_document, delete):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )
        entry = self.manual_entry(invoice)

        with self.assertRaises(ManualInvoiceDeletionError) as error:
            delete_manual_invoice_completely(invoice)

        self.assertIn("mehrere Dokumente", str(error.exception))
        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_not_called()
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "pending", "document_id": None},
    )
    def test_pending_or_unclear_uuid_resolution_blocks_local_delete(
        self, find_document, delete
    ):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="task-pending",
            paperless_status=ManualInvoice.PaperlessStatus.PENDING,
        )
        entry = self.manual_entry(invoice)
        with patch.object(
            PaperlessClient,
            "task_status",
            return_value={"status": "pending", "document_id": None},
        ) as task_status:
            with self.assertRaises(ManualInvoiceDeletionError) as error:
                delete_manual_invoice_completely(invoice)

        self.assertIn("noch nicht eindeutig", str(error.exception))
        task_status.assert_called_once_with("task-pending")
        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_not_called()
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @override_settings(PAPERLESS_BASE_URL="https://paperless.example", PAPERLESS_API_TOKEN="token")
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "pending", "document_id": None},
    )
    def test_uuid_lookup_with_no_document_allows_local_delete(self, find_document, delete):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )
        entry = self.manual_entry(invoice)

        delete_manual_invoice_completely(invoice)

        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_not_called()
        self.assertFalse(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @patch.object(PaperlessClient, "delete_document", side_effect=BookkeepingPaperlessError("Paperless antwortet mit HTTP-Status 404."))
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "pending", "document_id": None},
    )
    def test_missing_saved_paperless_document_is_handled_as_already_deleted(
        self, find_document, delete
    ):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)

        delete_manual_invoice_completely(invoice)

        delete.assert_called_once_with(812)
        find_document.assert_called_once_with(str(invoice.reference_uuid))
        self.assertFalse(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())

    @patch.object(PaperlessClient, "delete_document")
    def test_manual_delete_requires_csrf(self, delete):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse(
                "manual_invoice_delete",
                kwargs={"reference_uuid": invoice.reference_uuid},
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        delete.assert_not_called()

    def test_manual_delete_and_reset_actions_are_visible_in_required_views(self):
        draft = self.invoice(status=ManualInvoice.Status.DRAFT)
        list_response = self.client.get(reverse("manual_invoice_list"))
        self.assertContains(list_response, "Beleg vollständig löschen")
        self.assertContains(
            list_response,
            reverse("manual_invoice_delete", kwargs={"reference_uuid": draft.reference_uuid}),
        )

        edit_response = self.client.get(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": draft.reference_uuid},
            )
        )
        self.assertContains(edit_response, "Buchungssatz zurücksetzen")
        self.assertContains(edit_response, "Beleg vollständig löschen")

        ready = self.invoice()
        self.manual_entry(ready)
        ready_response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": BankTransaction.Status.REVIEWED,
                "period_type": "month",
                "period": "2026-07",
            },
        )
        self.assertContains(ready_response, "Buchungssatz zurücksetzen")
        self.assertContains(ready_response, "Beleg vollständig löschen")

    def test_paperless_only_action_is_visible_in_draft_edit_and_ready_views(self):
        draft = self.invoice(status=ManualInvoice.Status.DRAFT)
        list_response = self.client.get(reverse("manual_invoice_list"))
        self.assertContains(list_response, "Nur aus Paperless löschen")
        self.assertContains(
            list_response,
            reverse(
                "manual_invoice_paperless_delete",
                kwargs={"reference_uuid": draft.reference_uuid},
            ),
        )

        edit_response = self.client.get(
            reverse(
                "manual_invoice_edit",
                kwargs={"reference_uuid": draft.reference_uuid},
            )
        )
        self.assertContains(edit_response, "Nur aus Paperless löschen")

        ready = self.invoice()
        self.manual_entry(ready)
        ready_response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": BankTransaction.Status.REVIEWED,
                "period_type": "month",
                "period": "2026-07",
            },
        )
        self.assertContains(ready_response, "Nur aus Paperless löschen")

        deleted = self.invoice(
            status=ManualInvoice.Status.DRAFT,
            paperless_deleted_at=timezone.now(),
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.DELETED,
        )
        deleted_response = self.client.get(
            reverse("manual_invoice_edit", kwargs={"reference_uuid": deleted.reference_uuid})
        )
        self.assertContains(deleted_response, "Aus Paperless gelöscht")
        self.assertNotContains(deleted_response, "Nur aus Paperless löschen")
        self.assertNotContains(deleted_response, "In Paperless öffnen")

    def test_ready_manual_invoice_actions_are_compact_icon_links_with_accessible_labels(self):
        invoice = self.invoice()
        self.manual_entry(invoice)
        response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": BankTransaction.Status.REVIEWED,
                "period_type": "month",
                "period": "2026-07",
            },
        )
        content = response.content.decode()

        for label in (
            "Bearbeiten",
            "In Paperless öffnen",
            "Nur aus Paperless löschen",
            "Buchungssatz zurücksetzen",
            "Beleg vollständig löschen",
        ):
            self.assertIn(f'title="{label}"', content)
            self.assertIn(f'aria-label="{label}"', content)
        for icon in (
            "bi-pencil",
            "bi-box-arrow-up-right",
            "bi-file-earmark-x",
            "bi-arrow-counterclockwise",
            "bi-trash",
        ):
            self.assertIn(f"bi {icon}", content)

        self.assertIn('target="_blank"', content)
        self.assertIn('rel="noopener noreferrer"', content)
        self.assertIn(
            f'href="{reverse("manual_invoice_paperless_delete", kwargs={"reference_uuid": invoice.reference_uuid})}"',
            content,
        )
        self.assertIn(
            f'href="{reverse("manual_invoice_delete", kwargs={"reference_uuid": invoice.reference_uuid})}"',
            content,
        )
        self.assertIn(
            f'href="{reverse("manual_invoice_reset_booking", kwargs={"reference_uuid": invoice.reference_uuid})}"',
            content,
        )
        self.assertNotIn(
            f'<form method="post" action="{reverse("manual_invoice_delete", kwargs={"reference_uuid": invoice.reference_uuid})}"',
            content,
        )

    def test_ready_manual_invoice_without_paperless_document_has_no_paperless_icon(self):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.NOT_STARTED,
        )
        self.manual_entry(invoice)
        response = self.client.get(
            reverse("bookkeeping_overview"),
            {
                "status": BankTransaction.Status.REVIEWED,
                "period_type": "month",
                "period": "2026-07",
            },
        )

        self.assertNotContains(response, 'title="In Paperless öffnen"')
        self.assertNotContains(response, 'aria-label="In Paperless öffnen"')
        self.assertNotContains(response, 'title="Nur aus Paperless löschen"')

    @patch.object(PaperlessClient, "task_status", return_value={"status": "pending", "document_id": None})
    @patch.object(PaperlessClient, "delete_document")
    def test_running_paperless_task_blocks_paperless_only_delete(self, delete, task_status):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="task-pending",
            paperless_status=ManualInvoice.PaperlessStatus.PENDING,
        )

        with self.assertRaises(ManualInvoiceDeletionError):
            delete_manual_invoice_from_paperless(invoice)

        task_status.assert_called_once_with("task-pending")
        delete.assert_not_called()
        invoice.refresh_from_db()
        self.assertIsNone(invoice.paperless_deleted_at)
        self.assertEqual(invoice.paperless_task_id, "task-pending")

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_get_is_read_only_and_shows_invoice_data(self, delete):
        invoice = self.invoice()
        url = reverse(
            "manual_invoice_paperless_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.get(url)

        self.assertContains(response, "INV-14")
        self.assertContains(response, "BHG14_1")
        self.assertContains(response, "rechnung-14.pdf")
        self.assertContains(response, "812")
        self.assertContains(
            response,
            "Der manuelle Beleg, seine Buchungszeilen sowie OCR- und KI-Daten bleiben in Quintus erhalten.",
        )
        invoice.refresh_from_db()
        self.assertIsNone(invoice.paperless_deleted_at)
        self.assertEqual(invoice.paperless_document_id, 812)
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_cancel_is_read_only(self, delete):
        invoice = self.invoice(status=ManualInvoice.Status.DRAFT)
        entry = self.manual_entry(invoice)
        url = reverse(
            "manual_invoice_paperless_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_requires_csrf(self, delete):
        invoice = self.invoice()
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse(
                "manual_invoice_paperless_delete",
                kwargs={"reference_uuid": invoice.reference_uuid},
            )
        )

        self.assertEqual(response.status_code, 403)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.paperless_deleted_at)
        self.assertEqual(invoice.paperless_document_id, 812)
        delete.assert_not_called()

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_keeps_local_invoice_entries_and_status(self, delete):
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        original = {
            "reference_uuid": invoice.reference_uuid,
            "invoice_number": invoice.invoice_number,
            "partner_name": invoice.partner_name,
            "notes": invoice.notes,
            "ai_status": invoice.ai_status,
            "ai_model_used": invoice.ai_model_used,
            "ai_result": invoice.ai_result,
            "temporary_pdf": invoice.temporary_pdf.name,
        }
        url = reverse(
            "manual_invoice_paperless_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("status=reviewed", response["Location"])
        invoice.refresh_from_db()
        self.assertTrue(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        self.assertEqual(invoice.reference_uuid, original["reference_uuid"])
        self.assertEqual(invoice.invoice_number, original["invoice_number"])
        self.assertEqual(invoice.partner_name, original["partner_name"])
        self.assertEqual(invoice.notes, original["notes"])
        self.assertEqual(invoice.ai_status, original["ai_status"])
        self.assertEqual(invoice.ai_model_used, original["ai_model_used"])
        self.assertEqual(invoice.ai_result, original["ai_result"])
        self.assertEqual(invoice.temporary_pdf.name, original["temporary_pdf"])
        self.assertEqual(invoice.status, ManualInvoice.Status.READY)
        self.assertIsNotNone(invoice.paperless_deleted_at)
        self.assertIsNone(invoice.paperless_document_id)
        self.assertEqual(invoice.paperless_task_id, "")
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.DELETED)
        self.assertEqual(invoice.paperless_error, "")
        delete.assert_called_once_with(812)

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_draft_returns_to_manual_invoice_list(self, delete):
        invoice = self.invoice(status=ManualInvoice.Status.DRAFT)
        url = reverse(
            "manual_invoice_paperless_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(response["Location"], reverse("manual_invoice_list"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, ManualInvoice.Status.DRAFT)
        delete.assert_called_once_with(812)

    @patch.object(PaperlessClient, "delete_document")
    def test_paperless_only_delete_error_changes_nothing_locally(self, delete):
        delete.side_effect = BookkeepingPaperlessError("Paperless-Fehler")
        invoice = self.invoice()
        entry = self.manual_entry(invoice)
        document_name = invoice.temporary_pdf.name
        url = reverse(
            "manual_invoice_paperless_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(response["Location"], url)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.paperless_deleted_at)
        self.assertEqual(invoice.paperless_document_id, 812)
        self.assertEqual(invoice.paperless_task_id, "task-existing")
        self.assertEqual(invoice.paperless_status, ManualInvoice.PaperlessStatus.COMPLETED)
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(invoice.temporary_pdf.storage.exists(document_name))
        delete.assert_called_once_with(812)

    @override_settings(
        PAPERLESS_BASE_URL="https://paperless.example",
        PAPERLESS_API_TOKEN="token",
    )
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        return_value={"status": "completed", "document_id": 815},
    )
    def test_paperless_only_delete_resolves_missing_id_by_uuid(self, find_document, delete):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )

        delete_manual_invoice_from_paperless(invoice)

        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_called_once_with(815)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.paperless_deleted_at)

    @override_settings(
        PAPERLESS_BASE_URL="https://paperless.example",
        PAPERLESS_API_TOKEN="token",
    )
    @patch.object(PaperlessClient, "delete_document")
    @patch.object(
        PaperlessClient,
        "find_document_by_reference",
        side_effect=BookkeepingPaperlessError(
            "In Paperless wurden mehrere Dokumente mit derselben Bookkeeping-Referenz gefunden."
        ),
    )
    def test_paperless_only_delete_blocks_multiple_uuid_matches(self, find_document, delete):
        invoice = self.invoice(
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.FAILED,
        )

        with self.assertRaises(ManualInvoiceDeletionError):
            delete_manual_invoice_from_paperless(invoice)

        find_document.assert_called_once_with(str(invoice.reference_uuid))
        delete.assert_not_called()
        invoice.refresh_from_db()
        self.assertIsNone(invoice.paperless_deleted_at)

    @patch.object(PaperlessClient, "delete_document")
    def test_full_delete_after_paperless_only_delete_does_not_call_paperless_again(self, delete):
        invoice = self.invoice(paperless_deleted_at=timezone.now())
        invoice.paperless_status = ManualInvoice.PaperlessStatus.DELETED
        invoice.paperless_document_id = None
        invoice.paperless_task_id = ""
        invoice.save(
            update_fields=(
                "paperless_deleted_at",
                "paperless_status",
                "paperless_document_id",
                "paperless_task_id",
            )
        )
        entry = self.manual_entry(invoice)
        url = reverse(
            "manual_invoice_delete",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ManualInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=entry.pk).exists())
        delete.assert_not_called()

    @patch.object(PaperlessClient, "upload_manual_invoice")
    @patch.object(PaperlessClient, "task_status")
    @patch.object(PaperlessClient, "document_ocr_text")
    def test_deleted_invoice_edit_and_upload_workflows_never_upload_or_read_ocr(
        self, ocr_text, task_status, upload
    ):
        invoice = self.invoice(
            status=ManualInvoice.Status.DRAFT,
            paperless_deleted_at=timezone.now(),
            paperless_document_id=None,
            paperless_task_id="",
            paperless_status=ManualInvoice.PaperlessStatus.DELETED,
        )
        invoice.save(
            update_fields=(
                "paperless_deleted_at",
                "paperless_document_id",
                "paperless_task_id",
                "paperless_status",
            )
        )
        edit_url = reverse(
            "manual_invoice_edit",
            kwargs={"reference_uuid": invoice.reference_uuid},
        )
        response = self.client.get(edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aus Paperless gelöscht")
        self.assertNotContains(response, "Nur aus Paperless löschen")
        upload.assert_not_called()
        task_status.assert_not_called()
        ocr_text.assert_not_called()
