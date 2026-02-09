import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (
    BetriebskostenBeleg,
    Buchung,
    LeaseAgreement,
    Meter,
    MeterReading,
    Property,
    Tenant,
    Unit,
)


class MeterYearlyConsumptionTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Testobjekt",
            zip_code="1010",
            city="Wien",
            street_address="Teststraße 1",
        )

    def _create_meter(self, kind: str) -> Meter:
        return Meter.objects.create(
            property=self.property,
            meter_type=Meter.MeterType.ELECTRICITY,
            kind=kind,
        )

    def test_consumption_single_reading(self):
        meter = self._create_meter(Meter.CalculationKind.CONSUMPTION)
        MeterReading.objects.create(
            meter=meter,
            date=date(2024, 6, 30),
            value=Decimal("120.000"),
        )

        results = meter.calculate_yearly_consumption()
        self.assertEqual(len(results), 1)
        result = results[0]

        start_date = date(2024, 1, 1)
        end_date = date(2024, 6, 30)
        duration_days = (end_date - start_date).days + 1
        expected_avg = Decimal("120.000") / Decimal(duration_days)

        self.assertEqual(result["calc_year"], 2024)
        self.assertEqual(result["start_date"], start_date)
        self.assertEqual(result["end_date"], end_date)
        self.assertEqual(result["end_value"], Decimal("120.000"))
        self.assertEqual(result["consumption"], Decimal("120.000"))
        self.assertEqual(result["duration_days"], duration_days)
        self.assertEqual(result["avg_per_day"], expected_avg)

    def test_consumption_multiple_readings(self):
        meter = self._create_meter(Meter.CalculationKind.CONSUMPTION)
        MeterReading.objects.create(
            meter=meter,
            date=date(2025, 3, 1),
            value=Decimal("10.000"),
        )
        MeterReading.objects.create(
            meter=meter,
            date=date(2025, 12, 31),
            value=Decimal("20.000"),
        )

        results = meter.calculate_yearly_consumption()
        self.assertEqual(len(results), 1)
        result = results[0]

        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        duration_days = (end_date - start_date).days + 1
        expected_total = Decimal("30.000")
        expected_avg = expected_total / Decimal(duration_days)

        self.assertEqual(result["calc_year"], 2025)
        self.assertEqual(result["start_date"], start_date)
        self.assertEqual(result["end_date"], end_date)
        self.assertEqual(result["end_value"], expected_total)
        self.assertEqual(result["consumption"], expected_total)
        self.assertEqual(result["duration_days"], duration_days)
        self.assertEqual(result["avg_per_day"], expected_avg)

    def test_reading_with_start_before_year(self):
        meter = self._create_meter(Meter.CalculationKind.READING)
        MeterReading.objects.create(
            meter=meter,
            date=date(2023, 12, 31),
            value=Decimal("100.000"),
        )
        MeterReading.objects.create(
            meter=meter,
            date=date(2024, 6, 30),
            value=Decimal("150.000"),
        )
        MeterReading.objects.create(
            meter=meter,
            date=date(2024, 12, 31),
            value=Decimal("200.000"),
        )

        results = meter.calculate_yearly_consumption()
        result_2024 = next(item for item in results if item["calc_year"] == 2024)

        start_date = date(2023, 12, 31)
        end_date = date(2024, 12, 31)
        duration_days = (end_date - start_date).days + 1
        expected_consumption = Decimal("100.000")
        expected_avg = expected_consumption / Decimal(duration_days)

        self.assertEqual(result_2024["start_date"], start_date)
        self.assertEqual(result_2024["end_date"], end_date)
        self.assertEqual(result_2024["consumption"], expected_consumption)
        self.assertEqual(result_2024["avg_per_day"], expected_avg)

    def test_reading_single_entry(self):
        meter = self._create_meter(Meter.CalculationKind.READING)
        MeterReading.objects.create(
            meter=meter,
            date=date(2025, 7, 1),
            value=Decimal("50.000"),
        )

        results = meter.calculate_yearly_consumption()
        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertEqual(result["start_date"], date(2025, 7, 1))
        self.assertEqual(result["end_date"], date(2025, 7, 1))
        self.assertEqual(result["duration_days"], 1)
        self.assertEqual(result["consumption"], Decimal("0.000"))
        self.assertEqual(result["avg_per_day"], Decimal("0.000"))

    def test_calculate_yearly_consumption_all_sorted(self):
        meter_a = self._create_meter(Meter.CalculationKind.READING)
        meter_b = self._create_meter(Meter.CalculationKind.CONSUMPTION)

        MeterReading.objects.create(
            meter=meter_a,
            date=date(2024, 12, 31),
            value=Decimal("10.000"),
        )
        MeterReading.objects.create(
            meter=meter_b,
            date=date(2024, 6, 30),
            value=Decimal("5.000"),
        )

        results = Meter.calculate_yearly_consumption_all()
        self.assertEqual(len(results), 2)
        self.assertLessEqual(results[0]["meter_id"], results[1]["meter_id"])


class LeaseAgreementHistoryTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Testobjekt",
            zip_code="1010",
            city="Wien",
            street_address="Teststraße 1",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Max",
            last_name="Mustermann",
        )

    def _create_lease(self) -> LeaseAgreement:
        return LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )

    def test_history_created_on_create(self):
        lease = self._create_lease()
        self.assertEqual(lease.history.count(), 1)

    def test_history_created_on_update(self):
        lease = self._create_lease()
        lease.net_rent = Decimal("600.00")
        lease.save()
        self.assertEqual(lease.history.count(), 2)

    def test_history_created_on_tenants_changed(self):
        lease = self._create_lease()
        base_count = lease.history.count()
        lease.tenants.add(self.tenant)
        self.assertEqual(lease.history.count(), base_count + 1)

    def test_seed_lease_history(self):
        lease = self._create_lease()
        lease.tenants.add(self.tenant)
        lease.history.all().delete()
        self.assertEqual(lease.history.count(), 0)

        call_command("seed_lease_history")

        self.assertEqual(lease.history.count(), 1)
        history_entry = lease.history.first()
        self.assertEqual(history_entry.history_change_reason, "Initialer Stand")


class SollStellungCommandTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Soll",
            zip_code="1010",
            city="Wien",
            street_address="Testgasse 10",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="2",
            name="Top 2",
            usable_area=Decimal("60.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )

    def test_generate_monthly_soll_is_idempotent(self):
        call_command("generate_monthly_soll", month="2026-01")
        first_run_count = Buchung.objects.filter(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            datum=date(2026, 1, 1),
        ).count()

        call_command("generate_monthly_soll", month="2026-01")
        second_run_count = Buchung.objects.filter(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            datum=date(2026, 1, 1),
        ).count()

        self.assertEqual(first_run_count, 3)
        self.assertEqual(second_run_count, 3)

    def test_generate_monthly_soll_keeps_one_entry_per_category_after_double_run(self):
        month_start = date(2026, 4, 1)
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL Hauptmietzins 04.2026",
            datum=month_start,
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )

        call_command("generate_monthly_soll", month="2026-04")
        call_command("generate_monthly_soll", month="2026-04")

        month_entries = Buchung.objects.filter(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            datum=month_start,
        )
        self.assertEqual(month_entries.count(), 3)
        self.assertEqual(
            month_entries.filter(kategorie=Buchung.Kategorie.HMZ).count(),
            1,
        )
        self.assertEqual(
            month_entries.filter(kategorie=Buchung.Kategorie.BK).count(),
            1,
        )
        self.assertEqual(
            month_entries.filter(kategorie=Buchung.Kategorie.HK).count(),
            1,
        )

    def test_generate_rent_debits_alias_works(self):
        call_command("generate_rent_debits", month="2026-02")
        self.assertEqual(
            Buchung.objects.filter(
                mietervertrag=self.lease,
                typ=Buchung.Typ.SOLL,
                datum=date(2026, 2, 1),
            ).count(),
            3,
        )

    def test_generate_monthly_soll_applies_tax_rates_per_component(self):
        parking_unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.PARKING,
            door_number="P1",
            name="Stellplatz 1",
        )
        parking_lease = LeaseAgreement.objects.create(
            unit=parking_unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("100.00"),
            operating_costs_net=Decimal("20.00"),
            heating_costs_net=Decimal("30.00"),
        )

        call_command("generate_monthly_soll", month="2026-03")

        apartment_hmz = Buchung.objects.get(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            datum=date(2026, 3, 1),
        )
        apartment_bk = Buchung.objects.get(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            datum=date(2026, 3, 1),
        )
        apartment_hk = Buchung.objects.get(
            mietervertrag=self.lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HK,
            datum=date(2026, 3, 1),
        )
        parking_hmz = Buchung.objects.get(
            mietervertrag=parking_lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            datum=date(2026, 3, 1),
        )
        parking_bk = Buchung.objects.get(
            mietervertrag=parking_lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            datum=date(2026, 3, 1),
        )
        parking_hk = Buchung.objects.get(
            mietervertrag=parking_lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HK,
            datum=date(2026, 3, 1),
        )

        self.assertEqual(apartment_hmz.ust_prozent, Decimal("10.00"))
        self.assertEqual(apartment_bk.ust_prozent, Decimal("10.00"))
        self.assertEqual(apartment_hk.ust_prozent, Decimal("20.00"))
        self.assertEqual(parking_hmz.ust_prozent, Decimal("20.00"))
        self.assertEqual(parking_bk.ust_prozent, Decimal("10.00"))
        self.assertEqual(parking_hk.ust_prozent, Decimal("20.00"))


class BuchungCreateViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Buchung",
            zip_code="1050",
            city="Wien",
            street_address="Testweg 5",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="5",
            name="Top 5",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )

    def test_create_view_prefills_from_lease_query_param(self):
        response = self.client.get(reverse("buchung_create"), {"lease": self.lease.pk})
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("liegenschaft"), self.property.pk)
        self.assertEqual(form.initial.get("einheit"), self.unit.pk)
        self.assertEqual(form.initial.get("typ"), Buchung.Typ.SOLL)

    def test_create_view_assigns_prefilled_lease_on_save(self):
        response = self.client.post(
            reverse("buchung_create") + f"?lease={self.lease.pk}",
            {
                "liegenschaft": str(self.property.pk),
                "einheit": str(self.unit.pk),
                "typ": Buchung.Typ.SOLL,
                "kategorie": Buchung.Kategorie.HMZ,
                "buchungstext": "VPI-Anpassung",
                "datum": "2026-02-01",
                "netto": "10.00",
                "ust_prozent": "10.00",
                "brutto": "11.00",
                "storniert_von": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        buchung = Buchung.objects.get(buchungstext="VPI-Anpassung")
        self.assertEqual(buchung.mietervertrag_id, self.lease.pk)
        self.assertEqual(buchung.typ, Buchung.Typ.SOLL)


class LeaseDetailViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Detail",
            zip_code="1060",
            city="Wien",
            street_address="Detailgasse 2",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="6",
            name="Top 6",
            usable_area=Decimal("50.00"),
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )

    def test_lease_detail_contains_monthly_summary_rows(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL 01/2026",
            datum=date(2026, 1, 1),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Zahlung 01/2026",
            datum=date(2026, 1, 10),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL 02/2026",
            datum=date(2026, 2, 1),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Zahlung 02/2026",
            datum=date(2026, 2, 5),
            netto=Decimal("63.64"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("70.00"),
        )

        response = self.client.get(reverse("lease_detail", args=[self.lease.pk]))
        self.assertEqual(response.status_code, 200)

        rows = response.context["konto_rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["kind"], "month_summary")
        self.assertEqual(rows[3]["kind"], "month_summary")

        february_summary = rows[0]
        january_summary = rows[3]

        self.assertEqual(january_summary["month_label"], "01.2026")
        self.assertEqual(january_summary["month_soll"], Decimal("110.00"))
        self.assertEqual(january_summary["month_haben"], Decimal("55.00"))
        self.assertEqual(january_summary["month_end_kontostand"], Decimal("-55.00"))
        self.assertEqual(january_summary["offen"], Decimal("55.00"))

        self.assertEqual(february_summary["month_label"], "02.2026")
        self.assertEqual(february_summary["month_soll"], Decimal("55.00"))
        self.assertEqual(february_summary["month_haben"], Decimal("70.00"))
        self.assertEqual(february_summary["month_end_kontostand"], Decimal("-40.00"))
        self.assertEqual(february_summary["offen"], Decimal("40.00"))


class BetriebskostenBelegModelTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt BK",
            zip_code="1040",
            city="Wien",
            street_address="BK-Gasse 1",
        )

    def test_clean_accepts_valid_netto_ust_brutto(self):
        beleg = BetriebskostenBeleg(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2026, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        beleg.full_clean()

    def test_clean_rejects_invalid_brutto(self):
        beleg = BetriebskostenBeleg(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 1, 11),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("119.99"),
        )
        with self.assertRaises(ValidationError):
            beleg.full_clean()

    def test_default_ust_is_20_percent(self):
        beleg = BetriebskostenBeleg(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 12),
            netto=Decimal("100.00"),
            brutto=Decimal("120.00"),
        )
        self.assertEqual(beleg.ust_prozent, Decimal("20.00"))


class BankImportWorkflowTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Import",
            zip_code="1020",
            city="Wien",
            street_address="Importgasse 1",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="3",
            name="Top 3",
            usable_area=Decimal("55.00"),
            operating_cost_share=Decimal("12.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Erwin",
            last_name="Import",
            iban="AT611904300234573201",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("0.00"),
            heating_costs_net=Decimal("0.00"),
        )
        self.lease.tenants.add(self.tenant)

    def _upload_payload(self, payload) -> None:
        uploaded = SimpleUploadedFile(
            "bank.json",
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        response = self.client.post(
            reverse("bank_import"),
            {"action": "preview", "json_file": uploaded},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_preview_and_confirm_creates_single_haben_booking(self):
        payload = [
            {
                "referenceNumber": "REF-1000",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 55000, "precision": 2},
                "booking": "2026-01-05T10:00:00+0000",
                "reference": "Miete 01/2026",
            }
        ]

        self._upload_payload(payload)
        session = self.client.session
        preview_rows = session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0]["lease_id"], str(self.lease.pk))

        response = self.client.post(
            reverse("bank_import"),
            {"action": "confirm", "lease_0": str(self.lease.pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        entries = Buchung.objects.filter(
            mietervertrag=self.lease,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
        )
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertTrue(entry.buchungstext.startswith("BANKIMPORT [REF-1000]"))
        self.assertEqual(entry.ust_prozent, Decimal("10.00"))
        self.assertEqual(entry.netto, Decimal("500.00"))
        self.assertEqual(entry.brutto, Decimal("550.00"))

    def test_confirm_is_idempotent_by_reference(self):
        payload = [
            {
                "referenceNumber": "REF-1001",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 55000, "precision": 2},
                "booking": "2026-01-06T10:00:00+0000",
                "reference": "Miete 01/2026",
            }
        ]

        self._upload_payload(payload)
        self.client.post(
            reverse("bank_import"),
            {"action": "confirm", "lease_0": str(self.lease.pk)},
            follow=True,
        )

        self._upload_payload(payload)
        self.client.post(
            reverse("bank_import"),
            {"action": "confirm", "lease_0": str(self.lease.pk)},
            follow=True,
        )

        entries = Buchung.objects.filter(
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext__startswith="BANKIMPORT [REF-1001]",
        )
        self.assertEqual(entries.count(), 1)

    def test_auto_split_for_one_payment_covering_two_contracts(self):
        second_unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.PARKING,
            door_number="P2",
            name="Stellplatz 2",
        )
        second_lease = LeaseAgreement.objects.create(
            unit=second_unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("34.99"),
            operating_costs_net=Decimal("0.00"),
            heating_costs_net=Decimal("0.00"),
        )
        second_lease.tenants.add(self.tenant)

        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL 01/2026",
            datum=date(2026, 1, 1),
            netto=Decimal("41.99"),
            ust_prozent=Decimal("0.00"),
            brutto=Decimal("41.99"),
        )
        Buchung.objects.create(
            mietervertrag=second_lease,
            einheit=second_unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL 01/2026",
            datum=date(2026, 1, 1),
            netto=Decimal("41.99"),
            ust_prozent=Decimal("0.00"),
            brutto=Decimal("41.99"),
        )

        payload = [
            {
                "referenceNumber": "REF-SPLIT-1",
                "partnerName": "Bondar",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 8398, "precision": 2},
                "booking": "2026-01-05T10:00:00+0000",
                "reference": "Miete Parkplätze",
            }
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 1)
        self.assertTrue(preview_rows[0]["auto_split"])
        self.assertEqual(len(preview_rows[0]["auto_split_allocations"]), 2)

        response = self.client.post(
            reverse("bank_import"),
            {"action": "confirm", "lease_0": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        split_entries = Buchung.objects.filter(
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext__startswith="BANKIMPORT [REF-SPLIT-1]",
        )
        self.assertEqual(split_entries.count(), 2)
        self.assertEqual(
            split_entries.filter(mietervertrag=self.lease).count(),
            1,
        )
        self.assertEqual(
            split_entries.filter(mietervertrag=second_lease).count(),
            1,
        )
        total = sum((entry.brutto for entry in split_entries), Decimal("0.00"))
        self.assertEqual(total, Decimal("83.98"))
        first_entry = split_entries.get(mietervertrag=self.lease)
        second_entry = split_entries.get(mietervertrag=second_lease)
        self.assertEqual(first_entry.ust_prozent, Decimal("10.00"))
        self.assertEqual(second_entry.ust_prozent, Decimal("20.00"))

    def test_import_splits_one_miete_payment_into_10_and_20_percent(self):
        self.lease.heating_costs_net = Decimal("50.00")
        self.lease.save(update_fields=["heating_costs_net"])

        payload = [
            {
                "referenceNumber": "REF-MIXED-1",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 61000, "precision": 2},
                "booking": "2026-01-07T10:00:00+0000",
                "reference": "Miete inkl. Heizung 01/2026",
            }
        ]

        self._upload_payload(payload)
        response = self.client.post(
            reverse("bank_import"),
            {"action": "confirm", "lease_0": str(self.lease.pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        entries = Buchung.objects.filter(
            mietervertrag=self.lease,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext__startswith="BANKIMPORT [REF-MIXED-1]",
        ).order_by("ust_prozent")
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries[0].ust_prozent, Decimal("10.00"))
        self.assertEqual(entries[1].ust_prozent, Decimal("20.00"))
        self.assertEqual(entries[0].netto, Decimal("500.00"))
        self.assertEqual(entries[1].netto, Decimal("50.00"))
        self.assertEqual(entries[0].brutto, Decimal("550.00"))
        self.assertEqual(entries[1].brutto, Decimal("60.00"))

    def test_imports_bk_and_skips_duplicate_reference(self):
        payload = [
            {
                "referenceNumber": "REF-BK-1000",
                "partnerName": "Strom Wien GmbH",
                "partnerAccount": {"iban": "AT123456789012345678"},
                "amount": {"value": -12000, "precision": 2},
                "booking": "2026-01-12T10:00:00+0000",
                "reference": "Strom 01/2026",
            }
        ]

        self._upload_payload(payload)
        first_preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(first_preview_rows), 1)
        self.assertEqual(first_preview_rows[0]["booking_type"], "bk")

        response = self.client.post(
            reverse("bank_import"),
            {
                "action": "confirm",
                "type_0": "bk",
                "bk_property_0": str(self.property.pk),
                "bk_art_0": BetriebskostenBeleg.BKArt.STROM,
                "bk_ust_0": "0.00",
                "lease_0": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            BetriebskostenBeleg.objects.filter(import_referenz="REF-BK-1000").count(),
            1,
        )

        self._upload_payload(payload)
        self.client.post(
            reverse("bank_import"),
            {
                "action": "confirm",
                "type_0": "bk",
                "bk_property_0": str(self.property.pk),
                "bk_art_0": BetriebskostenBeleg.BKArt.STROM,
                "bk_ust_0": "0.00",
                "lease_0": "",
            },
            follow=True,
        )

        self.assertEqual(
            BetriebskostenBeleg.objects.filter(import_referenz="REF-BK-1000").count(),
            1,
        )

    def test_bk_preview_prefills_art_from_text_and_default_ust(self):
        payload = [
            {
                "referenceNumber": "REF-BK-EVN",
                "partnerName": "EVN Energie",
                "partnerAccount": {"iban": "AT111111111111111111"},
                "amount": {"value": -4500, "precision": 2},
                "booking": "2026-01-13T10:00:00+0000",
                "reference": "Monatsabrechnung",
            },
            {
                "referenceNumber": "REF-BK-WASSER",
                "partnerName": "Stadtwerke",
                "partnerAccount": {"iban": "AT222222222222222222"},
                "amount": {"value": -3800, "precision": 2},
                "booking": "2026-01-13T11:00:00+0000",
                "reference": "Trinkwasser 01/2026",
            },
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["booking_type"], "bk")
        self.assertEqual(preview_rows[0]["bk_art"], BetriebskostenBeleg.BKArt.STROM)
        self.assertEqual(preview_rows[0]["bk_ust_prozent"], "20.00")
        self.assertEqual(preview_rows[1]["bk_art"], BetriebskostenBeleg.BKArt.WASSER)
        self.assertEqual(preview_rows[1]["bk_ust_prozent"], "20.00")

    def test_confirm_can_dismiss_single_preview_row(self):
        payload = [
            {
                "referenceNumber": "REF-DISMISS-1",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 55000, "precision": 2},
                "booking": "2026-01-14T10:00:00+0000",
                "reference": "Miete 01/2026",
            },
            {
                "referenceNumber": "REF-DISMISS-2",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 55000, "precision": 2},
                "booking": "2026-01-15T10:00:00+0000",
                "reference": "Miete 02/2026",
            },
        ]

        self._upload_payload(payload)
        response = self.client.post(
            reverse("bank_import"),
            {
                "action": "confirm",
                "lease_0": str(self.lease.pk),
                "lease_1": str(self.lease.pk),
                "dismiss_1": "1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Buchung.objects.filter(
                typ=Buchung.Typ.IST,
                kategorie=Buchung.Kategorie.ZAHLUNG,
                buchungstext__startswith="BANKIMPORT [REF-DISMISS-1]",
            ).count(),
            1,
        )
        self.assertEqual(
            Buchung.objects.filter(
                typ=Buchung.Typ.IST,
                kategorie=Buchung.Kategorie.ZAHLUNG,
                buchungstext__startswith="BANKIMPORT [REF-DISMISS-2]",
            ).count(),
            0,
        )

    def test_zero_amount_row_removed_after_confirm(self):
        payload = [
            {
                "referenceNumber": "REF-ZERO-1",
                "partnerName": "Null Betrag",
                "partnerAccount": {"iban": "AT000000000000000000"},
                "amount": {"value": 0, "precision": 2},
                "booking": "2026-01-20T10:00:00+0000",
                "reference": "Test Nullbetrag",
            }
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 1)
        self.assertFalse(preview_rows[0]["bookable"])

        response = self.client.post(
            reverse("bank_import"),
            {"action": "confirm"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        remaining_preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(remaining_preview_rows, [])
        self.assertEqual(
            Buchung.objects.filter(
                typ=Buchung.Typ.IST,
                kategorie=Buchung.Kategorie.ZAHLUNG,
                buchungstext__startswith="BANKIMPORT [REF-ZERO-1]",
            ).count(),
            0,
        )

    def test_special_bk_rules_for_text_amount_and_prefill_dismiss(self):
        bhg14 = Property.objects.create(
            name="BHG14",
            zip_code="1010",
            city="Wien",
            street_address="Beispielgasse 14",
        )
        payload = [
            {
                "referenceNumber": "REF-RULE-1",
                "partnerName": "Foo",
                "partnerAccount": {"iban": "AT111111111111111111"},
                "amount": {"value": 710, "precision": 2},
                "booking": "2026-01-16T10:00:00+0000",
                "reference": "Beitr.KtoNr.: 065015757",
            },
            {
                "referenceNumber": "REF-RULE-2",
                "partnerName": "Bar",
                "partnerAccount": {"iban": "AT222222222222222222"},
                "amount": {"value": 12000, "precision": 2},
                "booking": "2026-01-16T11:00:00+0000",
                "reference": "Gehalt",
            },
            {
                "referenceNumber": "REF-RULE-3",
                "partnerName": "Baz",
                "partnerAccount": {"iban": "AT333333333333333333"},
                "amount": {"value": 20000, "precision": 2},
                "booking": "2026-01-16T12:00:00+0000",
                "reference": "Gehalt",
            },
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 3)
        self.assertEqual(preview_rows[0]["booking_type"], "bk")
        self.assertEqual(preview_rows[0]["bk_art"], BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN)
        self.assertEqual(preview_rows[0]["bk_ust_prozent"], "0.00")
        self.assertEqual(preview_rows[0]["bk_property_id"], str(bhg14.pk))
        self.assertEqual(preview_rows[1]["booking_type"], "bk")
        self.assertEqual(preview_rows[1]["bk_art"], BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN)
        self.assertEqual(preview_rows[1]["bk_ust_prozent"], "0.00")
        self.assertEqual(preview_rows[1]["bk_property_id"], str(bhg14.pk))
        self.assertTrue(preview_rows[2]["dismiss"])

    def test_prefills_mhs69_property_for_meidl_hptstr_69_text(self):
        mhs69 = Property.objects.create(
            name="MHS69",
            zip_code="1120",
            city="Wien",
            street_address="Meidlinger Hauptstrasse 69",
        )
        payload = [
            {
                "referenceNumber": "REF-MHS69-1",
                "partnerName": "Lieferant X",
                "partnerAccount": {"iban": "AT444444444444444444"},
                "amount": {"value": -5000, "precision": 2},
                "booking": "2026-01-17T10:00:00+0000",
                "reference": "Meidl.Hptstr.69",
            }
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0]["bk_property_id"], str(mhs69.pk))


class OffenePostenViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Offen",
            zip_code="1030",
            city="Wien",
            street_address="Kontogasse 5",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="4",
            name="Top 4",
            usable_area=Decimal("70.00"),
            operating_cost_share=Decimal("20.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Anna",
            last_name="Offen",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.lease.tenants.add(self.tenant)

    def test_offene_posten_marks_partial_payment(self):
        call_command("generate_monthly_soll", month="2026-01")
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Teilzahlung Januar",
            datum=date(2026, 1, 10),
            netto=Decimal("300.00"),
            ust_prozent=Decimal("0.00"),
            brutto=Decimal("300.00"),
        )

        response = self.client.get(reverse("offene_posten"), {"monat": "2026-01"})
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status_label"], "Teilzahlung")
        self.assertGreater(rows[0]["offen"], Decimal("0.00"))

    def test_offene_posten_carries_balance_into_next_month(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL 01/2026",
            datum=date(2026, 1, 1),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("0.00"),
            brutto=Decimal("100.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Teilzahlung 01/2026",
            datum=date(2026, 1, 15),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("0.00"),
            brutto=Decimal("80.00"),
        )

        response = self.client.get(reverse("offene_posten"), {"monat": "2026-02"})
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vortrag"], Decimal("-20.00"))
        self.assertEqual(rows[0]["soll"], Decimal("0.00"))
        self.assertEqual(rows[0]["haben"], Decimal("0.00"))
        self.assertEqual(rows[0]["endsaldo"], Decimal("-20.00"))
        self.assertEqual(rows[0]["offen"], Decimal("20.00"))
        self.assertEqual(rows[0]["status_label"], "Rückstand")


class BetriebskostenAbrechnungViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Abrechnung",
            zip_code="1070",
            city="Wien",
            street_address="Abrechnungsgasse 7",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="7",
            name="Top 7",
            usable_area=Decimal("45.00"),
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )

    def test_overview_aggregates_netto_for_selected_year_and_property(self):
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2026, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 2, 10),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 3, 10),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("24.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.SONSTIG,
            datum=date(2026, 4, 10),
            netto=Decimal("10.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("12.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2025, 12, 20),
            netto=Decimal("999.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("1198.80"),
        )

        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL HMZ 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="SOLL BK 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("88.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HK,
            buchungstext="SOLL HK 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="IST 2026 10%",
            datum=date(2026, 1, 15),
            netto=Decimal("580.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("638.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="IST 2026 20%",
            datum=date(2026, 1, 15),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "uebersicht"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_tab"], "uebersicht")
        self.assertEqual(response.context["ausgaben_strom"], Decimal("100.00"))
        self.assertEqual(response.context["ausgaben_wasser"], Decimal("50.00"))
        self.assertEqual(response.context["ausgaben_betriebskosten"], Decimal("30.00"))
        self.assertEqual(response.context["ausgaben_gesamt"], Decimal("180.00"))
        self.assertEqual(response.context["einnahmen_betriebskosten"], Decimal("80.00"))
        self.assertEqual(response.context["einnahmen_heizung"], Decimal("30.00"))
        self.assertEqual(response.context["einnahmen_gesamt"], Decimal("110.00"))
        self.assertEqual(response.context["saldo"], Decimal("-70.00"))

    def test_defaults_to_bhg14_and_current_year(self):
        bhg14 = Property.objects.create(
            name="BHG14",
            zip_code="1010",
            city="Wien",
            street_address="Hauptstraße 14",
        )
        unit_bhg14 = Unit.objects.create(
            property=bhg14,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
            usable_area=Decimal("50.00"),
        )
        lease_bhg14 = LeaseAgreement.objects.create(
            unit=unit_bhg14,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("400.00"),
            operating_costs_net=Decimal("80.00"),
            heating_costs_net=Decimal("20.00"),
        )
        current_year = date.today().year
        Buchung.objects.create(
            mietervertrag=lease_bhg14,
            einheit=unit_bhg14,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="SOLL BK aktuelles Jahr",
            datum=date(current_year, 1, 1),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("88.00"),
        )

        response = self.client.get(reverse("betriebskostenabrechnung"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_property_id"], str(bhg14.pk))
        self.assertEqual(response.context["selected_year"], current_year)
        self.assertIn(current_year, response.context["year_choices"])

    def test_year_choices_only_include_relevant_booking_years(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="SOLL BK 2024",
            datum=date(2024, 1, 1),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL HMZ 2025",
            datum=date(2025, 1, 1),
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="IST ZAHLUNG 2026",
            datum=date(2026, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2027, 3, 1),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("24.00"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year_choices"], [2024, 2026, 2027])
        self.assertNotIn(2025, response.context["year_choices"])

    def test_overview_includes_meter_consumption_groups_for_selected_year(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="SOLL BK 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("10.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("11.00"),
        )
        general_meter = Meter.objects.create(
            property=self.property,
            meter_type=Meter.MeterType.ELECTRICITY,
            meter_number="GEN-1",
        )
        unit_meter = Meter.objects.create(
            property=self.property,
            unit=self.unit,
            meter_type=Meter.MeterType.WATER_COLD,
            meter_number="UNIT-1",
            kind=Meter.CalculationKind.CONSUMPTION,
            unit_of_measure=Meter.UnitOfMeasure.M3,
        )
        MeterReading.objects.create(
            meter=general_meter,
            date=date(2025, 12, 31),
            value=Decimal("100.000"),
        )
        MeterReading.objects.create(
            meter=general_meter,
            date=date(2026, 12, 31),
            value=Decimal("150.000"),
        )
        MeterReading.objects.create(
            meter=unit_meter,
            date=date(2026, 6, 30),
            value=Decimal("12.000"),
        )
        MeterReading.objects.create(
            meter=unit_meter,
            date=date(2026, 12, 31),
            value=Decimal("8.000"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "uebersicht"},
        )
        self.assertEqual(response.status_code, 200)
        groups = response.context["meter_consumption_groups"]
        self.assertEqual(len(groups), 2)

        labels = [group["label"] for group in groups]
        self.assertIn("Objekt Abrechnung (Allgemein)", labels)
        self.assertIn("Top 7 · 7", labels)

        all_rows = [row for group in groups for row in group["rows"]]
        self.assertTrue(
            any(
                row["meter_number"] == "GEN-1" and row["consumption_display"] == "50.000"
                for row in all_rows
            )
        )
        self.assertTrue(
            any(
                row["meter_number"] == "UNIT-1" and row["consumption_display"] == "20.000"
                for row in all_rows
            )
        )

    def test_bk_allgemein_distributes_costs_by_operating_cost_share_with_checksum(self):
        self.unit.operating_cost_share = Decimal("20.00")
        self.unit.save(update_fields=["operating_cost_share"])
        second_unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="8",
            name="Top 8",
            usable_area=Decimal("55.00"),
            operating_cost_share=Decimal("30.00"),
        )
        second_lease = LeaseAgreement.objects.create(
            unit=second_unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("600.00"),
            operating_costs_net=Decimal("120.00"),
            heating_costs_net=Decimal("70.00"),
        )
        tenant_one = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Erika",
            last_name="Muster",
        )
        tenant_two = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Paul",
            last_name="Beispiel",
        )
        self.lease.tenants.add(tenant_one)
        second_lease.tenants.add(tenant_two)

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 2, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.SONSTIG,
            datum=date(2026, 2, 11),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "bk-allgemein"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_tab"], "bk-allgemein")
        data = response.context["bk_allg"]
        self.assertTrue(data["has_source_costs"])
        self.assertTrue(data["has_distribution_rows"])
        self.assertEqual(data["original_sum"], Decimal("100.00"))
        self.assertEqual(data["distributed_sum"], Decimal("100.00"))
        self.assertEqual(data["rounding_diff"], Decimal("0.00"))
        self.assertEqual(len(data["rows"]), 2)

        rows_by_label = {row["label"]: row for row in data["rows"]}
        self.assertEqual(rows_by_label["Top 7 - Erika Muster"]["bk_anteil"], Decimal("20.00"))
        self.assertEqual(rows_by_label["Top 8 - Paul Beispiel"]["bk_anteil"], Decimal("30.00"))
        self.assertEqual(rows_by_label["Top 7 - Erika Muster"]["cost_share"], Decimal("40.00"))
        self.assertEqual(rows_by_label["Top 8 - Paul Beispiel"]["cost_share"], Decimal("60.00"))
