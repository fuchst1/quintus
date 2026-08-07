import re
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from .choices import (
    CATEGORY_CHOICES,
    DEFAULT_VAT_SYMBOL,
    RECEIPT_GROUP_CHOICES,
    VAT_SYMBOL_CHOICES,
)

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
    value_date = models.DateField("Valutadatum", null=True, blank=True)
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
    previous_version = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="next_version",
        null=True,
        blank=True,
    )
    version_number = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    change_reason = models.TextField(
        "Änderungsgrund",
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _immutable_used_fields = (
        "name",
        "direction",
        "match_type",
        "iban",
        "expected_amount",
        "text_pattern",
        "notes",
        "change_reason",
        "previous_version_id",
        "version_number",
    )

    def __str__(self):
        return f"{self.name} – Version {self.version_number}"

    @property
    def is_used(self):
        return self.transactions.exists()

    @property
    def linked_transaction_count(self):
        annotated_count = getattr(self, "_linked_transaction_count", None)
        if annotated_count is not None:
            return annotated_count
        return self.transactions.count()

    @property
    def has_successor(self):
        return MatchingRule.objects.filter(previous_version=self).exists()

    def clean(self):
        self.iban = normalize_iban(self.iban)
        self.text_pattern = self.text_pattern or ""
        errors = {}
        if self.previous_version_id is None:
            if self.version_number != 1:
                errors["version_number"] = (
                    "Regeln ohne Vorgängerversion müssen Version 1 sein."
                )
        else:
            previous_version = self.previous_version
            if self.version_number != previous_version.version_number + 1:
                errors["version_number"] = (
                    "Die Versionsnummer muss auf die Vorgängerversion folgen."
                )
            if not self.change_reason.strip():
                errors["change_reason"] = "Bitte einen Änderungsgrund angeben."
            if MatchingRule.objects.filter(
                previous_version_id=self.previous_version_id
            ).exclude(pk=self.pk).exists():
                errors["previous_version"] = (
                    "Diese Regelversion hat bereits eine Nachfolgeversion."
                )

        if self.pk:
            try:
                stored_rule = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                stored_rule = None
            if stored_rule is not None and stored_rule.is_used:
                changed_fields = [
                    field_name
                    for field_name in self._immutable_used_fields
                    if getattr(stored_rule, field_name) != getattr(self, field_name)
                ]
                if changed_fields:
                    errors["__all__"] = (
                        "Diese Regel wurde bereits verwendet und ist daher "
                        "schreibgeschützt."
                    )
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

    def delete(self, *args, **kwargs):
        if self.is_used:
            raise ValidationError(
                "Diese Regel wurde bereits verwendet und kann nicht gelöscht werden."
            )
        if self.has_successor:
            raise ValidationError(
                "Diese Regel ist eine Vorgängerversion und kann nicht gelöscht werden."
            )
        return super().delete(*args, **kwargs)


class MatchingRuleBookingTemplate(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    matching_rule = models.ForeignKey(
        MatchingRule,
        on_delete=models.CASCADE,
        related_name="booking_templates",
    )
    position = models.PositiveIntegerField("Position")
    booking_text = models.TextField("Buchungstext", blank=True)
    invoice_number = models.CharField(
        "Rechnungsnummer",
        max_length=100,
        blank=True,
    )
    partner_name = models.CharField(
        "Lieferant/Kunde",
        max_length=255,
        blank=True,
    )
    gross_amount = models.DecimalField(
        "Betrag",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    vat_symbol = models.CharField(
        "USt-Symbol",
        max_length=2,
        choices=VAT_SYMBOL_CHOICES,
        default=DEFAULT_VAT_SYMBOL,
    )
    category = models.CharField(
        "Kategorie",
        max_length=4,
        choices=CATEGORY_CHOICES,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("matching_rule", "position"),
                name="unique_matching_rule_booking_template_position",
            ),
        ]

    def clean(self):
        errors = {}
        if self.matching_rule_id and self.matching_rule.is_used:
            try:
                stored_template = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                stored_template = None
            if stored_template is None or any(
                getattr(stored_template, field_name) != getattr(self, field_name)
                for field_name in (
                    "matching_rule_id",
                    "position",
                    "booking_text",
                    "invoice_number",
                    "partner_name",
                    "gross_amount",
                    "vat_symbol",
                    "category",
                )
            ):
                errors["__all__"] = (
                    "Diese Regel wurde bereits verwendet und ist daher "
                    "schreibgeschützt."
                )
        if self.gross_amount is not None and self.gross_amount <= 0:
            errors["gross_amount"] = "Der Betrag muss positiv sein."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.matching_rule.is_used:
            raise ValidationError(
                "Diese Regel wurde bereits verwendet und ist daher schreibgeschützt."
            )
        return super().delete(*args, **kwargs)


class BookingEntry(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    bank_transaction = models.ForeignKey(
        BankTransaction,
        on_delete=models.CASCADE,
        related_name="booking_entries",
    )
    receipt_group = models.CharField(
        "Belegkreis",
        max_length=2,
        choices=RECEIPT_GROUP_CHOICES,
        blank=True,
    )
    receipt_number = models.CharField(
        "Belegnummer",
        max_length=100,
        blank=True,
    )
    payment_date = models.DateField("Zahlungsdatum")
    booking_text = models.TextField("Buchungstext")
    invoice_number = models.CharField(
        "Rechnungsnummer",
        max_length=100,
        blank=True,
    )
    partner_name = models.CharField("Lieferant/Kunde", max_length=255)
    gross_amount = models.DecimalField(
        "Bruttobetrag",
        max_digits=14,
        decimal_places=2,
    )
    vat_symbol = models.CharField(
        "USt-Symbol",
        max_length=2,
        choices=VAT_SYMBOL_CHOICES,
        blank=True,
        default=DEFAULT_VAT_SYMBOL,
    )
    category = models.CharField(
        "Kategorie",
        max_length=4,
        choices=CATEGORY_CHOICES,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
