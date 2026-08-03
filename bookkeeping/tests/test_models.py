from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from bookkeeping.models import Bankkonto, Kostenstelle, Mandant


class MasterDataModelTests(TestCase):
    def setUp(self):
        self.mandant = Mandant.objects.create(name="Test KG", kurzname="TEST")

    def test_bank_account_normalizes_iban(self):
        account = Bankkonto(
            mandant=self.mandant,
            bezeichnung="Hauptkonto",
            iban_normalisiert="at61 1904 3002 3457 3201",
        )
        account.full_clean()
        self.assertEqual(account.iban_normalisiert, "AT611904300234573201")

    def test_cost_center_rejects_invalid_validity_range(self):
        cost_center = Kostenstelle(
            mandant=self.mandant,
            code="TEST",
            bezeichnung="Test",
            aktiv_von=date(2026, 2, 1),
            aktiv_bis=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            cost_center.full_clean()
