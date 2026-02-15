from builtins import property as builtin_property
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import mimetypes
import os

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Prefetch
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from simple_history.models import HistoricalRecords

from .storage_paths import datei_upload_to

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
    account_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Kontonummer"),
    )

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


class ReminderRuleConfig(models.Model):
    code = models.CharField(
        max_length=80,
        unique=True,
        verbose_name=_("Code"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Titel"),
    )
    lead_months = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(60)],
        verbose_name=_("Vorlauf (Monate)"),
        help_text=_("Wie viele Monate vor dem Termin erinnert werden soll."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Aktiv"),
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        verbose_name=_("Sortierung"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Erstellt am"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Aktualisiert am"),
    )

    class Meta:
        verbose_name = _("Erinnerungsregel")
        verbose_name_plural = _("Erinnerungsregeln")
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"


class ReminderEmailLog(models.Model):
    period_start = models.DateField(verbose_name=_("Periode ab"))
    recipient_email = models.EmailField(verbose_name=_("Empfänger-E-Mail"))
    rule_code = models.CharField(max_length=80, verbose_name=_("Regel-Code"))
    lease = models.ForeignKey(
        "LeaseAgreement",
        on_delete=models.CASCADE,
        related_name="reminder_email_logs",
        verbose_name=_("Mietvertrag"),
    )
    due_date = models.DateField(verbose_name=_("Fällig am"))
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Gesendet am"))

    class Meta:
        verbose_name = _("Erinnerungsversand")
        verbose_name_plural = _("Erinnerungsversände")
        constraints = [
            models.UniqueConstraint(
                fields=["period_start", "recipient_email", "rule_code", "lease", "due_date"],
                name="uniq_reminder_mail_period_recipient_rule_lease_due",
            )
        ]
        indexes = [
            models.Index(fields=["period_start", "recipient_email"]),
            models.Index(fields=["rule_code", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_email} · {self.rule_code} · {self.due_date}"


class Abrechnungslauf(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Entwurf")
        APPLIED = "applied", _("Angewendet")

    liegenschaft = models.ForeignKey(
        "Property",
        on_delete=models.PROTECT,
        related_name="abrechnungslaeufe",
        verbose_name=_("Liegenschaft"),
    )
    jahr = models.PositiveIntegerField(verbose_name=_("Jahr"))
    brief_nummer_start = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Startnummer Brief"),
        help_text=_("Fortlaufende Startnummer für diesen Brieflauf (muss bestätigt werden)."),
    )
    brief_freitext = models.TextField(
        blank=True,
        verbose_name=_("Brief-Freitext"),
        help_text=_("Optionaler Freitext, der in allen Schreiben dieses Laufs angezeigt wird."),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name=_("Status"),
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Angewendet am"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Abrechnungslauf")
        verbose_name_plural = _("Abrechnungsläufe")
        ordering = ["-jahr", "liegenschaft__name", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["liegenschaft", "jahr"],
                name="uniq_abrechnungslauf_liegenschaft_jahr",
            )
        ]

    def __str__(self) -> str:
        return f"{self.liegenschaft} · {self.jahr}"


class Abrechnungsschreiben(models.Model):
    lauf = models.ForeignKey(
        "Abrechnungslauf",
        on_delete=models.CASCADE,
        related_name="schreiben",
        verbose_name=_("Abrechnungslauf"),
    )
    mietervertrag = models.ForeignKey(
        "LeaseAgreement",
        on_delete=models.PROTECT,
        related_name="abrechnungsschreiben",
        verbose_name=_("Mietvertrag"),
    )
    einheit = models.ForeignKey(
        "Unit",
        on_delete=models.PROTECT,
        related_name="abrechnungsschreiben",
        verbose_name=_("Einheit"),
    )
    pdf_datei = models.ForeignKey(
        "Datei",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abrechnungsschreiben",
        verbose_name=_("Brief-PDF"),
    )
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("PDF erzeugt am"),
    )
    laufende_nummer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Laufende Nummer"),
    )
    settlement_booking_bk = models.ForeignKey(
        "Buchung",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abrechnungsschreiben_settlement_bk",
        verbose_name=_("Ausgleichsbuchung BK"),
    )
    settlement_booking_hk = models.ForeignKey(
        "Buchung",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abrechnungsschreiben_settlement_hk",
        verbose_name=_("Ausgleichsbuchung HK"),
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Angewendet am"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Abrechnungsschreiben")
        verbose_name_plural = _("Abrechnungsschreiben")
        ordering = ["einheit__name", "mietervertrag_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lauf", "mietervertrag"],
                name="uniq_abrechnungsschreiben_lauf_mietervertrag",
            )
        ]

    def __str__(self) -> str:
        return f"{self.lauf} · {self.mietervertrag}"


