import csv
import io
import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .choices import CATEGORY_CHOICES, RECEIPT_GROUP_BANK
from .category_display import category_description
from .csv_export import quarter_bounds
from .formatting import format_austrian_decimal
from .forms import (
    BookingEntryForm,
    MatchingRuleBookingTemplateForm,
    MatchingRuleForm,
)
from .matching import match_imported_transactions
from .models import (
    BankTransaction,
    BookingEntry,
    MatchingRule,
    MatchingRuleBookingTemplate,
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
            self.assertContains(response, "Transaktionen importieren")
            self.assertContains(response, 'name="json_file"')
            self.assertContains(response, "Matching ausführen")
            self.assertNotContains(response, "<table")
            self.assertNotContains(response, "Transaktionen angezeigt")
            self.assertNotContains(response, 'id="transaction-month"')
        for response in (open_response, ready_response, rules_response):
            self.assertNotContains(response, "Transaktionen importieren")
            self.assertNotContains(response, 'name="json_file"')
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

    def test_default_filter_shows_all_open_transactions_in_newest_month(self):
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

        self.assertEqual(response.context["selected_status"], "open")
        self.assertEqual(response.context["selected_month"], "2026-07")
        self.assertContains(response, "Offene Transaktionen – Juli 2026")
        self.assertContains(response, "Offen Juli")
        self.assertContains(response, "Zugeordnet Juli")
        self.assertNotContains(response, "Offen Juni")

        self.assertEqual(
            {row["name"] for row in response.context["transactions"]},
            {"Offen Juli", "Zugeordnet Juli"},
        )

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

        self.assertContains(response, "Buchungsfertige Transaktionen")
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

        self.assertContains(response, '<th class="bookkeeping-purpose">Buchungstext</th>', html=True)
        self.assertContains(response, "Korrigierter Buchungstext")
        self.assertContains(response, "Original: Originaler Banktext")

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

    def test_bank_import_dashboard_uses_available_quarters_and_selected_period(self):
        transactions = (
            self.create_transaction(
                date(2026, 7, 1), BankTransaction.Status.IMPORTED, "Q3 offen"
            ),
            self.create_transaction(
                date(2026, 8, 1), BankTransaction.Status.MATCHED, "Q3 zugeordnet"
            ),
            self.create_transaction(
                date(2026, 9, 30), BankTransaction.Status.REVIEWED, "Q3 geprüft"
            ),
            self.create_transaction(
                date(2026, 9, 30), BankTransaction.Status.BOOKED, "Q3 gebucht"
            ),
            self.create_transaction(
                date(2026, 10, 1), BankTransaction.Status.IMPORTED, "Q4 offen"
            ),
        )
        for transaction, amount in zip(
            transactions,
            (Decimal("100.00"), Decimal("-25.00"), Decimal("50.00"), Decimal("25.00"), Decimal("900.00")),
        ):
            transaction.amount = amount
            transaction.save(update_fields=("amount",))
        matching_rule = MatchingRule.objects.create(
            name="Mietregel",
            direction=MatchingRule.Direction.INCOMING,
            match_type=MatchingRule.MatchType.EXACT,
            iban="AT611904300234573201",
            expected_amount=Decimal("100.00"),
        )
        transactions[1].matched_rule = matching_rule
        transactions[1].save(update_fields=("matched_rule",))

        default_response = self.get_overview(status="bank_import")

        self.assertEqual(
            default_response.context["available_dashboard_periods"],
            [
                {"value": "2026-Q4", "label": "Q4 2026"},
                {"value": "2026-Q3", "label": "Q3 2026"},
            ],
        )
        self.assertEqual(default_response.context["dashboard_period"], "2026-Q4")
        self.assertEqual(default_response.context["dashboard_total"], 1)

        q3_response = self.get_overview(
            status="bank_import",
            dashboard_period="2026-Q3",
        )

        self.assertEqual(q3_response.context["dashboard_total"], 4)
        self.assertEqual(q3_response.context["dashboard_open"], 2)
        self.assertEqual(q3_response.context["dashboard_ready"], 2)
        self.assertEqual(q3_response.context["dashboard_processed_percent"], "50,00 %")
        self.assertEqual(q3_response.context["dashboard_incoming"], "175,00 EUR")
        self.assertEqual(q3_response.context["dashboard_outgoing"], "25,00 EUR")
        self.assertEqual(q3_response.context["dashboard_balance"], "150,00 EUR")
        self.assertEqual(q3_response.context["dashboard_auto_matched"], 1)
        self.assertEqual(q3_response.context["dashboard_without_matching"], 3)
        self.assertEqual(q3_response.context["dashboard_latest_booking_date"], "30.09.2026")
        self.assertEqual(q3_response.context["dashboard_active_matching_rules"], 1)
        self.assertNotContains(q3_response, "Q3 offen")
        self.assertNotContains(q3_response, "Transaktionen angezeigt")
        self.assertNotContains(q3_response, "<table")

    def test_empty_bank_import_dashboard_is_neutral(self):
        response = self.get_overview(status="bank_import")

        self.assertContains(response, "Noch keine Transaktionen importiert.")
        self.assertNotContains(response, 'id="dashboard-period"')
        self.assertNotContains(response, "bookkeeping-dashboard-grid")
        self.assertNotContains(response, "0,00 EUR")

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

    def test_ready_export_defaults_to_newest_quarter_with_booking_entries(self):
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

        self.assertEqual(response.context["export_period"], "2026-Q4")
        self.assertEqual(
            response.context["available_export_periods"],
            [
                {"value": "2026-Q4", "label": "Q4 2026"},
                {"value": "2026-Q3", "label": "Q3 2026"},
            ],
        )
        self.assertContains(response, 'name="period"')
        self.assertContains(response, '<form method="get" class="bookkeeping-period-filter">')
        self.assertContains(response, "Der Export enthält immer das vollständige Quartal.")

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

        self.assertContains(
            response,
            "Keine offenen Transaktionen für Juli 2026 vorhanden.",
        )

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
        self.assertNotContains(table_response, "Nur Q4")
        self.assertContains(csv_response, "Nur Q3")
        self.assertNotContains(csv_response, "Nur Q4")

    def test_booking_entries_are_sorted_by_payment_date_and_ids(self):
        first_transaction = self.create_transaction(partner_name="Erste")
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

        actions_header = '<th class="bookkeeping-actions">Aktionen</th>'
        date_header = '<th class="bookkeeping-date">Buchungsdatum</th>'
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

        self.assertContains(response, '<th class="bookkeeping-actions">Aktionen</th>')
        self.assertContains(response, "Buchung erfassen")
        self.assertNotContains(response, "Anmerkung")
        self.assertNotContains(response, "Nur intern sichtbar")
        self.assertNotContains(response, "Matching-Erklärung")
        self.assertNotContains(
            response,
            '<th class="bookkeeping-matching-rule">Matching-Regel</th>',
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

        self.assertContains(response, "Buchungsdaten")
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
        self.assertContains(response, "Matching-Regeln ordnen Banktransaktionen")
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
