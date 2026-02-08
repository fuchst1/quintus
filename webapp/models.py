from builtins import property as builtin_property
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Prefetch
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from simple_history.models import HistoricalRecords

# Validator für die Postleitzahl (4 bis 5 Ziffern)
zip_validator = RegexValidator(
    regex=r'^\d{4,5}$',
    message=_("Die Postleitzahl darf nur aus Zahlen bestehen (4 bis 5 Ziffern).")
)


class Manager(models.Model):
    class TaxMode(models.TextChoices):
        NETTO = "netto", _("Netto (Regelbesteuerung)")
        BRUTTO = "brutto", _("Brutto (Kleinunternehmer / Pauschaliert)")

    company_name = models.CharField(max_length=255, verbose_name=_("Firma"))
    contact_person = models.CharField(max_length=255, verbose_name=_("Ansprechpartner"))
    email = models.EmailField(verbose_name=_("E-Mail"))
    phone = models.CharField(
        max_length=50,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?\d+$',
                message=_("Telefon darf nur Ziffern enthalten, optional mit führendem +."),
            )
        ],
        verbose_name=_("Telefon"),
    )
    website = models.URLField(blank=True, verbose_name=_("Webseite"))

    tax_mode = models.CharField(
        max_length=10,
        choices=TaxMode.choices,
        default=TaxMode.NETTO,
        verbose_name=_("Steuer-Modus"),
        help_text=_("Wichtig für die Vorsteuerabzugsberechtigung."),
    )

    class Meta:
        verbose_name = _("Verwalter")
        verbose_name_plural = _("Verwalter")

    def __str__(self) -> str:
        return self.company_name


class Property(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    zip_code = models.CharField(
        max_length=20, 
        validators=[zip_validator],
        verbose_name=_("Postleitzahl")
    )
    city = models.CharField(max_length=100, verbose_name=_("Stadt"))
    street_address = models.CharField(max_length=255, verbose_name=_("Straße und Hausnummer"))
    
    heating_share_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=85.00,
        validators=[
            MinValueValidator(55.00), 
            MaxValueValidator(85.00)
        ],
        verbose_name=_("Heizkostenanteil (%)"),
        help_text=_("Erlaubter Bereich: 55% bis 85%."),
    )
    
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))
    manager = models.ForeignKey(
        Manager,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="properties",
        verbose_name=_("Verwalter"),
    )
    owners = models.ManyToManyField(
        "Owner",
        through="Ownership",
        related_name="properties",
        verbose_name=_("Eigentümer"),
    )

    class Meta:
        verbose_name = _("Liegenschaft")
        verbose_name_plural = _("Liegenschaften")

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class Unit(models.Model):
    class UnitType(models.TextChoices):
        APARTMENT = "apartment", _("Wohnung")
        PARKING = "parking", _("Parkplatz")
        COMMERCIAL = "commercial", _("Gewerbe")
        OTHER = "other", _("Sonstiges")

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="units",
        verbose_name=_("Liegenschaft"),
    )
    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices,
        default=UnitType.APARTMENT,
        verbose_name=_("Einheitstyp"),
    )
    door_number = models.CharField(max_length=50, verbose_name=_("Türnummer"))
    name = models.CharField(max_length=255, verbose_name=_("Bezeichnung"))
    usable_area = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        null=True,
        blank=True,
        verbose_name=_("Nutzfläche (m²)"),
    )
    operating_cost_share = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        null=True,
        blank=True,
        verbose_name=_("Betriebskostenanteil"),
        help_text=_("Anteil an den Betriebskosten (z. B. Prozent oder Faktor)."),
    )

    class Meta:
        verbose_name = _("Einheit")
        verbose_name_plural = _("Einheiten")

    def __str__(self) -> str:
        return f"{self.name} ({self.property.name})"

    @builtin_property
    def current_status(self) -> str:
        if self.leases.filter(status=LeaseAgreement.Status.AKTIV).exists():
            return "Vermietet"
        return "Frei"


