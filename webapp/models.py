from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator

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
        verbose_name=_("Nutzfläche (m²)"),
    )
    operating_cost_share = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name=_("Betriebskostenanteil"),
        help_text=_("Anteil an den Betriebskosten (z. B. Prozent oder Faktor)."),
    )

    class Meta:
        verbose_name = _("Einheit")
        verbose_name_plural = _("Einheiten")

    def __str__(self) -> str:
        return f"{self.name} ({self.property.name})"


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
    iban = models.CharField(max_length=34, blank=True, verbose_name=_("IBAN / Bankkonto-ID"))
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))

    class Meta:
        verbose_name = _("Mieter")
        verbose_name_plural = _("Mieter")

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
    class IndexType(models.TextChoices):
        VPI = "vpi", _("VPI")
        FIX = "fix", _("Fix")

    unit = models.ForeignKey("Unit", on_delete=models.PROTECT, related_name="leases")
    tenants = models.ManyToManyField("Tenant", related_name="leases", verbose_name=_("Mieter"))
    manager = models.ForeignKey(
        "Manager",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Verwalter"),
    )

    entry_date = models.DateField(verbose_name=_("Einzugsdatum"))
    exit_date = models.DateField(null=True, blank=True, verbose_name=_("Auszugsdatum"))

    index_type = models.CharField(
        max_length=10,
        choices=IndexType.choices,
        default=IndexType.VPI,
    )
    last_index_adjustment = models.DateField(null=True, blank=True, verbose_name=_("Letzte Wertsicherung"))
    index_base_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
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
    )

    @property
    def rent_per_sqm(self):
        if self.unit.usable_area > 0:
            return self.net_rent / self.unit.usable_area
        return Decimal("0.00")

    @property
    def total_gross_rent(self):
        return (self.net_rent + self.operating_costs_net) * Decimal("1.10") + (
            self.heating_costs_net * Decimal("1.20")
        )

    class Meta:
        verbose_name = _("Mietvertrag")
        verbose_name_plural = _("Mietverträge")

    def __str__(self) -> str:
        return f"{self.unit} · {self.entry_date}"
