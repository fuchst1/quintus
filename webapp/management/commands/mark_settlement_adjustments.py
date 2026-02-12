from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from webapp.models import Buchung
from webapp.services.settlement_adjustments import match_settlement_adjustment_text


class Command(BaseCommand):
    help = (
        "Markiert IST-Buchungen als Ausgleich Vorjahresabrechnung "
        "auf Basis von Textmustern im Buchungstext."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Setzt die Markierung in der Datenbank. Ohne --apply nur Vorschau.",
        )
        parser.add_argument(
            "--jahr",
            type=int,
            help="Optionales Jahr (YYYY) fuer die Auswahl.",
        )
        parser.add_argument(
            "--liegenschaft",
            type=int,
            help="Optionale Liegenschafts-ID fuer die Auswahl.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        year = options.get("jahr")
        property_id = options.get("liegenschaft")

        queryset = Buchung.objects.filter(
            typ=Buchung.Typ.IST,
            is_settlement_adjustment=False,
        ).select_related("mietervertrag__unit__property", "einheit__property")

        if year:
            queryset = queryset.filter(datum__year=year)
        if property_id:
            queryset = queryset.filter(
                Q(mietervertrag__unit__property_id=property_id)
                | Q(einheit__property_id=property_id)
            )

        candidates: list[tuple[int, str]] = []
        for booking in queryset.order_by("datum", "id"):
            matched, reason = match_settlement_adjustment_text(booking.buchungstext)
            if not matched:
                continue
            candidates.append((booking.pk, reason))

        self.stdout.write(f"Gepruefte Buchungen: {queryset.count()}")
        self.stdout.write(f"Treffer: {len(candidates)}")

        if not candidates:
            self.stdout.write(self.style.SUCCESS("Keine Treffer gefunden."))
            return

        reason_by_id = {booking_id: reason for booking_id, reason in candidates}
        matched_bookings = queryset.filter(pk__in=reason_by_id.keys()).order_by("datum", "id")
        for booking in matched_bookings:
            property_name = ""
            if booking.mietervertrag and booking.mietervertrag.unit and booking.mietervertrag.unit.property:
                property_name = booking.mietervertrag.unit.property.name
            elif booking.einheit and booking.einheit.property:
                property_name = booking.einheit.property.name
            self.stdout.write(
                f"- #{booking.pk} {booking.datum:%d.%m.%Y} "
                f"[{property_name or 'ohne Liegenschaft'}] "
                f"{reason_by_id[booking.pk]} "
                f"Text: {booking.buchungstext}"
            )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-Run: Keine Daten geaendert. Mit --apply werden Treffer markiert."
                )
            )
            return

        updated_count = Buchung.objects.filter(
            pk__in=reason_by_id.keys(),
            is_settlement_adjustment=False,
        ).update(is_settlement_adjustment=True)
        self.stdout.write(self.style.SUCCESS(f"{updated_count} Buchungen markiert."))
