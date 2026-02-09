from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from webapp.models import Buchung, LeaseAgreement, Unit


class Command(BaseCommand):
    help = "Erzeugt monatliche SOLL-Buchungen für aktive Mietverträge."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            type=str,
            help="Monat im Format YYYY-MM (z. B. 2026-02).",
        )

    def handle(self, *args, **options):
        month_start = self._parse_month(options.get("month"))
        month_end = self._month_end(month_start)

        leases = list(
            LeaseAgreement.objects.select_related("unit")
            .filter(status=LeaseAgreement.Status.AKTIV, entry_date__lte=month_end)
            .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=month_start))
        )
        lease_ids = [lease.pk for lease in leases]

        to_create = []
        soll_categories = [
            Buchung.Kategorie.HMZ,
            Buchung.Kategorie.BK,
            Buchung.Kategorie.HK,
        ]
        for lease in leases:
            for category, netto, tax_rate in self._soll_components_for_lease(lease):
                if netto is None or netto <= 0:
                    continue

                ust_prozent = (tax_rate * Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                brutto = (netto * (Decimal("1.00") + tax_rate)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                to_create.append(
                    Buchung(
                        mietervertrag=lease,
                        einheit=lease.unit,
                        typ=Buchung.Typ.SOLL,
                        kategorie=category,
                        buchungstext=f"SOLL {category.label} {month_start.strftime('%m.%Y')}",
                        datum=month_start,
                        netto=netto,
                        ust_prozent=ust_prozent,
                        brutto=brutto,
                    )
                )

        for buchung in to_create:
            buchung.full_clean(validate_unique=False, validate_constraints=False)

        base_queryset = Buchung.objects.filter(
            typ=Buchung.Typ.SOLL,
            datum=month_start,
            mietervertrag_id__in=lease_ids,
            kategorie__in=soll_categories,
        )
        existing_before = base_queryset.count()
        created_count = 0
        skipped_conflicts = 0

        if to_create:
            Buchung.objects.bulk_create(to_create, ignore_conflicts=True)
            existing_after = base_queryset.count()
            created_count = max(existing_after - existing_before, 0)
            skipped_conflicts = max(len(to_create) - created_count, 0)

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"{created_count} SOLL-Buchungen für {month_start.strftime('%m.%Y')} erstellt. "
                    f"{skipped_conflicts} aufgrund bestehender Einträge/Konflikte übersprungen."
                )
            )
        )

    def _parse_month(self, month_value):
        if not month_value:
            today = timezone.localdate()
            return date(today.year, today.month, 1)
        try:
            year_str, month_str = month_value.split("-")
            return date(int(year_str), int(month_str), 1)
        except (ValueError, TypeError):
            raise CommandError("Ungültiges Format. Erwartet: YYYY-MM")

    @staticmethod
    def _month_end(month_start):
        last_day = monthrange(month_start.year, month_start.month)[1]
        return date(month_start.year, month_start.month, last_day)

    def _soll_components_for_lease(self, lease):
        return [
            (Buchung.Kategorie.HMZ, lease.net_rent, self._hmz_rate(lease.unit)),
            (Buchung.Kategorie.BK, lease.operating_costs_net, Decimal("0.10")),
            (Buchung.Kategorie.HK, lease.heating_costs_net, Decimal("0.20")),
        ]

    @staticmethod
    def _hmz_rate(unit):
        if unit and unit.unit_type == Unit.UnitType.PARKING:
            return Decimal("0.20")
        return Decimal("0.10")