class VpiIndexValue(models.Model):
    month = models.DateField(
        unique=True,
        verbose_name=_("Monat"),
        help_text=_("Monatswert als erster Tag des Monats (z. B. 01.01.2026)."),
    )
    index_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("VPI 2020"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("VPI-Indexwert")
        verbose_name_plural = _("VPI-Indexwerte")
        ordering = ["-month", "-id"]

    def clean(self):
        super().clean()
        if self.month and self.month.day != 1:
            raise ValidationError({"month": _("Der Monat muss auf den 1. des Monats gesetzt sein.")})

    def __str__(self) -> str:
        return f"{self.month:%m/%Y} · {self.index_value}"


class VpiAdjustmentRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Entwurf")
        APPLIED = "applied", _("Angewendet")

    index_value = models.ForeignKey(
        "VpiIndexValue",
        on_delete=models.PROTECT,
        related_name="adjustment_runs",
        verbose_name=_("VPI-Indexwert"),
    )
    run_date = models.DateField(verbose_name=_("Laufdatum"))
    brief_nummer_start = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Startnummer Brief"),
        help_text=_("Fortlaufende Startnummer für diesen Brieflauf (muss bestätigt werden)."),
    )
    brief_freitext = models.TextField(
        blank=True,
        verbose_name=_("Brief-Freitext"),
        help_text=_("Optionaler Freitext, der in allen Schreiben dieses Laufs angezeigt wird."),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Angewendet am"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("VPI-Anpassungslauf")
        verbose_name_plural = _("VPI-Anpassungsläufe")
        ordering = ["-run_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["index_value"],
                name="uniq_vpi_adjustment_run_index_value",
            )
        ]

    def __str__(self) -> str:
        return f"VPI-Lauf {self.index_value.month:%m/%Y} · {self.run_date:%d.%m.%Y}"


class VpiAdjustmentLetter(models.Model):
    run = models.ForeignKey(
        "VpiAdjustmentRun",
        on_delete=models.CASCADE,
        related_name="letters",
        verbose_name=_("VPI-Anpassungslauf"),
    )
    lease = models.ForeignKey(
        "LeaseAgreement",
        on_delete=models.PROTECT,
        related_name="vpi_adjustment_letters",
        verbose_name=_("Mietvertrag"),
    )
    unit = models.ForeignKey(
        "Unit",
        on_delete=models.PROTECT,
        related_name="vpi_adjustment_letters",
        verbose_name=_("Einheit"),
    )
    effective_date = models.DateField(verbose_name=_("Wirksam ab"))
    old_index_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Alter Indexwert"))
    new_index_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Neuer Indexwert"))
    factor = models.DecimalField(max_digits=12, decimal_places=6, verbose_name=_("Faktor"))
    old_hmz_net = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Alter HMZ Netto"))
    new_hmz_net = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Neuer HMZ Netto"))
    delta_hmz_net = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Differenz HMZ Netto"))
    catchup_months = models.PositiveIntegerField(default=0, verbose_name=_("Monate Nachverrechnung"))
    catchup_net_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Nachverrechnung Netto"),
    )
    catchup_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        verbose_name=_("Nachverrechnung USt (%)"),
    )
    catchup_gross_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Nachverrechnung Brutto"),
    )
    skip_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Übersprungen wegen"),
    )
    pdf_datei = models.ForeignKey(
        "Datei",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vpi_adjustment_letters",
        verbose_name=_("Brief-PDF"),
    )
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("PDF erzeugt am"),
    )
    laufende_nummer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Laufende Nummer"),
    )
    catchup_booking = models.ForeignKey(
        "Buchung",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vpi_adjustment_letters",
        verbose_name=_("Nachverrechnungs-Buchung"),
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Angewendet am"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("VPI-Anpassungsschreiben")
        verbose_name_plural = _("VPI-Anpassungsschreiben")
        ordering = ["unit__name", "lease_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "lease"],
                name="uniq_vpi_adjustment_letter_run_lease",
            )
        ]

    def __str__(self) -> str:
        return f"{self.run} · {self.lease}"


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


