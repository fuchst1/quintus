from __future__ import annotations

import io
import zipfile
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.text import slugify

from webapp.models import Buchung, LeaseAgreement, VpiAdjustmentLetter, VpiAdjustmentRun, VpiIndexValue
from webapp.services.operating_cost_service import hmz_tax_percent_for_unit
from webapp.services.reminders import add_months
from webapp.services.vpi_adjustment_pdf_service import (
    VpiAdjustmentPdfGenerationError,
    VpiAdjustmentPdfService,
)
from webapp.services.vpi_adjustment_storage_service import VpiAdjustmentStorageService

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class VpiAdjustmentRunService:
    def __init__(self, *, run: VpiAdjustmentRun):
        self.run = run
        self.index_value = run.index_value
        self.new_index_value = Decimal(run.index_value.index_value).quantize(CENT, rounding=ROUND_HALF_UP)
        self.run_date = run.run_date

    @staticmethod
    def _to_money_decimal(value: object) -> Decimal:
        return Decimal(str(value or "0.00")).quantize(CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _to_ratio_decimal(value: object) -> Decimal:
        return Decimal(str(value or "0.000000")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _date_str(value: date) -> str:
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _month_key(value: date) -> str:
        return value.strftime("%m/%Y")

    @staticmethod
    def _format_money_at(value: object) -> str:
        amount = VpiAdjustmentRunService._to_money_decimal(value)
        return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _month_start(value: date) -> date:
        return date(value.year, value.month, 1)

    @staticmethod
    def _month_end(value: date) -> date:
        last_day = monthrange(value.year, value.month)[1]
        return date(value.year, value.month, last_day)

    @classmethod
    def _month_range(cls, start_month: date, end_month: date) -> list[date]:
        if end_month < start_month:
            return []
        values: list[date] = []
        current = cls._month_start(start_month)
        end = cls._month_start(end_month)
        while current <= end:
            values.append(current)
            current = add_months(current, 1)
        return values

    @staticmethod
    def _gross_from_net(netto: Decimal, tax_percent: Decimal) -> Decimal:
        return (netto * (Decimal("1.00") + (tax_percent / Decimal("100")))).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _net_from_gross(gross: Decimal, tax_percent: Decimal) -> Decimal:
        divisor = Decimal("1.00") + (tax_percent / Decimal("100"))
        if divisor <= Decimal("0.00"):
            return gross.quantize(CENT, rounding=ROUND_HALF_UP)
        return (gross / divisor).quantize(CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _tenant_names(lease: LeaseAgreement) -> str:
        tenant_names = [
            f"{tenant.first_name} {tenant.last_name}".strip()
            for tenant in lease.tenants.all()
        ]
        tenant_names = [name for name in tenant_names if name]
        return ", ".join(tenant_names) if tenant_names else "—"

    @classmethod
    def next_letter_number_suggestion(cls) -> int:
        highest_assigned = (
            VpiAdjustmentLetter.objects.aggregate(max_number=Max("laufende_nummer")).get("max_number")
            or 0
        )
        highest_reserved = 0
        reserved_runs = (
            VpiAdjustmentRun.objects.filter(brief_nummer_start__isnull=False)
            .annotate(letter_count=Count("letters"))
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
    def ensure_run(*, index_value: VpiIndexValue, run_date: date) -> VpiAdjustmentRun:
        run, _created = VpiAdjustmentRun.objects.get_or_create(
            index_value=index_value,
            defaults={"run_date": run_date},
        )
        return run

    def _leasedue_candidates(self):
        return (
            LeaseAgreement.objects.filter(
                status=LeaseAgreement.Status.AKTIV,
                index_type=LeaseAgreement.IndexType.VPI,
                entry_date__lte=self.run_date,
            )
            .select_related("unit", "unit__property", "manager")
            .prefetch_related("tenants")
            .order_by("unit__property__name", "unit__name", "id")
        )

    def _catchup_metrics(
        self,
        *,
        lease: LeaseAgreement,
        effective_date: date,
        new_hmz_net: Decimal,
        tax_percent: Decimal,
    ) -> dict[str, object]:
        start_month = self._month_start(effective_date)
        end_month = self._month_start(self.run_date)
        months = self._month_range(start_month, end_month)
        if not months:
            return {
                "months": 0,
                "net_total": ZERO,
                "gross_total": ZERO,
                "range_start": None,
                "range_end": None,
            }

        new_hmz_gross = self._gross_from_net(new_hmz_net, tax_percent)
        gross_total = ZERO
        positive_months: list[date] = []
        for month_start in months:
            existing_hmz = (
                Buchung.objects.filter(
                    mietervertrag=lease,
                    typ=Buchung.Typ.SOLL,
                    kategorie=Buchung.Kategorie.HMZ,
                    datum=month_start,
                )
                .order_by("-id")
                .first()
            )
            if existing_hmz is None:
                continue
            existing_gross = self._to_money_decimal(existing_hmz.brutto)
            diff = (new_hmz_gross - existing_gross).quantize(CENT, rounding=ROUND_HALF_UP)
            if diff > ZERO:
                positive_months.append(month_start)
                gross_total += diff

        gross_total = gross_total.quantize(CENT, rounding=ROUND_HALF_UP)
        return {
            "months": len(positive_months),
            "net_total": self._net_from_gross(gross_total, tax_percent),
            "gross_total": gross_total,
            "range_start": positive_months[0] if positive_months else None,
            "range_end": positive_months[-1] if positive_months else None,
        }

    def _snapshot_for_lease(self, lease: LeaseAgreement) -> dict[str, object] | None:
        if lease.last_index_adjustment is None:
            return {
                "unit": lease.unit,
                "effective_date": self.run_date,
                "old_index_value": ZERO,
                "new_index_value": self.new_index_value,
                "factor": Decimal("0.000000"),
                "old_hmz_net": self._to_money_decimal(lease.net_rent),
                "new_hmz_net": self._to_money_decimal(lease.net_rent),
                "delta_hmz_net": ZERO,
                "catchup_months": 0,
                "catchup_net_total": ZERO,
                "catchup_tax_percent": hmz_tax_percent_for_unit(lease.unit),
                "catchup_gross_total": ZERO,
                "skip_reason": "Letzte Wertsicherung fehlt.",
            }

        effective_date = add_months(lease.last_index_adjustment, 12)
        if effective_date > self.run_date:
            return None

        old_index_value = self._to_money_decimal(lease.index_base_value)
        old_hmz_net = self._to_money_decimal(lease.net_rent)
        tax_percent = hmz_tax_percent_for_unit(lease.unit)

        if old_index_value <= ZERO:
            return {
                "unit": lease.unit,
                "effective_date": effective_date,
                "old_index_value": old_index_value,
                "new_index_value": self.new_index_value,
                "factor": Decimal("0.000000"),
                "old_hmz_net": old_hmz_net,
                "new_hmz_net": old_hmz_net,
                "delta_hmz_net": ZERO,
                "catchup_months": 0,
                "catchup_net_total": ZERO,
                "catchup_tax_percent": tax_percent,
                "catchup_gross_total": ZERO,
                "skip_reason": "Index-Basiswert fehlt oder ist ungültig.",
            }

        factor = (self.new_index_value / old_index_value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        new_hmz_net = (old_hmz_net * factor).quantize(CENT, rounding=ROUND_HALF_UP)
        delta_hmz_net = (new_hmz_net - old_hmz_net).quantize(CENT, rounding=ROUND_HALF_UP)

        if self.new_index_value <= old_index_value:
            return {
                "unit": lease.unit,
                "effective_date": effective_date,
                "old_index_value": old_index_value,
                "new_index_value": self.new_index_value,
                "factor": factor,
                "old_hmz_net": old_hmz_net,
                "new_hmz_net": new_hmz_net,
                "delta_hmz_net": delta_hmz_net,
                "catchup_months": 0,
                "catchup_net_total": ZERO,
                "catchup_tax_percent": tax_percent,
                "catchup_gross_total": ZERO,
                "skip_reason": "Kein Erhöhungsfaktor (neuer Index nicht höher).",
            }

        catchup = self._catchup_metrics(
            lease=lease,
            effective_date=effective_date,
            new_hmz_net=new_hmz_net,
            tax_percent=tax_percent,
        )
        return {
            "unit": lease.unit,
            "effective_date": effective_date,
            "old_index_value": old_index_value,
            "new_index_value": self.new_index_value,
            "factor": factor,
            "old_hmz_net": old_hmz_net,
            "new_hmz_net": new_hmz_net,
            "delta_hmz_net": delta_hmz_net,
            "catchup_months": catchup["months"],
            "catchup_net_total": catchup["net_total"],
            "catchup_tax_percent": tax_percent,
            "catchup_gross_total": catchup["gross_total"],
            "skip_reason": "",
        }

    def ensure_letters(self) -> list[VpiAdjustmentLetter]:
        active_letter_ids: list[int] = []
        for lease in self._leasedue_candidates():
            snapshot = self._snapshot_for_lease(lease)
            if snapshot is None:
                continue

            letter, _created = VpiAdjustmentLetter.objects.update_or_create(
                run=self.run,
                lease=lease,
                defaults=snapshot,
            )
            active_letter_ids.append(letter.id)

        stale_letters = self.run.letters.exclude(id__in=active_letter_ids).select_related("pdf_datei")
        for stale in stale_letters:
            VpiAdjustmentStorageService._archive_existing_pdf(stale)
        stale_letters.delete()

        return list(self.run.letters.select_related("lease", "unit", "pdf_datei").order_by("unit__name", "lease_id"))

    def apply_readiness(self, *, ensure_letters: bool = False) -> tuple[bool, str]:
        if self.run.status == VpiAdjustmentRun.Status.APPLIED:
            return False, "Dieser VPI-Lauf wurde bereits angewendet."

        if ensure_letters:
            self.ensure_letters()

        if not self.run.brief_nummer_start or int(self.run.brief_nummer_start) <= 0:
            return False, "Bitte zuerst eine gültige Startnummer für den Brieflauf speichern."

        letters = list(self.run.letters.only("id", "skip_reason", "pdf_datei_id"))
        if not letters:
            return False, "Für diesen Lauf sind keine fälligen VPI-Verträge vorhanden."

        actionable_letters = [letter for letter in letters if not (letter.skip_reason or "").strip()]
        missing_pdfs = [letter for letter in actionable_letters if letter.pdf_datei_id is None]
        if missing_pdfs:
            return False, "Bitte zuerst die Briefe erzeugen, bevor die Anpassung angewendet wird."
        return True, ""

    @staticmethod
    def _sequence_numbers_for_letters(*, letters: list[VpiAdjustmentLetter], start_number: int) -> dict[int, int]:
        return {
            letter.id: start_number + index
            for index, letter in enumerate(letters)
        }

    def _greeting(self, *, letter: VpiAdjustmentLetter) -> str:
        tenants = list(letter.lease.tenants.all())
        if len(tenants) != 1:
            return "Sehr geehrte Damen und Herren,"
        tenant = tenants[0]
        last_name = (tenant.last_name or "").strip()
        if tenant.salutation == tenant.Salutation.FRAU and last_name:
            return f"Sehr geehrte Frau {last_name},"
        if tenant.salutation == tenant.Salutation.HERR and last_name:
            return f"Sehr geehrter Herr {last_name},"
        return "Sehr geehrte Damen und Herren,"

    def _catchup_period_text(self, *, letter: VpiAdjustmentLetter) -> str:
        start = self._month_start(letter.effective_date)
        end = self._month_start(self.run_date)
        return f"{self._month_key(start)}-{self._month_key(end)}"

    @staticmethod
    def _format_document_number(*, sequence_number: int | None, year: int) -> str:
        if not sequence_number:
            return "—"
        return f"{int(sequence_number):02d}/{int(year)}"

    def payload_for_letter(
        self,
        *,
        letter: VpiAdjustmentLetter,
        sequence_number: int | None = None,
    ) -> dict[str, object]:
        if sequence_number is None:
            sequence_number = letter.laufende_nummer

        lease = letter.lease
        property_obj = lease.unit.property if lease.unit else None
        manager = lease.manager or (property_obj.manager if property_obj else None)
        issue_date = timezone.localdate()
        sender_name = (manager.company_name if manager else "") or (property_obj.name if property_obj else "Verwaltung")

        old_hmz_gross = self._gross_from_net(self._to_money_decimal(letter.old_hmz_net), letter.catchup_tax_percent)
        new_hmz_gross = self._gross_from_net(self._to_money_decimal(letter.new_hmz_net), letter.catchup_tax_percent)
        delta_hmz_gross = (new_hmz_gross - old_hmz_gross).quantize(CENT, rounding=ROUND_HALF_UP)
        has_catchup = self._to_money_decimal(letter.catchup_gross_total) > ZERO

        return {
            "document_number": sequence_number,
            "document_number_display": self._format_document_number(
                sequence_number=sequence_number,
                year=issue_date.year,
            ),
            "subject": "Wertsicherungsanpassung gemäß VPI 2020",
            "issue_date": self._date_str(issue_date),
            "index_month": self.index_value.month.strftime("%m/%Y"),
            "run_date": self._date_str(self.run_date),
            "effective_date": self._date_str(letter.effective_date),
            "property_name": property_obj.name if property_obj else "—",
            "unit_label": lease.unit.name if lease.unit else "—",
            "tenant_names": self._tenant_names(lease),
            "greeting_text": self._greeting(letter=letter),
            "sender_name": sender_name,
            "sender_contact": (manager.contact_person if manager else "") or "",
            "sender_email": (manager.email if manager else "") or "",
            "sender_phone": (manager.phone if manager else "") or "",
            "old_index_value": self._to_money_decimal(letter.old_index_value),
            "new_index_value": self._to_money_decimal(letter.new_index_value),
            "factor": self._to_ratio_decimal(letter.factor),
            "old_hmz_net": self._to_money_decimal(letter.old_hmz_net),
            "new_hmz_net": self._to_money_decimal(letter.new_hmz_net),
            "delta_hmz_net": self._to_money_decimal(letter.delta_hmz_net),
            "old_hmz_gross": old_hmz_gross,
            "new_hmz_gross": new_hmz_gross,
            "delta_hmz_gross": delta_hmz_gross,
            "catchup_months": int(letter.catchup_months or 0),
            "catchup_period_text": self._catchup_period_text(letter=letter),
            "catchup_net_total": self._to_money_decimal(letter.catchup_net_total),
            "catchup_gross_total": self._to_money_decimal(letter.catchup_gross_total),
            "catchup_tax_percent": self._to_money_decimal(letter.catchup_tax_percent),
            "has_catchup": has_catchup,
            "payment_due_date": self._date_str(issue_date + timedelta(days=14)),
            "skip_reason": (letter.skip_reason or "").strip(),
            "free_text": (self.run.brief_freitext or "").strip(),
            "old_hmz_net_display": self._format_money_at(letter.old_hmz_net),
            "new_hmz_net_display": self._format_money_at(letter.new_hmz_net),
            "delta_hmz_net_display": self._format_money_at(letter.delta_hmz_net),
            "old_hmz_gross_display": self._format_money_at(old_hmz_gross),
            "new_hmz_gross_display": self._format_money_at(new_hmz_gross),
            "delta_hmz_gross_display": self._format_money_at(delta_hmz_gross),
            "catchup_gross_display": self._format_money_at(letter.catchup_gross_total),
            "catchup_net_display": self._format_money_at(letter.catchup_net_total),
        }

    def build_letter_filename(
        self,
        *,
        letter: VpiAdjustmentLetter,
        sequence_number: int | None = None,
    ) -> str:
        if sequence_number is None:
            sequence_number = letter.laufende_nummer
        unit_source = letter.unit.door_number or letter.unit.name or f"einheit-{letter.unit_id}"
        unit_slug = slugify(unit_source) or f"einheit-{letter.unit_id}"
        number_prefix = f"{int(sequence_number):06d}_" if sequence_number else ""
        return f"{number_prefix}VPI-Anpassung_{self.index_value.month:%Y%m}_{unit_slug}_{letter.lease_id}.pdf"

    def build_zip_filename(self) -> str:
        return f"VPI-Briefe_{self.index_value.month:%Y%m}.zip"

    @transaction.atomic
    def generate_letters_zip(self) -> tuple[bytes, int]:
        if not self.run.brief_nummer_start or int(self.run.brief_nummer_start) <= 0:
            raise RuntimeError("Bitte zuerst die Startnummer für den Brieflauf speichern und bestätigen.")

        self.ensure_letters()
        letters = list(
            self.run.letters.select_related("lease", "lease__unit", "lease__unit__property", "pdf_datei")
            .prefetch_related("lease__tenants")
            .order_by("unit__door_number", "unit__name", "lease_id")
        )
        sequence_numbers = self._sequence_numbers_for_letters(
            letters=letters,
            start_number=int(self.run.brief_nummer_start),
        )

        buffer = io.BytesIO()
        generated_count = 0
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for letter in letters:
                sequence_number = sequence_numbers.get(letter.id)
                if sequence_number and letter.laufende_nummer != sequence_number:
                    letter.laufende_nummer = sequence_number
                    letter.save(update_fields=["laufende_nummer", "updated_at"])

                if (letter.skip_reason or "").strip():
                    continue

                payload = self.payload_for_letter(letter=letter, sequence_number=sequence_number)
                filename = self.build_letter_filename(letter=letter, sequence_number=sequence_number)
                try:
                    pdf_bytes = VpiAdjustmentPdfService.generate_letter_pdf(payload=payload)
                except VpiAdjustmentPdfGenerationError as exc:
                    unit_label = payload.get("unit_label", "—")
                    document_number = payload.get("document_number_display", "—")
                    raise RuntimeError(
                        f"PDF-Erstellung fehlgeschlagen für Einheit {unit_label} (Nr. {document_number}): {exc}"
                    ) from exc

                VpiAdjustmentStorageService.persist_letter_pdf(
                    letter=letter,
                    filename=filename,
                    pdf_bytes=pdf_bytes,
                )
                archive.writestr(filename, pdf_bytes)
                generated_count += 1

        return buffer.getvalue(), generated_count

    @staticmethod
    def _next_available_catchup_date(*, lease: LeaseAgreement, start_date: date) -> date:
        current = start_date
        for _ in range(90):
            conflict_exists = Buchung.objects.filter(
                mietervertrag=lease,
                typ=Buchung.Typ.SOLL,
                kategorie=Buchung.Kategorie.HMZ,
                datum=current,
            ).exists()
            if not conflict_exists:
                return current
            current = current + timedelta(days=1)
        raise RuntimeError("Konnte kein freies Datum für Nachverrechnungsbuchung finden.")

    def _catchup_text(self, *, letter: VpiAdjustmentLetter) -> str:
        if int(letter.catchup_months or 0) <= 0:
            return "Nachverrechnung VPI"
        return f"Nachverrechnung VPI {self._catchup_period_text(letter=letter)}"

    @transaction.atomic
    def apply_run(self) -> dict[str, int]:
        if self.run.status == VpiAdjustmentRun.Status.APPLIED:
            return {
                "updated_leases": 0,
                "catchup_bookings": 0,
                "skipped_letters": 0,
            }

        ready, reason = self.apply_readiness(ensure_letters=True)
        if not ready:
            raise RuntimeError(reason)

        letters = list(
            self.run.letters.select_related("lease", "lease__unit", "catchup_booking")
            .order_by("unit__door_number", "unit__name", "lease_id")
        )

        applied_at = timezone.now()
        updated_leases = 0
        catchup_bookings = 0
        skipped_letters = 0

        for letter in letters:
            if letter.applied_at is not None:
                continue

            if (letter.skip_reason or "").strip():
                skipped_letters += 1
                letter.applied_at = applied_at
                letter.save(update_fields=["applied_at", "updated_at"])
                continue

            lease = letter.lease
            lease.net_rent = self._to_money_decimal(letter.new_hmz_net)
            lease.index_base_value = self._to_money_decimal(letter.new_index_value)
            lease.last_index_adjustment = letter.effective_date
            lease.save(update_fields=["net_rent", "index_base_value", "last_index_adjustment"])
            updated_leases += 1

            if self._to_money_decimal(letter.catchup_gross_total) > ZERO and letter.catchup_booking_id is None:
                booking_date = self._next_available_catchup_date(
                    lease=lease,
                    start_date=applied_at.date(),
                )
                catchup_booking = Buchung(
                    mietervertrag=lease,
                    einheit=lease.unit,
                    typ=Buchung.Typ.SOLL,
                    kategorie=Buchung.Kategorie.HMZ,
                    buchungstext=self._catchup_text(letter=letter),
                    datum=booking_date,
                    netto=self._to_money_decimal(letter.catchup_net_total),
                    ust_prozent=self._to_money_decimal(letter.catchup_tax_percent),
                    brutto=self._to_money_decimal(letter.catchup_gross_total),
                )
                catchup_booking.full_clean(validate_unique=False, validate_constraints=False)
                catchup_booking.save()
                letter.catchup_booking = catchup_booking
                catchup_bookings += 1

            letter.applied_at = applied_at
            letter.save(update_fields=["catchup_booking", "applied_at", "updated_at"])

        self.run.status = VpiAdjustmentRun.Status.APPLIED
        self.run.applied_at = applied_at
        self.run.save(update_fields=["status", "applied_at", "updated_at"])

        return {
            "updated_leases": updated_leases,
            "catchup_bookings": catchup_bookings,
            "skipped_letters": skipped_letters,
        }
