import json
import uuid
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .matching import match_imported_transactions
from .models import BankTransaction, MatchingRule


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
        self.assertContains(response, "123.45 EUR")
        self.assertContains(response, "-7.50 EUR")
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
        self.assertContains(response, "Matching-Regel")
        self.assertContains(response, rule.name)

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
        self.assertContains(response, "1250.00")
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
            self.assertContains(response, 'href="/bookkeeping/matching-rules/"')
        self.assertContains(
            overview_response,
            'href="/bookkeeping/" class="bookkeeping-nav-link bookkeeping-nav-link-active"',
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
        self.assertContains(response, 'value="100.00"')

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
