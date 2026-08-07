import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models


IBAN_PATTERN = re.compile(r"^[A-Z0-9]{15,34}$")


def normalize_iban(value):
    return "".join(str(value or "").split()).upper()


class BankTransaction(models.Model):
    class Direction(models.TextChoices):
        INCOMING = "incoming", "Eingang"
        OUTGOING = "outgoing", "Ausgang"

    class Status(models.TextChoices):
        IMPORTED = "imported", "Eingelesen"
        MATCHED = "matched", "Zugeordnet"
        REVIEWED = "reviewed", "Geprüft"
        BOOKED = "booked", "Gebucht"

    class Source(models.TextChoices):
        BANK_IMPORT = "bank_import", "Bankimport"
        MANUAL = "manual", "Manuell"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    source_hash = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        default=None,
    )
    matched_rule = models.ForeignKey(
        "MatchingRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    booking_date = models.DateField()
    partner_name = models.CharField(max_length=255, blank=True)
    partner_iban = models.CharField(max_length=34, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    purpose = models.TextField(blank=True)
    notes = models.TextField("Anmerkung", blank=True, default="")
    direction = models.CharField(max_length=8, choices=Direction.choices)
    source = models.CharField(
        max_length=11,
        choices=Source.choices,
        default=Source.BANK_IMPORT,
    )
    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.IMPORTED,
    )
    imported_at = models.DateTimeField(auto_now_add=True)


class MatchingRule(models.Model):
    class Direction(models.TextChoices):
        INCOMING = "incoming", "Eingang"
        OUTGOING = "outgoing", "Ausgang"

    class MatchType(models.TextChoices):
        EXACT = "exact", "Exakter Betrag"
        REGEX = "regex", "Textmuster"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(max_length=255)
    direction = models.CharField(max_length=8, choices=Direction.choices)
    match_type = models.CharField(
        max_length=5,
        choices=MatchType.choices,
        default=MatchType.EXACT,
    )
    iban = models.CharField(max_length=34, blank=True)
    expected_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    text_pattern = models.CharField(max_length=500, blank=True)
    notes = models.TextField("Anmerkung", blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        self.iban = normalize_iban(self.iban)
        self.text_pattern = self.text_pattern or ""
        errors = {}
        if self.match_type == self.MatchType.EXACT:
            if not self.iban:
                errors["iban"] = "Für exakte Regeln ist eine IBAN erforderlich."
            elif not IBAN_PATTERN.fullmatch(self.iban):
                errors["iban"] = (
                    "IBAN muss nach Normalisierung 15 bis 34 alphanumerische Zeichen enthalten."
                )
            if self.expected_amount is not None and self.expected_amount <= 0:
                errors["expected_amount"] = "Der erwartete Betrag muss positiv sein."
            if self.text_pattern.strip():
                errors["text_pattern"] = (
                    "Das Textmuster muss bei exakten Regeln leer sein."
                )
        elif self.match_type == self.MatchType.REGEX:
            if not self.text_pattern.strip():
                errors["text_pattern"] = "Für Textmuster-Regeln ist ein Textmuster erforderlich."
            else:
                try:
                    re.compile(self.text_pattern, re.IGNORECASE)
                except re.error:
                    errors["text_pattern"] = (
                        "Das Textmuster ist kein gültiger regulärer Ausdruck."
                    )
            if self.expected_amount is not None:
                errors["expected_amount"] = (
                    "Der erwartete Betrag muss bei Textmuster-Regeln leer sein."
                )
            if self.iban and not IBAN_PATTERN.fullmatch(self.iban):
                errors["iban"] = (
                    "IBAN muss nach Normalisierung 15 bis 34 alphanumerische Zeichen enthalten."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.iban = normalize_iban(self.iban)
        self.full_clean()
        return super().save(*args, **kwargs)
