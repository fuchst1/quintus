from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Meter, MeterReading, Property


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
