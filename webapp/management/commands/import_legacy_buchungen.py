from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from webapp.models import BetriebskostenBeleg, Buchung, LeaseAgreement, Property, Unit


@dataclass(frozen=True)
class LegacyBuchungRow:
    legacy_id: int
    rechnungtext: str
    bruttobetrag: Decimal
    nettobetrag: Decimal
    ust: Decimal
    bk: str
    ausgabe: int
    datum: date
    einheit_id: int | None
    liegenschaft_id: int | None


class Command(BaseCommand):
    help = "Importiert Legacy-MySQL-Buchungen aus SQL-Dump in Buchungen/Belege."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sql-file",
            type=str,
            default="ifkg(11).sql",
            help="Pfad zur Legacy-SQL-Datei (Default: ifkg(11).sql).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur auswerten, nichts in die DB schreiben.",
        )

    def handle(self, *args, **options):
        sql_file = Path(options["sql_file"]).expanduser()
        dry_run = bool(options["dry_run"])

        if not sql_file.exists():
            raise CommandError(f"SQL-Datei nicht gefunden: {sql_file}")
        if not sql_file.is_file():
            raise CommandError(f"Kein gültiger Dateipfad: {sql_file}")

        sql_text = sql_file.read_text(encoding="utf-8", errors="replace")
        legacy_properties = self._parse_legacy_properties(sql_text)
        legacy_units = self._parse_legacy_units(sql_text, legacy_properties)
        legacy_buchungen = self._parse_legacy_buchungen(sql_text)

        current_property_lookup = self._build_current_property_lookup()
        unit_lookup = self._build_current_unit_lookup()
        lease_lookup = self._build_lease_lookup()

        buchung_payloads: list[dict[str, object]] = []
        beleg_payloads: list[dict[str, object]] = []

        unit_map_warnings = 0
        lease_map_warnings = 0
        soll_conflict_warnings = 0
        expense_property_warnings = 0
        income_category_warnings = 0
        vat_mismatch_rows_detected = 0

        seen_soll_unique: set[tuple[int, date, str]] = set()

        for row in legacy_buchungen:
            normalized_text = self._normalize_booking_text(row.rechnungtext)
            netto = row.nettobetrag.quantize(Decimal("0.01"))
            brutto = row.bruttobetrag.quantize(Decimal("0.01"))
            ust_prozent = row.ust.quantize(Decimal("0.01"))

            if self._has_vat_mismatch(netto=netto, brutto=brutto, ust_prozent=ust_prozent):
                vat_mismatch_rows_detected += 1

            if row.ausgabe == 0:
                mapped_category = self._map_legacy_income_category(row.bk)
                if mapped_category is None:
                    income_category_warnings += 1
                    continue

                mapped_unit_id = self._map_legacy_unit_id(
                    legacy_einheit_id=row.einheit_id,
                    legacy_units=legacy_units,
                    unit_lookup=unit_lookup,
                )
                if row.einheit_id is not None and mapped_unit_id is None:
                    unit_map_warnings += 1

                mapped_lease_id = self._map_lease_id(
                    mapped_unit_id=mapped_unit_id,
                    booking_date=row.datum,
                    lease_lookup=lease_lookup,
                )
                if mapped_unit_id is not None and mapped_lease_id is None:
                    lease_map_warnings += 1

                effective_lease_id = mapped_lease_id
                if effective_lease_id is not None:
                    soll_key = (effective_lease_id, row.datum, mapped_category)
                    if soll_key in seen_soll_unique:
                        # UniqueConstraint auf SOLL: (mietervertrag, datum, kategorie, typ=soll)
                        # Bei Konflikt lösen wir die Zuordnung vom Mietvertrag, damit Import idempotent bleibt.
                        effective_lease_id = None
                        soll_conflict_warnings += 1
                    else:
                        seen_soll_unique.add(soll_key)

                soll_payload = {
                    "typ": Buchung.Typ.SOLL,
                    "kategorie": mapped_category,
                    "buchungstext": normalized_text,
                    "datum": row.datum,
                    "netto": netto,
                    "ust_prozent": ust_prozent,
                    "brutto": brutto,
                    "einheit_id": mapped_unit_id,
                    "mietervertrag_id": effective_lease_id,
                }
                ist_payload = {
                    "typ": Buchung.Typ.IST,
                    "kategorie": mapped_category,
                    "buchungstext": normalized_text,
                    "datum": row.datum,
                    "netto": netto,
                    "ust_prozent": ust_prozent,
                    "brutto": brutto,
                    "einheit_id": mapped_unit_id,
                    "mietervertrag_id": effective_lease_id,
                }
                buchung_payloads.append(soll_payload)
                buchung_payloads.append(ist_payload)
                continue

            if row.ausgabe == 1:
                mapped_property_id = self._map_legacy_property_id(
                    legacy_liegenschaft_id=row.liegenschaft_id,
                    legacy_properties=legacy_properties,
                    current_property_lookup=current_property_lookup,
                )
                if mapped_property_id is None:
                    expense_property_warnings += 1
                    continue

                beleg_payloads.append(
                    {
                        "import_quelle": "legacy_mysql_buchungen",
                        "import_referenz": f"ifkg-buchungen-{row.legacy_id}",
                        "liegenschaft_id": mapped_property_id,
                        "bk_art": self._map_legacy_expense_bk_art(row.bk),
                        "datum": row.datum,
                        "netto": netto,
                        "ust_prozent": ust_prozent,
                        "brutto": brutto,
                        "lieferant_name": "",
                        "iban": "",
                        "buchungstext": normalized_text,
                    }
                )
                continue

            raise CommandError(f"Ungültiger ausgabe-Wert in legacy row #{row.legacy_id}: {row.ausgabe}")

        parsed_rows = len(legacy_buchungen)

        inserted_buchung_rows = 0
        skipped_existing_buchung_rows = 0
        inserted_beleg_rows = 0
        skipped_existing_beleg_rows = 0

        if dry_run:
            for payload in buchung_payloads:
                if Buchung.objects.filter(**payload).exists():
                    skipped_existing_buchung_rows += 1
                else:
                    inserted_buchung_rows += 1

            for payload in beleg_payloads:
                if BetriebskostenBeleg.objects.filter(
                    import_quelle=payload["import_quelle"],
                    import_referenz=payload["import_referenz"],
                ).exists():
                    skipped_existing_beleg_rows += 1
                else:
                    inserted_beleg_rows += 1
        else:
            with transaction.atomic():
                new_buchungen = []
                buchung_count_before = Buchung.objects.count()
                for payload in buchung_payloads:
                    if Buchung.objects.filter(**payload).exists():
                        skipped_existing_buchung_rows += 1
                        continue
                    new_buchungen.append(Buchung(**payload))
                if new_buchungen:
                    # bulk_create umgeht post_save-Signale (simple_history) und reduziert Schreiblast.
                    Buchung.objects.bulk_create(new_buchungen, ignore_conflicts=True, batch_size=500)
                buchung_count_after = Buchung.objects.count()
                inserted_buchung_rows = max(buchung_count_after - buchung_count_before, 0)
                skipped_existing_buchung_rows = len(buchung_payloads) - inserted_buchung_rows

                legacy_source = "legacy_mysql_buchungen"
                beleg_count_before = BetriebskostenBeleg.objects.filter(
                    import_quelle=legacy_source
                ).count()
                new_belege = []
                for payload in beleg_payloads:
                    if BetriebskostenBeleg.objects.filter(
                        import_quelle=payload["import_quelle"],
                        import_referenz=payload["import_referenz"],
                    ).exists():
                        skipped_existing_beleg_rows += 1
                        continue
                    new_belege.append(
                        BetriebskostenBeleg(
                            liegenschaft_id=payload["liegenschaft_id"],
                            bk_art=payload["bk_art"],
                            datum=payload["datum"],
                            netto=payload["netto"],
                            ust_prozent=payload["ust_prozent"],
                            brutto=payload["brutto"],
                            lieferant_name=payload["lieferant_name"],
                            iban=payload["iban"],
                            buchungstext=payload["buchungstext"],
                            import_quelle=payload["import_quelle"],
                            import_referenz=payload["import_referenz"],
                        )
                    )
                if new_belege:
                    BetriebskostenBeleg.objects.bulk_create(
                        new_belege,
                        ignore_conflicts=True,
                        batch_size=500,
                    )
                beleg_count_after = BetriebskostenBeleg.objects.filter(
                    import_quelle=legacy_source
                ).count()
                inserted_beleg_rows = max(beleg_count_after - beleg_count_before, 0)
                skipped_existing_beleg_rows = len(beleg_payloads) - inserted_beleg_rows

        inserted_rows = inserted_buchung_rows + inserted_beleg_rows
        skipped_existing_rows = skipped_existing_buchung_rows + skipped_existing_beleg_rows

        self.stdout.write(f"parsed_rows: {parsed_rows}")
        self.stdout.write(f"inserted_rows: {inserted_rows}")
        self.stdout.write(f"skipped_existing_rows: {skipped_existing_rows}")
        self.stdout.write(f"inserted_buchung_rows: {inserted_buchung_rows}")
        self.stdout.write(f"skipped_existing_buchung_rows: {skipped_existing_buchung_rows}")
        self.stdout.write(f"inserted_beleg_rows: {inserted_beleg_rows}")
        self.stdout.write(f"skipped_existing_beleg_rows: {skipped_existing_beleg_rows}")
        self.stdout.write(f"unit_map_warnings: {unit_map_warnings}")
        self.stdout.write(f"lease_map_warnings: {lease_map_warnings}")
        self.stdout.write(f"soll_conflict_warnings: {soll_conflict_warnings}")
        self.stdout.write(f"expense_property_warnings: {expense_property_warnings}")
        self.stdout.write(f"income_category_warnings: {income_category_warnings}")
        self.stdout.write(f"vat_mismatch_rows_detected: {vat_mismatch_rows_detected}")

    @staticmethod
    def _normalize_booking_text(text: str) -> str:
        normalized = (text or "").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        return normalized[:255]

    @staticmethod
    def _map_legacy_income_category(legacy_bk: str) -> str | None:
        mapping = {
            "miete": Buchung.Kategorie.HMZ,
            "bk": Buchung.Kategorie.BK,
            "heizung": Buchung.Kategorie.HK,
        }
        return mapping.get((legacy_bk or "").strip())

    @staticmethod
    def _map_legacy_expense_bk_art(legacy_bk: str) -> str:
        key = (legacy_bk or "").strip()
        if key == "wasser":
            return BetriebskostenBeleg.BKArt.WASSER
        if key == "strom":
            return BetriebskostenBeleg.BKArt.STROM
        if key == "heizung":
            return BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN
        return BetriebskostenBeleg.BKArt.BETRIEBSKOSTEN

    @staticmethod
    def _has_vat_mismatch(*, netto: Decimal, brutto: Decimal, ust_prozent: Decimal) -> bool:
        expected = (netto + (netto * ust_prozent / Decimal("100"))).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        actual = brutto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return expected != actual

    @staticmethod
    def _build_current_property_lookup() -> dict[str, int]:
        lookup: dict[str, int] = {}
        for prop in Property.objects.only("id", "name").all():
            lookup[prop.name.strip()] = prop.id
        return lookup

    @staticmethod
    def _build_current_unit_lookup() -> dict[tuple[str, str], int]:
        lookup: dict[tuple[str, str], int] = {}
        for unit in Unit.objects.select_related("property").all():
            key = (unit.property.name.strip(), (unit.door_number or "").strip())
            lookup[key] = unit.id
        return lookup

    @staticmethod
    def _build_lease_lookup() -> dict[int, list[LeaseAgreement]]:
        lookup: dict[int, list[LeaseAgreement]] = {}
        for lease in LeaseAgreement.objects.only("id", "unit_id", "entry_date", "exit_date").all():
            if lease.unit_id is None:
                continue
            lookup.setdefault(lease.unit_id, []).append(lease)
        return lookup

    @staticmethod
    def _map_legacy_property_id(
        *,
        legacy_liegenschaft_id: int | None,
        legacy_properties: dict[int, str],
        current_property_lookup: dict[str, int],
    ) -> int | None:
        if legacy_liegenschaft_id is None:
            return None
        legacy_property_name = legacy_properties.get(legacy_liegenschaft_id)
        if not legacy_property_name:
            return None
        return current_property_lookup.get(legacy_property_name.strip())

    @staticmethod
    def _map_legacy_unit_id(
        *,
        legacy_einheit_id: int | None,
        legacy_units: dict[int, tuple[str, str]],
        unit_lookup: dict[tuple[str, str], int],
    ) -> int | None:
        if legacy_einheit_id is None:
            return None
        legacy_identity = legacy_units.get(legacy_einheit_id)
        if legacy_identity is None:
            return None
        return unit_lookup.get(legacy_identity)

    @staticmethod
    def _map_lease_id(
        *,
        mapped_unit_id: int | None,
        booking_date: date,
        lease_lookup: dict[int, list[LeaseAgreement]],
    ) -> int | None:
        if mapped_unit_id is None:
            return None
        candidates = []
        for lease in lease_lookup.get(mapped_unit_id, []):
            if lease.entry_date and booking_date < lease.entry_date:
                continue
            if lease.exit_date and booking_date > lease.exit_date:
                continue
            candidates.append(lease.id)
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _parse_legacy_properties(self, sql_text: str) -> dict[int, str]:
        rows = self._parse_insert_rows(sql_text=sql_text, table_name="liegenschaften")
        properties: dict[int, str] = {}
        for values in rows:
            if len(values) < 2:
                continue
            legacy_id = self._as_int(values[0], "liegenschaften.id")
            property_name = (values[1] or "").strip()
            properties[legacy_id] = property_name
        return properties

    def _parse_legacy_units(
        self,
        sql_text: str,
        legacy_properties: dict[int, str],
    ) -> dict[int, tuple[str, str]]:
        rows = self._parse_insert_rows(sql_text=sql_text, table_name="einheiten")
        units: dict[int, tuple[str, str]] = {}
        for values in rows:
            if len(values) < 8:
                continue
            legacy_unit_id = self._as_int(values[0], "einheiten.id")
            legacy_top = (values[3] or "").strip()
            legacy_property_id = self._as_nullable_int(values[7], "einheiten.liegenschaft_id")
            legacy_property_name = legacy_properties.get(legacy_property_id, "") if legacy_property_id else ""
            units[legacy_unit_id] = (legacy_property_name.strip(), legacy_top)
        return units

    def _parse_legacy_buchungen(self, sql_text: str) -> list[LegacyBuchungRow]:
        rows = self._parse_insert_rows(sql_text=sql_text, table_name="buchungen")
        parsed_rows: list[LegacyBuchungRow] = []
        for values in rows:
            if len(values) < 12:
                continue
            parsed_rows.append(
                LegacyBuchungRow(
                    legacy_id=self._as_int(values[0], "buchungen.id"),
                    rechnungtext=values[1] or "",
                    bruttobetrag=self._as_decimal(values[2], "buchungen.bruttobetrag"),
                    nettobetrag=self._as_decimal(values[3], "buchungen.nettobetrag"),
                    ust=self._as_decimal(values[5], "buchungen.ust"),
                    bk=(values[6] or "").strip(),
                    ausgabe=self._as_int(values[7], "buchungen.ausgabe"),
                    datum=self._as_date(values[8], "buchungen.datum"),
                    einheit_id=self._as_nullable_int(values[10], "buchungen.einheit_id"),
                    liegenschaft_id=self._as_nullable_int(values[11], "buchungen.liegenschaft_id"),
                )
            )
        return parsed_rows

    def _parse_insert_rows(self, *, sql_text: str, table_name: str) -> list[list[str | None]]:
        rows: list[list[str | None]] = []
        pattern = re.compile(
            rf"INSERT INTO `{re.escape(table_name)}`\s*\([^)]*\)\s*VALUES\s*(.*?);",
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(sql_text):
            value_block = match.group(1)
            for tuple_text in self._split_value_tuples(value_block):
                rows.append(self._parse_tuple(tuple_text))
        if not rows:
            raise CommandError(f"Keine INSERT-Daten für Tabelle `{table_name}` gefunden.")
        return rows

    @staticmethod
    def _split_value_tuples(value_block: str) -> Iterable[str]:
        tuples: list[str] = []
        idx = 0
        length = len(value_block)
        while idx < length:
            while idx < length and value_block[idx] != "(":
                idx += 1
            if idx >= length:
                break
            depth = 0
            in_string = False
            escaped = False
            start = idx
            while idx < length:
                ch = value_block[idx]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == "'":
                        in_string = False
                else:
                    if ch == "'":
                        in_string = True
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            tuples.append(value_block[start : idx + 1])
                            idx += 1
                            break
                idx += 1
        return tuples

    @staticmethod
    def _parse_tuple(tuple_text: str) -> list[str | None]:
        if not tuple_text.startswith("(") or not tuple_text.endswith(")"):
            raise CommandError(f"Ungültiger SQL-Tupelwert: {tuple_text[:50]}")

        content = tuple_text[1:-1]
        values: list[str | None] = []
        buffer: list[str] = []
        in_string = False
        escaped = False

        def push_current():
            raw = "".join(buffer).strip()
            if not in_string and raw.upper() == "NULL":
                values.append(None)
            else:
                values.append(raw)

        for ch in content:
            if in_string:
                if escaped:
                    buffer.append(Command._decode_mysql_escape(ch))
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "'":
                    in_string = False
                else:
                    buffer.append(ch)
                continue

            if ch == "'":
                in_string = True
                continue
            if ch == ",":
                push_current()
                buffer = []
                continue
            buffer.append(ch)

        push_current()
        return values

    @staticmethod
    def _decode_mysql_escape(ch: str) -> str:
        mapping = {
            "0": "\0",
            "b": "\b",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "Z": "\x1a",
            "\\": "\\",
            "'": "'",
            '"': '"',
        }
        return mapping.get(ch, ch)

    def _as_int(self, value: str | None, field_name: str) -> int:
        if value is None:
            raise CommandError(f"Pflichtfeld leer: {field_name}")
        try:
            return int(value)
        except ValueError as exc:
            raise CommandError(f"Ungültiger Integer in {field_name}: {value!r}") from exc

    def _as_nullable_int(self, value: str | None, field_name: str) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError as exc:
            raise CommandError(f"Ungültiger Integer in {field_name}: {value!r}") from exc

    def _as_decimal(self, value: str | None, field_name: str) -> Decimal:
        if value is None:
            raise CommandError(f"Pflichtfeld leer: {field_name}")
        try:
            return Decimal(value)
        except Exception as exc:
            raise CommandError(f"Ungültiger Decimal-Wert in {field_name}: {value!r}") from exc

    def _as_date(self, value: str | None, field_name: str) -> date:
        if value is None:
            raise CommandError(f"Pflichtfeld leer: {field_name}")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError(f"Ungültiges Datum in {field_name}: {value!r}") from exc
