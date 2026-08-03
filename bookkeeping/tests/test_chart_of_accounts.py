import tempfile
from datetime import date
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from bookkeeping.models import AuditEreignis, KontenplanEintrag, KontenplanVersion, Mandant
from bookkeeping.services.chart_of_accounts import (
    ReferenceValidationError,
    import_chart_of_accounts,
    validate_chart_of_accounts_workbook,
    validate_monthly_bank_json,
)
from bookkeeping.tests.fixtures import make_bank_json, make_workbook_bytes


class ReferenceValidationTests(TestCase):
    def test_accepts_any_valid_transaction_count_by_default(self):
        result = validate_monthly_bank_json(make_bank_json(count=3))
        self.assertEqual(result["transaction_count"], 3)

    def test_optional_expected_transaction_count_is_enforced(self):
        with self.assertRaises(ReferenceValidationError):
            validate_monthly_bank_json(make_bank_json(count=3), expected_transactions=24)

    def test_rejects_duplicate_reference_number(self):
        payload = make_bank_json(count=2).decode("utf-8").replace('"REF-2"', '"REF-1"')
        with self.assertRaises(ReferenceValidationError):
            validate_monthly_bank_json(payload.encode("utf-8"))

    def test_rejects_empty_partner_iban(self):
        payload = make_bank_json(count=1).decode("utf-8").replace("AT6119043002345732001", "")
        with self.assertRaises(ReferenceValidationError):
            validate_monthly_bank_json(payload.encode("utf-8"))

    def test_extracts_chart_entries(self):
        result = validate_chart_of_accounts_workbook(make_workbook_bytes(categories=("A", "B")))
        self.assertEqual(result["entry_count"], 2)
        self.assertEqual(result["entries"][0]["kategorie_text"], "A")


class ChartOfAccountsImportTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()
        self.mandant = Mandant.objects.create(name="Test KG", kurzname="TEST")

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def test_import_is_versioned_and_audited(self):
        version = import_chart_of_accounts(
            mandant=self.mandant,
            bezeichnung="Q2 2026",
            gueltig_ab=date(2026, 4, 1),
            uploaded_file=SimpleUploadedFile("vorlage.xlsx", make_workbook_bytes(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        self.assertTrue(Path(version.vorlage_datei.path).is_file())
        self.assertEqual(KontenplanEintrag.objects.filter(version=version).count(), 2)
        self.assertTrue(AuditEreignis.objects.filter(objekt_id=str(version.pk), aktion="kontenplan_importiert").exists())

    def test_new_import_deactivates_previous_version(self):
        first = import_chart_of_accounts(
            mandant=self.mandant,
            bezeichnung="Q1",
            gueltig_ab=date(2026, 1, 1),
            uploaded_file=SimpleUploadedFile("q1.xlsx", make_workbook_bytes(categories=("Q1",)), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        second = import_chart_of_accounts(
            mandant=self.mandant,
            bezeichnung="Q2",
            gueltig_ab=date(2026, 4, 1),
            uploaded_file=SimpleUploadedFile("q2.xlsx", make_workbook_bytes(categories=("Q2",)), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        first.refresh_from_db()
        self.assertFalse(first.aktiv)
        self.assertTrue(second.aktiv)
        self.assertEqual(KontenplanVersion.objects.filter(mandant=self.mandant, aktiv=True).count(), 1)