class Datei(models.Model):
    class Kategorie(models.TextChoices):
        BILD = "bild", _("Bild")
        DOKUMENT = "dokument", _("Dokument")
        RECHNUNG = "rechnung", _("Rechnung")
        BRIEF = "brief", _("Brief")
        ZAEHLERFOTO = "zaehlerfoto", _("Zählerfoto")
        VERTRAG = "vertrag", _("Vertrag")
        SONSTIGES = "sonstiges", _("Sonstiges")

    file = models.FileField(
        upload_to=datei_upload_to,
        verbose_name=_("Datei"),
        help_text=_("Hochgeladene Binärdatei (z. B. Bild, PDF oder Dokument)."),
    )
    original_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Originalname"),
        help_text=_("Dateiname beim Upload."),
    )
    mime_type = models.CharField(
        max_length=127,
        blank=True,
        verbose_name=_("MIME-Typ"),
        help_text=_("Automatisch erkannter MIME-Typ (z. B. application/pdf)."),
    )
    size_bytes = models.PositiveBigIntegerField(
        default=0,
        verbose_name=_("Dateigröße (Bytes)"),
        help_text=_("Automatisch ermittelte Dateigröße."),
    )
    checksum_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("SHA-256 Checksumme"),
        help_text=_("Wird für Duplikatserkennung verwendet."),
    )
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
        verbose_name=_("Duplikat von"),
        help_text=_(
            "Bei Soft-Dedup wird hier auf die zuerst gespeicherte identische Datei verwiesen."
        ),
    )
    kategorie = models.CharField(
        max_length=20,
        choices=Kategorie.choices,
        default=Kategorie.SONSTIGES,
        verbose_name=_("Kategorie"),
        help_text=_("Fachliche Einordnung der Datei."),
    )
    beschreibung = models.TextField(
        blank=True,
        verbose_name=_("Beschreibung"),
        help_text=_("Optionale Beschreibung zur Datei."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Hochgeladen am"),
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Archiviert"),
        help_text=_("Archivierte Dateien werden nicht mehr in Standardlisten angezeigt."),
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Archiviert am"),
    )
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archivierte_dateien",
        verbose_name=_("Archiviert von"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hochgeladene_dateien",
        verbose_name=_("Hochgeladen von"),
        help_text=_("Benutzer, der die Datei hochgeladen hat."),
    )

    class Meta:
        verbose_name = _("Datei")
        verbose_name_plural = _("Dateien")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["kategorie"], name="datei_kategorie_idx"),
            models.Index(fields=["created_at"], name="datei_created_at_idx"),
            models.Index(fields=["is_archived", "created_at"], name="datei_arch_created_idx"),
        ]

    def __str__(self) -> str:
        return self.original_name or os.path.basename(self.file.name or "") or f"Datei #{self.pk}"

    def set_upload_context(
        self,
        *,
        content_object=None,
        entity_type: str | None = None,
        entity_id: int | str | None = None,
    ):
        if content_object is not None and getattr(content_object, "pk", None) is not None:
            self._upload_content_object = content_object
            self._upload_entity_type = content_object._meta.model_name
            self._upload_entity_id = content_object.pk
            return
        if entity_type and entity_id is not None:
            self._upload_entity_type = str(entity_type)
            self._upload_entity_id = str(entity_id)

    def clean(self):
        super().clean()
        self._sync_file_metadata()
        self._apply_dedup_policy()

    def save(self, *args, **kwargs):
        self._sync_file_metadata()
        self._apply_dedup_policy()
        super().save(*args, **kwargs)

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of_id is not None

    def _sync_file_metadata(self):
        if not self.file:
            return
        current_name = os.path.basename(self.file.name or "")
        if current_name:
            if not self.original_name:
                self.original_name = current_name
            guessed_type = mimetypes.guess_type(self.original_name or current_name)[0]
            self.mime_type = guessed_type or "application/octet-stream"
        file_size = getattr(self.file, "size", None)
        if file_size is not None:
            self.size_bytes = int(file_size)
        checksum = self._compute_sha256_checksum()
        if checksum:
            self.checksum_sha256 = checksum

    def _compute_sha256_checksum(self) -> str:
        if not self.file:
            return ""
        hasher = hashlib.sha256()
        current_position = None
        try:
            if hasattr(self.file, "open"):
                self.file.open("rb")
            stream = getattr(self.file, "file", self.file)
            if hasattr(stream, "tell"):
                try:
                    current_position = stream.tell()
                except (OSError, ValueError):
                    current_position = None
            if hasattr(stream, "seek"):
                stream.seek(0)
            if hasattr(self.file, "chunks"):
                for chunk in self.file.chunks():
                    if chunk:
                        hasher.update(chunk)
            else:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    hasher.update(chunk)
        finally:
            if current_position is not None and hasattr(stream, "seek"):
                stream.seek(current_position)
        return hasher.hexdigest()

    def _apply_dedup_policy(self):
        self.duplicate_of = None
        if not self.checksum_sha256:
            return
        existing = (
            Datei.objects.filter(checksum_sha256=self.checksum_sha256)
            .exclude(pk=self.pk)
            .order_by("id")
            .first()
        )
        if existing is None:
            return
        hard_dedup = bool(getattr(settings, "DATEI_HARD_DEDUP", False))
        if hard_dedup:
            raise ValidationError(
                {"file": _("Diese Datei wurde bereits hochgeladen (gleiche SHA-256 Checksumme).")}
            )
        self.duplicate_of = existing.duplicate_of or existing


