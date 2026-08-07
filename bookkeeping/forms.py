import re
from decimal import Decimal

from django import forms
from django.forms.boundfield import BoundField

from .choices import DEFAULT_VAT_SYMBOL, RECEIPT_GROUP_BANK, RECEIPT_GROUP_CHOICES
from .formatting import (
    format_austrian_decimal,
    normalize_austrian_decimal_input,
)
from .models import (
    BankTransaction,
    BookingEntry,
    IBAN_PATTERN,
    MatchingRule,
    normalize_iban,
)


class MatchingRuleBoundField(BoundField):
    """Add the visual and accessibility state for fields with errors."""

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        attrs = dict(attrs or {})
        if self.errors:
            widget_attrs = self.field.widget.attrs
            classes = attrs.get("class", widget_attrs.get("class", ""))
            if "is-invalid" not in classes.split():
                classes = f"{classes} is-invalid".strip()
            attrs["class"] = classes
            attrs["aria-invalid"] = "true"
        return super().as_widget(widget, attrs, only_initial)


class AustrianDecimalField(forms.DecimalField):
    """Decimal input accepting Austrian separators without changing storage."""

    default_error_messages = {
        "invalid": "Bitte einen gültigen Betrag eingeben, zum Beispiel 43,48.",
    }

    def to_python(self, value):
        return super().to_python(normalize_austrian_decimal_input(value))

    def prepare_value(self, value):
        if isinstance(value, Decimal):
            return format_austrian_decimal(value)
        return super().prepare_value(value)


class MatchingRuleForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    expected_amount = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        label="Erwarteter Betrag",
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = MatchingRule
        fields = (
            "name",
            "direction",
            "match_type",
            "iban",
            "expected_amount",
            "text_pattern",
            "notes",
            "active",
        )
        labels = {
            "name": "Bezeichnung",
            "direction": "Richtung",
            "match_type": "Regeltyp",
            "iban": "IBAN",
            "expected_amount": "Erwarteter Betrag",
            "text_pattern": "Textmuster",
            "notes": "Anmerkung",
            "active": "Aktiv",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "direction": forms.Select(attrs={"class": "form-select"}),
            "match_type": forms.Select(attrs={"class": "form-select"}),
            "iban": forms.TextInput(attrs={"class": "form-control"}),
            "text_pattern": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_iban(self):
        iban = normalize_iban(self.cleaned_data.get("iban", ""))
        if iban and not IBAN_PATTERN.fullmatch(iban):
            raise forms.ValidationError(
                "Bitte eine IBAN mit 15 bis 34 alphanumerischen Zeichen eingeben."
            )
        return iban

    def clean(self):
        cleaned_data = super().clean()
        match_type = cleaned_data.get("match_type")
        iban = cleaned_data.get("iban", "")
        expected_amount = cleaned_data.get("expected_amount")
        text_pattern = cleaned_data.get("text_pattern", "") or ""

        if not match_type and "match_type" not in self.data:
            match_type = MatchingRule.MatchType.EXACT
            cleaned_data["match_type"] = match_type

        if match_type == MatchingRule.MatchType.EXACT:
            if not iban:
                self.add_error(
                    "iban", "Für exakte Regeln ist eine IBAN erforderlich."
                )
            if expected_amount is None:
                self.add_error(
                    "expected_amount",
                    "Für exakte Regeln ist ein erwarteter Betrag erforderlich.",
                )
            elif expected_amount <= 0:
                self.add_error(
                    "expected_amount", "Der erwartete Betrag muss positiv sein."
                )
            if text_pattern.strip():
                self.add_error(
                    "text_pattern",
                    "Das Textmuster muss bei exakten Regeln leer sein.",
                )
        elif match_type == MatchingRule.MatchType.REGEX:
            if not text_pattern.strip():
                self.add_error(
                    "text_pattern",
                    "Für Textmuster-Regeln ist ein Textmuster erforderlich.",
                )
            else:
                try:
                    re.compile(text_pattern, re.IGNORECASE)
                except re.error:
                    self.add_error(
                        "text_pattern",
                        "Das Textmuster ist kein gültiger regulärer Ausdruck.",
                    )
            if expected_amount is not None:
                self.add_error(
                    "expected_amount",
                    "Der erwartete Betrag muss bei Textmuster-Regeln leer sein.",
                )

        return cleaned_data


class BankTransactionNoteForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    class Meta:
        model = BankTransaction
        fields = ("notes",)
        labels = {"notes": "Anmerkung"}
        widgets = {
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 5}
            ),
        }


class BookingEntryForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    receipt_group = forms.ChoiceField(
        choices=RECEIPT_GROUP_CHOICES,
        required=False,
        disabled=True,
        label="Belegkreis",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    receipt_number = forms.CharField(
        required=False,
        disabled=True,
        label="Belegnummer",
        widget=forms.TextInput(
            attrs={"class": "form-control", "readonly": "readonly"}
        ),
    )
    payment_date = forms.DateField(
        required=False,
        disabled=True,
        label="Zahlungsdatum",
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={"class": "form-control", "readonly": "readonly"},
        ),
    )
    gross_amount = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        label="Bruttobetrag",
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )
    notes = forms.CharField(
        required=False,
        label="Anmerkung",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    class Meta:
        model = BookingEntry
        fields = (
            "receipt_group",
            "receipt_number",
            "payment_date",
            "booking_text",
            "invoice_number",
            "partner_name",
            "gross_amount",
            "vat_symbol",
            "category",
        )
        labels = {
            "receipt_group": "Belegkreis",
            "receipt_number": "Belegnummer",
            "payment_date": "Zahlungsdatum",
            "booking_text": "Buchungstext",
            "invoice_number": "Rechnungsnummer",
            "partner_name": "Lieferant/Kunde",
            "gross_amount": "Bruttobetrag",
            "vat_symbol": "USt-Symbol",
            "category": "Kategorie",
        }
        widgets = {
            "booking_text": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "partner_name": forms.TextInput(attrs={"class": "form-control"}),
            "vat_symbol": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, bank_transaction=None, final=False, **kwargs):
        self.bank_transaction = bank_transaction
        self.final = final
        super().__init__(*args, **kwargs)

        required_fields = (
            "receipt_group",
            "payment_date",
            "booking_text",
            "partner_name",
            "gross_amount",
            "vat_symbol",
            "category",
        )
        for field_name in required_fields:
            self.fields[field_name].required = final

        if bank_transaction is not None:
            effective_payment_date = (
                bank_transaction.value_date or bank_transaction.booking_date
            )
            if not self.instance._state.adding:
                effective_payment_date = self.instance.payment_date
            self.initial["receipt_group"] = RECEIPT_GROUP_BANK
            self.initial["payment_date"] = effective_payment_date
            self.initial["receipt_number"] = str(effective_payment_date.month)
            if self.instance._state.adding:
                self.initial.setdefault("partner_name", bank_transaction.partner_name)
                self.initial.setdefault("booking_text", bank_transaction.purpose)
                self.initial.setdefault("gross_amount", bank_transaction.amount)
                self.initial.setdefault("vat_symbol", DEFAULT_VAT_SYMBOL)
            self.initial.setdefault("notes", bank_transaction.notes)

    def clean(self):
        cleaned_data = super().clean()
        if self.bank_transaction is not None:
            effective_payment_date = (
                self.instance.payment_date
                if not self.instance._state.adding
                else (
                    self.bank_transaction.value_date
                    or self.bank_transaction.booking_date
                )
            )
            cleaned_data["receipt_group"] = RECEIPT_GROUP_BANK
            cleaned_data["payment_date"] = effective_payment_date
            cleaned_data["receipt_number"] = str(effective_payment_date.month)

        if not self.final and self.bank_transaction is not None:
            defaults = {
                "partner_name": self.bank_transaction.partner_name,
                "booking_text": self.bank_transaction.purpose,
                "gross_amount": self.bank_transaction.amount,
            }
            for field_name, default in defaults.items():
                if cleaned_data.get(field_name) in (None, ""):
                    cleaned_data[field_name] = default
        return cleaned_data
