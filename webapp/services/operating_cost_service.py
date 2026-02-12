from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from django.db.models import DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce

from ..models import (
    BetriebskostenBeleg,
    Buchung,
    LeaseAgreement,
    Meter,
    MeterReading,
    Property,
    Unit,
)

CENT = Decimal("0.01")
CENT3 = Decimal("0.001")
ZERO = Decimal("0.00")


def quantize_cent(value: Decimal | str | int | None) -> Decimal:
    return Decimal(value or ZERO).quantize(CENT, rounding=ROUND_HALF_UP)


def quantize_cent3(value: Decimal | str | int | None) -> Decimal:
    return Decimal(value or ZERO).quantize(CENT3, rounding=ROUND_HALF_UP)


def month_bounds(check_date: date) -> tuple[date, date]:
    month_start = date(check_date.year, check_date.month, 1)
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = date(month_start.year, month_start.month, last_day)
    return month_start, month_end


def hmz_tax_percent_for_unit(unit: Unit | None) -> Decimal:
    if unit and unit.unit_type == Unit.UnitType.PARKING:
        return Decimal("20.00")
    return Decimal("10.00")


class CostDistributionStrategy(Protocol):
    key: str
    label: str

    def build_rows(
        self,
        *,
        property_obj: Property,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, object]]:
        ...


class OperatingCostShareDistributionStrategy:
    key = "operating_cost_share"
    label = "BK-Anteil"

    def build_rows(
        self,
        *,
        property_obj: Property,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, object]]:
        lease_queryset = (
            LeaseAgreement.objects.filter(entry_date__lte=period_end)
            .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=period_start))
            .prefetch_related("tenants")
            .order_by("-entry_date", "-id")
        )
        units = (
            Unit.objects.filter(property=property_obj)
            .prefetch_related(
                Prefetch("leases", queryset=lease_queryset, to_attr="leases_for_year")
            )
            .order_by("name", "door_number", "id")
        )

        rows: list[dict[str, object]] = []
        for unit in units:
            share = quantize_cent(unit.operating_cost_share)
            if share <= ZERO:
                continue
            tenant_label = OperatingCostService.unit_tenant_label(unit)
            rows.append(
                {
                    "unit_id": unit.pk,
                    "label": f"{unit.name} - {tenant_label}" if tenant_label else unit.name,
                    "bk_anteil": share,
                    "weight": share,
                    "cost_share": ZERO,
                }
            )
        return rows


class AreaDistributionStrategy:
    # Placeholder for future strategy extraction (m2-based distribution)
    key = "usable_area"
    label = "Nutzfläche"

    def build_rows(
        self,
        *,
        property_obj: Property,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, object]]:
        raise NotImplementedError("Nutzflächen-Strategie ist noch nicht implementiert.")


class UnitCountDistributionStrategy:
    # Placeholder for future strategy extraction (equal unit distribution)
    key = "unit_count"
    label = "Einheiten"

    def build_rows(
        self,
        *,
        property_obj: Property,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, object]]:
        raise NotImplementedError("Einheiten-Strategie ist noch nicht implementiert.")


class ConsumptionDistributionStrategy:
    # Placeholder for future strategy extraction (consumption-based distribution)
    key = "consumption"
    label = "Verbrauch"

    def build_rows(
        self,
        *,
        property_obj: Property,
        period_start: date,
        period_end: date,
    ) -> list[dict[str, object]]:
        raise NotImplementedError("Verbrauchs-Strategie ist noch nicht implementiert.")


