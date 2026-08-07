import json
import uuid
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .choices import CATEGORY_CHOICES, RECEIPT_GROUP_BANK, VAT_SYMBOL_CHOICES
from .formatting import format_austrian_decimal
from .forms import BookingEntryForm, MatchingRuleForm
from .matching import match_imported_transactions
from .models import BankTransaction, BookingEntry, MatchingRule
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
        self.assertContains(response, "Eingelesen")
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

    def test_default_filter_shows_only_open_transactions_in_newest_month(self):
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

        self.assertEqual(response.context["selected_status"], "imported")
        self.assertEqual(response.context["selected_month"], "2026-07")
        self.assertContains(response, "Offene Transaktionen – Juli 2026")
        self.assertContains(response, "Offen Juli")
        self.assertNotContains(response, "Offen Juni")
        self.assertNotContains(response, "Zugeordnet Juli")

    def test_each_valid_status_filter_shows_only_that_status(self):
        transactions = {
            BankTransaction.Status.IMPORTED: "Offen",
            BankTransaction.Status.MATCHED: "Zugeordnet",
            BankTransaction.Status.REVIEWED: "Geprüft",
            BankTransaction.Status.BOOKED: "Exportiert",
        }
        for status, partner_name in transactions.items():
            self.create_transaction(date(2026, 7, 15), status, partner_name)

        for status, partner_name in transactions.items():
            with self.subTest(status=status):
                response = self.get_overview(status=status, month="2026-07")
                self.assertEqual(response.context["selected_status"], status)
                self.assertEqual(
                    [row["name"] for row in response.context["transactions"]],
                    [partner_name],
                )

        booked_response = self.get_overview(
            status=BankTransaction.Status.BOOKED,
            month="2026-07",
        )
        self.assertContains(booked_response, "Exportiert")
        self.assertNotContains(booked_response, "Gebucht")

    def test_invalid_status_falls_back_to_imported(self):
        self.create_transaction(
            date(2026, 7, 15), BankTransaction.Status.IMPORTED, "Offen"
        )
        self.create_transaction(
            date(2026, 7, 16), BankTransaction.Status.MATCHED, "Zugeordnet"
        )

        response = self.get_overview(status="unknown", month="2026-07")

        self.assertEqual(response.context["selected_status"], "imported")
        self.assertEqual(
            [row["name"] for row in response.context["transactions"]], ["Offen"]
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
            {"imported": 1, "matched": 1, "reviewed": 1, "booked": 1},
        )
        self.assertContains(response, 'aria-label="1 Transaktionen"')

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
            {"imported": 2, "matched": 1, "reviewed": 0, "booked": 0},
        )

    def test_sidebar_status_links_preserve_selected_month(self):
        self.create_transaction(
            date(2026, 6, 15), BankTransaction.Status.IMPORTED, "Offen Juni"
        )
        response = self.get_overview(status="matched", month="2026-06")

        self.assertContains(
            response,
            'href="/bookkeeping/?status=imported&amp;month=2026-06"',
        )
        self.assertContains(
            response,
            'href="/bookkeeping/?status=matched&amp;month=2026-06" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
        )

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
            "/bookkeeping/?status=imported&month=2026-07",
        )


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

    def test_booked_transactions_show_notes_read_only(self):
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

        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "booked", "month": "2026-07"},
        )

        self.assertContains(response, "Exportnotiz")
        self.assertContains(response, "Erklärung für den Export.")
        self.assertContains(response, rule.name)
        self.assertNotContains(
            response,
            f'href="{self.note_href(bank_transaction, "booked")}"',
        )

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

    def test_booked_note_update_is_rejected_without_changing_note(self):
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
        self.assertEqual(bank_transaction.notes, "Bestehende Exportnotiz")

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

    def test_matching_rule_note_is_displayed_live_without_copying_to_transaction(self):
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

        self.client.post(
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
        )

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.matched_rule_id, rule.pk)
        self.assertEqual(bank_transaction.notes, "")
        response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": "matched", "month": "2026-07"},
        )
        self.assertContains(response, "Regelnotiz neu")
        self.assertNotContains(response, "Regelnotiz alt")


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
        self.assertContains(response, 'name="receipt_number" value="7"')
        self.assertContains(response, 'name="payment_date" value="20.07.2026"')

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
            ["", *(value for value, _label in VAT_SYMBOL_CHOICES)],
        )
        self.assertEqual(
            [value for value, _label in form.fields["category"].choices],
            ["", *(value for value, _label in CATEGORY_CHOICES)],
        )
        self.assertContains(response, "7600 – Büromaterial und Drucksorten")

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
            "/bookkeeping/?status=reviewed&month=2026-07",
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.REVIEWED)
        self.assertIsNone(bank_transaction.matched_rule_id)
        self.assertEqual(BookingEntry.objects.filter(bank_transaction=bank_transaction).count(), 1)

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
        self.assertContains(response, "signierten Transaktionsbetrag")
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
        self.assertContains(response, "7600 – Büromaterial und Drucksorten")
        self.assertContains(response, "Bearbeiten")
        self.assertContains(
            response,
            f'href="{self.booking_url(bank_transaction, "reviewed").replace("&", "&amp;")}"',
        )

    def test_booked_transactions_cannot_edit_booking_data(self):
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

        response = self.client.post(
            self.booking_url(bank_transaction, status="booked"),
            self.complete_data(bank_transaction, category="Unzulässig"),
        )

        self.assertEqual(
            response["Location"],
            "/bookkeeping/?status=booked&month=2026-07",
        )
        entry = BookingEntry.objects.get(bank_transaction=bank_transaction)
        self.assertEqual(entry.category, "7600")

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

    def test_rematching_clears_previous_incorrect_match(self):
        rule = self.create_rule(expected_amount=Decimal("872.03"))
        bank_transaction = self.create_transaction(
            amount=Decimal("46.46"),
            status=BankTransaction.Status.MATCHED,
            matched_rule=rule,
        )

        result = match_imported_transactions()

        bank_transaction.refresh_from_db()
        self.assertEqual(result, (0, 1, 0))
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(bank_transaction.matched_rule_id)

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
        self.assertEqual(bank_transaction.status, BankTransaction.Status.MATCHED)
        self.assertContains(response, "1 zugeordnet, 0 ohne Treffer, 0 mehrdeutig.")
        matched_response = self.client.get(
            reverse("bookkeeping_overview"),
            {"status": BankTransaction.Status.MATCHED, "month": "2026-02"},
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
        self.assertContains(response, "1 zugeordnet, 0 ohne Treffer, 0 mehrdeutig.")


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
            self.assertContains(response, 'href="/bookkeeping/#bank-import"')
            self.assertContains(response, "Offen")
            self.assertContains(response, "Zugeordnet")
            self.assertContains(response, "Geprüft")
            self.assertContains(response, "Exportiert")
            self.assertContains(response, 'href="/bookkeeping/matching-rules/"')
        self.assertContains(
            overview_response,
            'href="/bookkeeping/?status=imported" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
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

    def test_edit_resets_linked_matched_transactions(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction(rule)

        self.client.post(
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

        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(bank_transaction.matched_rule_id)

    def test_edit_is_blocked_for_reviewed_or_booked_transactions(self):
        rule = self.create_rule()
        self.create_transaction(rule, status=BankTransaction.Status.REVIEWED)

        response = self.client.get(
            reverse("matching_rule_edit", kwargs={"pk": rule.pk}),
            follow=True,
        )

        self.assertContains(response, "kann nicht bearbeitet werden")
        self.assertContains(response, "geprüften oder gebuchten")

    def test_delete_get_shows_confirmation_without_deleting(self):
        rule = self.create_rule()

        response = self.client.get(
            reverse("matching_rule_delete", kwargs={"pk": rule.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matching-Regel „Mietzahlung“ wirklich löschen?")
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())

    def test_delete_only_works_through_post_and_resets_matched_transactions(self):
        rule = self.create_rule()
        bank_transaction = self.create_transaction(rule)
        delete_url = reverse("matching_rule_delete", kwargs={"pk": rule.pk})

        self.client.get(delete_url)
        self.assertTrue(MatchingRule.objects.filter(pk=rule.pk).exists())

        response = self.client.post(delete_url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MatchingRule.objects.filter(pk=rule.pk).exists())
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(bank_transaction.matched_rule_id)
        self.assertContains(response, "Matching-Regel „Mietzahlung“ gelöscht.")

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
