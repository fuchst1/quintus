from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Case, Count, IntegerField, Max, Q, Value, When
from django.utils import timezone
from django.utils.text import slugify

from webapp.models import (
    Abrechnungslauf,
    Abrechnungsschreiben,
    LeaseAgreement,
)
from webapp.services.annual_statement_pdf_service import (
    AnnualStatementPdfGenerationError,
    AnnualStatementPdfService,
)
from webapp.services.annual_statement_storage_service import AnnualStatementStorageService
from webapp.services.operating_cost_service import OperatingCostService


class AnnualStatementRunService:
    def __init__(self, *, run: Abrechnungslauf):
        self.run = run
        self.property = run.liegenschaft
        self.year = run.jahr
        self.period_start = date(self.year, 1, 1)
        self.period_end = date(self.year, 12, 31)
        self._annual_rows_by_unit_cache: dict[int, dict[str, object]] | None = None
        self._report_data_cache: dict[str, object] | None = None
        self._report_allocations_cache: dict[str, object] | None = None

    @classmethod
    def next_letter_number_suggestion(cls) -> int:
        highest_assigned = (
            Abrechnungsschreiben.objects.aggregate(max_number=Max("laufende_nummer")).get("max_number")
            or 0
        )
        highest_reserved = 0
        reserved_runs = (
            Abrechnungslauf.objects.filter(brief_nummer_start__isnull=False)
            .annotate(letter_count=Count("schreiben"))
            .only("brief_nummer_start")
        )
        for run in reserved_runs:
            start_number = int(run.brief_nummer_start or 0)
            if start_number <= 0:
                continue
            count = int(run.letter_count or 0)
            reserved_end = start_number + max(count, 1) - 1
            if reserved_end > highest_reserved:
                highest_reserved = reserved_end
        return max(highest_assigned, highest_reserved) + 1

    @staticmethod
    def _to_money_decimal(value: object) -> Decimal:
        if value in (None, ""):
            return Decimal("0.00")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")
        return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _format_money_at(value: object) -> str:
        amount = AnnualStatementRunService._to_money_decimal(value)
        return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _format_document_number(*, sequence_number: int | None, year: int) -> str:
        if not sequence_number:
            return "—"
        return f"{int(sequence_number):02d}/{int(year)}"

    def _report_data(self) -> dict[str, object]:
        if self._report_data_cache is not None:
            return self._report_data_cache
        self._report_data_cache = OperatingCostService(property=self.property, year=self.year).get_report_data()
        return self._report_data_cache

    def _report_allocations(self) -> dict[str, object]:
        if self._report_allocations_cache is not None:
            return self._report_allocations_cache
        report = self._report_data()
        self._report_allocations_cache = report.get("allocations", {})
        return self._report_allocations_cache

    def _annual_rows_by_unit(self) -> dict[int, dict[str, object]]:
        if self._annual_rows_by_unit_cache is not None:
            return self._annual_rows_by_unit_cache

        rows = self._report_allocations().get("annual_statement", {}).get("rows", [])
        mapped: dict[int, dict[str, object]] = {}
        for row in rows:
            unit_id = row.get("unit_id")
            if not unit_id:
                continue
            mapped[int(unit_id)] = row
        self._annual_rows_by_unit_cache = mapped
        return mapped

    def _allocation_value_by_unit(
        self,
        *,
        allocation_key: str,
        unit_id: int,
        value_key: str = "cost_share",
    ) -> Decimal:
        rows = self._report_allocations().get(allocation_key, {}).get("rows", [])
        for row in rows:
            if int(row.get("unit_id") or 0) == unit_id:
                return self._to_money_decimal(row.get(value_key))
        return Decimal("0.00")

    @staticmethod
    def _date_str(value: date) -> str:
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _lease_tenants(letter: Abrechnungsschreiben) -> list:
        return list(letter.mietervertrag.tenants.all())

    def _greeting(self, *, letter: Abrechnungsschreiben) -> str:
        tenants = self._lease_tenants(letter)
        if len(tenants) != 1:
            return "Sehr geehrte Damen und Herren,"
        tenant = tenants[0]
        last_name = (tenant.last_name or "").strip()
        if tenant.salutation == tenant.Salutation.FRAU and last_name:
            return f"Sehr geehrte Frau {last_name},"
        if tenant.salutation == tenant.Salutation.HERR and last_name:
            return f"Sehr geehrter Herr {last_name},"
        return "Sehr geehrte Damen und Herren,"

    def _unit_label(self, *, letter: Abrechnungsschreiben) -> str:
        street = (self.property.street_address or "").strip()
        door = (letter.einheit.door_number or "").strip()
        if street and door:
            return f"{street}, Top {door}"
        if street:
            return street
        if door:
            return f"Top {door}"
        return (letter.einheit.name or "Einheit").strip() or "Einheit"

    def _expense_summary_rows(self) -> tuple[list[dict[str, object]], Decimal]:
        expenses = self._report_data().get("financials", {}).get("expenses", {})
        rows = [
            {
                "label": "Betriebskosten",
                "amount": self._to_money_decimal(expenses.get("betriebskosten")),
            },
            {
                "label": "Wasser",
                "amount": self._to_money_decimal(expenses.get("wasser")),
            },
            {
                "label": "Strom",
                "amount": self._to_money_decimal(expenses.get("strom")),
            },
        ]
        total = sum((row["amount"] for row in rows), Decimal("0.00")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        for row in rows:
            row["amount_display"] = self._format_money_at(row["amount"])
        return rows, total

    def _meter_summary_rows(self, *, letter: Abrechnungsschreiben) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        meter_groups = self._report_data().get("meter", {}).get("groups", [])

        for group in meter_groups:
            group_unit_id_raw = group.get("unit_id")
            include_group = True
            if group_unit_id_raw is not None:
                try:
                    group_unit_id = int(group_unit_id_raw)
                except (TypeError, ValueError):
                    group_unit_id = None
                if group_unit_id not in (0, letter.einheit_id):
                    include_group = False
            if not include_group:
                continue

            group_label = str(group.get("label") or "Allgemein")
            for meter_row in group.get("rows", []):
                consumption_display = str(meter_row.get("consumption_display") or "—").strip()
                if consumption_display in {"", "—"}:
                    continue
                unit_label = str(meter_row.get("unit_label") or "").strip()
                rows.append(
                    {
                        "group_label": group_label,
                        "meter_type": str(meter_row.get("meter_type") or "—"),
                        "meter_number": str(meter_row.get("meter_number") or "—"),
                        "consumption": consumption_display,
                        "unit_label": unit_label,
                        "start_value": str(meter_row.get("start_value_display") or "—"),
                        "end_value": str(meter_row.get("end_value_display") or "—"),
                    }
                )

        rows.sort(
            key=lambda item: (
                0 if "(Allgemein)" in item["group_label"] else 1,
                item["group_label"].casefold(),
                item["meter_type"].casefold(),
                item["meter_number"].casefold(),
            )
        )
        return rows

    def _base_payload(self, *, letter: Abrechnungsschreiben) -> dict[str, object]:
        today = timezone.localdate()
        manager = self.property.manager
        sender_name = self.property.name
        sender_contact = ""
        sender_email = ""
        sender_phone = ""
        sender_website = ""
        sender_account = ""
        if manager is not None:
            sender_name = (manager.company_name or "").strip() or sender_name
            sender_contact = (manager.contact_person or "").strip()
            sender_email = (manager.email or "").strip()
            sender_phone = (manager.phone or "").strip()
            sender_website = (manager.website or "").strip()
            if sender_website:
                sender_website = (
                    sender_website.removeprefix("https://")
                    .removeprefix("http://")
                    .rstrip("/")
                )
            sender_account = (manager.account_number or "").strip()

        zip_city = " ".join(
            part for part in [(self.property.zip_code or "").strip(), (self.property.city or "").strip()] if part
        )
        tenant_names = self._tenant_names(letter)

        return {
            "property_name": self.property.name,
            "year": self.year,
            "period_text": f"01.01.{self.year} bis 31.12.{self.year}",
            "issue_date": self._date_str(today),
            "subject": f"Betriebskostenabrechnung {self.year}",
            "unit_label": self._unit_label(letter=letter),
            "tenant_names": tenant_names,
            "greeting_text": self._greeting(letter=letter),
            "intro_text": (
                f"für die Einheit {self._unit_label(letter=letter)} erhalten Sie hiermit die "
                f"Betriebskostenabrechnung für den Zeitraum 01.01.{self.year} bis 31.12.{self.year}."
            ),
            "sender_name": sender_name,
            "sender_contact": sender_contact,
            "sender_email": sender_email,
            "sender_phone": sender_phone,
            "sender_website": sender_website,
            "sender_account": sender_account,
            "sender_street": (self.property.street_address or "").strip(),
            "sender_zip_city": zip_city,
            "recipient_name": tenant_names,
            "recipient_street": (self.property.street_address or "").strip(),
            "recipient_zip_city": zip_city,
            "closing_text": "Mit freundlichen Grüßen",
            "has_sender_account": bool(sender_account),
            "payment_due_date": self._date_str(today + timedelta(days=14)),
            "free_text": (self.run.brief_freitext or "").strip(),
        }

    def _sequence_numbers_for_letters(
        self,
        *,
        letters: list[Abrechnungsschreiben],
    ) -> dict[int, int | None]:
        start_number = int(self.run.brief_nummer_start or 0)
        if start_number <= 0:
            return {letter.id: None for letter in letters}
        return {
            letter.id: start_number + index
            for index, letter in enumerate(letters)
        }

    def _lease_for_unit(self, *, unit_id: int) -> LeaseAgreement | None:
        leases = (
            LeaseAgreement.objects.filter(unit_id=unit_id, entry_date__lte=self.period_end)
            .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=self.period_start))
            .annotate(
                status_priority=Case(
                    When(status=LeaseAgreement.Status.AKTIV, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .select_related("unit")
            .prefetch_related("tenants")
            .order_by("status_priority", "-entry_date", "-id")
        )
        return leases.first()

    @staticmethod
    def ensure_run(*, property_obj, year: int) -> Abrechnungslauf:
        run, _created = Abrechnungslauf.objects.get_or_create(
            liegenschaft=property_obj,
            jahr=year,
        )
        return run

    def ensure_letters(self) -> list[Abrechnungsschreiben]:
        rows_by_unit = self._annual_rows_by_unit()
        target_letters: list[Abrechnungsschreiben] = []
        active_letter_ids: list[int] = []

        for unit_id in sorted(rows_by_unit.keys()):
            lease = self._lease_for_unit(unit_id=unit_id)
            if lease is None:
                continue
            letter, _created = Abrechnungsschreiben.objects.get_or_create(
                lauf=self.run,
                mietervertrag=lease,
                defaults={"einheit": lease.unit},
            )
            if letter.einheit_id != lease.unit_id:
                letter.einheit = lease.unit
                letter.save(update_fields=["einheit", "updated_at"])
            active_letter_ids.append(letter.id)
            target_letters.append(letter)

        stale_letters = self.run.schreiben.exclude(id__in=active_letter_ids).select_related("pdf_datei")
        for stale in stale_letters:
            AnnualStatementStorageService._archive_existing_pdf(stale)
        stale_letters.delete()

        return target_letters

    def payload_for_letter(
        self,
        *,
        letter: Abrechnungsschreiben,
        sequence_number: int | None = None,
    ) -> dict[str, object]:
        payload = self._base_payload(letter=letter)
        if sequence_number is None:
            sequence_number = letter.laufende_nummer
        payload["document_number"] = sequence_number
        payload["document_number_display"] = self._format_document_number(
            sequence_number=sequence_number,
            year=self.year,
        )
        row = self._annual_rows_by_unit().get(letter.einheit_id)
        expense_summary_rows, expense_summary_total = self._expense_summary_rows()
        meter_summary_rows = self._meter_summary_rows(letter=letter)

        if row is None:
            payload.update(
                {
                    "netto_10": Decimal("0.00"),
                    "netto_20": Decimal("0.00"),
                    "netto_total": Decimal("0.00"),
                    "ust_10": Decimal("0.00"),
                    "ust_20": Decimal("0.00"),
                    "ust_total": Decimal("0.00"),
                    "gross_10": Decimal("0.00"),
                    "gross_20": Decimal("0.00"),
                    "gross_total": Decimal("0.00"),
                    "akonto_bk_brutto": Decimal("0.00"),
                    "akonto_hk_brutto": Decimal("0.00"),
                    "akonto_total_brutto": Decimal("0.00"),
                    "saldo_brutto_10": Decimal("0.00"),
                    "saldo_brutto_20": Decimal("0.00"),
                    "saldo_brutto": Decimal("0.00"),
                    "saldo_text": "Keine Werte vorhanden.",
                    "payment_type": "ausgeglichen",
                    "payment_amount": Decimal("0.00"),
                    "payment_amount_display": self._format_money_at(Decimal("0.00")),
                    "payment_hint": "Für diesen Brief liegen aktuell keine Abrechnungswerte vor.",
                    "statement_rows": [],
                    "meter_summary_rows": meter_summary_rows,
                    "expense_summary_rows": expense_summary_rows,
                    "expense_summary_total": expense_summary_total,
                    "expense_summary_total_display": self._format_money_at(expense_summary_total),
                }
            )
            return payload

        netto_10 = self._to_money_decimal(row.get("costs_net_10"))
        netto_20 = self._to_money_decimal(row.get("costs_net_20"))
        gross_10 = self._to_money_decimal(row.get("gross_10"))
        gross_20 = self._to_money_decimal(row.get("gross_20"))
        gross_total = self._to_money_decimal(row.get("gross_total"))
        ust_10 = (gross_10 - netto_10).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ust_20 = (gross_20 - netto_20).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        netto_total = (netto_10 + netto_20).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ust_total = (ust_10 + ust_20).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        akonto_bk_net = self._to_money_decimal(row.get("akonto_bk"))
        akonto_hk_net = self._to_money_decimal(row.get("akonto_hk"))
        akonto_bk_brutto = (akonto_bk_net * Decimal("1.10")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        akonto_hk_brutto = (akonto_hk_net * Decimal("1.20")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        akonto_total_brutto = (akonto_bk_brutto + akonto_hk_brutto).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        saldo_brutto = (akonto_total_brutto - gross_total).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        saldo_brutto_10 = (akonto_bk_brutto - gross_10).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        saldo_brutto_20 = (akonto_hk_brutto - gross_20).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        component_bk_allg = self._allocation_value_by_unit(
            allocation_key="bk_distribution",
            unit_id=letter.einheit_id,
            value_key="anteil_euro",
        )
        component_wasser = self._allocation_value_by_unit(
            allocation_key="water",
            unit_id=letter.einheit_id,
        )
        component_allg_strom = self._allocation_value_by_unit(
            allocation_key="electricity_common",
            unit_id=letter.einheit_id,
        )
        component_warmwasser = self._allocation_value_by_unit(
            allocation_key="hot_water",
            unit_id=letter.einheit_id,
        )
        component_heizung = self._allocation_value_by_unit(
            allocation_key="heating",
            unit_id=letter.einheit_id,
        )

        statement_rows = [
            {
                "position": "BK allgemein (10%)",
                "netto": component_bk_allg,
                "ust": (component_bk_allg * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "brutto": (component_bk_allg * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "akonto_brutto": None,
                "saldo_brutto": None,
                "is_total": False,
            },
            {
                "position": "Wasser (10%)",
                "netto": component_wasser,
                "ust": (component_wasser * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "brutto": (component_wasser * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "akonto_brutto": None,
                "saldo_brutto": None,
                "is_total": False,
            },
            {
                "position": "Allgemeinstrom (10%)",
                "netto": component_allg_strom,
                "ust": (component_allg_strom * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "brutto": (component_allg_strom * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "akonto_brutto": None,
                "saldo_brutto": None,
                "is_total": False,
            },
            {
                "position": "Warmwasser (10%)",
                "netto": component_warmwasser,
                "ust": (component_warmwasser * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "brutto": (component_warmwasser * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "akonto_brutto": None,
                "saldo_brutto": None,
                "is_total": False,
            },
            {
                "position": "Betriebskosten gesamt (10%)",
                "netto": netto_10,
                "ust": ust_10,
                "brutto": gross_10,
                "akonto_brutto": akonto_bk_brutto,
                "saldo_brutto": saldo_brutto_10,
                "is_total": True,
            },
            {
                "position": "Heizung gesamt (20%)",
                "netto": netto_20,
                "ust": ust_20,
                "brutto": gross_20,
                "akonto_brutto": akonto_hk_brutto,
                "saldo_brutto": saldo_brutto_20,
                "is_total": True,
            },
            {
                "position": "Gesamt",
                "netto": netto_total,
                "ust": ust_total,
                "brutto": gross_total,
                "akonto_brutto": akonto_total_brutto,
                "saldo_brutto": saldo_brutto,
                "is_total": True,
            },
        ]
        for statement_row in statement_rows:
            statement_row["netto_display"] = self._format_money_at(statement_row.get("netto"))
            statement_row["ust_display"] = self._format_money_at(statement_row.get("ust"))
            statement_row["brutto_display"] = self._format_money_at(statement_row.get("brutto"))
            if statement_row.get("akonto_brutto") is not None:
                statement_row["akonto_brutto_display"] = self._format_money_at(
                    statement_row.get("akonto_brutto")
                )
            else:
                statement_row["akonto_brutto_display"] = None
            if statement_row.get("saldo_brutto") is not None:
                statement_row["saldo_brutto_display"] = self._format_money_at(
                    statement_row.get("saldo_brutto")
                )
            else:
                statement_row["saldo_brutto_display"] = None

        payment_type = "ausgeglichen"
        payment_amount = Decimal("0.00")
        payment_hint = "Es ergibt sich kein offener Betrag aus dieser Abrechnung."
        if saldo_brutto > Decimal("0.00"):
            saldo_text = "Guthaben zugunsten des Mieters"
            payment_type = "guthaben"
            payment_amount = saldo_brutto
            payment_hint = (
                f"Wir überweisen das Guthaben innerhalb von 14 Tagen, spätestens bis {payload['payment_due_date']}, "
                "auf Ihr bekanntes Konto."
            )
        elif saldo_brutto < Decimal("0.00"):
            saldo_text = "Nachzahlung offen"
            payment_type = "nachzahlung"
            payment_amount = (saldo_brutto * Decimal("-1.00")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if payload.get("has_sender_account"):
                payment_hint = (
                    f"Bitte überweisen Sie den offenen Betrag innerhalb von 14 Tagen, spätestens bis "
                    f"{payload['payment_due_date']}, auf das unten angeführte Konto."
                )
            else:
                payment_hint = (
                    f"Bitte überweisen Sie den offenen Betrag innerhalb von 14 Tagen, spätestens bis "
                    f"{payload['payment_due_date']}. Die Kontodaten erhalten Sie gesondert."
                )
        else:
            saldo_text = "Abrechnung ausgeglichen"

        payload.update(
            {
                "netto_10": netto_10,
                "netto_20": netto_20,
                "netto_total": netto_total,
                "ust_10": ust_10,
                "ust_20": ust_20,
                "ust_total": ust_total,
                "gross_10": gross_10,
                "gross_20": gross_20,
                "gross_total": gross_total,
                "akonto_bk_brutto": akonto_bk_brutto,
                "akonto_hk_brutto": akonto_hk_brutto,
                "akonto_total_brutto": akonto_total_brutto,
                "saldo_brutto_10": saldo_brutto_10,
                "saldo_brutto_20": saldo_brutto_20,
                "saldo_brutto": saldo_brutto,
                "saldo_text": saldo_text,
                "payment_type": payment_type,
                "payment_amount": payment_amount,
                "payment_amount_display": self._format_money_at(payment_amount),
                "payment_hint": payment_hint,
                "statement_rows": statement_rows,
                "meter_summary_rows": meter_summary_rows,
                "expense_summary_rows": expense_summary_rows,
                "expense_summary_total": expense_summary_total,
                "expense_summary_total_display": self._format_money_at(expense_summary_total),
            }
        )
        return payload

    @staticmethod
    def _tenant_names(letter: Abrechnungsschreiben) -> str:
        tenant_names = [
            f"{tenant.first_name} {tenant.last_name}".strip()
            for tenant in letter.mietervertrag.tenants.all()
        ]
        tenant_names = [name for name in tenant_names if name]
        return ", ".join(tenant_names) if tenant_names else "—"

    def build_letter_filename(
        self,
        *,
        letter: Abrechnungsschreiben,
        sequence_number: int | None = None,
    ) -> str:
        if sequence_number is None:
            sequence_number = letter.laufende_nummer
        unit_source = letter.einheit.door_number or letter.einheit.name or f"einheit-{letter.einheit_id}"
        unit_slug = slugify(unit_source) or f"einheit-{letter.einheit_id}"
        number_prefix = f"{int(sequence_number):06d}_" if sequence_number else ""
        return f"{number_prefix}BK-Abrechnung_{self.year}_{unit_slug}_{letter.mietervertrag_id}.pdf"

    def build_zip_filename(self) -> str:
        property_slug = slugify(self.property.name) or f"liegenschaft-{self.property.pk}"
        return f"BK-Briefe_{property_slug}_{self.year}.zip"

    @transaction.atomic
    def generate_letters_zip(self) -> tuple[bytes, int]:
        if not self.run.brief_nummer_start or int(self.run.brief_nummer_start) <= 0:
            raise RuntimeError(
                "Bitte zuerst die Startnummer für den Brieflauf speichern und bestätigen."
            )
        self.ensure_letters()
        letters = list(
            self.run.schreiben.select_related("mietervertrag", "einheit", "pdf_datei")
            .prefetch_related("mietervertrag__tenants")
            .order_by("einheit__door_number", "einheit__name", "mietervertrag_id")
        )
        sequence_numbers = self._sequence_numbers_for_letters(letters=letters)

        buffer = io.BytesIO()
        generated_count = 0
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for letter in letters:
                sequence_number = sequence_numbers.get(letter.id)
                if sequence_number and letter.laufende_nummer != sequence_number:
                    letter.laufende_nummer = sequence_number
                    letter.save(update_fields=["laufende_nummer", "updated_at"])
                payload = self.payload_for_letter(letter=letter, sequence_number=sequence_number)
                filename = self.build_letter_filename(letter=letter, sequence_number=sequence_number)
                try:
                    pdf_bytes = AnnualStatementPdfService.generate_letter_pdf(payload=payload)
                except AnnualStatementPdfGenerationError as exc:
                    unit_label = payload.get("unit_label", "—")
                    document_number = payload.get("document_number_display", "—")
                    raise RuntimeError(
                        f"PDF-Erstellung fehlgeschlagen für Einheit {unit_label} (Nr. {document_number}): {exc}"
                    ) from exc
                AnnualStatementStorageService.persist_letter_pdf(
                    letter=letter,
                    filename=filename,
                    pdf_bytes=pdf_bytes,
                )
                archive.writestr(filename, pdf_bytes)
                generated_count += 1

        return buffer.getvalue(), generated_count