class DateiZuordnung(models.Model):
    datei = models.ForeignKey(
        Datei,
        on_delete=models.CASCADE,
        related_name="zuordnungen",
        verbose_name=_("Datei"),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("Objekttyp"),
    )
    object_id = models.PositiveBigIntegerField(
        verbose_name=_("Objekt-ID"),
    )
    content_object = GenericForeignKey("content_type", "object_id")
    sichtbar_fuer_verwalter = models.BooleanField(
        default=True,
        verbose_name=_("Sichtbar für Verwalter"),
    )
    sichtbar_fuer_eigentuemer = models.BooleanField(
        default=False,
        verbose_name=_("Sichtbar für Eigentümer"),
    )
    sichtbar_fuer_mieter = models.BooleanField(
        default=False,
        verbose_name=_("Sichtbar für Mieter"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Zugeordnet am"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datei_zuordnungen",
        verbose_name=_("Zugeordnet von"),
    )

    class Meta:
        verbose_name = _("Datei-Zuordnung")
        verbose_name_plural = _("Datei-Zuordnungen")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="dateizuord_ct_oid_idx"),
            models.Index(fields=["created_at"], name="dateizuord_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.datei} -> {self.content_type}#{self.object_id}"


class DateiOperationLog(models.Model):
    class Operation(models.TextChoices):
        UPLOAD = "upload", _("Upload")
        VIEW = "view", _("Ansicht/Download")
        DELETE = "delete", _("Löschen")

    operation = models.CharField(
        max_length=20,
        choices=Operation.choices,
        verbose_name=_("Operation"),
    )
    success = models.BooleanField(
        default=True,
        verbose_name=_("Erfolgreich"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="datei_operationen",
        verbose_name=_("Benutzer"),
    )
    datei = models.ForeignKey(
        Datei,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operation_logs",
        verbose_name=_("Datei"),
    )
    datei_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Dateiname"),
        help_text=_("Dateiname zum Zeitpunkt der Operation."),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Objekttyp"),
    )
    object_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Objekt-ID"),
    )
    content_object = GenericForeignKey("content_type", "object_id")
    detail = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Details"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Zeitpunkt"),
    )

    class Meta:
        verbose_name = _("Datei-Operation")
        verbose_name_plural = _("Datei-Operationen")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["operation", "created_at"], name="dateiop_op_created_idx"),
            models.Index(fields=["content_type", "object_id"], name="dateiop_ct_oid_idx"),
            models.Index(fields=["created_at"], name="dateiop_created_idx"),
        ]

    def __str__(self) -> str:
        actor = self.actor.get_username() if self.actor else "System"
        return f"{self.get_operation_display()} · {actor} · {self.created_at:%d.%m.%Y %H:%M}"


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
    is_settlement_adjustment = models.BooleanField(
        default=False,
        verbose_name=_("Ausgleich Vorjahresabrechnung"),
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=["mietervertrag", "datum", "kategorie", "typ"],
                condition=models.Q(
                    typ="soll",
                    mietervertrag__isnull=False,
                ),
                name="uniq_buchung_soll_mietvertrag_datum_kategorie_typ",
            ),
        ]

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


class BetriebskostenGruppe(models.Model):
    SYSTEM_KEY_UNGROUPED = "ungrouped"

    name = models.CharField(max_length=120, unique=True, verbose_name=_("Name"))
    sort_order = models.PositiveIntegerField(default=100, verbose_name=_("Sortierung"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    system_key = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Systemschlüssel"),
    )

    class Meta:
        verbose_name = _("Betriebskosten-Gruppe")
        verbose_name_plural = _("Betriebskosten-Gruppen")
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_or_create_ungrouped(cls) -> tuple["BetriebskostenGruppe", bool]:
        return cls.objects.get_or_create(
            system_key=cls.SYSTEM_KEY_UNGROUPED,
            defaults={
                "name": "Ungruppiert",
                "sort_order": 0,
                "is_active": True,
            },
        )


def default_betriebskosten_gruppe_pk() -> int:
    group, _created = BetriebskostenGruppe.get_or_create_ungrouped()
    return group.pk


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
    ausgabengruppe = models.ForeignKey(
        "BetriebskostenGruppe",
        on_delete=models.PROTECT,
        related_name="belege",
        verbose_name=_("Ausgabengruppe"),
        default=default_betriebskosten_gruppe_pk,
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
