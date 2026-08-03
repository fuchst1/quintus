from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bookkeeping.storage_paths import kontenplan_vorlage_upload_to


iban_validator = RegexValidator(
    regex=r"^[A-Z0-9]{15,34}$",
    message=_("Die normalisierte IBAN darf nur Großbuchstaben und Ziffern enthalten."),
)


class Mandant(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    kurzname = models.CharField(max_length=40, unique=True, verbose_name=_("Kurzname"))
    steuerliche_id = models.CharField(max_length=100, blank=True, verbose_name=_("Steuerliche ID"))
    waehrung = models.CharField(max_length=3, default="EUR", verbose_name=_("Währung"))
    aktiv = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    erstellt_am = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))
    aktualisiert_am = models.DateTimeField(auto_now=True, verbose_name=_("Aktualisiert am"))

    class Meta:
        verbose_name = _("Mandant")
        verbose_name_plural = _("Mandanten")
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


class Bankkonto(models.Model):
    mandant = models.ForeignKey(Mandant, on_delete=models.PROTECT, related_name="bankkonten")
    iban_normalisiert = models.CharField(max_length=34, validators=[iban_validator], verbose_name=_("IBAN"))
    bezeichnung = models.CharField(max_length=255, verbose_name=_("Bezeichnung"))
    waehrung = models.CharField(max_length=3, default="EUR", verbose_name=_("Währung"))
    aktiv_von = models.DateField(null=True, blank=True, verbose_name=_("Aktiv von"))
    aktiv_bis = models.DateField(null=True, blank=True, verbose_name=_("Aktiv bis"))

    class Meta:
        verbose_name = _("Bankkonto")
        verbose_name_plural = _("Bankkonten")
        ordering = ["mandant__name", "bezeichnung", "id"]
        constraints = [
            models.UniqueConstraint(fields=["mandant", "iban_normalisiert"], name="bk_unique_mandant_iban"),
        ]

    def clean_fields(self, exclude=None) -> None:
        if self.iban_normalisiert:
            self.iban_normalisiert = self.iban_normalisiert.replace(" ", "").upper()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        super().clean()
        if self.aktiv_von and self.aktiv_bis and self.aktiv_bis < self.aktiv_von:
            from django.core.exceptions import ValidationError

            raise ValidationError({"aktiv_bis": _("Das Ende darf nicht vor dem Beginn liegen.")})

    def __str__(self) -> str:
        return f"{self.mandant} · {self.bezeichnung}"


class Kostenstelle(models.Model):
    mandant = models.ForeignKey(Mandant, on_delete=models.PROTECT, related_name="kostenstellen")
    code = models.CharField(max_length=80, verbose_name=_("Code"))
    bezeichnung = models.CharField(max_length=255, verbose_name=_("Bezeichnung"))
    external_source = models.CharField(max_length=80, blank=True, verbose_name=_("Externe Quelle"))
    external_id = models.CharField(max_length=120, blank=True, verbose_name=_("Externe ID"))
    aktiv_von = models.DateField(null=True, blank=True, verbose_name=_("Aktiv von"))
    aktiv_bis = models.DateField(null=True, blank=True, verbose_name=_("Aktiv bis"))

    class Meta:
        verbose_name = _("Kostenstelle")
        verbose_name_plural = _("Kostenstellen")
        ordering = ["mandant__name", "code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["mandant", "code"], name="bk_unique_mandant_kostenstelle"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.aktiv_von and self.aktiv_bis and self.aktiv_bis < self.aktiv_von:
            from django.core.exceptions import ValidationError

            raise ValidationError({"aktiv_bis": _("Das Ende darf nicht vor dem Beginn liegen.")})

    def __str__(self) -> str:
        return f"{self.mandant} · {self.code}"


class KontenplanVersion(models.Model):
    mandant = models.ForeignKey(Mandant, on_delete=models.PROTECT, related_name="kontenplanversionen")
    bezeichnung = models.CharField(max_length=255, verbose_name=_("Bezeichnung"))
    gueltig_ab = models.DateField(verbose_name=_("Gültig ab"))
    vorlage_datei = models.FileField(upload_to=kontenplan_vorlage_upload_to, verbose_name=_("Originalvorlage"))
    vorlage_dateiname = models.CharField(max_length=255, verbose_name=_("Originaldateiname"))
    vorlage_sha256 = models.CharField(max_length=64, verbose_name=_("SHA-256"))
    importiert_am = models.DateTimeField(auto_now_add=True, verbose_name=_("Importiert am"))
    aktiv = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        verbose_name = _("Kontenplanversion")
        verbose_name_plural = _("Kontenplanversionen")
        ordering = ["mandant__name", "-gueltig_ab", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["mandant", "vorlage_sha256"], name="bk_unique_mandant_vorlage_hash"),
            models.UniqueConstraint(
                fields=["mandant"],
                condition=Q(aktiv=True),
                name="bk_one_active_kontenplan_per_mandant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.mandant} · {self.bezeichnung}"


class KontenplanEintrag(models.Model):
    version = models.ForeignKey(KontenplanVersion, on_delete=models.CASCADE, related_name="eintraege")
    kategorie_text = models.CharField(max_length=255, verbose_name=_("Kategorie"))
    kontonummer = models.CharField(max_length=80, blank=True, verbose_name=_("Kontonummer"))
    bezeichnung = models.CharField(max_length=255, blank=True, verbose_name=_("Bezeichnung"))
    kontoart = models.CharField(max_length=120, blank=True, verbose_name=_("Kontoart"))
    kontoklasse = models.CharField(max_length=120, blank=True, verbose_name=_("Kontoklasse"))
    ust_stcode = models.CharField(max_length=40, blank=True, verbose_name=_("USt-Steuercode"))
    ust_prozent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("USt (%)"))
    aktiv = models.BooleanField(default=True, verbose_name=_("Aktiv"))

    class Meta:
        verbose_name = _("Kontenplaneintrag")
        verbose_name_plural = _("Kontenplaneinträge")
        ordering = ["kategorie_text", "id"]
        constraints = [
            models.UniqueConstraint(fields=["version", "kategorie_text"], name="bk_unique_version_kategorie"),
        ]

    def __str__(self) -> str:
        return self.kategorie_text
