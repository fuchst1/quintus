from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from webapp.models import BetriebskostenBeleg, Buchung, LeaseAgreement, Property, Unit


class ImportLegacyBuchungenCommandTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="TESTPROP",
            zip_code="1000",
            city="Wien",
            street_address="Testgasse 1",
        )
        self.unit_apartment = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="TESTPROP_1",
        )
        self.unit_parking = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.PARKING,
            door_number="SP1",
            name="TESTPROP_SP1",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit_apartment,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            exit_date=date(2024, 12, 31),
            net_rent=Decimal("100.00"),
            operating_costs_net=Decimal("10.00"),
            heating_costs_net=Decimal("5.00"),
            deposit=Decimal("0.00"),
        )
        self.sql_file = self._build_legacy_sql_file()

    def test_dry_run_reports_counts_without_writing(self):
        output = StringIO()
        call_command(
            "import_legacy_buchungen",
            sql_file=str(self.sql_file),
            dry_run=True,
            stdout=output,
        )
        summary = self._parse_summary(output.getvalue())

        self.assertEqual(summary["parsed_rows"], 4)
        self.assertEqual(summary["inserted_rows"], 7)
        self.assertEqual(summary["skipped_existing_rows"], 0)
        self.assertEqual(summary["inserted_buchung_rows"], 6)
        self.assertEqual(summary["inserted_beleg_rows"], 1)
        self.assertEqual(summary["unit_map_warnings"], 1)
        self.assertEqual(summary["lease_map_warnings"], 1)
        self.assertEqual(summary["soll_conflict_warnings"], 0)
        self.assertEqual(summary["expense_property_warnings"], 0)
        self.assertEqual(summary["income_category_warnings"], 0)
        self.assertEqual(summary["vat_mismatch_rows_detected"], 1)
        self.assertEqual(Buchung.objects.count(), 0)
        self.assertEqual(BetriebskostenBeleg.objects.count(), 0)

    def test_import_mapping_and_idempotency(self):
        output_first = StringIO()
        call_command(
            "import_legacy_buchungen",
            sql_file=str(self.sql_file),
            stdout=output_first,
        )
        summary_first = self._parse_summary(output_first.getvalue())

        self.assertEqual(summary_first["parsed_rows"], 4)
        self.assertEqual(summary_first["inserted_rows"], 7)
        self.assertEqual(summary_first["inserted_buchung_rows"], 6)
        self.assertEqual(summary_first["inserted_beleg_rows"], 1)
        self.assertEqual(Buchung.objects.count(), 6)
        self.assertEqual(BetriebskostenBeleg.objects.count(), 1)

        miete_soll = Buchung.objects.get(
            buchungstext="Miete Wohnung",
            typ=Buchung.Typ.SOLL,
        )
        miete_ist = Buchung.objects.get(
            buchungstext="Miete Wohnung",
            typ=Buchung.Typ.IST,
        )
        self.assertEqual(miete_soll.kategorie, Buchung.Kategorie.HMZ)
        self.assertEqual(miete_ist.kategorie, Buchung.Kategorie.HMZ)
        self.assertEqual(miete_soll.netto, Decimal("100.00"))
        self.assertEqual(miete_ist.netto, Decimal("100.00"))
        self.assertEqual(miete_soll.brutto, Decimal("110.00"))
        self.assertEqual(miete_ist.brutto, Decimal("110.00"))
        self.assertEqual(miete_soll.einheit_id, self.unit_apartment.id)
        self.assertEqual(miete_ist.einheit_id, self.unit_apartment.id)
        self.assertEqual(miete_soll.mietervertrag_id, self.lease.id)
        self.assertEqual(miete_ist.mietervertrag_id, self.lease.id)

        parkplatz_soll = Buchung.objects.get(
            buchungstext="BK Parkplatz",
            typ=Buchung.Typ.SOLL,
        )
        parkplatz_ist = Buchung.objects.get(
            buchungstext="BK Parkplatz",
            typ=Buchung.Typ.IST,
        )
        self.assertEqual(parkplatz_soll.kategorie, Buchung.Kategorie.BK)
        self.assertEqual(parkplatz_ist.kategorie, Buchung.Kategorie.BK)
        self.assertEqual(parkplatz_soll.einheit_id, self.unit_parking.id)
        self.assertEqual(parkplatz_ist.einheit_id, self.unit_parking.id)
        self.assertIsNone(parkplatz_soll.mietervertrag_id)
        self.assertIsNone(parkplatz_ist.mietervertrag_id)

        mismatch_soll = Buchung.objects.get(
            buchungstext="Mismatched Text",
            typ=Buchung.Typ.SOLL,
        )
        mismatch_ist = Buchung.objects.get(
            buchungstext="Mismatched Text",
            typ=Buchung.Typ.IST,
        )
        self.assertEqual(mismatch_soll.netto, Decimal("10.90"))
        self.assertEqual(mismatch_soll.brutto, Decimal("12.00"))
        self.assertEqual(mismatch_ist.netto, Decimal("10.90"))
        self.assertEqual(mismatch_ist.brutto, Decimal("12.00"))
        self.assertIsNone(mismatch_soll.einheit_id)
        self.assertIsNone(mismatch_ist.einheit_id)

        self.assertFalse(Buchung.objects.filter(buchungstext="Strom Rechnung").exists())
        beleg = BetriebskostenBeleg.objects.get(import_quelle="legacy_mysql_buchungen")
        self.assertEqual(beleg.import_referenz, "ifkg-buchungen-2")
        self.assertEqual(beleg.liegenschaft_id, self.property.id)
        self.assertEqual(beleg.bk_art, BetriebskostenBeleg.BKArt.STROM)
        self.assertEqual(beleg.datum, date(2024, 6, 2))
        self.assertEqual(beleg.netto, Decimal("100.00"))
        self.assertEqual(beleg.brutto, Decimal("120.00"))
        self.assertEqual(beleg.ust_prozent, Decimal("20.00"))
        self.assertEqual(beleg.buchungstext, "Strom Rechnung")

        output_second = StringIO()
        call_command(
            "import_legacy_buchungen",
            sql_file=str(self.sql_file),
            stdout=output_second,
        )
        summary_second = self._parse_summary(output_second.getvalue())

        self.assertEqual(summary_second["parsed_rows"], 4)
        self.assertEqual(summary_second["inserted_rows"], 0)
        self.assertEqual(summary_second["skipped_existing_rows"], 7)
        self.assertEqual(summary_second["inserted_buchung_rows"], 0)
        self.assertEqual(summary_second["inserted_beleg_rows"], 0)
        self.assertEqual(summary_second["skipped_existing_buchung_rows"], 6)
        self.assertEqual(summary_second["skipped_existing_beleg_rows"], 1)
        self.assertEqual(Buchung.objects.count(), 6)
        self.assertEqual(BetriebskostenBeleg.objects.count(), 1)

    def _build_legacy_sql_file(self) -> Path:
        sql = """
INSERT INTO `liegenschaften` (`id`, `name`, `plz`, `ort`, `adresse`, `notizen`, `eigentuemer1_id`, `eigentuemer2_id`, `heat_usage_percent`) VALUES
(1, 'TESTPROP', '1000', 'Wien', 'Testgasse 1', NULL, NULL, NULL, 85.00);

INSERT INTO `einheiten` (`id`, `name`, `typ`, `top`, `nutzflaeche`, `bkanteil`, `notizen`, `liegenschaft_id`) VALUES
(2, 'TESTPROP_1', 'Wohnung', '1', 50.00, 1.00, NULL, 1),
(10, 'TESTPROP_SP1', 'Parkplatz', 'SP1', 0.00, 0.00, NULL, 1);

INSERT INTO `buchungen` (`id`, `rechnungtext`, `bruttobetrag`, `nettobetrag`, `ustbetrag`, `ust`, `bk`, `ausgabe`, `datum`, `sachkonto_id`, `einheit_id`, `liegenschaft_id`) VALUES
(1, 'Miete Wohnung', 110.00, 100.00, 10.00, '10', 'miete', 0, '2024-06-01', NULL, 2, 1),
(2, 'Strom Rechnung', 120.00, 100.00, 20.00, '20', 'strom', 1, '2024-06-02', NULL, NULL, 1),
(3, 'BK Parkplatz', 11.00, 10.00, 1.00, '10', 'bk', 0, '2024-06-03', NULL, 10, 1),
(4, 'Mismatched\r\nText', 12.00, 10.90, 1.10, '10', 'bk', 0, '2024-06-04', NULL, 999, 1);
""".strip()
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8")
        try:
            tmp.write(sql)
            tmp.flush()
        finally:
            tmp.close()
        path = Path(tmp.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    @staticmethod
    def _parse_summary(output: str) -> dict[str, int]:
        keys = {
            "parsed_rows",
            "inserted_rows",
            "skipped_existing_rows",
            "inserted_buchung_rows",
            "skipped_existing_buchung_rows",
            "inserted_beleg_rows",
            "skipped_existing_beleg_rows",
            "unit_map_warnings",
            "lease_map_warnings",
            "soll_conflict_warnings",
            "expense_property_warnings",
            "income_category_warnings",
            "vat_mismatch_rows_detected",
        }
        summary: dict[str, int] = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key in keys:
                summary[key] = int(value)
        return summary
