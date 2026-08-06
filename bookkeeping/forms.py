import re

from django import forms
from django.forms.boundfield import BoundField

from .models import IBAN_PATTERN, MatchingRule, normalize_iban


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


class MatchingRuleForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    expected_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        label="Erwarteter Betrag",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
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
            "active",
        )
        labels = {
            "name": "Bezeichnung",
            "direction": "Richtung",
            "match_type": "Regeltyp",
            "iban": "IBAN",
            "expected_amount": "Erwarteter Betrag",
            "text_pattern": "Textmuster",
            "active": "Aktiv",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "direction": forms.Select(attrs={"class": "form-select"}),
            "match_type": forms.Select(attrs={"class": "form-select"}),
            "iban": forms.TextInput(attrs={"class": "form-control"}),
            "text_pattern": forms.TextInput(attrs={"class": "form-control"}),
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
