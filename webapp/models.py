from django.db import models
from django.utils.translation import gettext_lazy as _


class Property(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    zip_code = models.CharField(max_length=20, verbose_name=_("Postleitzahl"))
    city = models.CharField(max_length=100, verbose_name=_("Stadt"))
    street_address = models.CharField(max_length=255, verbose_name=_("Straße und Hausnummer"))
    heating_share_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=85.00,
        verbose_name=_("Heizkostenanteil (%)"),
        help_text=_("Standardwert für Heizkostenanteil in Prozent."),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notizen"))
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
        verbose_name=_("Nutzfläche (m²)"),
    )
    operating_cost_share = models.DecimalField(
        max_digits=6,
        decimal_places=2,
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
    phone = models.CharField(max_length=50, blank=True, verbose_name=_("Telefon"))

    class Meta:
        verbose_name = _("Eigentümer")
        verbose_name_plural = _("Eigentümer")

    def __str__(self) -> str:
        return self.name


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