class OperatingCostService:
    def __init__(
        self,
        property: Property | None,
        year: int,
        distribution_strategy: CostDistributionStrategy | None = None,
    ) -> None:
        self.property = property
        self.year = int(year)
        self.period_start = date(self.year, 1, 1)
        self.period_end = date(self.year, 12, 31)
        self.distribution_strategy = distribution_strategy or OperatingCostShareDistributionStrategy()
        self._soll_profile_cache: dict[tuple[int, int, int], dict[str, dict[str, Decimal]]] = {}

    def get_report_data(self) -> dict[str, object]:
        expenses = {
            "strom": ZERO,
            "wasser": ZERO,
            "betriebskosten": ZERO,
        }
        income = {
            "betriebskosten": ZERO,
            "heizung": ZERO,
        }
        meter_groups: list[dict[str, object]] = []
        bk_allg_raw = self._empty_bk_allg_data()
        allocations = self._empty_allocations()

        if self.property is not None:
            expenses = self._expense_aggregation()
            income_bk, income_hk = self._allocated_income_from_ist_bookings()
            income = {
                "betriebskosten": income_bk,
                "heizung": income_hk,
            }
            meter_groups = self._meter_consumption_groups()
            bk_allg_raw = self._bk_allgemein_data_raw()
            allocations = self._build_legacy_allocations(bk_allg_raw=bk_allg_raw, expenses=expenses)

        expenses_total = (
            expenses["strom"] + expenses["wasser"] + expenses["betriebskosten"]
        ).quantize(CENT)
        income_total = (income["betriebskosten"] + income["heizung"]).quantize(CENT)
        saldo = (income_total - expenses_total).quantize(CENT)

        return {
            "meta": {
                "property_id": str(self.property.pk) if self.property else "",
                "property_name": self.property.name if self.property else "",
                "year": self.year,
                "period_start": self.period_start.isoformat(),
                "period_end": self.period_end.isoformat(),
            },
            "financials": {
                "expenses": {
                    "strom": self._money_str(expenses["strom"]),
                    "wasser": self._money_str(expenses["wasser"]),
                    "betriebskosten": self._money_str(expenses["betriebskosten"]),
                    "gesamt": self._money_str(expenses_total),
                },
                "income": {
                    "betriebskosten": self._money_str(income["betriebskosten"]),
                    "heizung": self._money_str(income["heizung"]),
                    "gesamt": self._money_str(income_total),
                },
                "saldo": self._money_str(saldo),
            },
            "meter": {
                "groups": meter_groups,
            },
            "distribution": {
                "bk_allgemein": self._serialize_bk_allg_data(bk_allg_raw),
            },
            "allocations": allocations,
        }

    def get_tenant_statement(self, unit: Unit | None) -> dict[str, object]:
        if self.property is None or unit is None:
            return self._empty_tenant_statement(unit=unit)

        unit_qs = (
            Unit.objects.select_related("property")
            .prefetch_related(
                Prefetch(
                    "leases",
                    queryset=(
                        LeaseAgreement.objects.filter(entry_date__lte=self.period_end)
                        .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=self.period_start))
                        .prefetch_related("tenants")
                        .order_by("-entry_date", "-id")
                    ),
                    to_attr="leases_for_year",
                )
            )
            .filter(pk=unit.pk, property=self.property)
        )
        selected_unit = unit_qs.first()
        if selected_unit is None:
            return self._empty_tenant_statement(unit=unit)

        leases = list(getattr(selected_unit, "leases_for_year", []) or [])
        active_lease = next(
            (lease for lease in leases if lease.status == LeaseAgreement.Status.AKTIV),
            None,
        )
        selected_lease = active_lease or (leases[0] if leases else None)
        tenant_names = []
        if selected_lease:
            tenant_names = [
                f"{tenant.first_name} {tenant.last_name}".strip()
                for tenant in selected_lease.tenants.all()
                if f"{tenant.first_name} {tenant.last_name}".strip()
            ]

        report = self.get_report_data()
        allocations = report.get("allocations", {})
        bk_row = next(
            (
                row
                for row in allocations.get("bk_distribution", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )
        water_row = next(
            (
                row
                for row in allocations.get("water", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )
        allg_strom_row = next(
            (
                row
                for row in allocations.get("electricity_common", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )
        warmwasser_row = next(
            (
                row
                for row in allocations.get("hot_water", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )
        heizung_row = next(
            (
                row
                for row in allocations.get("heating", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )
        annual_row = next(
            (
                row
                for row in allocations.get("annual_statement", {}).get("rows", [])
                if row.get("unit_id") == selected_unit.pk
            ),
            {},
        )

        cost_bk = quantize_cent(bk_row.get("anteil_euro"))
        cost_wasser = quantize_cent(water_row.get("cost_share"))
        cost_allg_strom = quantize_cent(allg_strom_row.get("cost_share"))
        cost_warmwasser = quantize_cent(warmwasser_row.get("cost_share"))
        cost_heizung = quantize_cent(heizung_row.get("cost_share"))
        costs_net = (
            cost_bk + cost_wasser + cost_allg_strom + cost_warmwasser + cost_heizung
        ).quantize(CENT)
        costs_gross = quantize_cent(annual_row.get("gross_total"))
        akonto_bk = quantize_cent(annual_row.get("akonto_bk"))
        akonto_hk = quantize_cent(annual_row.get("akonto_hk"))
        total_prepayments = (akonto_bk + akonto_hk).quantize(CENT)
        balance = (total_prepayments - costs_gross).quantize(CENT)

        lines = [
            {
                "type": "cost",
                "category": "bk_allgemein",
                "label": "BK allgemein",
                "amount": self._money_str(cost_bk),
            },
            {
                "type": "cost",
                "category": "wasser",
                "label": "Wasser",
                "amount": self._money_str(cost_wasser),
            },
            {
                "type": "cost",
                "category": "allgemeinstrom",
                "label": "Allgemeinstrom",
                "amount": self._money_str(cost_allg_strom),
            },
            {
                "type": "cost",
                "category": "warmwasser",
                "label": "Warmwasser",
                "amount": self._money_str(cost_warmwasser),
            },
            {
                "type": "cost",
                "category": "heizung",
                "label": "Heizung",
                "amount": self._money_str(cost_heizung),
            },
            {
                "type": "prepayment",
                "category": "bk",
                "label": "Vorauszahlung Betriebskosten",
                "amount": self._money_str(akonto_bk),
            },
            {
                "type": "prepayment",
                "category": "hk",
                "label": "Vorauszahlung Heizung",
                "amount": self._money_str(akonto_hk),
            },
        ]

        return {
            "meta": {
                "property_id": str(self.property.pk),
                "property_name": self.property.name,
                "year": self.year,
                "period_start": self.period_start.isoformat(),
                "period_end": self.period_end.isoformat(),
            },
            "unit": {
                "id": selected_unit.pk,
                "name": selected_unit.name,
                "door_number": selected_unit.door_number or "",
                "tenant_names": tenant_names,
                "lease_id": selected_lease.pk if selected_lease else None,
            },
            "lines": lines,
            "totals": {
                "costs_net": self._money_str(costs_net),
                "costs_gross": self._money_str(costs_gross),
                "prepayments": self._money_str(total_prepayments),
                "balance": self._money_str(balance),
            },
        }

    def _expense_aggregation(self) -> dict[str, Decimal]:
        if self.property is None:
            return {
                "strom": ZERO,
                "wasser": ZERO,
                "betriebskosten": ZERO,
            }
        expenses = (
            BetriebskostenBeleg.objects.filter(
                liegenschaft=self.property,
                datum__gte=self.period_start,
                datum__lte=self.period_end,
            ).aggregate(
                strom=Coalesce(
                    Sum(
                        "netto",
                        filter=Q(bk_art=BetriebskostenBeleg.BKArt.STROM),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(ZERO),
                ),
                wasser=Coalesce(
                    Sum(
                        "netto",
                        filter=Q(bk_art=BetriebskostenBeleg.BKArt.WASSER),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(ZERO),
                ),
                betriebskosten=Coalesce(
                    Sum(
                        "netto",
                        filter=Q(
                            bk_art__in=[
                                BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
                                BetriebskostenBeleg.BKArt.SONSTIG,
                            ]
                        ),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(ZERO),
                ),
            )
        )
        return {
            "strom": quantize_cent(expenses.get("strom")),
            "wasser": quantize_cent(expenses.get("wasser")),
            "betriebskosten": quantize_cent(expenses.get("betriebskosten")),
        }

    def _allocated_income_from_ist_bookings(
        self,
        lease_ids: set[int] | None = None,
    ) -> tuple[Decimal, Decimal]:
        if self.property is None:
            return ZERO, ZERO

        income_bk = ZERO
        income_hk = ZERO

        query = Buchung.objects.filter(
            typ=Buchung.Typ.IST,
            is_settlement_adjustment=False,
            datum__gte=self.period_start,
            datum__lte=self.period_end,
        )
        if lease_ids is None:
            query = query.filter(
                Q(mietervertrag__unit__property=self.property) | Q(einheit__property=self.property)
            )
        else:
            if not lease_ids:
                return ZERO, ZERO
            query = query.filter(mietervertrag_id__in=lease_ids)

        ist_bookings = query.select_related("mietervertrag", "mietervertrag__unit").order_by("datum", "id")

        for booking in ist_bookings:
            netto = quantize_cent(booking.netto)
            if netto <= ZERO:
                continue

            if booking.kategorie == Buchung.Kategorie.BK:
                income_bk += netto
                continue
            if booking.kategorie == Buchung.Kategorie.HK:
                income_hk += netto
                continue
            if booking.kategorie != Buchung.Kategorie.ZAHLUNG:
                continue

            lease = booking.mietervertrag
            if lease is None:
                continue

            profile = self._soll_profile_for_month(lease=lease, booking_date=booking.datum)
            bucket_key = self._rate_bucket_key(booking.ust_prozent)
            bucket_data = profile.get(bucket_key)
            if not bucket_data:
                continue

            bucket_total = quantize_cent(bucket_data["total"])
            if bucket_total <= ZERO:
                continue

            bk_share = (
                netto * bucket_data["bk"] / bucket_total
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            hk_share = (
                netto * bucket_data["hk"] / bucket_total
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            income_bk += bk_share
            income_hk += hk_share

        return income_bk.quantize(CENT), income_hk.quantize(CENT)

    def _soll_profile_for_month(
        self,
        *,
        lease: LeaseAgreement,
        booking_date: date,
    ) -> dict[str, dict[str, Decimal]]:
        cache_key = (lease.pk, booking_date.year, booking_date.month)
        if cache_key in self._soll_profile_cache:
            return self._soll_profile_cache[cache_key]

        month_start, month_end = month_bounds(booking_date)
        rows = (
            Buchung.objects.filter(
                mietervertrag=lease,
                typ=Buchung.Typ.SOLL,
                datum__gte=month_start,
                datum__lte=month_end,
                kategorie__in=[
                    Buchung.Kategorie.HMZ,
                    Buchung.Kategorie.BK,
                    Buchung.Kategorie.HK,
                ],
            )
            .values("kategorie", "ust_prozent")
            .annotate(
                netto_sum=Coalesce(
                    Sum(
                        "netto",
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(ZERO),
                )
            )
        )

        profile: dict[str, dict[str, Decimal]] = {}
        for row in rows:
            bucket_key = self._rate_bucket_key(row["ust_prozent"])
            if bucket_key not in profile:
                profile[bucket_key] = {
                    "hmz": ZERO,
                    "bk": ZERO,
                    "hk": ZERO,
                    "total": ZERO,
                }
            amount = quantize_cent(row["netto_sum"])
            category = row["kategorie"]
            if category == Buchung.Kategorie.HMZ:
                profile[bucket_key]["hmz"] += amount
            elif category == Buchung.Kategorie.BK:
                profile[bucket_key]["bk"] += amount
            elif category == Buchung.Kategorie.HK:
                profile[bucket_key]["hk"] += amount

        if not profile:
            fallback_components = [
                ("hmz", hmz_tax_percent_for_unit(lease.unit), quantize_cent(lease.net_rent)),
                ("bk", Decimal("10.00"), quantize_cent(lease.operating_costs_net)),
                ("hk", Decimal("20.00"), quantize_cent(lease.heating_costs_net)),
            ]
            for field_name, tax_percent, amount in fallback_components:
                bucket_key = self._rate_bucket_key(tax_percent)
                if bucket_key not in profile:
                    profile[bucket_key] = {
                        "hmz": ZERO,
                        "bk": ZERO,
                        "hk": ZERO,
                        "total": ZERO,
                    }
                profile[bucket_key][field_name] += amount

        for bucket_data in profile.values():
            bucket_data["total"] = (
                bucket_data["hmz"] + bucket_data["bk"] + bucket_data["hk"]
            ).quantize(CENT)

        self._soll_profile_cache[cache_key] = profile
        return profile

    @staticmethod
    def _rate_bucket_key(rate: Decimal | str | int | None) -> str:
        return str(quantize_cent(rate))

    def _meter_consumption_groups(self) -> list[dict[str, object]]:
        if self.property is None:
            return []

        meters = list(
            Meter.objects.filter(property=self.property)
            .select_related("unit")
            .prefetch_related(
                Prefetch("readings", queryset=MeterReading.objects.order_by("date", "id"))
            )
        )
        meters.sort(
            key=lambda meter: (
                0 if meter.unit is None else 1,
                (meter.unit.name or "").casefold() if meter.unit else "",
                meter.meter_type,
                meter.pk,
            )
        )

        groups: list[dict[str, object]] = []
        group_map: dict[int, dict[str, object]] = {}
        for meter in meters:
            yearly_rows = Meter._calculate_yearly_consumption_for_meter(
                meter,
                list(meter.readings.all()),
            )
            year_row = next(
                (row for row in yearly_rows if row["calc_year"] == self.year),
                None,
            )
            consumption = None
            if year_row is not None and year_row.get("consumption") is not None:
                consumption = quantize_cent3(year_row["consumption"])
            if consumption is None:
                continue

            scope_key = meter.unit_id or 0
            if scope_key not in group_map:
                if meter.unit is None:
                    label = f"{self.property.name} (Allgemein)"
                else:
                    label = meter.unit.name
                    if meter.unit.door_number:
                        label = f"{label} · {meter.unit.door_number}"
                group = {
                    "label": label,
                    "unit_id": meter.unit_id or 0,
                    "is_general": meter.unit is None,
                    "rows": [],
                }
                group_map[scope_key] = group
                groups.append(group)

            start_value = None
            end_value = None
            start_date = None
            end_date = None
            if year_row is not None:
                start_date = year_row.get("start_date")
                end_date = year_row.get("end_date")
                if year_row.get("start_value") is not None:
                    start_value = quantize_cent3(year_row["start_value"])
                if year_row.get("end_value") is not None:
                    end_value = quantize_cent3(year_row["end_value"])

            group_map[scope_key]["rows"].append(
                {
                    "meter_type_key": meter.meter_type,
                    "meter_type": meter.get_meter_type_display(),
                    "meter_number": meter.meter_number or "",
                    "unit_label": meter.get_unit_of_measure_display(),
                    "consumption": None if consumption is None else str(consumption),
                    "consumption_display": "—" if consumption is None else str(consumption),
                    "start_date": start_date,
                    "end_date": end_date,
                    "start_value": None if start_value is None else str(start_value),
                    "end_value": None if end_value is None else str(end_value),
                    "start_value_display": "—" if start_value is None else str(start_value),
                    "end_value_display": "—" if end_value is None else str(end_value),
                }
            )

        return groups

    def _empty_allocations(self) -> dict[str, object]:
        return {
            "bk_distribution": {
                "rows": [],
                "cost_pool": "0.00",
                "distributed_sum": "0.00",
                "rounding_diff": "0.00",
            },
            "water": {
                "rows": [],
                "cost_pool": "0.00",
                "house_consumption_m3": "0.000",
                "measured_units_m3": "0.000",
                "schwund_m3": "0.000",
                "price_per_m3": "0.000000",
                "distributed_sum": "0.00",
                "rounding_diff": "0.00",
            },
            "electricity_common": {
                "rows": [],
                "stromkosten_total": "0.00",
                "hausstrom_kwh": "0.000",
                "wp_strom_kwh": "0.000",
                "allgemeinstrom_kwh": "0.000",
                "price_per_kwh": "0.000000",
                "cost_pool": "0.00",
                "distributed_sum": "0.00",
                "rounding_diff": "0.00",
            },
            "wp_metrics": {
                "input_kwh": "0.000",
                "output_heat_kwh": "0.000",
                "output_ww_kwh": "0.000",
                "ratio_heat": "0.000000",
                "ratio_ww": "0.000000",
            },
            "hot_water": {
                "rows": [],
                "cost_pool": "0.00",
                "house_consumption_m3": "0.000",
                "price_per_m3": "0.000000",
                "distributed_sum": "0.00",
                "rounding_diff": "0.00",
            },
            "heating": {
                "rows": [],
                "cost_pool": "0.00",
                "fixed_pool": "0.00",
                "variable_pool": "0.00",
                "fixed_percent": "0.00",
                "total_consumption_kwh": "0.000",
                "distributed_sum": "0.00",
                "rounding_diff": "0.00",
            },
            "annual_statement": {
                "rows": [],
                "totals": {
                    "net_10": "0.00",
                    "net_20": "0.00",
                    "gross_total": "0.00",
                    "akonto_total": "0.00",
                    "saldo_total": "0.00",
                },
            },
            "checks": {
                "sum_10_pool": "0.00",
                "sum_10_units": "0.00",
                "delta_10": "0.00",
                "sum_20_pool": "0.00",
                "sum_20_units": "0.00",
                "delta_20": "0.00",
            },
        }

    def _build_legacy_allocations(
        self,
        *,
        bk_allg_raw: dict[str, object],
        expenses: dict[str, Decimal],
    ) -> dict[str, object]:
        bk_distribution = self._legacy_bk_distribution_from_raw(bk_allg_raw)
        electricity_common = self._legacy_electricity_allocation(
            bk_distribution=bk_distribution,
            stromkosten_total=quantize_cent(expenses.get("strom")),
        )
        wp_metrics = self._legacy_wp_metrics()
        water = self._legacy_water_allocation(
            bk_distribution=bk_distribution,
            water_cost_pool=quantize_cent(expenses.get("wasser")),
        )
        hot_water = self._legacy_hot_water_allocation(
            bk_distribution=bk_distribution,
            electricity_common=electricity_common,
            wp_metrics=wp_metrics,
        )
        heating = self._legacy_heating_allocation(
            bk_distribution=bk_distribution,
            electricity_common=electricity_common,
            wp_metrics=wp_metrics,
        )
        annual_statement = self._legacy_annual_statement(
            bk_distribution=bk_distribution,
            water=water,
            electricity_common=electricity_common,
            hot_water=hot_water,
            heating=heating,
        )
        checks = self._legacy_plausibility_checks(
            bk_distribution=bk_distribution,
            water=water,
            electricity_common=electricity_common,
            hot_water=hot_water,
            heating=heating,
            annual_statement=annual_statement,
        )
        return {
            "bk_distribution": self._serialize_bk_distribution(bk_distribution),
            "water": self._serialize_water_allocation(water),
            "electricity_common": self._serialize_electricity_allocation(electricity_common),
            "wp_metrics": self._serialize_wp_metrics(wp_metrics),
            "hot_water": self._serialize_hotwater_allocation(hot_water),
            "heating": self._serialize_heating_allocation(heating),
            "annual_statement": self._serialize_annual_statement(annual_statement),
            "checks": {
                "sum_10_pool": self._money_str(checks["sum_10_pool"]),
                "sum_10_units": self._money_str(checks["sum_10_units"]),
                "delta_10": self._money_str(checks["delta_10"]),
                "sum_20_pool": self._money_str(checks["sum_20_pool"]),
                "sum_20_units": self._money_str(checks["sum_20_units"]),
                "delta_20": self._money_str(checks["delta_20"]),
            },
        }

    def _legacy_bk_distribution_from_raw(self, bk_allg_raw: dict[str, object]) -> dict[str, object]:
        rows = list(bk_allg_raw.get("rows", []))
        total_share = sum((quantize_cent(row.get("bk_anteil")) for row in rows), ZERO)
        distribution_rows: list[dict[str, object]] = []
        for row in rows:
            share_value = quantize_cent(row.get("bk_anteil"))
            if total_share > ZERO:
                anteil_prozent = (
                    share_value * Decimal("100.00") / total_share
                ).quantize(CENT, rounding=ROUND_HALF_UP)
            else:
                anteil_prozent = ZERO
            distribution_rows.append(
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "bk_anteil": share_value,
                    "anteil_prozent": anteil_prozent,
                    "anteil_euro": quantize_cent(row.get("cost_share")),
                }
            )

        return {
            "rows": distribution_rows,
            "cost_pool": quantize_cent(bk_allg_raw.get("original_sum")),
            "distributed_sum": quantize_cent(bk_allg_raw.get("distributed_sum")),
            "rounding_diff": quantize_cent(bk_allg_raw.get("rounding_diff")),
        }

    def _legacy_water_allocation(
        self,
        *,
        bk_distribution: dict[str, object],
        water_cost_pool: Decimal,
    ) -> dict[str, object]:
        distribution_rows = list(bk_distribution.get("rows", []))
        house_consumption = (
            self._meter_consumption_total(
                meter_type=Meter.MeterType.WATER_COLD,
                unit_id=None,
            )
            + self._meter_consumption_total(
                meter_type=Meter.MeterType.WATER_HOT,
                unit_id=None,
            )
        ).quantize(CENT3, rounding=ROUND_HALF_UP)
        cold_unit_consumption = self._meter_consumption_map(
            meter_type=Meter.MeterType.WATER_COLD,
        )
        hot_unit_consumption = self._meter_consumption_map(
            meter_type=Meter.MeterType.WATER_HOT,
        )
        unit_ids = set(cold_unit_consumption.keys()).union(hot_unit_consumption.keys())
        unit_consumption = {
            unit_id: (
                quantize_cent3(cold_unit_consumption.get(unit_id, Decimal("0.000")))
                + quantize_cent3(hot_unit_consumption.get(unit_id, Decimal("0.000")))
            ).quantize(CENT3, rounding=ROUND_HALF_UP)
            for unit_id in unit_ids
        }
        measured_units = sum((value for value in unit_consumption.values()), Decimal("0.000"))
        measured_units = quantize_cent3(measured_units)
        schwund = (house_consumption - measured_units).quantize(CENT3, rounding=ROUND_HALF_UP)

        price_per_m3 = Decimal("0.000000")
        if house_consumption > Decimal("0.000") and water_cost_pool > ZERO:
            price_per_m3 = (
                water_cost_pool / house_consumption
            ).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)

        rows: list[dict[str, object]] = []
        for row in distribution_rows:
            anteil_prozent = quantize_cent(row.get("anteil_prozent"))
            unit_id = row.get("unit_id")
            measured = quantize_cent3(unit_consumption.get(unit_id, Decimal("0.000")))
            schwund_anteil = (
                schwund * anteil_prozent / Decimal("100.00")
            ).quantize(CENT3, rounding=ROUND_HALF_UP)
            adjusted_consumption = (measured + schwund_anteil).quantize(
                CENT3,
                rounding=ROUND_HALF_UP,
            )
            raw_cost = (
                adjusted_consumption * price_per_m3
            ).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
            rows.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "anteil_prozent": anteil_prozent,
                    "measured_m3": measured,
                    "schwund_anteil_m3": schwund_anteil,
                    "abrechnungsmenge_m3": adjusted_consumption,
                    "raw_cost_share": raw_cost,
                    "cost_share": quantize_cent(raw_cost),
                }
            )

        rounded_total = sum(
            (quantize_cent(row["cost_share"]) for row in rows),
            ZERO,
        ).quantize(CENT)
        rounding_diff = (water_cost_pool - rounded_total).quantize(CENT, rounding=ROUND_HALF_UP)

        return {
            "rows": rows,
            "cost_pool": water_cost_pool,
            "house_consumption_m3": house_consumption,
            "measured_units_m3": measured_units,
            "schwund_m3": schwund,
            "price_per_m3": price_per_m3,
            "distributed_sum": rounded_total,
            "rounding_diff": rounding_diff,
        }

    def _legacy_electricity_allocation(
        self,
        *,
        bk_distribution: dict[str, object],
        stromkosten_total: Decimal,
    ) -> dict[str, object]:
        distribution_rows = list(bk_distribution.get("rows", []))
        house_kwh = self._meter_consumption_total(
            meter_type=Meter.MeterType.ELECTRICITY,
            unit_id=None,
        )
        wp_kwh = self._meter_consumption_total(
            meter_type=Meter.MeterType.WP_ELECTRICITY,
            unit_id=None,
        )
        common_kwh = (house_kwh - wp_kwh).quantize(CENT3, rounding=ROUND_HALF_UP)
        price_per_kwh = Decimal("0.000000")
        if house_kwh > Decimal("0.000") and stromkosten_total > ZERO:
            price_per_kwh = (
                stromkosten_total / house_kwh
            ).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
        common_cost_pool = (
            common_kwh * price_per_kwh
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        rows_for_allocation: list[dict[str, object]] = []
        for row in distribution_rows:
            rows_for_allocation.append(
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": quantize_cent(row.get("anteil_prozent")),
                    "weight": quantize_cent(row.get("anteil_prozent")),
                }
            )
        allocated_rows, distributed_sum = self._allocate_amount_by_weight(
            total_amount=common_cost_pool,
            rows=rows_for_allocation,
            weight_key="weight",
            amount_key="cost_share",
        )
        row_lookup = {row.get("unit_id"): row for row in allocated_rows}
        rows: list[dict[str, object]] = []
        for row in distribution_rows:
            allocated = row_lookup.get(row.get("unit_id"), {})
            rows.append(
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": quantize_cent(row.get("anteil_prozent")),
                    "cost_share": quantize_cent(allocated.get("cost_share")),
                }
            )
        rounding_diff = (common_cost_pool - distributed_sum).quantize(CENT, rounding=ROUND_HALF_UP)

        return {
            "rows": rows,
            "stromkosten_total": stromkosten_total,
            "hausstrom_kwh": house_kwh,
            "wp_strom_kwh": wp_kwh,
            "allgemeinstrom_kwh": common_kwh,
            "price_per_kwh": price_per_kwh,
            "cost_pool": common_cost_pool,
            "distributed_sum": distributed_sum,
            "rounding_diff": rounding_diff,
        }

    def _legacy_wp_metrics(self) -> dict[str, object]:
        input_kwh = self._meter_consumption_total(
            meter_type=Meter.MeterType.WP_ELECTRICITY,
            unit_id=None,
        )
        output_heat = self._meter_consumption_total(
            meter_type=Meter.MeterType.WP_HEAT,
            unit_id=None,
        )
        output_ww = self._meter_consumption_total(
            meter_type=Meter.MeterType.WP_WARMWATER,
            unit_id=None,
        )
        total_output = (output_heat + output_ww).quantize(CENT3, rounding=ROUND_HALF_UP)
        if total_output > Decimal("0.000"):
            ratio_heat = (
                output_heat / total_output
            ).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
            ratio_ww = (
                output_ww / total_output
            ).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)
        else:
            ratio_heat = Decimal("0.000000")
            ratio_ww = Decimal("0.000000")
        return {
            "input_kwh": input_kwh,
            "output_heat_kwh": output_heat,
            "output_ww_kwh": output_ww,
            "ratio_heat": ratio_heat,
            "ratio_ww": ratio_ww,
        }

    def _legacy_hot_water_allocation(
        self,
        *,
        bk_distribution: dict[str, object],
        electricity_common: dict[str, object],
        wp_metrics: dict[str, object],
    ) -> dict[str, object]:
        distribution_rows = list(bk_distribution.get("rows", []))
        cost_pool = (
            quantize_cent3(wp_metrics.get("input_kwh"))
            * Decimal(electricity_common.get("price_per_kwh") or Decimal("0.000000"))
            * Decimal(wp_metrics.get("ratio_ww") or Decimal("0.000000"))
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        unit_consumption = self._meter_consumption_map(
            meter_type=Meter.MeterType.WATER_HOT,
        )
        # Legacy-Formel: Gesamtverbrauch Warmwasser ist die Summe der Wohnungszaehler.
        house_consumption = sum(
            (quantize_cent3(value) for value in unit_consumption.values()),
            Decimal("0.000"),
        ).quantize(CENT3, rounding=ROUND_HALF_UP)
        price_per_m3 = Decimal("0.000000")
        if house_consumption > Decimal("0.000") and cost_pool > ZERO:
            price_per_m3 = (
                cost_pool / house_consumption
            ).quantize(Decimal("0.000000"), rounding=ROUND_HALF_UP)

        rows: list[dict[str, object]] = []
        for row in distribution_rows:
            unit_id = row.get("unit_id")
            consumption = quantize_cent3(unit_consumption.get(unit_id, Decimal("0.000")))
            cost_share = (
                consumption * price_per_m3
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            rows.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "consumption_m3": consumption,
                    "cost_share": cost_share,
                }
            )
        distributed_sum = sum(
            (quantize_cent(row["cost_share"]) for row in rows),
            ZERO,
        ).quantize(CENT)
        rounding_diff = (cost_pool - distributed_sum).quantize(CENT, rounding=ROUND_HALF_UP)

        return {
            "rows": rows,
            "cost_pool": cost_pool,
            "house_consumption_m3": house_consumption,
            "price_per_m3": price_per_m3,
            "distributed_sum": distributed_sum,
            "rounding_diff": rounding_diff,
        }

    def _legacy_heating_allocation(
        self,
        *,
        bk_distribution: dict[str, object],
        electricity_common: dict[str, object],
        wp_metrics: dict[str, object],
    ) -> dict[str, object]:
        distribution_rows = list(bk_distribution.get("rows", []))
        cost_pool = (
            quantize_cent3(wp_metrics.get("input_kwh"))
            * Decimal(electricity_common.get("price_per_kwh") or Decimal("0.000000"))
            * Decimal(wp_metrics.get("ratio_heat") or Decimal("0.000000"))
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        fixed_percent = quantize_cent(getattr(self.property, "heating_share_percent", ZERO))
        fixed_pool = (
            cost_pool * fixed_percent / Decimal("100.00")
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        variable_pool = (cost_pool - fixed_pool).quantize(CENT, rounding=ROUND_HALF_UP)

        fixed_rows_input: list[dict[str, object]] = []
        for row in distribution_rows:
            fixed_rows_input.append(
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": quantize_cent(row.get("anteil_prozent")),
                    "weight": quantize_cent(row.get("anteil_prozent")),
                }
            )
        fixed_rows, fixed_sum = self._allocate_amount_by_weight(
            total_amount=fixed_pool,
            rows=fixed_rows_input,
            weight_key="weight",
            amount_key="fixed_cost_share",
        )

        heat_consumption_map = self._meter_consumption_map(meter_type=Meter.MeterType.HEAT_ENERGY)
        variable_rows_input: list[dict[str, object]] = []
        for row in distribution_rows:
            unit_id = row.get("unit_id")
            variable_rows_input.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "consumption_kwh": quantize_cent3(heat_consumption_map.get(unit_id, Decimal("0.000"))),
                    "weight": quantize_cent3(heat_consumption_map.get(unit_id, Decimal("0.000"))),
                }
            )
        variable_rows, variable_sum = self._allocate_amount_by_weight(
            total_amount=variable_pool,
            rows=variable_rows_input,
            weight_key="weight",
            amount_key="variable_cost_share",
        )

        fixed_lookup = {row.get("unit_id"): row for row in fixed_rows}
        variable_lookup = {row.get("unit_id"): row for row in variable_rows}
        rows: list[dict[str, object]] = []
        for row in distribution_rows:
            unit_id = row.get("unit_id")
            fixed_share = quantize_cent(fixed_lookup.get(unit_id, {}).get("fixed_cost_share"))
            variable_share = quantize_cent(
                variable_lookup.get(unit_id, {}).get("variable_cost_share")
            )
            consumption = quantize_cent3(
                variable_lookup.get(unit_id, {}).get("consumption_kwh")
            )
            total_share = (fixed_share + variable_share).quantize(CENT)
            rows.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "anteil_prozent": quantize_cent(row.get("anteil_prozent")),
                    "consumption_kwh": consumption,
                    "fixed_cost_share": fixed_share,
                    "variable_cost_share": variable_share,
                    "cost_share": total_share,
                }
            )

        distributed_sum = sum(
            (quantize_cent(row["cost_share"]) for row in rows),
            ZERO,
        ).quantize(CENT)
        rounding_diff = (cost_pool - distributed_sum).quantize(CENT, rounding=ROUND_HALF_UP)

        return {
            "rows": rows,
            "cost_pool": cost_pool,
            "fixed_pool": fixed_pool,
            "variable_pool": variable_pool,
            "fixed_percent": fixed_percent,
            "total_consumption_kwh": sum(
                (
                    quantize_cent3(row.get("consumption_kwh"))
                    for row in variable_rows_input
                ),
                Decimal("0.000"),
            ).quantize(CENT3),
            "distributed_sum": distributed_sum,
            "rounding_diff": rounding_diff,
            "fixed_distributed_sum": fixed_sum,
            "variable_distributed_sum": variable_sum,
        }

    def _legacy_annual_statement(
        self,
        *,
        bk_distribution: dict[str, object],
        water: dict[str, object],
        electricity_common: dict[str, object],
        hot_water: dict[str, object],
        heating: dict[str, object],
    ) -> dict[str, object]:
        prepayments_by_unit = self._prepayment_map_by_unit()
        water_lookup = {row.get("unit_id"): row for row in water.get("rows", [])}
        electricity_lookup = {
            row.get("unit_id"): row for row in electricity_common.get("rows", [])
        }
        hot_water_lookup = {row.get("unit_id"): row for row in hot_water.get("rows", [])}
        heating_lookup = {row.get("unit_id"): row for row in heating.get("rows", [])}

        rows: list[dict[str, object]] = []
        totals = {
            "net_10": ZERO,
            "net_20": ZERO,
            "gross_total": ZERO,
            "akonto_total": ZERO,
            "saldo_total": ZERO,
        }
        for row in bk_distribution.get("rows", []):
            unit_id = row.get("unit_id")
            bk_cost = quantize_cent(row.get("anteil_euro"))
            water_cost = quantize_cent(water_lookup.get(unit_id, {}).get("cost_share"))
            allg_strom_cost = quantize_cent(
                electricity_lookup.get(unit_id, {}).get("cost_share")
            )
            warmwasser_cost = quantize_cent(hot_water_lookup.get(unit_id, {}).get("cost_share"))
            heizung_cost = quantize_cent(heating_lookup.get(unit_id, {}).get("cost_share"))

            net_10 = (bk_cost + water_cost + allg_strom_cost + warmwasser_cost).quantize(CENT)
            net_20 = heizung_cost
            gross_10 = (net_10 * Decimal("1.10")).quantize(CENT, rounding=ROUND_HALF_UP)
            gross_20 = (net_20 * Decimal("1.20")).quantize(CENT, rounding=ROUND_HALF_UP)
            gross_total = (gross_10 + gross_20).quantize(CENT)

            prepayment = prepayments_by_unit.get(unit_id, {"bk": ZERO, "hk": ZERO})
            akonto_bk = quantize_cent(prepayment.get("bk"))
            akonto_hk = quantize_cent(prepayment.get("hk"))
            akonto_total = (akonto_bk + akonto_hk).quantize(CENT)
            saldo = (akonto_total - gross_total).quantize(CENT)

            rows.append(
                {
                    "unit_id": unit_id,
                    "label": row.get("label", ""),
                    "costs_net_10": net_10,
                    "costs_net_20": net_20,
                    "gross_10": gross_10,
                    "gross_20": gross_20,
                    "gross_total": gross_total,
                    "akonto_bk": akonto_bk,
                    "akonto_hk": akonto_hk,
                    "akonto_total": akonto_total,
                    "saldo": saldo,
                }
            )
            totals["net_10"] = (totals["net_10"] + net_10).quantize(CENT)
            totals["net_20"] = (totals["net_20"] + net_20).quantize(CENT)
            totals["gross_total"] = (totals["gross_total"] + gross_total).quantize(CENT)
            totals["akonto_total"] = (totals["akonto_total"] + akonto_total).quantize(CENT)
            totals["saldo_total"] = (totals["saldo_total"] + saldo).quantize(CENT)

        return {
            "rows": rows,
            "totals": totals,
        }

    def _legacy_plausibility_checks(
        self,
        *,
        bk_distribution: dict[str, object],
        water: dict[str, object],
        electricity_common: dict[str, object],
        hot_water: dict[str, object],
        heating: dict[str, object],
        annual_statement: dict[str, object],
    ) -> dict[str, Decimal]:
        sum_10_pool = (
            quantize_cent(bk_distribution.get("cost_pool"))
            + quantize_cent(water.get("cost_pool"))
            + quantize_cent(electricity_common.get("cost_pool"))
            + quantize_cent(hot_water.get("cost_pool"))
        ).quantize(CENT)
        sum_10_units = quantize_cent(annual_statement.get("totals", {}).get("net_10"))
        sum_20_pool = quantize_cent(heating.get("cost_pool"))
        sum_20_units = quantize_cent(annual_statement.get("totals", {}).get("net_20"))
        return {
            "sum_10_pool": sum_10_pool,
            "sum_10_units": sum_10_units,
            "delta_10": (sum_10_pool - sum_10_units).quantize(CENT),
            "sum_20_pool": sum_20_pool,
            "sum_20_units": sum_20_units,
            "delta_20": (sum_20_pool - sum_20_units).quantize(CENT),
        }

    def _prepayment_map_by_unit(self) -> dict[int, dict[str, Decimal]]:
        if self.property is None:
            return {}
        prepayments: dict[int, dict[str, Decimal]] = {}
        query = (
            Buchung.objects.filter(
                Q(mietervertrag__unit__property=self.property) | Q(einheit__property=self.property),
                typ=Buchung.Typ.IST,
                is_settlement_adjustment=False,
                datum__gte=self.period_start,
                datum__lte=self.period_end,
            )
            .select_related("mietervertrag", "mietervertrag__unit", "einheit")
            .order_by("datum", "id")
        )

        for booking in query:
            unit_id = None
            if booking.mietervertrag and booking.mietervertrag.unit_id:
                unit_id = booking.mietervertrag.unit_id
            elif booking.einheit_id:
                unit_id = booking.einheit_id
            if unit_id is None:
                continue

            netto = quantize_cent(booking.netto)
            if netto <= ZERO:
                continue
            prepayments.setdefault(unit_id, {"bk": ZERO, "hk": ZERO})

            if booking.kategorie == Buchung.Kategorie.BK:
                prepayments[unit_id]["bk"] = (prepayments[unit_id]["bk"] + netto).quantize(CENT)
                continue
            if booking.kategorie == Buchung.Kategorie.HK:
                prepayments[unit_id]["hk"] = (prepayments[unit_id]["hk"] + netto).quantize(CENT)
                continue
            if booking.kategorie != Buchung.Kategorie.ZAHLUNG:
                continue

            lease = booking.mietervertrag
            if lease is None:
                continue
            profile = self._soll_profile_for_month(lease=lease, booking_date=booking.datum)
            bucket_data = profile.get(self._rate_bucket_key(booking.ust_prozent))
            if not bucket_data:
                continue
            bucket_total = quantize_cent(bucket_data["total"])
            if bucket_total <= ZERO:
                continue

            bk_share = (
                netto * bucket_data["bk"] / bucket_total
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            hk_share = (
                netto * bucket_data["hk"] / bucket_total
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            prepayments[unit_id]["bk"] = (prepayments[unit_id]["bk"] + bk_share).quantize(CENT)
            prepayments[unit_id]["hk"] = (prepayments[unit_id]["hk"] + hk_share).quantize(CENT)

        return prepayments

    def _meter_consumption_total(
        self,
        *,
        meter_type: str,
        unit_id: int | None,
    ) -> Decimal:
        meters = Meter.objects.filter(property=self.property, meter_type=meter_type)
        if unit_id is None:
            meters = meters.filter(unit__isnull=True)
        else:
            meters = meters.filter(unit_id=unit_id)
        meters = meters.prefetch_related(
            Prefetch("readings", queryset=MeterReading.objects.order_by("date", "id"))
        )
        total = Decimal("0.000")
        for meter in meters:
            yearly_rows = Meter._calculate_yearly_consumption_for_meter(
                meter,
                list(meter.readings.all()),
            )
            year_row = next(
                (row for row in yearly_rows if row["calc_year"] == self.year),
                None,
            )
            if year_row is None or year_row.get("consumption") is None:
                continue
            total += quantize_cent3(year_row["consumption"])
        return total.quantize(CENT3, rounding=ROUND_HALF_UP)

    def _meter_consumption_map(self, *, meter_type: str) -> dict[int, Decimal]:
        meters = (
            Meter.objects.filter(property=self.property, meter_type=meter_type, unit__isnull=False)
            .select_related("unit")
            .prefetch_related(
                Prefetch("readings", queryset=MeterReading.objects.order_by("date", "id"))
            )
        )
        totals: dict[int, Decimal] = {}
        for meter in meters:
            yearly_rows = Meter._calculate_yearly_consumption_for_meter(
                meter,
                list(meter.readings.all()),
            )
            year_row = next(
                (row for row in yearly_rows if row["calc_year"] == self.year),
                None,
            )
            if year_row is None or year_row.get("consumption") is None:
                continue
            totals.setdefault(meter.unit_id, Decimal("0.000"))
            totals[meter.unit_id] += quantize_cent3(year_row["consumption"])
        return {unit_id: quantize_cent3(value) for unit_id, value in totals.items()}

    def _allocate_amount_by_weight(
        self,
        *,
        total_amount: Decimal,
        rows: list[dict[str, object]],
        weight_key: str,
        amount_key: str,
    ) -> tuple[list[dict[str, object]], Decimal]:
        working_rows: list[dict[str, object]] = []
        total_weight = sum(
            (
                Decimal(row.get(weight_key) or Decimal("0.000"))
                for row in rows
                if Decimal(row.get(weight_key) or Decimal("0.000")) > Decimal("0.000")
            ),
            Decimal("0.000"),
        )
        total_amount_q = quantize_cent(total_amount)
        if total_weight <= Decimal("0.000"):
            for row in rows:
                copied = dict(row)
                copied[amount_key] = ZERO
                working_rows.append(copied)
            return working_rows, ZERO

        for row in rows:
            copied = dict(row)
            weight = Decimal(row.get(weight_key) or Decimal("0.000"))
            if weight <= Decimal("0.000"):
                raw_amount = ZERO
            else:
                raw_amount = (
                    total_amount_q * weight / total_weight
                ).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
            copied["__raw_amount"] = raw_amount
            copied[amount_key] = quantize_cent(raw_amount)
            working_rows.append(copied)

        distributed_sum = sum(
            (quantize_cent(row[amount_key]) for row in working_rows),
            ZERO,
        ).quantize(CENT)
        diff = (total_amount_q - distributed_sum).quantize(CENT)
        if diff != ZERO and working_rows:
            step = CENT if diff > ZERO else -CENT
            cents_to_allocate = int((diff.copy_abs() / CENT).to_integral_value())
            if diff > ZERO:
                order = sorted(
                    range(len(working_rows)),
                    key=lambda index: working_rows[index]["__raw_amount"] - working_rows[index][amount_key],
                    reverse=True,
                )
            else:
                order = sorted(
                    range(len(working_rows)),
                    key=lambda index: working_rows[index]["__raw_amount"] - working_rows[index][amount_key],
                )
            if not order:
                order = list(range(len(working_rows)))
            for offset in range(cents_to_allocate):
                row_index = order[offset % len(order)]
                working_rows[row_index][amount_key] = (
                    quantize_cent(working_rows[row_index][amount_key]) + step
                ).quantize(CENT)

        for row in working_rows:
            row.pop("__raw_amount", None)
            row[amount_key] = quantize_cent(row[amount_key])
        distributed_sum = sum(
            (quantize_cent(row[amount_key]) for row in working_rows),
            ZERO,
        ).quantize(CENT)
        return working_rows, distributed_sum

    def _serialize_bk_distribution(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "bk_anteil": self._money_str(row.get("bk_anteil")),
                    "anteil_prozent": self._money_str(row.get("anteil_prozent")),
                    "anteil_euro": self._money_str(row.get("anteil_euro")),
                }
                for row in data.get("rows", [])
            ],
            "cost_pool": self._money_str(data.get("cost_pool")),
            "distributed_sum": self._money_str(data.get("distributed_sum")),
            "rounding_diff": self._money_str(data.get("rounding_diff")),
        }

    def _serialize_water_allocation(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": self._money_str(row.get("anteil_prozent")),
                    "measured_m3": self._qty3_str(row.get("measured_m3")),
                    "schwund_anteil_m3": self._qty3_str(row.get("schwund_anteil_m3")),
                    "abrechnungsmenge_m3": self._qty3_str(row.get("abrechnungsmenge_m3")),
                    "cost_share": self._money_str(row.get("cost_share")),
                }
                for row in data.get("rows", [])
            ],
            "cost_pool": self._money_str(data.get("cost_pool")),
            "house_consumption_m3": self._qty3_str(data.get("house_consumption_m3")),
            "measured_units_m3": self._qty3_str(data.get("measured_units_m3")),
            "schwund_m3": self._qty3_str(data.get("schwund_m3")),
            "price_per_m3": self._ratio6_str(data.get("price_per_m3")),
            "distributed_sum": self._money_str(data.get("distributed_sum")),
            "rounding_diff": self._money_str(data.get("rounding_diff")),
        }

    def _serialize_electricity_allocation(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": self._money_str(row.get("anteil_prozent")),
                    "cost_share": self._money_str(row.get("cost_share")),
                }
                for row in data.get("rows", [])
            ],
            "stromkosten_total": self._money_str(data.get("stromkosten_total")),
            "hausstrom_kwh": self._qty3_str(data.get("hausstrom_kwh")),
            "wp_strom_kwh": self._qty3_str(data.get("wp_strom_kwh")),
            "allgemeinstrom_kwh": self._qty3_str(data.get("allgemeinstrom_kwh")),
            "price_per_kwh": self._ratio6_str(data.get("price_per_kwh")),
            "cost_pool": self._money_str(data.get("cost_pool")),
            "distributed_sum": self._money_str(data.get("distributed_sum")),
            "rounding_diff": self._money_str(data.get("rounding_diff")),
        }

    def _serialize_wp_metrics(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "input_kwh": self._qty3_str(data.get("input_kwh")),
            "output_heat_kwh": self._qty3_str(data.get("output_heat_kwh")),
            "output_ww_kwh": self._qty3_str(data.get("output_ww_kwh")),
            "ratio_heat": self._ratio6_str(data.get("ratio_heat")),
            "ratio_ww": self._ratio6_str(data.get("ratio_ww")),
        }

    def _serialize_hotwater_allocation(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "consumption_m3": self._qty3_str(row.get("consumption_m3")),
                    "cost_share": self._money_str(row.get("cost_share")),
                }
                for row in data.get("rows", [])
            ],
            "cost_pool": self._money_str(data.get("cost_pool")),
            "house_consumption_m3": self._qty3_str(data.get("house_consumption_m3")),
            "price_per_m3": self._ratio6_str(data.get("price_per_m3")),
            "distributed_sum": self._money_str(data.get("distributed_sum")),
            "rounding_diff": self._money_str(data.get("rounding_diff")),
        }

    def _serialize_heating_allocation(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "anteil_prozent": self._money_str(row.get("anteil_prozent")),
                    "consumption_kwh": self._qty3_str(row.get("consumption_kwh")),
                    "fixed_cost_share": self._money_str(row.get("fixed_cost_share")),
                    "variable_cost_share": self._money_str(row.get("variable_cost_share")),
                    "cost_share": self._money_str(row.get("cost_share")),
                }
                for row in data.get("rows", [])
            ],
            "cost_pool": self._money_str(data.get("cost_pool")),
            "fixed_pool": self._money_str(data.get("fixed_pool")),
            "variable_pool": self._money_str(data.get("variable_pool")),
            "fixed_percent": self._money_str(data.get("fixed_percent")),
            "total_consumption_kwh": self._qty3_str(data.get("total_consumption_kwh")),
            "distributed_sum": self._money_str(data.get("distributed_sum")),
            "rounding_diff": self._money_str(data.get("rounding_diff")),
        }

    def _serialize_annual_statement(self, data: dict[str, object]) -> dict[str, object]:
        return {
            "rows": [
                {
                    "unit_id": row.get("unit_id"),
                    "label": row.get("label", ""),
                    "costs_net_10": self._money_str(row.get("costs_net_10")),
                    "costs_net_20": self._money_str(row.get("costs_net_20")),
                    "gross_10": self._money_str(row.get("gross_10")),
                    "gross_20": self._money_str(row.get("gross_20")),
                    "gross_total": self._money_str(row.get("gross_total")),
                    "akonto_bk": self._money_str(row.get("akonto_bk")),
                    "akonto_hk": self._money_str(row.get("akonto_hk")),
                    "akonto_total": self._money_str(row.get("akonto_total")),
                    "saldo": self._money_str(row.get("saldo")),
                }
                for row in data.get("rows", [])
            ],
            "totals": {
                "net_10": self._money_str(data.get("totals", {}).get("net_10")),
                "net_20": self._money_str(data.get("totals", {}).get("net_20")),
                "gross_total": self._money_str(data.get("totals", {}).get("gross_total")),
                "akonto_total": self._money_str(data.get("totals", {}).get("akonto_total")),
                "saldo_total": self._money_str(data.get("totals", {}).get("saldo_total")),
            },
        }

    @staticmethod
    def _empty_bk_allg_data() -> dict[str, object]:
        return {
            "rows": [],
            "original_sum": ZERO,
            "distributed_sum": ZERO,
            "rounding_diff": ZERO,
            "has_source_costs": False,
            "has_distribution_rows": False,
            "strategy": "operating_cost_share",
            "strategy_label": "BK-Anteil",
        }

    def _bk_allgemein_data_raw(self) -> dict[str, object]:
        if self.property is None:
            return self._empty_bk_allg_data()

        original_sum = (
            BetriebskostenBeleg.objects.filter(
                liegenschaft=self.property,
                datum__gte=self.period_start,
                datum__lte=self.period_end,
                bk_art=BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN,
            ).aggregate(
                total=Coalesce(
                    Sum(
                        "netto",
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(ZERO),
                )
            )["total"]
            or ZERO
        )
        original_sum = quantize_cent(original_sum)
        if original_sum <= ZERO:
            return self._empty_bk_allg_data()

        rows = self.distribution_strategy.build_rows(
            property_obj=self.property,
            period_start=self.period_start,
            period_end=self.period_end,
        )
        if not rows:
            return {
                "rows": [],
                "original_sum": original_sum,
                "distributed_sum": ZERO,
                "rounding_diff": original_sum,
                "has_source_costs": True,
                "has_distribution_rows": False,
                "strategy": self.distribution_strategy.key,
                "strategy_label": self.distribution_strategy.label,
            }

        distributed_rows, distributed_sum = self._distribute_with_rounding_correction(
            total_amount=original_sum,
            rows=rows,
        )
        rounding_diff = quantize_cent(original_sum - distributed_sum)

        return {
            "rows": distributed_rows,
            "original_sum": original_sum,
            "distributed_sum": distributed_sum,
            "rounding_diff": rounding_diff,
            "has_source_costs": original_sum > ZERO,
            "has_distribution_rows": bool(distributed_rows),
            "strategy": self.distribution_strategy.key,
            "strategy_label": self.distribution_strategy.label,
        }

    def _distribute_with_rounding_correction(
        self,
        *,
        total_amount: Decimal,
        rows: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], Decimal]:
        working_rows: list[dict[str, object]] = []
        total_weight = sum((quantize_cent(row.get("weight")) for row in rows), ZERO).quantize(CENT)
        if total_weight <= ZERO:
            for row in rows:
                copied = dict(row)
                copied["cost_share"] = ZERO
                working_rows.append(copied)
            return working_rows, ZERO

        for row in rows:
            copied = dict(row)
            weight = quantize_cent(row.get("weight"))
            raw_share = (total_amount * weight / total_weight).quantize(
                Decimal("0.0000001"),
                rounding=ROUND_HALF_UP,
            )
            rounded_share = raw_share.quantize(CENT, rounding=ROUND_HALF_UP)
            copied["raw_share"] = raw_share
            copied["cost_share"] = rounded_share
            working_rows.append(copied)

        distributed_sum = sum(
            (quantize_cent(row["cost_share"]) for row in working_rows),
            ZERO,
        ).quantize(CENT)
        diff = quantize_cent(total_amount - distributed_sum)

        if diff != ZERO and working_rows:
            step = CENT if diff > ZERO else -CENT
            cents_to_allocate = int((diff.copy_abs() / CENT).to_integral_value())
            if diff > ZERO:
                order = sorted(
                    range(len(working_rows)),
                    key=lambda index: working_rows[index]["raw_share"] - working_rows[index]["cost_share"],
                    reverse=True,
                )
            else:
                order = sorted(
                    range(len(working_rows)),
                    key=lambda index: working_rows[index]["raw_share"] - working_rows[index]["cost_share"],
                )

            if not order:
                order = list(range(len(working_rows)))

            for offset in range(cents_to_allocate):
                row_index = order[offset % len(order)]
                current_share = quantize_cent(working_rows[row_index]["cost_share"])
                working_rows[row_index]["cost_share"] = (current_share + step).quantize(CENT)

        for row in working_rows:
            row.pop("raw_share", None)
            row["cost_share"] = quantize_cent(row["cost_share"])

        distributed_sum = sum(
            (quantize_cent(row["cost_share"]) for row in working_rows),
            ZERO,
        ).quantize(CENT)
        return working_rows, distributed_sum

    @staticmethod
    def unit_tenant_label(unit: Unit) -> str:
        leases = list(getattr(unit, "leases_for_year", []) or [])
        if not leases:
            return ""

        active_lease = next(
            (lease for lease in leases if lease.status == LeaseAgreement.Status.AKTIV),
            None,
        )
        selected_lease = active_lease or leases[0]
        tenant_names = [
            f"{tenant.first_name} {tenant.last_name}".strip()
            for tenant in selected_lease.tenants.all()
        ]
        tenant_names = [name for name in tenant_names if name]
        return ", ".join(tenant_names)

    def _serialize_bk_allg_data(self, data: dict[str, object]) -> dict[str, object]:
        rows = [
            {
                "unit_id": row.get("unit_id"),
                "label": row.get("label", ""),
                "bk_anteil": self._money_str(quantize_cent(row.get("bk_anteil"))),
                "cost_share": self._money_str(quantize_cent(row.get("cost_share"))),
            }
            for row in data.get("rows", [])
        ]

        return {
            "rows": rows,
            "original_sum": self._money_str(quantize_cent(data.get("original_sum"))),
            "distributed_sum": self._money_str(quantize_cent(data.get("distributed_sum"))),
            "rounding_diff": self._money_str(quantize_cent(data.get("rounding_diff"))),
            "has_source_costs": bool(data.get("has_source_costs")),
            "has_distribution_rows": bool(data.get("has_distribution_rows")),
            "strategy": data.get("strategy", "operating_cost_share"),
            "strategy_label": data.get("strategy_label", "BK-Anteil"),
        }

    @staticmethod
    def _money_str(value: Decimal | str | int | None) -> str:
        return str(quantize_cent(value))

    @staticmethod
    def _qty3_str(value: Decimal | str | int | None) -> str:
        return str(quantize_cent3(value))

    @staticmethod
    def _ratio6_str(value: Decimal | str | int | None) -> str:
        return str(
            Decimal(value or Decimal("0.000000")).quantize(
                Decimal("0.000000"),
                rounding=ROUND_HALF_UP,
            )
        )

    def _empty_tenant_statement(self, unit: Unit | None) -> dict[str, object]:
        return {
            "meta": {
                "property_id": str(self.property.pk) if self.property else "",
                "property_name": self.property.name if self.property else "",
                "year": self.year,
                "period_start": self.period_start.isoformat(),
                "period_end": self.period_end.isoformat(),
            },
            "unit": {
                "id": unit.pk if unit else None,
                "name": unit.name if unit else "",
                "door_number": unit.door_number if unit else "",
                "tenant_names": [],
                "lease_id": None,
            },
            "lines": [
                {
                    "type": "cost",
                    "category": "bk_allgemein",
                    "label": "BK allgemein",
                    "amount": "0.00",
                },
                {
                    "type": "prepayment",
                    "category": "bk",
                    "label": "Vorauszahlung Betriebskosten",
                    "amount": "0.00",
                },
                {
                    "type": "prepayment",
                    "category": "hk",
                    "label": "Vorauszahlung Heizung",
                    "amount": "0.00",
                },
            ],
            "totals": {
                "costs_net": "0.00",
                "costs_gross": "0.00",
                "prepayments": "0.00",
                "balance": "0.00",
            },
        }