class Owner(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    email = models.EmailField(verbose_name=_("E-Mail"))
    phone = models.CharField(
        max_length=50,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?\d+$',
                message=_("Telefon darf nur Ziffern enthalten, optional mit führendem +."),
            )
        ],
        verbose_name=_("Telefon"),
    )
    street_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Adresse"),
    )
    zip_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[zip_validator],
        verbose_name=_("Postleitzahl"),
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Ort"),
    )
    iban = models.CharField(
        max_length=34,
        blank=True,
        verbose_name=_("IBAN"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    class Meta:
        verbose_name = _("Eigentümer")
        verbose_name_plural = _("Eigentümer")

    def __str__(self) -> str:
        return self.name


class Tenant(models.Model):
    class Salutation(models.TextChoices):
        HERR = "herr", _("Herr")
        FRAU = "frau", _("Frau")
        DIVERS = "divers", _("Divers")
        FIRMA = "firma", _("Firma")

    salutation = models.CharField(
        max_length=20,
        choices=Salutation.choices,
        default=Salutation.HERR,
        verbose_name=_("Anrede"),
    )
    first_name = models.CharField(max_length=100, verbose_name=_("Vorname"))
    last_name = models.CharField(max_length=100, verbose_name=_("Nachname"))
    date_of_birth = models.DateField(null=True, blank=True, verbose_name=_("Geburtsdatum"))
    email = models.EmailField(blank=True, verbose_name=_("E-Mail"))
    phone = models.CharField(
        max_length=50,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?\d+$',
                message=_("Telefon darf nur Ziffern enthalten, optional mit führendem +."),
            )
        ],
        verbose_name=_("Telefon"),
    )
    iban = models.CharField(max_length=34, blank=True, verbose_name=_("IBAN / Bankkonto-ID"))
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    class Meta:
        verbose_name = _("Mieter")
        verbose_name_plural = _("Mieter")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.get_salutation_display()} {self.first_name} {self.last_name}"


class Ownership(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="ownerships",
        verbose_name=_("Liegenschaft"),
    )
    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="ownerships",
        verbose_name=_("Eigentümer"),
    )
    share_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_("Anteil (%)"),
        help_text=_("Eigentumsanteil in Prozent für diese Liegenschaft."),
    )

    class Meta:
        verbose_name = _("Eigentumsanteil")
        verbose_name_plural = _("Eigentumsanteile")
        unique_together = ("property", "owner")

    def __str__(self) -> str:
        return f"{self.owner} · {self.property}"


class LeaseAgreement(models.Model):
    class Status(models.TextChoices):
        AKTIV = "aktiv", _("Laufend")
        BEENDET = "beendet", _("Beendet")

    class IndexType(models.TextChoices):
        VPI = "vpi", _("VPI")
        FIX = "fix", _("Fix")

    unit = models.ForeignKey(
        "Unit",
        on_delete=models.CASCADE,
        related_name="leases",
        verbose_name=_("Einheit"),
    )
    tenants = models.ManyToManyField("Tenant", related_name="leases", verbose_name=_("Mieter"))
    manager = models.ForeignKey(
        "Manager",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Verwalter"),
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.AKTIV,
        verbose_name=_("Status"),
    )

    entry_date = models.DateField(verbose_name=_("Einzugsdatum"))
    exit_date = models.DateField(null=True, blank=True, verbose_name=_("Auszugsdatum"))

    index_type = models.CharField(
        max_length=10,
        choices=IndexType.choices,
        default=IndexType.VPI,
        verbose_name=_("Index-Typ"),
    )
    last_index_adjustment = models.DateField(null=True, blank=True, verbose_name=_("Letzte Wertsicherung"))
    index_base_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("Index-Basiswert"),
    )

    net_rent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("HMZ Netto"),
        validators=[MinValueValidator(0)],
    )
    operating_costs_net = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("BK Netto"),
        validators=[MinValueValidator(0)],
    )
    heating_costs_net = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Heizung Netto"),
        validators=[MinValueValidator(0)],
    )
    deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0)],
        verbose_name=_("Kaution"),
    )
    history = HistoricalRecords(m2m_fields=["tenants"])

    @property
    def rent_per_sqm(self):
        if self.unit.usable_area > 0:
            return self.net_rent / self.unit.usable_area
        return Decimal("0.00")

    @property
    def total_gross_rent(self):
        hmz_tax_rate = Decimal("0.10")
        if self.unit and self.unit.unit_type == Unit.UnitType.PARKING:
            hmz_tax_rate = Decimal("0.20")
        hmz_gross = self.net_rent * (Decimal("1.00") + hmz_tax_rate)
        bk_gross = self.operating_costs_net * Decimal("1.10")
        hk_gross = self.heating_costs_net * Decimal("1.20")
        return hmz_gross + bk_gross + hk_gross

    class Meta:
        verbose_name = _("Mietvertrag")
        verbose_name_plural = _("Mietverträge")

    def __str__(self) -> str:
        return f"{self.unit} · {self.entry_date}"


