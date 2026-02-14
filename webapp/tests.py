import io
import json
import os
import re
import zipfile
from io import StringIO
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import BetriebskostenBelegForm, DateiUploadForm
from .models import (
    Abrechnungslauf,
    BetriebskostenBeleg,
    BetriebskostenGruppe,
    Buchung,
    Datei,
    DateiOperationLog,
    DateiZuordnung,
    LeaseAgreement,
    Manager,
    Meter,
    MeterReading,
    Property,
    ReminderEmailLog,
    ReminderRuleConfig,
    Tenant,
    Unit,
    VpiAdjustmentLetter,
    VpiAdjustmentRun,
    VpiIndexValue,
)
from .storage_paths import build_derived_upload_path, build_deterministic_derived_upload_path
from .services.annual_statement_pdf_service import (
    AnnualStatementPdfGenerationError,
    AnnualStatementPdfService,
)
from .services.annual_statement_run_service import AnnualStatementRunService
from .services.files import MAX_FILE_SIZE_BY_CATEGORY, DateiService
from .services.operating_cost_service import OperatingCostService
from .services.reminders import ReminderService, add_months
from .services.vpi_adjustment_run_service import VpiAdjustmentRunService


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


class MeterReadingAttachmentPanelViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Zähler",
            zip_code="1050",
            city="Wien",
            street_address="Messgasse 5",
        )
        self.meter = Meter.objects.create(
            property=self.property,
            meter_type=Meter.MeterType.WATER_COLD,
            meter_number="W-1050",
            kind=Meter.CalculationKind.READING,
        )

    def test_create_view_with_meter_query_contains_attachments_panel(self):
        response = self.client.get(
            reverse("meter_reading_create"),
            {"meter": self.meter.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachments_panel", response.context)
        self.assertEqual(response.context["attachments_panel"]["title"], "Dateien zum Verbrauchszähler")
        self.assertContains(response, "Dateien zum Verbrauchszähler")
        self.assertContains(response, "col-12 col-xl-5")

    def test_by_meter_list_contains_inline_attachments_panel(self):
        MeterReading.objects.create(
            meter=self.meter,
            date=date(2026, 2, 1),
            value=Decimal("123.000"),
        )

        response = self.client.get(reverse("meter_reading_by_meter_list", args=[self.meter.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachments_panel", response.context)
        self.assertEqual(response.context["attachments_panel"]["title"], "Dateien zum Verbrauchszähler")
        self.assertContains(response, "Dateien zum Verbrauchszähler")
        self.assertContains(response, "col-12 col-xl-4")


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


class MarkSettlementAdjustmentsCommandTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Markierung",
            zip_code="1150",
            city="Wien",
            street_address="Markierungsgasse 1",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.matching_booking = Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Nachzahlung BK-Abrechnung 2025",
            datum=date(2026, 2, 1),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )
        self.non_matching_booking = Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="Normale Monatszahlung",
            datum=date(2026, 2, 2),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )

    def test_command_dry_run_does_not_modify_rows(self):
        output = StringIO()
        call_command("mark_settlement_adjustments", stdout=output)

        self.matching_booking.refresh_from_db()
        self.non_matching_booking.refresh_from_db()
        self.assertFalse(self.matching_booking.is_settlement_adjustment)
        self.assertFalse(self.non_matching_booking.is_settlement_adjustment)

    def test_command_is_idempotent(self):
        output_first = StringIO()
        call_command("mark_settlement_adjustments", "--apply", stdout=output_first)
        self.matching_booking.refresh_from_db()
        self.non_matching_booking.refresh_from_db()
        self.assertTrue(self.matching_booking.is_settlement_adjustment)
        self.assertFalse(self.non_matching_booking.is_settlement_adjustment)

        output_second = StringIO()
        call_command("mark_settlement_adjustments", "--apply", stdout=output_second)
        self.matching_booking.refresh_from_db()
        self.non_matching_booking.refresh_from_db()
        self.assertTrue(self.matching_booking.is_settlement_adjustment)
        self.assertFalse(self.non_matching_booking.is_settlement_adjustment)


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


class BuchungListViewTests(TestCase):
    def setUp(self):
        self.bhg14_property = Property.objects.create(
            name="BHG14",
            zip_code="1010",
            city="Wien",
            street_address="Hauptstraße 14",
        )
        self.other_property = Property.objects.create(
            name="Objekt Buchungsliste",
            zip_code="1130",
            city="Wien",
            street_address="Listenweg 13",
        )
        self.bhg14_unit = Unit.objects.create(
            property=self.bhg14_property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="14",
            name="Top 14",
        )
        self.other_unit = Unit.objects.create(
            property=self.other_property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="13",
            name="Top 13",
        )
        self.bhg14_lease = LeaseAgreement.objects.create(
            unit=self.bhg14_unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("90.00"),
            heating_costs_net=Decimal("40.00"),
        )
        self.other_lease = LeaseAgreement.objects.create(
            unit=self.other_unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("90.00"),
            heating_costs_net=Decimal("40.00"),
        )

    def test_list_defaults_to_current_year_and_bhg14(self):
        current_year = date.today().year

        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Aktuelles Jahr BHG14",
            datum=date(current_year, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.other_lease,
            einheit=self.other_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Aktuelles Jahr andere Liegenschaft",
            datum=date(current_year, 1, 10),
            netto=Decimal("90.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("99.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Nicht-Zahlung",
            datum=date(current_year, 1, 11),
            netto=Decimal("15.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("16.50"),
        )

        response = self.client.get(reverse("buchung_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], current_year)
        self.assertEqual(response.context["selected_property_id"], str(self.bhg14_property.pk))
        self.assertEqual(len(response.context["buchungen"]), 1)
        self.assertEqual(response.context["buchungen"][0].datum.year, current_year)
        self.assertEqual(response.context["buchungen"][0].mietervertrag_id, self.bhg14_lease.pk)
        self.assertEqual(response.context["buchungen"][0].typ, Buchung.Typ.IST)
        self.assertEqual(response.context["buchungen"][0].kategorie, Buchung.Kategorie.HMZ)

    def test_list_applies_requested_year_and_property_filter(self):
        current_year = date.today().year
        previous_year = current_year - 1

        Buchung.objects.create(
            mietervertrag=self.other_lease,
            einheit=self.other_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Aktuelles Jahr",
            datum=date(current_year, 2, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.other_lease,
            einheit=self.other_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Vorjahr",
            datum=date(previous_year, 2, 10),
            netto=Decimal("90.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("99.00"),
        )

        response = self.client.get(
            reverse("buchung_list"),
            {"jahr": str(previous_year), "liegenschaft": str(self.other_property.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], previous_year)
        self.assertEqual(response.context["selected_property_id"], str(self.other_property.pk))
        self.assertEqual(len(response.context["buchungen"]), 1)
        self.assertEqual(response.context["buchungen"][0].datum.year, previous_year)
        self.assertEqual(response.context["buchungen"][0].mietervertrag_id, self.other_lease.pk)

    def test_list_year_choices_include_available_ist_years(self):
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="IST 2024",
            datum=date(2024, 1, 10),
            netto=Decimal("10.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("11.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="IST 2025",
            datum=date(2025, 1, 10),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("22.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HK,
            buchungstext="IST 2026",
            datum=date(2026, 1, 10),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )

        response = self.client.get(
            reverse("buchung_list"),
            {"liegenschaft": str(self.bhg14_property.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year_choices"], [2024, 2025, 2026])

    def test_list_renders_filtered_sum_summary_row(self):
        current_year = date.today().year
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Summenzeile 1",
            datum=date(current_year, 2, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Summenzeile 2",
            datum=date(current_year, 2, 11),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )

        response = self.client.get(
            reverse("buchung_list"),
            {"liegenschaft": str(self.bhg14_property.pk), "jahr": str(current_year)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_sum_netto"], Decimal("150"))
        self.assertEqual(response.context["filtered_sum_brutto"], Decimal("165"))
        self.assertContains(response, "Summe gefiltert:")
        self.assertContains(response, "Netto")
        self.assertContains(response, "Brutto")

    def test_excel_export_download_contains_selected_rows(self):
        current_year = date.today().year
        included_booking = Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Export Zeile Sichtbar",
            datum=date(current_year, 3, 1),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        _hidden_booking = Buchung.objects.create(
            mietervertrag=self.bhg14_lease,
            einheit=self.bhg14_unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Export Zeile Versteckt",
            datum=date(current_year, 3, 2),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("55.00"),
        )

        response = self.client.get(
            reverse("buchung_export_excel"),
            {
                "liegenschaft": str(self.bhg14_property.pk),
                "jahr": str(current_year),
                "ids": str(included_booking.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertIn("Export Zeile Sichtbar", worksheet_xml)
        self.assertNotIn("Export Zeile Versteckt", worksheet_xml)
        self.assertIn("<v>100.00</v>", worksheet_xml)
        self.assertIn("<v>110.00</v>", worksheet_xml)


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

    def test_lease_detail_shows_only_last_month_in_mietkonto(self):
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
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["kind"], "month_summary")
        self.assertEqual(rows[1]["kind"], "booking")
        self.assertEqual(rows[2]["kind"], "booking")

        february_summary = rows[0]

        self.assertEqual(february_summary["month_label"], "02.2026")
        self.assertEqual(february_summary["month_soll"], Decimal("55.00"))
        self.assertEqual(february_summary["month_haben"], Decimal("70.00"))
        self.assertEqual(february_summary["month_end_kontostand"], Decimal("-40.00"))
        self.assertEqual(february_summary["offen"], Decimal("40.00"))
        self.assertEqual(rows[1]["buchung"].buchungstext, "Zahlung 02/2026")
        self.assertEqual(rows[2]["buchung"].buchungstext, "SOLL 02/2026")

    def test_lease_detail_shows_wertsicherung_instead_of_vpi_title(self):
        ReminderRuleConfig.objects.update_or_create(
            code="vpi_indexation",
            defaults={
                "title": "VPI-Erinnerung",
                "lead_months": 24,
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.lease.index_type = LeaseAgreement.IndexType.VPI
        self.lease.last_index_adjustment = timezone.localdate()
        self.lease.save(update_fields=["index_type", "last_index_adjustment"])

        response = self.client.get(reverse("lease_detail", args=[self.lease.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("lease_reminder_items", response.context)
        self.assertTrue(response.context["lease_reminder_items"])
        self.assertContains(response, "Wertsicherung")
        self.assertNotContains(response, "VPI-Erinnerung")

    def test_lease_update_contains_attachments_panel(self):
        response = self.client.get(reverse("lease_update", args=[self.lease.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachments_panel", response.context)
        self.assertEqual(response.context["attachments_panel"]["title"], "Dateien zum Mietverhältnis")


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


class BetriebskostenGruppeModelTests(TestCase):
    def test_get_or_create_ungrouped_is_idempotent(self):
        first, _first_created = BetriebskostenGruppe.get_or_create_ungrouped()
        second, second_created = BetriebskostenGruppe.get_or_create_ungrouped()
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.system_key, BetriebskostenGruppe.SYSTEM_KEY_UNGROUPED)
        self.assertEqual(first.name, "Ungruppiert")


class BetriebskostenBelegFormTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt BK Form",
            zip_code="1080",
            city="Wien",
            street_address="Formgasse 8",
        )
        self.ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()

    def test_form_uses_user_provided_brutto_value_for_validation(self):
        form = BetriebskostenBelegForm(
            data={
                "liegenschaft": str(self.property.pk),
                "bk_art": BetriebskostenBeleg.BKArt.STROM,
                "ausgabengruppe": str(self.ungrouped_group.pk),
                "datum": "2026-02-01",
                "netto": "100.00",
                "ust_prozent": "10.00",
                "brutto": "111.00",
                "buchungstext": "Test",
                "lieferant_name": "",
                "iban": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("brutto", form.errors)

    def test_form_prefills_calculated_ust_betrag_for_existing_entry(self):
        beleg = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 2, 2),
            netto=Decimal("123.45"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("148.14"),
        )

        form = BetriebskostenBelegForm(instance=beleg)
        self.assertEqual(form.fields["ust_betrag"].initial, Decimal("24.69"))


class BetriebskostenBelegCreateViewTests(TestCase):
    def setUp(self):
        self.bhg14 = Property.objects.create(
            name="BHG14",
            zip_code="1010",
            city="Wien",
            street_address="Hauptstraße 14",
        )

    def test_create_view_renders_without_template_variable_error(self):
        response = self.client.get(reverse("betriebskostenbeleg_create"))
        self.assertEqual(response.status_code, 200)

    def test_create_view_prefills_bhg14_and_betriebskosten_and_hides_supplier_fields(self):
        response = self.client.get(reverse("betriebskostenbeleg_create"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()

        self.assertEqual(form.initial.get("liegenschaft"), self.bhg14.pk)
        self.assertEqual(
            form.initial.get("bk_art"),
            BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
        )
        self.assertEqual(form.initial.get("ausgabengruppe"), ungrouped_group.pk)
        self.assertNotIn("lieferant_name", form.fields)
        self.assertNotIn("iban", form.fields)


class BetriebskostenGruppeViewTests(TestCase):
    def test_create_and_update_group(self):
        create_response = self.client.post(
            reverse("betriebskosten_gruppe_create"),
            {
                "name": "Hausreinigung",
                "sort_order": "30",
                "is_active": "on",
            },
            follow=False,
        )
        self.assertEqual(create_response.status_code, 302)
        group = BetriebskostenGruppe.objects.get(name="Hausreinigung")
        self.assertEqual(group.sort_order, 30)
        self.assertTrue(group.is_active)

        update_response = self.client.post(
            reverse("betriebskosten_gruppe_update", args=[group.pk]),
            {
                "name": "Hausreinigung 2026",
                "sort_order": "35",
                "is_active": "",
            },
            follow=False,
        )
        self.assertEqual(update_response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.name, "Hausreinigung 2026")
        self.assertEqual(group.sort_order, 35)
        self.assertFalse(group.is_active)


class BetriebskostenBelegListViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Belegliste",
            zip_code="1140",
            city="Wien",
            street_address="Belegweg 14",
        )
        self.ungrouped_group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
        self.custom_group = BetriebskostenGruppe.objects.create(
            name="Versicherung",
            sort_order=20,
            is_active=True,
        )

    def test_list_defaults_to_current_year(self):
        current_year = date.today().year
        previous_year = current_year - 1

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(current_year, 3, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
            buchungstext="Aktuelles Jahr",
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(previous_year, 3, 10),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
            buchungstext="Vorjahr",
        )

        response = self.client.get(reverse("betriebskostenbeleg_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], current_year)
        self.assertEqual(len(response.context["belege"]), 1)
        self.assertEqual(response.context["belege"][0].datum.year, current_year)

    def test_list_applies_requested_year_filter(self):
        current_year = date.today().year
        previous_year = current_year - 1

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(current_year, 4, 10),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("96.00"),
            buchungstext="Aktuelles Jahr",
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(previous_year, 4, 10),
            netto=Decimal("70.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("84.00"),
            buchungstext="Vorjahr",
        )

        response = self.client.get(reverse("betriebskostenbeleg_list"), {"jahr": str(previous_year)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], previous_year)
        self.assertEqual(len(response.context["belege"]), 1)
        self.assertEqual(response.context["belege"][0].datum.year, previous_year)

    def test_bulk_group_update_assigns_selected_rows(self):
        beleg_one = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 5, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
            ausgabengruppe=self.ungrouped_group,
        )
        beleg_two = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 5, 11),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("24.00"),
            ausgabengruppe=self.ungrouped_group,
        )

        response = self.client.post(
            reverse("betriebskostenbeleg_bulk_group_update"),
            {
                "selected_belege": [str(beleg_one.pk), str(beleg_two.pk)],
                "bulk_group_id": str(self.custom_group.pk),
                "next": reverse("betriebskostenbeleg_list"),
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        beleg_one.refresh_from_db()
        beleg_two.refresh_from_db()
        self.assertEqual(beleg_one.ausgabengruppe_id, self.custom_group.pk)
        self.assertEqual(beleg_two.ausgabengruppe_id, self.custom_group.pk)

    def test_bulk_delete_removes_selected_rows(self):
        beleg_one = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 8, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
            ausgabengruppe=self.ungrouped_group,
        )
        _beleg_two = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 8, 11),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("24.00"),
            ausgabengruppe=self.ungrouped_group,
        )

        response = self.client.post(
            reverse("betriebskostenbeleg_bulk_group_update"),
            {
                "selected_belege": [str(beleg_one.pk)],
                "bulk_action": "delete",
                "next": reverse("betriebskostenbeleg_list"),
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(BetriebskostenBeleg.objects.filter(pk=beleg_one.pk).exists())
        self.assertEqual(BetriebskostenBeleg.objects.count(), 1)

    def test_list_hides_bulk_checkboxes_by_default(self):
        response = self.client.get(reverse("betriebskostenbeleg_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "beleg-bulk-checkbox-cell d-none")
        self.assertContains(response, "bulk_action")

    def test_list_renders_filtered_netto_and_brutto_sums(self):
        current_year = date.today().year
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(current_year, 6, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
            buchungstext="Summe 1",
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(current_year, 6, 11),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
            buchungstext="Summe 2",
        )

        response = self.client.get(reverse("betriebskostenbeleg_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_sum_netto"], Decimal("150"))
        self.assertEqual(response.context["filtered_sum_brutto"], Decimal("180"))
        self.assertContains(response, "Summe gefiltert:")
        self.assertContains(response, "Netto")
        self.assertContains(response, "Brutto")

    def test_excel_export_download_contains_selected_rows(self):
        current_year = date.today().year
        included_beleg = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(current_year, 7, 1),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("96.00"),
            buchungstext="Excel Sichtbar",
            import_referenz="BK-EXCEL-1",
        )
        _hidden_beleg = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(current_year, 7, 2),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("24.00"),
            buchungstext="Excel Versteckt",
            import_referenz="BK-EXCEL-2",
        )

        response = self.client.get(
            reverse("betriebskostenbeleg_export_excel"),
            {
                "jahr": str(current_year),
                "ids": str(included_beleg.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertIn("Excel Sichtbar", worksheet_xml)
        self.assertNotIn("Excel Versteckt", worksheet_xml)
        self.assertIn("<v>80.00</v>", worksheet_xml)
        self.assertIn("<v>96.00</v>", worksheet_xml)


class BetriebskostenBelegUpdateViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt BK View",
            zip_code="1090",
            city="Wien",
            street_address="Filtergasse 9",
        )
        self.beleg = BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2026, 1, 15),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
            buchungstext="Strom Jänner",
        )

    def test_update_redirects_back_to_filtered_list_via_next(self):
        next_url = (
            f"{reverse('betriebskostenbeleg_list')}"
            "?suche=strom&art=strom&sort=datum&richtung=desc"
        )
        response = self.client.post(
            reverse("betriebskostenbeleg_update", args=[self.beleg.pk]),
            {
                "liegenschaft": str(self.property.pk),
                "bk_art": BetriebskostenBeleg.BKArt.STROM,
                "ausgabengruppe": str(self.beleg.ausgabengruppe_id),
                "datum": "2026-01-15",
                "netto": "110.00",
                "ust_prozent": "20.00",
                "brutto": "132.00",
                "buchungstext": "Strom Februar",
                "lieferant_name": "",
                "iban": "",
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.beleg.refresh_from_db()
        self.assertEqual(self.beleg.buchungstext, "Strom Februar")
        self.assertEqual(self.beleg.netto, Decimal("110.00"))
        self.assertEqual(self.beleg.brutto, Decimal("132.00"))

    def test_update_rejects_external_next_url(self):
        response = self.client.post(
            reverse("betriebskostenbeleg_update", args=[self.beleg.pk]),
            {
                "liegenschaft": str(self.property.pk),
                "bk_art": BetriebskostenBeleg.BKArt.STROM,
                "ausgabengruppe": str(self.beleg.ausgabengruppe_id),
                "datum": "2026-01-15",
                "netto": "100.00",
                "ust_prozent": "20.00",
                "brutto": "120.00",
                "buchungstext": "Strom Jänner",
                "lieferant_name": "",
                "iban": "",
                "next": "https://example.org/evil",
            },
        )

        self.assertRedirects(
            response,
            reverse("betriebskostenbeleg_list"),
            fetch_redirect_response=False,
        )


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
        self.assertTrue(first_preview_rows[0]["bk_group_id"])

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
        created_beleg = BetriebskostenBeleg.objects.get(import_referenz="REF-BK-1000")
        self.assertEqual(
            created_beleg.ausgabengruppe.system_key,
            BetriebskostenGruppe.SYSTEM_KEY_UNGROUPED,
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

    def test_settlement_adjustment_is_suggested_and_can_be_overridden(self):
        payload = [
            {
                "referenceNumber": "REF-SETTLEMENT-1",
                "partnerName": "Erwin Import",
                "partnerAccount": {"iban": "AT611904300234573201"},
                "amount": {"value": 55000, "precision": 2},
                "booking": "2026-01-18T10:00:00+0000",
                "reference": "Nachzahlung Heizkosten 2025",
            }
        ]

        self._upload_payload(payload)
        preview_rows = self.client.session.get("bank_import_preview_rows", [])
        self.assertEqual(len(preview_rows), 1)
        self.assertTrue(preview_rows[0]["suggested_settlement_adjustment"])
        self.assertTrue(preview_rows[0]["is_settlement_adjustment"])
        self.assertIn("nachzahl", preview_rows[0]["settlement_match_reason"].casefold())

        response = self.client.post(
            reverse("bank_import"),
            {
                "action": "confirm",
                "lease_0": str(self.lease.pk),
                "settlement_adjustment_0": "0",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        booking = Buchung.objects.get(
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext__startswith="BANKIMPORT [REF-SETTLEMENT-1]",
        )
        self.assertFalse(booking.is_settlement_adjustment)


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

        details_by_key = {
            row["key"]: row for row in response.context["overview_finance_details"]
        }
        self.assertEqual(details_by_key["strom"]["expenses_sum"], Decimal("100.00"))
        self.assertEqual(details_by_key["wasser"]["expenses_sum"], Decimal("50.00"))
        self.assertEqual(details_by_key["betriebskosten"]["expenses_sum"], Decimal("30.00"))
        self.assertEqual(details_by_key["heizung"]["expenses_sum"], Decimal("0.00"))
        self.assertEqual(details_by_key["betriebskosten"]["income_sum"], Decimal("80.00"))
        self.assertEqual(details_by_key["heizung"]["income_sum"], Decimal("30.00"))

        self.assertEqual(len(details_by_key["betriebskosten"]["income_rows"]), 1)
        self.assertEqual(
            details_by_key["betriebskosten"]["income_rows"][0]["source"],
            "Anteil aus Zahlung",
        )
        self.assertEqual(
            details_by_key["betriebskosten"]["income_rows"][0]["amount"],
            Decimal("80.00"),
        )
        self.assertEqual(len(details_by_key["heizung"]["income_rows"]), 1)
        self.assertEqual(
            details_by_key["heizung"]["income_rows"][0]["amount"],
            Decimal("30.00"),
        )

    def test_overview_excludes_settlement_adjustment_income_rows(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Regulaere BK Zahlung",
            datum=date(2026, 5, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
            is_settlement_adjustment=False,
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Nachzahlung Vorjahr",
            datum=date(2026, 5, 11),
            netto=Decimal("40.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("44.00"),
            is_settlement_adjustment=True,
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "uebersicht"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["einnahmen_betriebskosten"], Decimal("100.00"))

        details_by_key = {
            row["key"]: row for row in response.context["overview_finance_details"]
        }
        self.assertEqual(details_by_key["betriebskosten"]["income_sum"], Decimal("100.00"))
        self.assertEqual(len(details_by_key["betriebskosten"]["income_rows"]), 1)

    def test_overview_does_not_allocate_hmz_as_anteil_aus_zahlung(self):
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK Top7",
            datum=date(2026, 6, 1),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Miete Top7",
            datum=date(2026, 6, 1),
            netto=Decimal("600.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("660.00"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "uebersicht"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["einnahmen_betriebskosten"], Decimal("100.00"))

        details_by_key = {
            row["key"]: row for row in response.context["overview_finance_details"]
        }
        rows = details_by_key["betriebskosten"]["income_rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "IST-Buchung · Betriebskosten")

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
        rows_by_number = {row["meter_number"]: row for row in all_rows}
        self.assertEqual(rows_by_number["GEN-1"]["start_value_display"], "100.000")
        self.assertEqual(rows_by_number["GEN-1"]["end_value_display"], "150.000")
        self.assertEqual(rows_by_number["UNIT-1"]["start_value_display"], "—")
        self.assertEqual(rows_by_number["UNIT-1"]["end_value_display"], "20.000")

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

    def test_summary_trace_shows_component_breakdown_and_net_balance(self):
        self.unit.operating_cost_share = Decimal("20.00")
        self.unit.save(update_fields=["operating_cost_share"])

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK Akonto",
            datum=date(2026, 2, 10),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("22.00"),
        )

        response = self.client.get(
            reverse("betriebskostenabrechnung"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026", "reiter": "zusammenfassung"},
        )
        self.assertEqual(response.status_code, 200)
        trace = response.context["annual_statement_trace"]
        self.assertEqual(len(trace["rows"]), 1)
        row = trace["rows"][0]

        self.assertEqual(row["bk_allg"], Decimal("100.00"))
        self.assertEqual(row["wasser"], Decimal("0.00"))
        self.assertEqual(row["allgemeinstrom"], Decimal("0.00"))
        self.assertEqual(row["warmwasser"], Decimal("0.00"))
        self.assertEqual(row["heizung_total"], Decimal("0.00"))
        self.assertEqual(row["netto_10"], Decimal("100.00"))
        self.assertEqual(row["netto_20"], Decimal("0.00"))
        self.assertEqual(row["netto_total"], Decimal("100.00"))
        self.assertEqual(row["ust_10"], Decimal("10.00"))
        self.assertEqual(row["ust_20"], Decimal("0.00"))
        self.assertEqual(row["ust_total"], Decimal("10.00"))
        self.assertEqual(row["gross_10"], Decimal("110.00"))
        self.assertEqual(row["gross_20"], Decimal("0.00"))
        self.assertEqual(row["saldo_brutto_10"], Decimal("-88.00"))
        self.assertEqual(row["saldo_brutto_20"], Decimal("0.00"))
        self.assertEqual(row["akonto_total"], Decimal("20.00"))
        self.assertEqual(row["akonto_total_brutto"], Decimal("22.00"))
        self.assertEqual(row["saldo_netto"], Decimal("-80.00"))
        self.assertEqual(row["gross_total"], Decimal("110.00"))
        self.assertEqual(row["saldo_brutto"], Decimal("-88.00"))
        self.assertEqual(trace["totals"]["saldo_netto"], Decimal("-80.00"))
        self.assertEqual(trace["totals"]["ust_total"], Decimal("10.00"))


class AnnualStatementLetterRunTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="HV Muster GmbH",
            contact_person="Max Muster",
            email="office@example.at",
            phone="+431234567",
            account_number="",
            tax_mode=Manager.TaxMode.NETTO,
        )
        self.property = Property.objects.create(
            name="Objekt Briefe",
            zip_code="1010",
            city="Wien",
            street_address="Briefgasse 5",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="2",
            name="Top 2",
            operating_cost_share=Decimal("25.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Anna",
            last_name="Beispiel",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("120.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.lease.tenants.add(self.tenant)

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 15),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK Akonto",
            datum=date(2026, 2, 10),
            netto=Decimal("20.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("22.00"),
        )

    def _ensure_run(self):
        response = self.client.get(
            reverse("annual_statement_run_ensure"),
            {"liegenschaft": str(self.property.pk), "jahr": "2026"},
        )
        self.assertEqual(response.status_code, 302)
        return Abrechnungslauf.objects.get(liegenschaft=self.property, jahr=2026)

    def _generate_letters(self, *, run, start_number=1000):
        run.brief_nummer_start = start_number
        run.save(update_fields=["brief_nummer_start", "updated_at"])
        response = self.client.post(
            reverse("annual_statement_run_generate_letters", kwargs={"pk": run.pk})
        )
        self.assertEqual(response.status_code, 200)
        return response

    def _create_pdf_datei(self) -> Datei:
        return Datei.objects.create(
            file=SimpleUploadedFile("bk.pdf", b"%PDF-1.4", content_type="application/pdf"),
            kategorie=Datei.Kategorie.DOKUMENT,
        )

    def _mark_letters_with_pdf(self, *, run: Abrechnungslauf) -> None:
        for letter in run.schreiben.all():
            letter.pdf_datei = self._create_pdf_datei()
            letter.save(update_fields=["pdf_datei", "updated_at"])

    def test_ensure_view_creates_run_and_letter_rows(self):
        run = self._ensure_run()
        self.assertEqual(run.schreiben.count(), 1)
        letter = run.schreiben.select_related("mietervertrag", "einheit").first()
        self.assertEqual(letter.mietervertrag_id, self.lease.pk)
        self.assertEqual(letter.einheit_id, self.unit.pk)
        self.assertIsNone(run.brief_nummer_start)

    def test_preview_view_renders_letter_data(self):
        run = self._ensure_run()
        letter = run.schreiben.first()

        response = self.client.get(
            reverse(
                "annual_statement_letter_preview",
                kwargs={"run_pk": run.pk, "pk": letter.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Briefvorschau")
        self.assertContains(response, "Anna Beispiel")
        self.assertContains(response, "Top 2")
        self.assertContains(response, "HV Muster GmbH")
        self.assertContains(response, "Betriebskostenabrechnung 2026")
        self.assertContains(response, "Rechnungsnummer")
        self.assertContains(response, "Kontodaten erhalten Sie gesondert")
        self.assertContains(response, "Anhang: Zählerstände")
        self.assertContains(response, "Anhang: Kostenzusammenfassung")
        self.assertContains(response, "Summe der Kosten")
        self.assertContains(response, "Originalbelege")
        self.assertContains(response, "Immo-Fuchs KG")

    def test_preview_shows_grouped_expenses_with_ungrouped_warning(self):
        cleaning_group = BetriebskostenGruppe.objects.create(
            name="Hausreinigung",
            sort_order=10,
            is_active=True,
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            ausgabengruppe=cleaning_group,
            datum=date(2026, 2, 15),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
            buchungstext="Stiegenhaus Reinigung",
        )

        run = self._ensure_run()
        letter = run.schreiben.first()
        response = self.client.get(
            reverse(
                "annual_statement_letter_preview",
                kwargs={"run_pk": run.pk, "pk": letter.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hausreinigung")
        self.assertContains(response, "Stiegenhaus Reinigung")
        self.assertContains(response, "Ungruppiert")
        self.assertContains(response, "Hinweis:")

    def test_money_format_uses_austrian_thousand_separator(self):
        self.assertEqual(
            AnnualStatementRunService._format_money_at(Decimal("1614.12")),
            "1.614,12",
        )

    def test_document_number_format_uses_sequence_and_year(self):
        self.assertEqual(
            AnnualStatementRunService._format_document_number(sequence_number=1, year=2026),
            "01/2026",
        )
        self.assertEqual(
            AnnualStatementRunService._format_document_number(sequence_number=700, year=2026),
            "700/2026",
        )
        self.assertEqual(
            AnnualStatementRunService._format_document_number(sequence_number=None, year=2026),
            "—",
        )

    def test_run_freetext_is_saved_and_visible_in_preview(self):
        run = self._ensure_run()
        response = self.client.post(
            reverse("annual_statement_run_update_note", kwargs={"pk": run.pk}),
            {
                "brief_freitext": "Bitte beachten Sie die geänderte Frist.",
                "brief_nummer_start": "700",
            },
        )
        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.brief_freitext, "Bitte beachten Sie die geänderte Frist.")
        self.assertEqual(run.brief_nummer_start, 700)

        letter = run.schreiben.first()
        preview_response = self.client.get(
            reverse(
                "annual_statement_letter_preview",
                kwargs={"run_pk": run.pk, "pk": letter.pk},
            )
        )
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Bitte beachten Sie die geänderte Frist.")

    def test_generate_letters_returns_zip_and_stores_document_on_lease(self):
        run = self._ensure_run()

        response = self._generate_letters(run=run, start_number=700)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".zip", response["Content-Disposition"])
        self.assertEqual(response["X-Generated-Letters"], "1")

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        file_names = archive.namelist()
        self.assertEqual(len(file_names), 1)
        self.assertTrue(file_names[0].endswith(".pdf"))
        self.assertRegex(
            file_names[0],
            r"^700_2026_[A-Z0-9]+_Betriebskostenabrechnung_\d{8}\.pdf$",
        )
        self.assertTrue(archive.read(file_names[0]).startswith(b"%PDF"))

        letter = run.schreiben.select_related("pdf_datei").get()
        self.assertIsNotNone(letter.generated_at)
        self.assertIsNotNone(letter.pdf_datei_id)
        self.assertEqual(letter.laufende_nummer, 700)
        self.assertEqual(letter.pdf_datei.kategorie, Datei.Kategorie.DOKUMENT)

        lease_content_type = ContentType.objects.get_for_model(self.lease)
        self.assertTrue(
            DateiZuordnung.objects.filter(
                datei=letter.pdf_datei,
                content_type=lease_content_type,
                object_id=self.lease.pk,
            ).exists()
        )

    def test_generate_letters_twice_archives_previous_pdf(self):
        run = self._ensure_run()
        self._generate_letters(run=run, start_number=900)
        letter = run.schreiben.get()
        first_pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(first_pdf_id)
        self.assertEqual(letter.laufende_nummer, 900)

        self._generate_letters(run=run, start_number=900)
        letter.refresh_from_db()
        second_pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(second_pdf_id)
        self.assertNotEqual(first_pdf_id, second_pdf_id)
        self.assertEqual(run.schreiben.count(), 1)
        self.assertEqual(letter.laufende_nummer, 900)

        first_pdf = Datei.objects.get(pk=first_pdf_id)
        self.assertTrue(first_pdf.is_archived)
        self.assertTrue(
            DateiZuordnung.objects.filter(
                datei_id=second_pdf_id,
                object_id=self.lease.pk,
                content_type=ContentType.objects.get_for_model(self.lease),
            ).exists()
        )

    def test_archived_letter_download_link_resolves_to_current_pdf(self):
        run = self._ensure_run()
        self._generate_letters(run=run, start_number=901)
        letter = run.schreiben.get()
        archived_pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(archived_pdf_id)

        self._generate_letters(run=run, start_number=901)
        letter.refresh_from_db()
        current_pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(current_pdf_id)
        self.assertNotEqual(archived_pdf_id, current_pdf_id)

        response = self.client.get(reverse("datei_download", kwargs={"pk": archived_pdf_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        downloaded_bytes = b"".join(response.streaming_content)
        with letter.pdf_datei.file.open("rb") as current_file:
            self.assertEqual(downloaded_bytes, current_file.read())

    def test_delete_run_confirm_page_renders(self):
        run = self._ensure_run()
        response = self.client.get(reverse("annual_statement_run_delete", kwargs={"pk": run.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brieflauf löschen")
        self.assertContains(response, "Archivieren (empfohlen)")

    def test_delete_run_with_keep_keeps_pdf(self):
        run = self._ensure_run()
        self._generate_letters(run=run, start_number=1001)
        letter = run.schreiben.get()
        pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(pdf_id)

        response = self.client.post(
            reverse("annual_statement_run_delete", kwargs={"pk": run.pk}),
            {"file_action": "keep"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Abrechnungslauf.objects.filter(pk=run.pk).exists())
        self.assertTrue(Datei.objects.filter(pk=pdf_id).exists())
        self.assertFalse(Datei.objects.get(pk=pdf_id).is_archived)

    def test_delete_run_with_archive_archives_pdf(self):
        run = self._ensure_run()
        self._generate_letters(run=run, start_number=1002)
        letter = run.schreiben.get()
        pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(pdf_id)

        response = self.client.post(
            reverse("annual_statement_run_delete", kwargs={"pk": run.pk}),
            {"file_action": "archive"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Abrechnungslauf.objects.filter(pk=run.pk).exists())
        self.assertTrue(Datei.objects.filter(pk=pdf_id).exists())
        self.assertTrue(Datei.objects.get(pk=pdf_id).is_archived)

    def test_delete_run_with_delete_removes_pdf(self):
        run = self._ensure_run()
        self._generate_letters(run=run, start_number=1003)
        letter = run.schreiben.get()
        pdf_id = letter.pdf_datei_id
        self.assertIsNotNone(pdf_id)

        response = self.client.post(
            reverse("annual_statement_run_delete", kwargs={"pk": run.pk}),
            {"file_action": "delete"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Abrechnungslauf.objects.filter(pk=run.pk).exists())
        self.assertFalse(Datei.objects.filter(pk=pdf_id).exists())

    def test_generate_letters_requires_confirmed_start_number(self):
        run = self._ensure_run()
        response = self.client.post(
            reverse("annual_statement_run_generate_letters", kwargs={"pk": run.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(run.schreiben.count(), 1)
        letter = run.schreiben.first()
        self.assertIsNone(letter.pdf_datei_id)
        self.assertIsNone(letter.laufende_nummer)

    def test_preview_uses_property_fallback_when_manager_missing(self):
        self.property.manager = None
        self.property.save(update_fields=["manager"])
        run = self._ensure_run()
        letter = run.schreiben.first()

        response = self.client.get(
            reverse(
                "annual_statement_letter_preview",
                kwargs={"run_pk": run.pk, "pk": letter.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Objekt Briefe")

    def test_pdf_service_requires_working_weasyprint(self):
        payload = {
            "sender_name": "Test Verwaltung",
            "sender_street": "Teststraße 1",
            "sender_zip_city": "1010 Wien",
            "recipient_name": "Anna Beispiel",
            "recipient_street": "Briefgasse 5",
            "recipient_zip_city": "1010 Wien",
            "issue_date": "11.02.2026",
            "subject": "Betriebskostenabrechnung 2026",
            "greeting_text": "Sehr geehrte Damen und Herren,",
            "intro_text": "Testintro",
            "year": 2026,
            "period_text": "01.01.2026 bis 31.12.2026",
            "unit_label": "Top 2 · 2",
            "netto_10": Decimal("10.00"),
            "netto_20": Decimal("5.00"),
            "netto_total": Decimal("15.00"),
            "ust_10": Decimal("1.00"),
            "ust_20": Decimal("1.00"),
            "ust_total": Decimal("2.00"),
            "gross_10": Decimal("11.00"),
            "gross_20": Decimal("6.00"),
            "gross_total": Decimal("17.00"),
            "akonto_total_brutto": Decimal("10.00"),
            "saldo_brutto": Decimal("-7.00"),
            "saldo_text": "Nachzahlung offen",
            "payment_type": "nachzahlung",
            "payment_amount": Decimal("7.00"),
            "payment_due_date": "25.02.2026",
            "payment_hint": "Bitte überweisen.",
            "closing_text": "Mit freundlichen Grüßen",
            "has_sender_account": False,
            "sender_account": "",
            "statement_rows": [],
            "meter_summary_rows": [],
            "expense_summary_rows": [],
            "expense_summary_total": Decimal("0.00"),
            "document_number_display": "1",
            "free_text": "",
        }
        if not AnnualStatementPdfService.weasyprint_available():
            with self.assertRaises(AnnualStatementPdfGenerationError):
                AnnualStatementPdfService.generate_letter_pdf(payload=payload)
            return

        pdf_bytes = AnnualStatementPdfService.generate_letter_pdf(payload=payload)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertNotIn(b"/BaseFont /Helvetica", pdf_bytes)

    def test_generate_letters_shows_error_when_pdf_generation_fails(self):
        run = self._ensure_run()
        run.brief_nummer_start = 777
        run.save(update_fields=["brief_nummer_start", "updated_at"])

        with patch(
            "webapp.services.annual_statement_pdf_service.AnnualStatementPdfService.generate_letter_pdf",
            side_effect=AnnualStatementPdfGenerationError("Testfehler PDF"),
        ):
            response = self.client.post(
                reverse("annual_statement_run_generate_letters", kwargs={"pk": run.pk}),
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PDF-Erstellung fehlgeschlagen für Einheit")
        self.assertContains(response, "Testfehler PDF")
        letter = run.schreiben.get()
        self.assertIsNone(letter.pdf_datei_id)

    def test_apply_endpoint_stays_blocked_until_letters_are_generated(self):
        run = self._ensure_run()
        response = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)
        run.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run.status, Abrechnungslauf.Status.DRAFT)
        self.assertContains(response, "Bitte zuerst die BK-Briefe erzeugen")
        self.assertEqual(Buchung.objects.filter(mietervertrag=self.lease, typ=Buchung.Typ.SOLL).count(), 0)

    def test_apply_creates_two_soll_bookings_and_marks_run_applied(self):
        run = self._ensure_run()
        self._mark_letters_with_pdf(run=run)

        with patch.object(
            AnnualStatementRunService,
            "_annual_rows_by_unit",
            return_value={
                self.unit.pk: {
                    "costs_net_10": Decimal("100.00"),
                    "costs_net_20": Decimal("50.00"),
                    "akonto_bk": Decimal("20.00"),
                    "akonto_hk": Decimal("10.00"),
                }
            },
        ):
            response = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)

        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, Abrechnungslauf.Status.APPLIED)
        self.assertIsNotNone(run.applied_at)

        letter = run.schreiben.get()
        letter.refresh_from_db()
        self.assertIsNotNone(letter.applied_at)
        self.assertIsNotNone(letter.settlement_booking_bk_id)
        self.assertIsNotNone(letter.settlement_booking_hk_id)

        booking_bk = Buchung.objects.get(pk=letter.settlement_booking_bk_id)
        booking_hk = Buchung.objects.get(pk=letter.settlement_booking_hk_id)
        self.assertEqual(booking_bk.typ, Buchung.Typ.SOLL)
        self.assertEqual(booking_bk.kategorie, Buchung.Kategorie.BK)
        self.assertEqual(booking_bk.netto, Decimal("80.00"))
        self.assertEqual(booking_bk.ust_prozent, Decimal("10.00"))
        self.assertEqual(booking_bk.brutto, Decimal("88.00"))
        self.assertTrue(booking_bk.is_settlement_adjustment)
        self.assertEqual(booking_hk.typ, Buchung.Typ.SOLL)
        self.assertEqual(booking_hk.kategorie, Buchung.Kategorie.HK)
        self.assertEqual(booking_hk.netto, Decimal("40.00"))
        self.assertEqual(booking_hk.ust_prozent, Decimal("20.00"))
        self.assertEqual(booking_hk.brutto, Decimal("48.00"))
        self.assertTrue(booking_hk.is_settlement_adjustment)

    def test_apply_creates_negative_soll_bookings_for_guthaben(self):
        run = self._ensure_run()
        self._mark_letters_with_pdf(run=run)

        with patch.object(
            AnnualStatementRunService,
            "_annual_rows_by_unit",
            return_value={
                self.unit.pk: {
                    "costs_net_10": Decimal("20.00"),
                    "costs_net_20": Decimal("10.00"),
                    "akonto_bk": Decimal("100.00"),
                    "akonto_hk": Decimal("50.00"),
                }
            },
        ):
            response = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)

        self.assertEqual(response.status_code, 200)
        letter = run.schreiben.get()
        booking_bk = Buchung.objects.get(pk=letter.settlement_booking_bk_id)
        booking_hk = Buchung.objects.get(pk=letter.settlement_booking_hk_id)
        self.assertEqual(booking_bk.netto, Decimal("-80.00"))
        self.assertEqual(booking_bk.brutto, Decimal("-88.00"))
        self.assertEqual(booking_hk.netto, Decimal("-40.00"))
        self.assertEqual(booking_hk.brutto, Decimal("-48.00"))

    def test_apply_skips_zero_components_and_still_marks_letter_applied(self):
        run = self._ensure_run()
        self._mark_letters_with_pdf(run=run)

        with patch.object(
            AnnualStatementRunService,
            "_annual_rows_by_unit",
            return_value={
                self.unit.pk: {
                    "costs_net_10": Decimal("0.00"),
                    "costs_net_20": Decimal("0.00"),
                    "akonto_bk": Decimal("0.00"),
                    "akonto_hk": Decimal("0.00"),
                }
            },
        ):
            response = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)

        self.assertEqual(response.status_code, 200)
        letter = run.schreiben.get()
        self.assertIsNone(letter.settlement_booking_bk_id)
        self.assertIsNone(letter.settlement_booking_hk_id)
        self.assertIsNotNone(letter.applied_at)
        self.assertEqual(
            Buchung.objects.filter(
                mietervertrag=self.lease,
                typ=Buchung.Typ.SOLL,
                kategorie__in=[Buchung.Kategorie.BK, Buchung.Kategorie.HK],
            ).count(),
            0,
        )

    def test_apply_shifts_booking_date_when_same_day_soll_exists(self):
        run = self._ensure_run()
        self._mark_letters_with_pdf(run=run)
        apply_date = timezone.localdate()
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="Bestehende BK-SOLL",
            datum=apply_date,
            netto=Decimal("1.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("1.10"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease,
            einheit=self.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HK,
            buchungstext="Bestehende HK-SOLL",
            datum=apply_date,
            netto=Decimal("1.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("1.20"),
        )

        with patch.object(
            AnnualStatementRunService,
            "_annual_rows_by_unit",
            return_value={
                self.unit.pk: {
                    "costs_net_10": Decimal("100.00"),
                    "costs_net_20": Decimal("50.00"),
                    "akonto_bk": Decimal("20.00"),
                    "akonto_hk": Decimal("10.00"),
                }
            },
        ):
            response = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)

        self.assertEqual(response.status_code, 200)
        letter = run.schreiben.get()
        booking_bk = Buchung.objects.get(pk=letter.settlement_booking_bk_id)
        booking_hk = Buchung.objects.get(pk=letter.settlement_booking_hk_id)
        self.assertEqual(booking_bk.datum, apply_date + timedelta(days=1))
        self.assertEqual(booking_hk.datum, apply_date + timedelta(days=1))

    def test_apply_is_idempotent_when_run_already_applied(self):
        run = self._ensure_run()
        self._mark_letters_with_pdf(run=run)
        fixed_rows = {
            self.unit.pk: {
                "costs_net_10": Decimal("100.00"),
                "costs_net_20": Decimal("50.00"),
                "akonto_bk": Decimal("20.00"),
                "akonto_hk": Decimal("10.00"),
            }
        }

        with patch.object(AnnualStatementRunService, "_annual_rows_by_unit", return_value=fixed_rows):
            first = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)
            second = self.client.post(reverse("annual_statement_run_apply", kwargs={"pk": run.pk}), follow=True)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            Buchung.objects.filter(
                mietervertrag=self.lease,
                typ=Buchung.Typ.SOLL,
                kategorie__in=[Buchung.Kategorie.BK, Buchung.Kategorie.HK],
            ).count(),
            2,
        )


class OperatingCostServiceTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Service",
            zip_code="1080",
            city="Wien",
            street_address="Servicegasse 1",
        )
        self.unit_one = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
            operating_cost_share=Decimal("20.00"),
        )
        self.unit_two = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="2",
            name="Top 2",
            operating_cost_share=Decimal("30.00"),
        )
        self.tenant_one = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Eva",
            last_name="Muster",
        )
        self.tenant_two = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Tom",
            last_name="Beispiel",
        )
        self.lease_one = LeaseAgreement.objects.create(
            unit=self.unit_one,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("80.00"),
            heating_costs_net=Decimal("30.00"),
        )
        self.lease_two = LeaseAgreement.objects.create(
            unit=self.unit_two,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("600.00"),
            operating_costs_net=Decimal("120.00"),
            heating_costs_net=Decimal("70.00"),
        )
        self.lease_one.tenants.add(self.tenant_one)
        self.lease_two.tenants.add(self.tenant_two)

    def test_report_data_applies_rounding_correction_for_distribution(self):
        unit_three = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="3",
            name="Top 3",
            operating_cost_share=Decimal("1.00"),
        )
        lease_three = LeaseAgreement.objects.create(
            unit=unit_three,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2025, 1, 1),
            net_rent=Decimal("400.00"),
            operating_costs_net=Decimal("60.00"),
            heating_costs_net=Decimal("20.00"),
        )
        lease_three.tenants.add(
            Tenant.objects.create(
                salutation=Tenant.Salutation.DIVERS,
                first_name="Kim",
                last_name="Test",
            )
        )
        self.unit_one.operating_cost_share = Decimal("1.00")
        self.unit_one.save(update_fields=["operating_cost_share"])
        self.unit_two.operating_cost_share = Decimal("1.00")
        self.unit_two.save(update_fields=["operating_cost_share"])

        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 2, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        bk_allg = report["distribution"]["bk_allgemein"]
        self.assertEqual(bk_allg["original_sum"], "100.00")
        self.assertEqual(bk_allg["distributed_sum"], "100.00")
        self.assertEqual(bk_allg["rounding_diff"], "0.00")

        cost_shares = [Decimal(row["cost_share"]) for row in bk_allg["rows"]]
        self.assertEqual(sum(cost_shares, Decimal("0.00")), Decimal("100.00"))
        self.assertIn(Decimal("33.34"), cost_shares)

    def test_get_tenant_statement_returns_costs_and_prepayments(self):
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 2, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="SOLL HMZ 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="SOLL BK 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("80.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("88.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HK,
            buchungstext="SOLL HK 2026",
            datum=date(2026, 1, 1),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="IST 2026 10%",
            datum=date(2026, 1, 15),
            netto=Decimal("580.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("638.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.ZAHLUNG,
            buchungstext="IST 2026 20%",
            datum=date(2026, 1, 15),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )

        statement = OperatingCostService(property=self.property, year=2026).get_tenant_statement(
            self.unit_one
        )
        self.assertEqual(statement["totals"]["costs_net"], "40.00")
        self.assertEqual(statement["totals"]["costs_gross"], "44.00")
        self.assertEqual(statement["totals"]["prepayments"], "110.00")
        self.assertEqual(statement["totals"]["balance"], "66.00")

    def test_report_data_excludes_settlement_adjustment_payments(self):
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK reguler",
            datum=date(2026, 2, 1),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("110.00"),
            is_settlement_adjustment=False,
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK Nachzahlung Vorjahr",
            datum=date(2026, 2, 2),
            netto=Decimal("40.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("44.00"),
            is_settlement_adjustment=True,
        )

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        self.assertEqual(report["financials"]["income"]["betriebskosten"], "100.00")

    def test_report_data_does_not_allocate_hmz_to_bk_hk(self):
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.BK,
            buchungstext="BK bezahlt",
            datum=date(2026, 3, 1),
            netto=Decimal("120.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("132.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HK,
            buchungstext="HK bezahlt",
            datum=date(2026, 3, 1),
            netto=Decimal("30.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("36.00"),
        )
        Buchung.objects.create(
            mietervertrag=self.lease_one,
            einheit=self.unit_one,
            typ=Buchung.Typ.IST,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="Miete bezahlt",
            datum=date(2026, 3, 1),
            netto=Decimal("700.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("770.00"),
        )

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        self.assertEqual(report["financials"]["income"]["betriebskosten"], "120.00")
        self.assertEqual(report["financials"]["income"]["heizung"], "30.00")

    def test_report_data_contains_legacy_allocation_blocks(self):
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 10),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 1, 11),
            netto=Decimal("50.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("60.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2026, 1, 12),
            netto=Decimal("120.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("144.00"),
        )

        def create_meter_with_delta(meter_type, unit, delta):
            meter = Meter.objects.create(
                property=self.property,
                unit=unit,
                meter_type=meter_type,
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2025, 12, 31),
                value=Decimal("0.000"),
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2026, 12, 31),
                value=Decimal(delta),
            )
            return meter

        create_meter_with_delta(Meter.MeterType.ELECTRICITY, None, "300.000")
        create_meter_with_delta(Meter.MeterType.WP_ELECTRICITY, None, "90.000")
        create_meter_with_delta(Meter.MeterType.WP_HEAT, None, "180.000")
        create_meter_with_delta(Meter.MeterType.WP_WARMWATER, None, "120.000")
        create_meter_with_delta(Meter.MeterType.WATER_COLD, None, "100.000")
        create_meter_with_delta(Meter.MeterType.WATER_COLD, self.unit_one, "40.000")
        create_meter_with_delta(Meter.MeterType.WATER_COLD, self.unit_two, "50.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, None, "60.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_one, "20.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_two, "40.000")
        create_meter_with_delta(Meter.MeterType.HEAT_ENERGY, self.unit_one, "100.000")
        create_meter_with_delta(Meter.MeterType.HEAT_ENERGY, self.unit_two, "300.000")

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        allocations = report["allocations"]

        self.assertEqual(allocations["electricity_common"]["price_per_kwh"], "0.400000")
        self.assertEqual(allocations["electricity_common"]["cost_pool"], "84.00")
        self.assertEqual(allocations["water"]["cost_pool"], "50.00")
        self.assertEqual(allocations["water"]["schwund_m3"], "10.000")
        self.assertEqual(allocations["wp_metrics"]["ratio_heat"], "0.600000")
        self.assertEqual(allocations["wp_metrics"]["ratio_ww"], "0.400000")
        self.assertEqual(allocations["hot_water"]["cost_pool"], "14.40")
        self.assertEqual(allocations["heating"]["cost_pool"], "21.60")
        self.assertEqual(allocations["annual_statement"]["totals"]["net_10"], "248.40")
        self.assertEqual(allocations["annual_statement"]["totals"]["net_20"], "21.60")

    def test_water_allocation_uses_cold_and_hot_consumption(self):
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 15),
            netto=Decimal("10.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("12.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.WASSER,
            datum=date(2026, 2, 1),
            netto=Decimal("60.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("72.00"),
        )

        def create_meter_with_delta(meter_type, unit, delta):
            meter = Meter.objects.create(
                property=self.property,
                unit=unit,
                meter_type=meter_type,
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2025, 12, 31),
                value=Decimal("0.000"),
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2026, 12, 31),
                value=Decimal(delta),
            )

        create_meter_with_delta(Meter.MeterType.WATER_COLD, None, "100.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, None, "50.000")
        create_meter_with_delta(Meter.MeterType.WATER_COLD, self.unit_one, "30.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_one, "20.000")
        create_meter_with_delta(Meter.MeterType.WATER_COLD, self.unit_two, "50.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_two, "20.000")

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        water = report["allocations"]["water"]

        self.assertEqual(water["house_consumption_m3"], "150.000")
        self.assertEqual(water["measured_units_m3"], "120.000")
        rows = {row["unit_id"]: row for row in water["rows"]}
        self.assertEqual(rows[self.unit_one.pk]["measured_m3"], "50.000")
        self.assertEqual(rows[self.unit_two.pk]["measured_m3"], "70.000")

    def test_hot_water_allocation_uses_sum_of_unit_meters_for_total(self):
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            datum=date(2026, 1, 10),
            netto=Decimal("10.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("12.00"),
        )
        BetriebskostenBeleg.objects.create(
            liegenschaft=self.property,
            bk_art=BetriebskostenBeleg.BKArt.STROM,
            datum=date(2026, 1, 11),
            netto=Decimal("100.00"),
            ust_prozent=Decimal("20.00"),
            brutto=Decimal("120.00"),
        )

        def create_meter_with_delta(meter_type, unit, delta):
            meter = Meter.objects.create(
                property=self.property,
                unit=unit,
                meter_type=meter_type,
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2025, 12, 31),
                value=Decimal("0.000"),
            )
            MeterReading.objects.create(
                meter=meter,
                date=date(2026, 12, 31),
                value=Decimal(delta),
            )

        create_meter_with_delta(Meter.MeterType.ELECTRICITY, None, "1000.000")
        create_meter_with_delta(Meter.MeterType.WP_ELECTRICITY, None, "400.000")
        create_meter_with_delta(Meter.MeterType.WP_HEAT, None, "600.000")
        create_meter_with_delta(Meter.MeterType.WP_WARMWATER, None, "400.000")

        # Abweichender Hauszaehler darf fuer WW-Preis nicht mehr als Nenner genutzt werden.
        create_meter_with_delta(Meter.MeterType.WATER_HOT, None, "500.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_one, "20.000")
        create_meter_with_delta(Meter.MeterType.WATER_HOT, self.unit_two, "30.000")

        report = OperatingCostService(property=self.property, year=2026).get_report_data()
        hot_water = report["allocations"]["hot_water"]
        rows = {row["unit_id"]: row for row in hot_water["rows"]}

        self.assertEqual(hot_water["cost_pool"], "16.00")
        self.assertEqual(hot_water["house_consumption_m3"], "50.000")
        self.assertEqual(hot_water["price_per_m3"], "0.320000")
        self.assertEqual(rows[self.unit_one.pk]["cost_share"], "6.40")
        self.assertEqual(rows[self.unit_two.pk]["cost_share"], "9.60")


class DateiManagementModelTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Datei",
            zip_code="1090",
            city="Wien",
            street_address="Dateigasse 9",
        )

    def test_soft_dedup_sets_duplicate_reference(self):
        content = b"gleiches-dokument"
        first = Datei.objects.create(
            file=SimpleUploadedFile("vertrag.pdf", content, content_type="application/pdf"),
            kategorie=Datei.Kategorie.VERTRAG,
            beschreibung="Erstes Dokument",
        )
        second = Datei.objects.create(
            file=SimpleUploadedFile("vertrag-kopie.pdf", content, content_type="application/pdf"),
            kategorie=Datei.Kategorie.VERTRAG,
            beschreibung="Duplikat",
        )

        self.assertEqual(first.checksum_sha256, second.checksum_sha256)
        self.assertEqual(second.duplicate_of_id, first.pk)
        self.assertEqual(first.duplicate_of_id, None)

    @override_settings(DATEI_HARD_DEDUP=True)
    def test_hard_dedup_rejects_duplicate_checksum(self):
        content = b"duplikat-hart"
        Datei.objects.create(
            file=SimpleUploadedFile("beleg.pdf", content, content_type="application/pdf"),
            kategorie=Datei.Kategorie.DOKUMENT,
        )

        with self.assertRaises(ValidationError):
            Datei.objects.create(
                file=SimpleUploadedFile("beleg-kopie.pdf", content, content_type="application/pdf"),
                kategorie=Datei.Kategorie.DOKUMENT,
            )

    def test_generic_assignment_links_file_to_business_object(self):
        datei = Datei.objects.create(
            file=SimpleUploadedFile("zaehler.jpg", b"img", content_type="image/jpeg"),
            kategorie=Datei.Kategorie.ZAEHLERFOTO,
        )
        zuordnung = DateiZuordnung.objects.create(
            datei=datei,
            content_type=ContentType.objects.get_for_model(Property),
            object_id=self.property.pk,
        )

        self.assertEqual(zuordnung.content_object, self.property)

    def test_upload_path_uses_context_object_and_safe_filename(self):
        datei = Datei(
            file=SimpleUploadedFile(
                "Abrechnung März 2026.PDF",
                b"pdf",
                content_type="application/pdf",
            ),
            kategorie=Datei.Kategorie.DOKUMENT,
        )
        datei.set_upload_context(content_object=self.property)
        datei.save()

        file_path = datei.file.name
        self.assertTrue(
            file_path.startswith(
                f"uploads/property/{self.property.pk}/{Datei.Kategorie.DOKUMENT}/"
            )
        )
        self.assertRegex(
            file_path,
            r"/\d{4}/\d{2}/[0-9a-f]{32}_abrechnung-marz-2026\.pdf$",
        )

    def test_upload_path_falls_back_to_unassigned_context(self):
        datei = Datei.objects.create(
            file=SimpleUploadedFile("foto.png", b"img", content_type="image/png"),
            kategorie=Datei.Kategorie.BILD,
        )
        self.assertTrue(
            datei.file.name.startswith(
                f"uploads/unzugeordnet/0/{Datei.Kategorie.BILD}/"
            )
        )

    def test_upload_path_can_use_existing_assignment_context(self):
        datei = Datei.objects.create(
            file=SimpleUploadedFile("erstes.jpg", b"img-a", content_type="image/jpeg"),
            kategorie=Datei.Kategorie.BILD,
        )
        DateiZuordnung.objects.create(
            datei=datei,
            content_type=ContentType.objects.get_for_model(Property),
            object_id=self.property.pk,
        )

        datei.file = SimpleUploadedFile("Neues Foto.JPG", b"img-b", content_type="image/jpeg")
        datei.save()

        self.assertTrue(
            datei.file.name.startswith(
                f"uploads/property/{self.property.pk}/{Datei.Kategorie.BILD}/"
            )
        )
        self.assertRegex(
            datei.file.name,
            r"/\d{4}/\d{2}/[0-9a-f]{32}_neues-foto\.jpg$",
        )

    def test_build_derived_upload_path_uses_derived_root(self):
        datei = Datei.objects.create(
            file=SimpleUploadedFile("beleg.pdf", b"pdf", content_type="application/pdf"),
            kategorie=Datei.Kategorie.DOKUMENT,
        )
        derived_path = build_derived_upload_path(
            datei.file.name,
            "thumbnail",
            filename="Vorschau Bild.PNG",
        )
        self.assertTrue(derived_path.startswith("uploads/_derived/"))
        self.assertIn("/thumbnail/", derived_path)
        self.assertRegex(derived_path, r"[0-9a-f]{32}_vorschau-bild\.png$")


class DateiUploadFormValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="upload-admin",
            password="pw",
            is_staff=True,
        )
        self.property = Property.objects.create(
            name="Objekt Upload",
            zip_code="1020",
            city="Wien",
            street_address="Uploadgasse 10",
        )

    def _build_form(self, upload, *, kategorie=Datei.Kategorie.DOKUMENT):
        return DateiUploadForm(
            data={
                "target_app_label": "webapp",
                "target_model": "property",
                "target_object_id": self.property.pk,
                "kategorie": kategorie,
                "beschreibung": "Testdatei",
            },
            files={"file": upload},
            user=self.user,
        )

    def test_rejects_disallowed_extension(self):
        form = self._build_form(
            SimpleUploadedFile(
                "vertrag.pdf.exe",
                b"x",
                content_type="application/pdf",
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Dateityp nicht erlaubt", str(form.errors))

    def test_rejects_mime_extension_mismatch(self):
        form = self._build_form(
            SimpleUploadedFile(
                "vertrag.pdf",
                b"%PDF",
                content_type="image/png",
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("MIME-Typ und Dateiendung", str(form.errors))

    def test_accepts_filename_with_multiple_dots(self):
        form = self._build_form(
            SimpleUploadedFile(
                "abrechnung.2026.02.pdf",
                b"%PDF",
                content_type="application/pdf",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_enforces_size_limit_per_category(self):
        limit = MAX_FILE_SIZE_BY_CATEGORY[Datei.Kategorie.ZAEHLERFOTO]
        oversized = b"x" * (limit + 1)
        form = self._build_form(
            SimpleUploadedFile(
                "zaehlerfoto.jpg",
                oversized,
                content_type="image/jpeg",
            ),
            kategorie=Datei.Kategorie.ZAEHLERFOTO,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Datei ist zu groß", str(form.errors))

    def test_valid_form_creates_file_and_assignment(self):
        form = self._build_form(
            SimpleUploadedFile(
                "beleg.pdf",
                b"%PDF",
                content_type="application/pdf",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
        datei = form.save()
        self.assertEqual(datei.zuordnungen.count(), 1)
        self.assertIsNone(datei.uploaded_by_id)
        self.assertTrue(
            DateiOperationLog.objects.filter(
                datei=datei,
                operation=DateiOperationLog.Operation.UPLOAD,
                success=True,
            ).exists()
        )


class DateiServicePermissionAndAuditTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Rechte",
            zip_code="1030",
            city="Wien",
            street_address="Rechteweg 3",
        )
        self.staff_user = get_user_model().objects.create_user(
            username="staff-user",
            password="pw",
            is_staff=True,
        )
        self.mieter_user = get_user_model().objects.create_user(
            username="mieter-user",
            password="pw",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-user",
            password="pw",
        )

    def _upload_sample(self):
        return DateiService.upload(
            user=self.staff_user,
            uploaded_file=SimpleUploadedFile(
                "zaehler.jpg",
                b"img",
                content_type="image/jpeg",
            ),
            kategorie=Datei.Kategorie.ZAEHLERFOTO,
            target_object=self.property,
        )

    def test_upload_is_allowed_for_any_authenticated_user(self):
        datei = DateiService.upload(
            user=self.other_user,
            uploaded_file=SimpleUploadedFile(
                "beleg.pdf",
                b"%PDF",
                content_type="application/pdf",
            ),
            kategorie=Datei.Kategorie.DOKUMENT,
            target_object=self.property,
        )
        self.assertIsNotNone(datei.pk)
        self.assertIsNone(datei.uploaded_by_id)
        self.assertTrue(
            DateiOperationLog.objects.filter(
                operation=DateiOperationLog.Operation.UPLOAD,
                actor__isnull=True,
                success=True,
            ).exists()
        )

    def test_download_logs_success_without_role_checks(self):
        datei = self._upload_sample()
        prepared = DateiService.prepare_download(user=self.mieter_user, datei=datei)
        self.assertEqual(prepared.pk, datei.pk)
        self.assertTrue(
            DateiOperationLog.objects.filter(
                operation=DateiOperationLog.Operation.VIEW,
                actor__isnull=True,
                datei=datei,
                success=True,
            ).exists()
        )

    def test_download_denied_for_archived_file_is_audited(self):
        datei = self._upload_sample()
        DateiService.archive(user=self.staff_user, datei=datei)
        with self.assertRaises(PermissionDenied):
            DateiService.prepare_download(user=self.other_user, datei=datei)
        self.assertTrue(
            DateiOperationLog.objects.filter(
                operation=DateiOperationLog.Operation.VIEW,
                actor__isnull=True,
                datei=datei,
                success=False,
            ).exists()
        )

    def test_delete_logs_operation(self):
        datei = self._upload_sample()
        datei_id = datei.pk
        DateiService.delete(user=self.staff_user, datei=datei)
        self.assertFalse(Datei.objects.filter(pk=datei_id).exists())
        self.assertTrue(
            DateiOperationLog.objects.filter(
                operation=DateiOperationLog.Operation.DELETE,
                actor__isnull=True,
                success=True,
            ).exists()
        )


class DateiDownloadViewTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Download",
            zip_code="1040",
            city="Wien",
            street_address="Downloadgasse 4",
        )
        self.datei = DateiService.upload(
            user=None,
            uploaded_file=SimpleUploadedFile(
                "download.pdf",
                b"%PDF",
                content_type="application/pdf",
            ),
            kategorie=Datei.Kategorie.DOKUMENT,
            target_object=self.property,
        )

    def test_download_is_publicly_accessible(self):
        response = self.client.get(reverse("datei_download", kwargs={"pk": self.datei.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")

    def test_download_of_archived_file_returns_403(self):
        DateiService.archive(user=None, datei=self.datei)
        response = self.client.get(reverse("datei_download", kwargs={"pk": self.datei.pk}))
        self.assertEqual(response.status_code, 403)


class DateiUploadViewAnonymousTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Upload Anonym",
            zip_code="1080",
            city="Wien",
            street_address="Anonymweg 8",
        )

    def test_upload_works_without_login(self):
        response = self.client.post(
            reverse("datei_upload"),
            data={
                "next": reverse("dashboard"),
                "target_app_label": "webapp",
                "target_model": "property",
                "target_object_id": self.property.pk,
                "kategorie": Datei.Kategorie.DOKUMENT,
                "beschreibung": "Anonymer Upload",
                "file": SimpleUploadedFile(
                    "anonym.pdf",
                    b"%PDF",
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Datei.objects.order_by("-id").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.original_name, "anonym.pdf")
        self.assertIsNone(created.uploaded_by_id)

    def test_upload_invalid_shows_readable_error_message(self):
        response = self.client.post(
            reverse("datei_upload"),
            data={
                "next": reverse("dashboard"),
                "target_app_label": "webapp",
                "target_model": "property",
                "target_object_id": self.property.pk,
                "kategorie": Datei.Kategorie.DOKUMENT,
                "file": SimpleUploadedFile(
                    "anhang.exe",
                    b"MZ",
                    content_type="application/octet-stream",
                ),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Datei: Dateityp nicht erlaubt. Erlaubt sind PDF, JPG, JPEG und PNG.",
        )
        self.assertNotContains(response, "['")


class DateiArchiveTests(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Archiv",
            zip_code="1050",
            city="Wien",
            street_address="Archivgasse 5",
        )
        self.staff_user = get_user_model().objects.create_user(
            username="archiv-staff",
            password="pw",
            is_staff=True,
        )
        self.mieter_user = get_user_model().objects.create_user(
            username="archiv-mieter",
            password="pw",
        )

    def test_archive_marks_file_and_blocks_download_for_everyone(self):
        datei = DateiService.upload(
            user=self.staff_user,
            uploaded_file=SimpleUploadedFile(
                "foto.jpg",
                b"image",
                content_type="image/jpeg",
            ),
            kategorie=Datei.Kategorie.BILD,
            target_object=self.property,
        )
        self.assertTrue(DateiService.can_download(user=self.mieter_user, datei=datei))

        archived = DateiService.archive(user=self.staff_user, datei=datei)
        archived.refresh_from_db()
        self.assertTrue(archived.is_archived)
        self.assertIsNone(archived.archived_by_id)
        self.assertFalse(DateiService.can_download(user=self.mieter_user, datei=archived))
        self.assertFalse(DateiService.can_download(user=self.staff_user, datei=archived))

    def test_archive_view_archives_instead_of_hard_delete(self):
        datei = DateiService.upload(
            user=self.staff_user,
            uploaded_file=SimpleUploadedFile(
                "archiv.pdf",
                b"%PDF",
                content_type="application/pdf",
            ),
            kategorie=Datei.Kategorie.DOKUMENT,
            target_object=self.property,
        )
        response = self.client.post(
            reverse("datei_archive", kwargs={"pk": datei.pk}),
            {"next": reverse("dashboard")},
        )
        self.assertEqual(response.status_code, 302)
        datei.refresh_from_db()
        self.assertTrue(datei.is_archived)
        self.assertTrue(Datei.objects.filter(pk=datei.pk).exists())


class StoragePathDeterministicTests(TestCase):
    def test_deterministic_derived_path_is_stable(self):
        original = "uploads/property/10/bild/2026/02/123abc_foto.png"
        path_one = build_deterministic_derived_upload_path(
            original,
            "thumb",
            extension=".jpg",
        )
        path_two = build_deterministic_derived_upload_path(
            original,
            "thumb",
            extension=".jpg",
        )
        self.assertEqual(path_one, path_two)
        self.assertTrue(path_one.startswith("uploads/_derived/property/10/bild/2026/02/"))
        self.assertTrue(path_one.endswith("/thumb/123abc_foto.jpg"))


class DateiManagementCommandTests(TestCase):
    PNG_1X1 = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd"
        b"\x8d\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def setUp(self):
        self.property = Property.objects.create(
            name="Objekt Kommando",
            zip_code="1060",
            city="Wien",
            street_address="Cronweg 6",
        )
        self.staff_user = get_user_model().objects.create_user(
            username="cmd-staff",
            password="pw",
            is_staff=True,
        )

    def _create_datei(self, name: str, content: bytes, content_type: str, kategorie: str):
        return Datei.objects.create(
            file=SimpleUploadedFile(name, content, content_type=content_type),
            kategorie=kategorie,
            uploaded_by=self.staff_user,
        )

    def test_files_audit_reports_missing_dangling_and_duplicates(self):
        duplicate_content = b"gleicher-inhalt"
        first = self._create_datei("dupe1.pdf", duplicate_content, "application/pdf", Datei.Kategorie.DOKUMENT)
        second = self._create_datei("dupe2.pdf", duplicate_content, "application/pdf", Datei.Kategorie.DOKUMENT)
        missing = self._create_datei("missing.pdf", b"%PDF", "application/pdf", Datei.Kategorie.DOKUMENT)

        linked = self._create_datei("linked.pdf", b"%PDF2", "application/pdf", Datei.Kategorie.DOKUMENT)
        target_property = Property.objects.create(
            name="Objekt Dangling",
            zip_code="1070",
            city="Wien",
            street_address="Danglinggasse 7",
        )
        DateiZuordnung.objects.create(
            datei=linked,
            content_type=ContentType.objects.get_for_model(Property),
            object_id=target_property.pk,
        )
        target_property.delete()

        missing_path = missing.file.name
        missing.file.storage.delete(missing_path)
        self.assertFalse(missing.file.storage.exists(missing_path))

        out = StringIO()
        call_command("files_audit", json=True, stdout=out)
        payload = json.loads(out.getvalue())

        self.assertGreaterEqual(payload["missing_files_count"], 1)
        self.assertGreaterEqual(payload["dangling_assignments_count"], 1)
        self.assertGreaterEqual(payload["duplicate_checksum_groups_count"], 1)
        ids = {item["datei_id"] for item in payload["missing_files"]}
        self.assertIn(missing.pk, ids)
        self.assertTrue({first.pk, second.pk}.issubset(set(payload["duplicate_checksum_groups"][0]["datei_ids"])))

    def test_files_cleanup_orphans_archive_mode_is_idempotent(self):
        orphan = self._create_datei("orphan.pdf", b"%PDF", "application/pdf", Datei.Kategorie.DOKUMENT)
        linked = self._create_datei("linked.pdf", b"%PDFL", "application/pdf", Datei.Kategorie.DOKUMENT)
        DateiZuordnung.objects.create(
            datei=linked,
            content_type=ContentType.objects.get_for_model(Property),
            object_id=self.property.pk,
        )

        out_dry = StringIO()
        call_command("files_cleanup_orphans", json=True, stdout=out_dry)
        dry_payload = json.loads(out_dry.getvalue())
        self.assertEqual(dry_payload["mode"], "dry-run")
        self.assertGreaterEqual(dry_payload["orphans_count"], 1)
        orphan.refresh_from_db()
        self.assertFalse(orphan.is_archived)

        out_archive = StringIO()
        call_command("files_cleanup_orphans", "--archive", json=True, stdout=out_archive)
        archive_payload = json.loads(out_archive.getvalue())
        self.assertEqual(archive_payload["mode"], "archive")
        self.assertGreaterEqual(archive_payload["archived_count"], 1)
        orphan.refresh_from_db()
        self.assertTrue(orphan.is_archived)
        linked.refresh_from_db()
        self.assertFalse(linked.is_archived)

        out_archive_second = StringIO()
        call_command("files_cleanup_orphans", "--archive", json=True, stdout=out_archive_second)
        archive_payload_second = json.loads(out_archive_second.getvalue())
        self.assertEqual(archive_payload_second["archived_count"], 0)

    def test_files_generate_thumbnails_is_safe_for_reruns(self):
        image_datei = self._create_datei(
            "thumb-test.png",
            self.PNG_1X1,
            "image/png",
            Datei.Kategorie.ZAEHLERFOTO,
        )
        target_path = build_deterministic_derived_upload_path(
            image_datei.file.name,
            "thumb",
            extension=".jpg",
        )
        if image_datei.file.storage.exists(target_path):
            image_datei.file.storage.delete(target_path)

        out_first = StringIO()
        call_command("files_generate_thumbnails", "--json", stdout=out_first)
        first_payload = json.loads(out_first.getvalue())
        if first_payload.get("status") == "skipped":
            self.assertIn("Pillow", first_payload.get("reason", ""))
            return

        self.assertGreaterEqual(first_payload["created"], 1)
        self.assertTrue(image_datei.file.storage.exists(target_path))

        out_second = StringIO()
        call_command("files_generate_thumbnails", "--json", stdout=out_second)
        second_payload = json.loads(out_second.getvalue())
        self.assertGreaterEqual(second_payload["skipped_existing"], 1)

class ReminderServiceTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="Verwaltung Test",
            contact_person="Anna Admin",
            email="verwaltung@example.at",
        )
        self.manager_without_email = Manager.objects.create(
            company_name="Verwaltung Ohne Mail",
            contact_person="Otto Ohne",
            email="",
        )
        self.property = Property.objects.create(
            name="Objekt Erinnerung",
            zip_code="1010",
            city="Wien",
            street_address="Erinnerungsgasse 1",
            manager=self.manager,
        )
        self.unit_one = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
            usable_area=Decimal("50.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.unit_two = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="2",
            name="Top 2",
            usable_area=Decimal("45.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Max",
            last_name="Muster",
        )

        self.vpi_lease = LeaseAgreement.objects.create(
            unit=self.unit_one,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            exit_date=date(2028, 12, 31),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.vpi_lease.tenants.add(self.tenant)

        self.overdue_vpi_lease = LeaseAgreement.objects.create(
            unit=self.unit_two,
            manager=self.manager_without_email,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2024, 1, 1),
            exit_date=date(2028, 12, 31),
            net_rent=Decimal("450.00"),
            operating_costs_net=Decimal("90.00"),
            heating_costs_net=Decimal("40.00"),
        )
        self.overdue_vpi_lease.tenants.add(self.tenant)

        ReminderRuleConfig.objects.update_or_create(
            code="vpi_indexation",
            defaults={
                "title": "VPI-Indexierung",
                "lead_months": 2,
                "is_active": True,
                "sort_order": 10,
            },
        )
        ReminderRuleConfig.objects.update_or_create(
            code="lease_exit",
            defaults={
                "title": "Vertragsende",
                "lead_months": 3,
                "is_active": True,
                "sort_order": 20,
            },
        )

    def test_add_months_handles_end_of_month(self):
        self.assertEqual(add_months(date(2025, 1, 31), 1), date(2025, 2, 28))
        self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))

    def test_collect_items_uses_db_lead_months_and_includes_overdue(self):
        ReminderRuleConfig.objects.filter(code="vpi_indexation").update(lead_months=2)

        service = ReminderService(today=date(2026, 2, 12))
        items = service.collect_items()

        due_lease_ids = {item.lease_id for item in items if item.rule_code == "vpi_indexation"}
        self.assertIn(self.vpi_lease.pk, due_lease_ids)
        self.assertIn(self.overdue_vpi_lease.pk, due_lease_ids)
        self.assertTrue(any(item.is_overdue for item in items if item.lease_id == self.overdue_vpi_lease.pk))

    def test_collect_items_reads_recipient_from_manager_email(self):
        service = ReminderService(today=date(2026, 2, 12))
        items = service.collect_items()

        vpi_item = next(item for item in items if item.lease_id == self.vpi_lease.pk)
        overdue_item = next(item for item in items if item.lease_id == self.overdue_vpi_lease.pk)
        self.assertEqual(vpi_item.recipient_email, "verwaltung@example.at")
        self.assertEqual(overdue_item.recipient_email, "")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.at",
)
class ReminderCommandTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="Mail Verwaltung",
            contact_person="Mia Mail",
            email="mail@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt Mail",
            zip_code="1020",
            city="Wien",
            street_address="Mailgasse 2",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top Mail",
            usable_area=Decimal("60.00"),
            operating_cost_share=Decimal("12.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Erika",
            last_name="Empfang",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.FIX,
            exit_date=date(2026, 4, 10),
            net_rent=Decimal("700.00"),
            operating_costs_net=Decimal("120.00"),
            heating_costs_net=Decimal("60.00"),
        )
        self.lease.tenants.add(self.tenant)

        ReminderRuleConfig.objects.update_or_create(
            code="lease_exit",
            defaults={
                "title": "Vertragsende",
                "lead_months": 3,
                "is_active": True,
                "sort_order": 20,
            },
        )
        ReminderRuleConfig.objects.update_or_create(
            code="vpi_indexation",
            defaults={
                "title": "VPI-Indexierung",
                "lead_months": 2,
                "is_active": False,
                "sort_order": 10,
            },
        )

    def test_send_reminders_is_idempotent_within_same_week(self):
        call_command("send_reminders", today="2026-02-12")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ReminderEmailLog.objects.count(), 1)

        call_command("send_reminders", today="2026-02-12")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ReminderEmailLog.objects.count(), 1)

    def test_send_reminders_dry_run_writes_nothing(self):
        call_command("send_reminders", today="2026-02-12", dry_run=True)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ReminderEmailLog.objects.count(), 0)

    def test_send_reminders_skips_items_without_email(self):
        self.manager.email = ""
        self.manager.save(update_fields=["email"])

        call_command("send_reminders", today="2026-02-12")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ReminderEmailLog.objects.count(), 0)


class ReminderUiIntegrationTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="UI Verwaltung",
            contact_person="Uli UI",
            email="ui@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt UI",
            zip_code="1030",
            city="Wien",
            street_address="Uigasse 3",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="3",
            name="Top UI",
            usable_area=Decimal("55.00"),
            operating_cost_share=Decimal("11.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Lukas",
            last_name="Listen",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.FIX,
            exit_date=date(2026, 4, 1),
            net_rent=Decimal("650.00"),
            operating_costs_net=Decimal("110.00"),
            heating_costs_net=Decimal("55.00"),
        )
        self.lease.tenants.add(self.tenant)

        ReminderRuleConfig.objects.update_or_create(
            code="lease_exit",
            defaults={
                "title": "Vertragsende",
                "lead_months": 3,
                "is_active": True,
                "sort_order": 20,
            },
        )

    def test_dashboard_shows_reminder_section(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Erinnerungen")
        self.assertContains(response, "Vertragsende")

    def test_lease_list_highlights_rows_with_reminders(self):
        response = self.client.get(reverse("lease_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "lease-row-has-reminders")
        self.assertContains(response, "Vertragsende")

    def test_lease_list_shows_wertsicherung_label_for_vpi_rule(self):
        ReminderRuleConfig.objects.update_or_create(
            code="vpi_indexation",
            defaults={
                "title": "VPI-Erinnerung",
                "lead_months": 24,
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.lease.index_type = LeaseAgreement.IndexType.VPI
        self.lease.last_index_adjustment = timezone.localdate()
        self.lease.save(update_fields=["index_type", "last_index_adjustment"])

        response = self.client.get(reverse("lease_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wertsicherung")
        self.assertNotContains(response, "VPI-Erinnerung")

    def test_reminder_settings_can_update_lead_months(self):
        configs = list(ReminderRuleConfig.objects.order_by("sort_order", "code"))
        post_data = {
            "form-TOTAL_FORMS": str(len(configs)),
            "form-INITIAL_FORMS": str(len(configs)),
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
        }

        for index, config in enumerate(configs):
            post_data[f"form-{index}-id"] = str(config.id)
            post_data[f"form-{index}-title"] = config.title
            post_data[f"form-{index}-lead_months"] = str(config.lead_months)
            if config.is_active:
                post_data[f"form-{index}-is_active"] = "on"

        lease_exit_index = next(
            index for index, config in enumerate(configs) if config.code == "lease_exit"
        )
        post_data[f"form-{lease_exit_index}-lead_months"] = "4"

        response = self.client.post(reverse("reminder_settings"), data=post_data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("reminder_settings"))
        self.assertEqual(
            ReminderRuleConfig.objects.get(code="lease_exit").lead_months,
            4,
        )


class VpiAdjustmentModelTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="VPI Verwaltung",
            contact_person="Vera VPI",
            email="vpi@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt VPI",
            zip_code="1040",
            city="Wien",
            street_address="Indexgasse 1",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
            usable_area=Decimal("60.00"),
            operating_cost_share=Decimal("12.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Vito",
            last_name="Mieter",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.lease.tenants.add(self.tenant)

    def _build_letter(self, *, run: VpiAdjustmentRun) -> VpiAdjustmentLetter:
        return VpiAdjustmentLetter(
            run=run,
            lease=self.lease,
            unit=self.unit,
            effective_date=date(2026, 3, 1),
            old_index_value=Decimal("100.00"),
            new_index_value=Decimal("110.00"),
            factor=Decimal("1.100000"),
            old_hmz_net=Decimal("500.00"),
            new_hmz_net=Decimal("550.00"),
            delta_hmz_net=Decimal("50.00"),
            catchup_months=1,
            catchup_net_total=Decimal("50.00"),
            catchup_tax_percent=Decimal("10.00"),
            catchup_gross_total=Decimal("55.00"),
        )

    def test_vpi_index_value_month_must_be_first_day(self):
        invalid = VpiIndexValue(
            month=date(2026, 2, 2),
            index_value=Decimal("123.45"),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_vpi_index_value_month_is_unique(self):
        VpiIndexValue.objects.create(
            month=date(2026, 2, 1),
            index_value=Decimal("123.45"),
        )
        duplicate = VpiIndexValue(
            month=date(2026, 2, 1),
            index_value=Decimal("124.10"),
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_vpi_adjustment_letter_is_unique_per_run_and_lease(self):
        index_value = VpiIndexValue.objects.create(
            month=date(2026, 2, 1),
            index_value=Decimal("110.00"),
        )
        run = VpiAdjustmentRun.objects.create(
            index_value=index_value,
            run_date=date(2026, 4, 15),
        )
        first = self._build_letter(run=run)
        first.full_clean()
        first.save()

        duplicate = self._build_letter(run=run)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()


class VpiAdjustmentRunServiceTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="Service Verwaltung",
            contact_person="Susi Service",
            email="service@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt Service",
            zip_code="1050",
            city="Wien",
            street_address="Serviceweg 5",
            manager=self.manager,
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Tina",
            last_name="Test",
        )

        self.unit_due = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="1",
            name="Top 1",
            usable_area=Decimal("55.00"),
            operating_cost_share=Decimal("11.00"),
        )
        self.unit_future = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="2",
            name="Top 2",
            usable_area=Decimal("50.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.unit_missing = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="3",
            name="Top 3",
            usable_area=Decimal("48.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.unit_non_increase = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="4",
            name="Top 4",
            usable_area=Decimal("46.00"),
            operating_cost_share=Decimal("9.00"),
        )
        self.unit_fix = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="5",
            name="Top 5",
            usable_area=Decimal("52.00"),
            operating_cost_share=Decimal("10.00"),
        )

        self.due_lease = LeaseAgreement.objects.create(
            unit=self.unit_due,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.due_lease.tenants.add(self.tenant)

        self.future_lease = LeaseAgreement.objects.create(
            unit=self.unit_future,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 10, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("600.00"),
            operating_costs_net=Decimal("110.00"),
            heating_costs_net=Decimal("55.00"),
        )
        self.future_lease.tenants.add(self.tenant)

        self.missing_base_lease = LeaseAgreement.objects.create(
            unit=self.unit_missing,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=None,
            net_rent=Decimal("530.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.missing_base_lease.tenants.add(self.tenant)

        self.non_increase_lease = LeaseAgreement.objects.create(
            unit=self.unit_non_increase,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("120.00"),
            net_rent=Decimal("700.00"),
            operating_costs_net=Decimal("120.00"),
            heating_costs_net=Decimal("60.00"),
        )
        self.non_increase_lease.tenants.add(self.tenant)

        self.fix_lease = LeaseAgreement.objects.create(
            unit=self.unit_fix,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.FIX,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("480.00"),
            operating_costs_net=Decimal("95.00"),
            heating_costs_net=Decimal("45.00"),
        )
        self.fix_lease.tenants.add(self.tenant)

        self.index_value = VpiIndexValue.objects.create(
            month=date(2026, 2, 1),
            index_value=Decimal("110.00"),
        )
        self.run = VpiAdjustmentRun.objects.create(
            index_value=self.index_value,
            run_date=date(2026, 4, 15),
        )

        Buchung.objects.create(
            mietervertrag=self.due_lease,
            einheit=self.due_lease.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="HMZ 03/2026",
            datum=date(2026, 3, 1),
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )

    def _service(self) -> VpiAdjustmentRunService:
        return VpiAdjustmentRunService(run=self.run)

    def _create_pdf_datei(self) -> Datei:
        return Datei.objects.create(
            file=SimpleUploadedFile("vpi.pdf", b"%PDF-1.4", content_type="application/pdf"),
            kategorie=Datei.Kategorie.DOKUMENT,
        )

    def test_ensure_letters_filters_due_vpi_and_calculates_values(self):
        letters = self._service().ensure_letters()
        letters_by_lease = {letter.lease_id: letter for letter in letters}

        self.assertIn(self.due_lease.pk, letters_by_lease)
        self.assertIn(self.missing_base_lease.pk, letters_by_lease)
        self.assertIn(self.non_increase_lease.pk, letters_by_lease)
        self.assertNotIn(self.future_lease.pk, letters_by_lease)
        self.assertNotIn(self.fix_lease.pk, letters_by_lease)

        due_letter = letters_by_lease[self.due_lease.pk]
        self.assertEqual(due_letter.effective_date, date(2026, 3, 1))
        self.assertEqual(due_letter.factor, Decimal("1.065000"))
        self.assertEqual(due_letter.new_hmz_net, Decimal("532.50"))
        self.assertEqual(due_letter.delta_hmz_net, Decimal("32.50"))

    def test_payload_adjustment_percent_uses_effective_factor(self):
        service = self._service()
        service.ensure_letters()
        letter = VpiAdjustmentLetter.objects.get(run=self.run, lease=self.due_lease)

        payload = service.payload_for_letter(letter=letter, sequence_number=100)

        self.assertEqual(payload["factor"], Decimal("1.065000"))
        self.assertEqual(payload["adjustment_percent"], Decimal("6.50"))
        self.assertEqual(payload["adjustment_percent_display"], "6,50")
        self.assertEqual(payload["old_index_year"], 2025)
        self.assertEqual(payload["new_index_year"], 2026)

    def test_payload_old_index_year_prefers_configured_index_table_entry(self):
        VpiIndexValue.objects.create(
            month=date(2024, 12, 1),
            index_value=Decimal("100.00"),
        )
        service = self._service()
        service.ensure_letters()
        letter = VpiAdjustmentLetter.objects.get(run=self.run, lease=self.due_lease)

        payload = service.payload_for_letter(letter=letter, sequence_number=100)

        self.assertEqual(payload["old_index_year"], 2024)
        self.assertEqual(payload["new_index_year"], 2026)

    def test_factor_above_three_percent_is_split_between_tenant_and_owner(self):
        split_index = VpiIndexValue.objects.create(
            month=date(2026, 1, 1),
            index_value=Decimal("105.00"),
        )
        split_run = VpiAdjustmentRun.objects.create(
            index_value=split_index,
            run_date=date(2026, 4, 15),
        )
        letters = VpiAdjustmentRunService(run=split_run).ensure_letters()
        letter = next(item for item in letters if item.lease_id == self.due_lease.pk)

        self.assertEqual(letter.factor, Decimal("1.040000"))
        self.assertEqual(letter.new_hmz_net, Decimal("520.00"))
        self.assertEqual(letter.delta_hmz_net, Decimal("20.00"))

    def test_ensure_letters_includes_contracts_one_month_before_effective_date(self):
        early_index = VpiIndexValue.objects.create(
            month=date(2026, 1, 1),
            index_value=Decimal("110.00"),
        )
        early_run = VpiAdjustmentRun.objects.create(
            index_value=early_index,
            run_date=date(2026, 2, 14),
        )

        letters = VpiAdjustmentRunService(run=early_run).ensure_letters()
        letters_by_lease = {letter.lease_id: letter for letter in letters}

        self.assertIn(self.due_lease.pk, letters_by_lease)
        self.assertIn(self.missing_base_lease.pk, letters_by_lease)
        self.assertIn(self.non_increase_lease.pk, letters_by_lease)
        self.assertNotIn(self.future_lease.pk, letters_by_lease)
        self.assertEqual(letters_by_lease[self.due_lease.pk].effective_date, date(2026, 3, 1))

    def test_ensure_letters_marks_skip_reasons(self):
        letters = self._service().ensure_letters()
        letters_by_lease = {letter.lease_id: letter for letter in letters}

        self.assertIn("Index-Basiswert fehlt", letters_by_lease[self.missing_base_lease.pk].skip_reason)
        self.assertIn(
            "Kein Erhöhungsfaktor",
            letters_by_lease[self.non_increase_lease.pk].skip_reason,
        )

    def test_catchup_counts_only_months_with_existing_hmz_soll(self):
        service = self._service()
        service.ensure_letters()
        letter = VpiAdjustmentLetter.objects.get(run=self.run, lease=self.due_lease)

        self.assertEqual(letter.catchup_months, 1)
        self.assertEqual(letter.catchup_net_total, Decimal("32.50"))
        self.assertEqual(letter.catchup_gross_total, Decimal("35.75"))

        Buchung.objects.create(
            mietervertrag=self.due_lease,
            einheit=self.due_lease.unit,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext="HMZ 04/2026",
            datum=date(2026, 4, 1),
            netto=Decimal("500.00"),
            ust_prozent=Decimal("10.00"),
            brutto=Decimal("550.00"),
        )
        service.ensure_letters()
        letter.refresh_from_db()

        self.assertEqual(letter.catchup_months, 2)
        self.assertEqual(letter.catchup_net_total, Decimal("65.00"))
        self.assertEqual(letter.catchup_gross_total, Decimal("71.50"))

    def test_apply_run_is_idempotent(self):
        service = self._service()
        service.ensure_letters()
        self.run.brief_nummer_start = 100
        self.run.save(update_fields=["brief_nummer_start"])

        actionable_letter = VpiAdjustmentLetter.objects.get(run=self.run, lease=self.due_lease)
        actionable_letter.pdf_datei = self._create_pdf_datei()
        actionable_letter.save(update_fields=["pdf_datei", "updated_at"])

        with patch("webapp.services.vpi_adjustment_run_service.timezone.localdate", return_value=date(2026, 4, 15)):
            result_first = service.apply_run()
        self.assertEqual(result_first["updated_leases"], 1)
        self.assertEqual(result_first["catchup_bookings"], 1)

        self.due_lease.refresh_from_db()
        self.assertEqual(self.due_lease.net_rent, Decimal("532.50"))
        self.assertEqual(self.due_lease.index_base_value, Decimal("110.00"))
        self.assertEqual(self.due_lease.last_index_adjustment, date(2026, 3, 1))

        bookings = Buchung.objects.filter(
            mietervertrag=self.due_lease,
            typ=Buchung.Typ.SOLL,
            kategorie=Buchung.Kategorie.HMZ,
            buchungstext__startswith="Nachverrechnung VPI",
        )
        self.assertEqual(bookings.count(), 1)

        with patch("webapp.services.vpi_adjustment_run_service.timezone.localdate", return_value=date(2026, 4, 15)):
            result_second = service.apply_run()
        self.assertEqual(result_second["updated_leases"], 0)
        self.assertEqual(result_second["catchup_bookings"], 0)
        self.assertEqual(bookings.count(), 1)

    def test_build_letter_filename_uses_requested_pattern(self):
        self.property.name = "BHG14"
        self.property.save(update_fields=["name"])
        service = self._service()
        service.ensure_letters()
        letter = VpiAdjustmentLetter.objects.get(run=self.run, lease=self.due_lease)

        with patch("webapp.services.vpi_adjustment_run_service.timezone.localdate", return_value=date(2026, 2, 14)):
            filename = service.build_letter_filename(letter=letter, sequence_number=23)

        self.assertEqual(filename, "23_2026_BHG14_Wertsicherung_20260214.pdf")

    def test_apply_readiness_blocks_before_effective_date(self):
        early_index = VpiIndexValue.objects.create(
            month=date(2026, 1, 1),
            index_value=Decimal("110.00"),
        )
        early_run = VpiAdjustmentRun.objects.create(
            index_value=early_index,
            run_date=date(2026, 2, 14),
            brief_nummer_start=100,
        )
        service = VpiAdjustmentRunService(run=early_run)
        letters = service.ensure_letters()
        pdf = self._create_pdf_datei()
        for letter in letters:
            if (letter.skip_reason or "").strip():
                continue
            letter.pdf_datei = pdf
            letter.save(update_fields=["pdf_datei", "updated_at"])

        with patch("webapp.services.vpi_adjustment_run_service.timezone.localdate", return_value=date(2026, 2, 14)):
            ready, reason = service.apply_readiness()

        self.assertFalse(ready)
        self.assertIn("Anpassung kann erst ab 01.03.2026 angewendet werden.", reason)


class CheckVpiReleasesCommandTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="Command Verwaltung",
            contact_person="Conny Command",
            email="command@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt Command",
            zip_code="1060",
            city="Wien",
            street_address="Cronweg 6",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="6",
            name="Top 6",
            usable_area=Decimal("49.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.HERR,
            first_name="Karl",
            last_name="Cron",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.lease.tenants.add(self.tenant)

        self.pending_index = VpiIndexValue.objects.create(
            month=date(2026, 2, 1),
            index_value=Decimal("110.00"),
        )
        existing_run_index = VpiIndexValue.objects.create(
            month=date(2025, 2, 1),
            index_value=Decimal("106.00"),
        )
        VpiAdjustmentRun.objects.create(
            index_value=existing_run_index,
            run_date=date(2025, 3, 15),
        )
        VpiIndexValue.objects.create(
            month=date(2026, 1, 1),
            index_value=Decimal("109.00"),
        )

    def test_check_vpi_releases_reports_pending_values(self):
        out = StringIO()
        call_command("check_vpi_releases", stdout=out)
        output = out.getvalue()

        self.assertIn("indexwerte: 3", output)
        self.assertIn("ohne Lauf: 2", output)
        self.assertIn("- Offen: 01/2026", output)
        self.assertIn("- Offen: 02/2026", output)

    def test_check_vpi_releases_create_runs_is_idempotent(self):
        out_first = StringIO()
        call_command("check_vpi_releases", "--create-runs", "--today", "2026-04-10", stdout=out_first)
        self.assertTrue(
            VpiAdjustmentRun.objects.filter(
                index_value=self.pending_index,
                run_date=date(2026, 4, 10),
            ).exists()
        )
        self.assertIn("Läufe erstellt: 2", out_first.getvalue())
        self.assertIn("ohne Lauf: 0", out_first.getvalue())

        out_second = StringIO()
        call_command("check_vpi_releases", "--create-runs", "--today", "2026-04-10", stdout=out_second)
        self.assertIn("Läufe erstellt: 0", out_second.getvalue())
        self.assertIn("ohne Lauf: 0", out_second.getvalue())
        self.assertEqual(VpiAdjustmentRun.objects.filter(index_value=self.pending_index).count(), 1)


class VpiAdjustmentUiIntegrationTests(TestCase):
    def setUp(self):
        self.manager = Manager.objects.create(
            company_name="UI VPI Verwaltung",
            contact_person="Ute UI",
            email="ui-vpi@example.at",
        )
        self.property = Property.objects.create(
            name="Objekt UI VPI",
            zip_code="1070",
            city="Wien",
            street_address="Uiweg 7",
            manager=self.manager,
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_type=Unit.UnitType.APARTMENT,
            door_number="7",
            name="Top 7",
            usable_area=Decimal("51.00"),
            operating_cost_share=Decimal("10.00"),
        )
        self.tenant = Tenant.objects.create(
            salutation=Tenant.Salutation.FRAU,
            first_name="Uma",
            last_name="UI",
        )
        self.lease = LeaseAgreement.objects.create(
            unit=self.unit,
            manager=self.manager,
            status=LeaseAgreement.Status.AKTIV,
            entry_date=date(2024, 1, 1),
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment=date(2025, 3, 1),
            index_base_value=Decimal("100.00"),
            net_rent=Decimal("500.00"),
            operating_costs_net=Decimal("100.00"),
            heating_costs_net=Decimal("50.00"),
        )
        self.lease.tenants.add(self.tenant)
        self.older_index_value = VpiIndexValue.objects.create(
            month=date(2026, 1, 1),
            index_value=Decimal("109.00"),
        )
        self.latest_index_value = VpiIndexValue.objects.create(
            month=date(2026, 2, 1),
            index_value=Decimal("110.00"),
        )

    def test_run_uses_latest_index_value_without_manual_selection(self):
        response = self.client.get(
            reverse("vpi_adjustment_run_ensure"),
            {"run_date": "2026-04-15"},
        )
        run = VpiAdjustmentRun.objects.get(index_value=self.latest_index_value)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("vpi_adjustment_run_detail", kwargs={"pk": run.pk}),
        )
        self.assertEqual(run.run_date, date(2026, 4, 15))
        self.assertFalse(VpiAdjustmentRun.objects.filter(index_value=self.older_index_value).exists())

    def test_apply_endpoint_stays_blocked_until_letters_are_generated(self):
        run = VpiAdjustmentRunService.ensure_run(index_value=self.latest_index_value, run_date=date(2026, 4, 15))
        VpiAdjustmentRunService(run=run).ensure_letters()
        run.brief_nummer_start = 200
        run.save(update_fields=["brief_nummer_start"])

        response = self.client.post(reverse("vpi_adjustment_run_apply", kwargs={"pk": run.pk}))
        run.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(run.status, VpiAdjustmentRun.Status.DRAFT)

    def test_delete_draft_run_from_list(self):
        run = VpiAdjustmentRunService.ensure_run(index_value=self.latest_index_value, run_date=date(2026, 4, 15))
        VpiAdjustmentRunService(run=run).ensure_letters()
        letter = run.letters.filter(skip_reason="").first()
        self.assertIsNotNone(letter)
        pdf = Datei.objects.create(
            file=SimpleUploadedFile("vpi-delete.pdf", b"%PDF-1.4", content_type="application/pdf"),
            kategorie=Datei.Kategorie.DOKUMENT,
        )
        letter.pdf_datei = pdf
        letter.save(update_fields=["pdf_datei", "updated_at"])

        response = self.client.post(reverse("vpi_adjustment_run_delete", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("vpi_adjustment_run_list"))
        self.assertFalse(VpiAdjustmentRun.objects.filter(pk=run.pk).exists())
        self.assertFalse(VpiAdjustmentLetter.objects.filter(run_id=run.pk).exists())
        pdf.refresh_from_db()
        self.assertTrue(pdf.is_archived)

    def test_delete_applied_run_is_blocked(self):
        run = VpiAdjustmentRunService.ensure_run(index_value=self.latest_index_value, run_date=date(2026, 4, 15))
        run.status = VpiAdjustmentRun.Status.APPLIED
        run.save(update_fields=["status", "updated_at"])

        response = self.client.post(reverse("vpi_adjustment_run_delete", kwargs={"pk": run.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("vpi_adjustment_run_list"))
        self.assertTrue(VpiAdjustmentRun.objects.filter(pk=run.pk).exists())