class BankTransaktion(models.Model):
    referenz_nummer = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_("Referenznummer"),
    )
    partner_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Partner"),
    )
    iban = models.CharField(
        max_length=34,
        blank=True,
        verbose_name=_("IBAN"),
    )
    betrag = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Betrag"),
    )
    buchungsdatum = models.DateField(verbose_name=_("Buchungsdatum"))
    verwendungszweck = models.TextField(blank=True, verbose_name=_("Verwendungszweck"))

    class Meta:
        verbose_name = _("Banktransaktion")
        verbose_name_plural = _("Banktransaktionen")
        ordering = ["-buchungsdatum"]

    def __str__(self) -> str:
        return f"{self.referenz_nummer} ({self.buchungsdatum})"


class Buchung(models.Model):
    class Typ(models.TextChoices):
        SOLL = "soll", _("Forderung an Mieter")
        IST = "ist", _("Zahlungseingang vom Mieter")

    class Kategorie(models.TextChoices):
        HMZ = "hmz", _("Hauptmietzins")
        BK = "bk", _("Betriebskosten")
        HK = "hk", _("Heizkosten")
        WASSER = "wasser", _("Wasser/Abwasser")
        SONST = "sonst", _("Sonstiges")
        ZAHLUNG = "zahlung", _("Geldeingang")

    mietervertrag = models.ForeignKey(
        "LeaseAgreement",
        on_delete=models.PROTECT,
        related_name="buchungen",
        null=True,
        blank=True,
        verbose_name=_("Mietvertrag"),
    )
    einheit = models.ForeignKey(
        "Unit",
        on_delete=models.PROTECT,
        related_name="buchungen",
        null=True,
        blank=True,
        verbose_name=_("Einheit"),
    )
    bank_transaktion = models.ForeignKey(
        "BankTransaktion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buchungen",
        verbose_name=_("Banktransaktion"),
    )
    typ = models.CharField(
        max_length=20,
        choices=Typ.choices,
        verbose_name=_("Typ"),
    )
    kategorie = models.CharField(
        max_length=20,
        choices=Kategorie.choices,
        verbose_name=_("Kategorie"),
    )
    buchungstext = models.CharField(max_length=255, verbose_name=_("Buchungstext"))
    datum = models.DateField(verbose_name=_("Datum"))
    netto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Netto"))
    ust_prozent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        verbose_name=_("USt (%)"),
    )
    brutto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Brutto"))
    storniert_von = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stornos",
        verbose_name=_("Storniert von"),
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Buchung")
        verbose_name_plural = _("Buchungen")

    def __str__(self) -> str:
        return f"{self.datum} · {self.mietervertrag} · {self.brutto}"

    def clean(self):
        super().clean()
        if self.netto is None or self.ust_prozent is None or self.brutto is None:
            return
        expected = (
            self.netto + (self.netto * self.ust_prozent / Decimal("100"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        actual = Decimal(self.brutto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tolerance = Decimal("0.00")
        if self.typ == self.Typ.IST and self.kategorie == self.Kategorie.ZAHLUNG:
            # Bank-Bruttowerte kommen fix in Cent; bei Rückrechnung auf Netto mit 10/20 %
            # kann durch Rundung in seltenen Fällen 1 Cent Differenz entstehen.
            tolerance = Decimal("0.01")
        if (expected - actual).copy_abs() > tolerance:
            raise ValidationError(
                {
                    "brutto": _(
                        "Brutto entspricht nicht Netto plus USt. (2 Nachkommastellen)."
                    )
                }
            )


class BetriebskostenBeleg(models.Model):
    class BKArt(models.TextChoices):
        STROM = "strom", _("Strom")
        WASSER = "wasser", _("Wasser")
        BETRIEBSKOSTEN = "betriebskosten", _("Betriebskosten")
        SONSTIG = "sonstig", _("Sonstiges")

    liegenschaft = models.ForeignKey(
        "Property",
        on_delete=models.PROTECT,
        related_name="betriebskosten_belege",
        verbose_name=_("Liegenschaft"),
    )
    bk_art = models.CharField(
        max_length=30,
        choices=BKArt.choices,
        verbose_name=_("BK-Art"),
    )
    datum = models.DateField(verbose_name=_("Datum"))
    netto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Netto"))
    ust_prozent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        verbose_name=_("USt (%)"),
    )
    brutto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Brutto"))
    lieferant_name = models.CharField(max_length=255, blank=True, verbose_name=_("Lieferant"))
    iban = models.CharField(max_length=34, blank=True, verbose_name=_("IBAN"))
    buchungstext = models.CharField(max_length=255, blank=True, verbose_name=_("Buchungstext"))
    import_referenz = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Import-Referenz"))
    import_quelle = models.CharField(max_length=100, blank=True, default="bankimport", verbose_name=_("Import-Quelle"))

    class Meta:
        verbose_name = _("Betriebskostenbeleg")
        verbose_name_plural = _("Betriebskostenbelege")
        ordering = ["-datum", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["import_quelle", "import_referenz"],
                condition=models.Q(import_referenz__gt=""),
                name="uniq_bkbeleg_importquelle_referenz_not_blank",
            )
        ]

    def __str__(self) -> str:
        return f"{self.datum} · {self.liegenschaft} · {self.brutto}"

    def clean(self):
        super().clean()
        if self.netto is None or self.ust_prozent is None or self.brutto is None:
            return
        expected = (
            self.netto + (self.netto * self.ust_prozent / Decimal("100"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        actual = Decimal(self.brutto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if expected != actual:
            raise ValidationError(
                {
                    "brutto": _(
                        "Brutto entspricht nicht Netto plus USt. (2 Nachkommastellen)."
                    )
                }
            )


class Meter(models.Model):
    class MeterType(models.TextChoices):
        ELECTRICITY = "electricity", _("Strom")
        WATER_COLD = "water_cold", _("Kaltwasser")
        WATER_HOT = "water_hot", _("Warmwasser")
        HEAT_ENERGY = "heat_energy", _("Wärmeenergie")
        COOL_ENERGY = "cool_energy", _("Kälteenergie")
        WP_HEAT = "WP_heat", _("Wärmepumpe - Erzeugte Wärme")
        WP_ELECTRICITY = "WP_electricity", _("Wärmepumpe - Stromverbrauch")
        WP_WARMWATER = "WP_warmwater", _("Wärmepumpe - Warmwasser")
        ELECTRICITY_PV = "electricity_PV", _("Photovoltaik - Ertrag")

    class UnitOfMeasure(models.TextChoices):
        KWH = "kwh", _("kWh")
        M3 = "m3", _("m³")
        STK = "stk", _("Stk")

    class CalculationKind(models.TextChoices):
        READING = "reading", _("Ablesung (Differenz)")
        CONSUMPTION = "consumption", _("Direkteingabe Verbrauch")

    meter_number = models.CharField(
        max_length=50,
        verbose_name=_("Zählernummer"),
        null=True,
        blank=True,
    )
    meter_type = models.CharField(
        max_length=30,
        choices=MeterType.choices,
        verbose_name=_("Zählertyp"),
    )
    unit_of_measure = models.CharField(
        max_length=10,
        choices=UnitOfMeasure.choices,
        default=UnitOfMeasure.KWH,
        verbose_name=_("Maßeinheit"),
        help_text=_("Einheit, in der der Zählerstand erfasst wird (z. B. kWh oder m³)."),
    )
    kind = models.CharField(
        max_length=20,
        choices=CalculationKind.choices,
        default=CalculationKind.READING,
        verbose_name=_("Eingabeart"),
        help_text=_(
            "'Ablesung' berechnet die Differenz zweier Stände. "
            "'Direkteingabe' nimmt den Wert als Jahresverbrauch."
        ),
    )

    property = models.ForeignKey(
        "Property",
        on_delete=models.CASCADE,
        related_name="meters",
        verbose_name=_("Liegenschaft"),
    )
    unit = models.ForeignKey(
        "Unit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meters",
        verbose_name=_("Einheit"),
    )

    is_main_meter = models.BooleanField(
        default=False,
        verbose_name=_("Hauptzähler"),
        help_text=_("Markieren, wenn dies der Zähler für das gesamte Haus ist."),
    )

    description = models.TextField(blank=True, null=True, verbose_name=_("Beschreibung"))

    class Meta:
        verbose_name = _("Zähler")
        verbose_name_plural = _("Zähler")

    def __str__(self) -> str:
        scope = self.unit.door_number if self.unit else _("Haus")
        return f"{self.get_meter_type_display()} ({scope}) - {self.meter_number or '???'}"

    def calculate_yearly_consumption(self) -> list[dict[str, object]]:
        readings = list(self.readings.all().order_by("date", "id"))
        return self._calculate_yearly_consumption_for_meter(self, readings)

    @classmethod
    def calculate_yearly_consumption_all(cls) -> list[dict[str, object]]:
        readings_qs = MeterReading.objects.order_by("date", "id")
        meters = cls.objects.prefetch_related(
            Prefetch("readings", queryset=readings_qs)
        )
        results: list[dict[str, object]] = []
        for meter in meters:
            readings = list(meter.readings.all())
            results.extend(cls._calculate_yearly_consumption_for_meter(meter, readings))
        results.sort(key=lambda row: (row["meter_id"], row["calc_year"]))
        return results

    @staticmethod
    def _calculate_yearly_consumption_for_meter(
        meter: "Meter",
        readings: list["MeterReading"],
    ) -> list[dict[str, object]]:
        if not readings:
            return []

        readings = sorted(readings, key=lambda r: (r.date, r.pk))
        years = sorted({reading.date.year for reading in readings})
        results: list[dict[str, object]] = []

        for year in years:
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            readings_in_year = [
                reading
                for reading in readings
                if year_start <= reading.date <= year_end
            ]
            if not readings_in_year:
                continue

            if meter.kind == Meter.CalculationKind.CONSUMPTION:
                total_value = sum(
                    (reading.value for reading in readings_in_year),
                    Decimal("0"),
                )
                reading_count = len(readings_in_year)
                end_date = readings_in_year[-1].date if reading_count == 1 else year_end
                duration_days = (end_date - year_start).days + 1
                end_value = total_value
                avg_per_day = (
                    end_value / Decimal(duration_days)
                    if duration_days and end_value is not None
                    else None
                )
                results.append(
                    {
                        "meter_id": meter.pk,
                        "calc_year": year,
                        "kind": meter.kind,
                        "start_date": year_start,
                        "start_value": None,
                        "end_date": end_date,
                        "end_value": end_value,
                        "duration_days": duration_days,
                        "avg_per_day": avg_per_day,
                        "consumption": end_value,
                    }
                )
                continue

            start_reading = None
            for reading in readings:
                if reading.date <= year_start:
                    start_reading = reading
                else:
                    break
            if start_reading is None:
                start_reading = readings_in_year[0]
            end_reading = readings_in_year[-1]
            if end_reading is None:
                continue

            start_date = start_reading.date if start_reading else None
            end_date = end_reading.date
            start_value = start_reading.value if start_reading else None
            end_value = end_reading.value
            duration_days = (
                (end_date - start_date).days + 1 if start_date and end_date else None
            )
            avg_per_day = None
            consumption = None
            if (
                duration_days
                and start_value is not None
                and end_value is not None
            ):
                delta = end_value - start_value
                avg_per_day = delta / Decimal(duration_days)
                consumption = delta

            results.append(
                {
                    "meter_id": meter.pk,
                    "calc_year": year,
                    "kind": meter.kind,
                    "start_date": start_date,
                    "start_value": start_value,
                    "end_date": end_date,
                    "end_value": end_value,
                    "duration_days": duration_days,
                    "avg_per_day": avg_per_day,
                    "consumption": consumption,
                }
            )

        return results


class MeterReading(models.Model):
    meter = models.ForeignKey(
        Meter,
        on_delete=models.CASCADE,
        related_name="readings",
        verbose_name=_("Zähler"),
    )
    date = models.DateField(verbose_name=_("Ablesedatum"))
    value = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_("Wert / Zählerstand"),
    )
    note = models.TextField(blank=True, null=True, verbose_name=_("Notiz"))

    class Meta:
        verbose_name = _("Zählerstand")
        verbose_name_plural = _("Zählerstände")
        ordering = ["-date"]
        unique_together = ("meter", "date")

    def __str__(self) -> str:
        return f"{self.meter.meter_number} am {self.date}: {self.value}"
