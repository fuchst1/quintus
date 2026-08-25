import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms.boundfield import BoundField
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from .choices import (
    DEFAULT_VAT_SYMBOL,
    RECEIPT_GROUP_BANK,
    RECEIPT_GROUP_CHOICES,
    RECEIPT_GROUP_PRIVATE,
)
from .category_display import category_description_choices
from .formatting import (
    format_austrian_decimal,
    normalize_austrian_decimal_input,
)
from .models import (
    BankTransaction,
    BankStatement,
    BookingEntry,
    IBAN_PATTERN,
    MatchingRule,
    MatchingRuleBookingTemplate,
    ManualInvoice,
    ManualInvoiceEntry,
    QuarterBalance,
    normalize_iban,
)


ROUNDING_DIFFERENCE = Decimal("0.01")


def _rounding_difference_message(total, bank_amount, difference):
    return (
        f"Buchungszeilen: {format_austrian_decimal(total)} EUR · "
        f"Banktransaktion: {format_austrian_decimal(bank_amount)} EUR · "
        f"Differenz: {format_austrian_decimal(difference)} EUR"
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


class QuarterBalanceForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    opening_balance = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        label="Kontostand Quartalsbeginn",
        error_messages={
            "invalid": "Bitte einen gültigen Kontostand eingeben, zum Beispiel 1.234,56.",
            "max_decimal_places": "Bitte höchstens zwei Nachkommastellen eingeben.",
            "max_digits": "Bitte einen gültigen Kontostand eingeben.",
        },
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )
    closing_balance = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        label="Kontostand Quartalsende",
        error_messages={
            "invalid": "Bitte einen gültigen Kontostand eingeben, zum Beispiel 1.234,56.",
            "max_decimal_places": "Bitte höchstens zwei Nachkommastellen eingeben.",
            "max_digits": "Bitte einen gültigen Kontostand eingeben.",
        },
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = QuarterBalance
        fields = ("opening_balance", "closing_balance")


class BankStatementUploadForm(forms.Form):
    max_file_size_bytes = 25 * 1024 * 1024
    pdf = forms.FileField(
        label="Kontoauszug als PDF",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "application/pdf,.pdf"}
        ),
    )

    def clean_pdf(self):
        uploaded_file = self.cleaned_data["pdf"]
        if uploaded_file.size > self.max_file_size_bytes:
            raise forms.ValidationError(
                "Die PDF-Datei darf höchstens 25 MB groß sein."
            )
        if not str(uploaded_file.name or "").lower().endswith(".pdf"):
            raise forms.ValidationError("Bitte eine PDF-Datei auswählen.")
        current_position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        file_header = uploaded_file.read(5)
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(current_position)
        if file_header != b"%PDF-":
            raise forms.ValidationError("Die Datei ist kein gültiges PDF.")
        return uploaded_file


class ManualInvoiceUploadForm(BankStatementUploadForm):
    pdf = forms.FileField(
        label="Rechnung als PDF",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "application/pdf,.pdf"}
        ),
    )


class SupportingDocumentUploadForm(forms.Form):
    max_file_size_bytes = BankStatementUploadForm.max_file_size_bytes
    pdf = forms.FileField(
        label="PDF-Beleg",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "application/pdf,.pdf"}
        ),
    )

    def clean_pdf(self):
        uploaded_file = self.cleaned_data["pdf"]
        if uploaded_file.size > self.max_file_size_bytes:
            raise forms.ValidationError(
                "Die PDF-Datei darf höchstens 25 MB groß sein."
            )
        if not str(uploaded_file.name or "").lower().endswith(".pdf"):
            raise forms.ValidationError("Bitte eine PDF-Datei auswählen.")
        if str(getattr(uploaded_file, "content_type", "") or "").lower() not in {
            "application/pdf",
            "application/x-pdf",
        }:
            raise forms.ValidationError("Die Datei muss den Content-Type application/pdf haben.")
        current_position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        file_header = uploaded_file.read(5)
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(current_position)
        if file_header != b"%PDF-":
            raise forms.ValidationError("Die Datei ist kein gültiges PDF.")
        return uploaded_file


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
    amount_tolerance_type = forms.ChoiceField(
        choices=MatchingRule.ToleranceType.choices,
        required=False,
        label="Toleranz",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount_tolerance_value = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        label="Toleranzwert",
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
            "amount_tolerance_type",
            "amount_tolerance_value",
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
            "amount_tolerance_type": "Toleranz",
            "amount_tolerance_value": "Toleranzwert",
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

        tolerance_type = (
            cleaned_data.get("amount_tolerance_type")
            or MatchingRule.ToleranceType.NONE
        )
        cleaned_data["amount_tolerance_type"] = tolerance_type
        tolerance_value = cleaned_data.get("amount_tolerance_value")
        if tolerance_type == MatchingRule.ToleranceType.NONE:
            cleaned_data["amount_tolerance_value"] = None
        elif tolerance_type:
            if match_type != MatchingRule.MatchType.EXACT or expected_amount is None:
                self.add_error(
                    "amount_tolerance_type",
                    "Eine Betragstoleranz ist nur bei exakten Regeln mit "
                    "erwartetem Betrag möglich.",
                )
            elif tolerance_value is None or tolerance_value <= 0:
                self.add_error(
                    "amount_tolerance_value",
                    "Bitte einen Toleranzwert größer 0 angeben.",
                )
            elif (
                tolerance_type == MatchingRule.ToleranceType.PERCENT
                and tolerance_value > 100
            ):
                self.add_error(
                    "amount_tolerance_value",
                    "Die Toleranz darf 100 % nicht überschreiten.",
                )

        return cleaned_data


class MatchingRuleVersionForm(MatchingRuleForm):
    change_reason = forms.CharField(
        required=True,
        label="Änderungsgrund",
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2}
        ),
    )

    class Meta(MatchingRuleForm.Meta):
        fields = MatchingRuleForm.Meta.fields + ("change_reason",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["active"].initial = True
        self.fields["active"].disabled = True

    def clean_change_reason(self):
        change_reason = self.cleaned_data.get("change_reason", "").strip()
        if not change_reason:
            raise forms.ValidationError("Bitte einen Änderungsgrund angeben.")
        return change_reason


class BankTransactionNoteForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    class Meta:
        model = BankTransaction
        fields = ("notes",)
        labels = {"notes": "Anmerkung (optional)"}
        widgets = {
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
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
            "booking_text": forms.TextInput(attrs={"class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "partner_name": forms.TextInput(attrs={"class": "form-control"}),
            "vat_symbol": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, bank_transaction=None, final=False, **kwargs):
        self.bank_transaction = bank_transaction
        self.final = final
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = category_description_choices()

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


class BookingEntryFormSetBase(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rounding_difference = Decimal("0")

    def _active_forms(self):
        return [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]

    def clean(self):
        super().clean()
        valid_entry_ids = {
            str(entry_id)
            for entry_id in self.queryset.values_list("pk", flat=True)
        }
        submitted_entry_ids = [
            self.data.get(f"{self.add_prefix(index)}-id")
            for index in range(self.total_form_count())
        ]
        if any(
            entry_id and entry_id not in valid_entry_ids
            for entry_id in submitted_entry_ids
        ):
            raise ValidationError(
                "Eine Buchungszeile gehört nicht zu dieser Banktransaktion."
            )
        if any(self.errors):
            return

        if not self.form_kwargs.get("final"):
            return

        active_forms = self._active_forms()
        if not active_forms:
            raise ValidationError("Mindestens eine Buchungszeile ist erforderlich.")

        bank_transaction = self.form_kwargs.get("bank_transaction")
        if bank_transaction is None:
            return
        total = sum(
            (form.cleaned_data.get("gross_amount") or Decimal("0")
             for form in active_forms),
            Decimal("0"),
        )
        self.rounding_difference = bank_transaction.amount - total
        if abs(self.rounding_difference) > ROUNDING_DIFFERENCE:
            raise ValidationError(
                _rounding_difference_message(
                    total,
                    bank_transaction.amount,
                    self.rounding_difference,
                )
            )

    def apply_rounding_difference(self):
        if abs(self.rounding_difference) != ROUNDING_DIFFERENCE:
            return False
        active_forms = self._active_forms()
        if not active_forms:
            return False

        target_form = active_forms[0]
        for form in active_forms[1:]:
            if abs(form.cleaned_data["gross_amount"]) > abs(
                target_form.cleaned_data["gross_amount"]
            ):
                target_form = form
        adjusted_amount = (
            target_form.cleaned_data["gross_amount"]
            + self.rounding_difference
        )
        target_form.cleaned_data["gross_amount"] = adjusted_amount
        target_form.instance.gross_amount = adjusted_amount
        return True

    def save_new_objects(self, commit=True):
        self.new_objects = []
        initial_row_count = getattr(self, "initial_row_count", 0)
        for index, form in enumerate(self.extra_forms):
            if not form.has_changed() and index >= initial_row_count:
                continue
            if not form.cleaned_data:
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            self.new_objects.append(self.save_new(form, commit=commit))
        return self.new_objects

    def save(self, commit=True):
        objects = super().save(commit=commit)
        active_instances = [
            form.instance
            for form in self._active_forms()
            if form.instance.pk
        ]
        if not active_instances:
            active_instances = list(objects)
        if commit:
            for position, instance in enumerate(active_instances, start=1):
                if instance.position != position:
                    type(instance).objects.filter(pk=instance.pk).update(
                        position=position
                    )
                    instance.position = position
        else:
            for position, instance in enumerate(active_instances, start=1):
                instance.position = position
        return objects


BookingEntryFormSet = inlineformset_factory(
    BankTransaction,
    BookingEntry,
    form=BookingEntryForm,
    formset=BookingEntryFormSetBase,
    extra=0,
    can_delete=True,
)


class ManualInvoiceForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    invoice_date = forms.DateField(
        required=False,
        label="Rechnungsdatum",
        input_formats=("%d.%m.%Y", "%Y-%m-%d"),
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={"class": "form-control", "placeholder": "TT.MM.JJJJ"},
        ),
    )
    payment_date = forms.DateField(
        required=False,
        label="Zahlungsdatum",
        input_formats=("%d.%m.%Y", "%Y-%m-%d"),
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={"class": "form-control", "placeholder": "TT.MM.JJJJ"},
        ),
    )
    gross_amount = AustrianDecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        label="Gesamtbruttobetrag",
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = ManualInvoice
        fields = (
            "invoice_number",
            "invoice_date",
            "payment_date",
            "partner_name",
            "gross_amount",
            "notes",
        )
        labels = {
            "invoice_number": "Rechnungsnummer",
            "invoice_date": "Rechnungsdatum",
            "payment_date": "Zahlungsdatum",
            "partner_name": "Lieferant/Kunde",
            "gross_amount": "Gesamtbruttobetrag",
            "notes": "Anmerkung",
        }
        widgets = {
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "partner_name": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
        }

    def __init__(self, *args, final=False, **kwargs):
        self.final = final
        super().__init__(*args, **kwargs)
        if final:
            for field_name in ("payment_date", "partner_name", "gross_amount"):
                self.fields[field_name].required = True


class ManualInvoiceEntryForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    position = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    receipt_group = forms.ChoiceField(
        choices=((RECEIPT_GROUP_PRIVATE, "PR – Privat"),),
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
        input_formats=("%d.%m.%Y", "%Y-%m-%d"),
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={"class": "form-control", "readonly": "readonly"},
        ),
    )
    gross_amount = AustrianDecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        label="Bruttobetrag",
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = ManualInvoiceEntry
        fields = (
            "position",
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
            "position": "Position",
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
            "booking_text": forms.TextInput(attrs={"class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "partner_name": forms.TextInput(attrs={"class": "form-control"}),
            "vat_symbol": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, manual_invoice=None, final=False, **kwargs):
        self.manual_invoice = manual_invoice
        self.final = final
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = category_description_choices()
        for field_name in (
            "booking_text",
            "partner_name",
            "gross_amount",
            "vat_symbol",
            "category",
        ):
            self.fields[field_name].required = final
        invoice = manual_invoice
        if invoice is not None:
            self.initial.setdefault("receipt_group", RECEIPT_GROUP_PRIVATE)
            if invoice.payment_date:
                self.initial["payment_date"] = invoice.payment_date
                self.initial["receipt_number"] = str(invoice.payment_date.month)
            self.initial.setdefault("invoice_number", invoice.invoice_number)
            self.initial.setdefault("partner_name", invoice.partner_name)

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["receipt_group"] = RECEIPT_GROUP_PRIVATE
        invoice = self.manual_invoice
        if invoice is not None and invoice.payment_date:
            cleaned_data["payment_date"] = invoice.payment_date
            cleaned_data["receipt_number"] = str(invoice.payment_date.month)
        if invoice is not None:
            if not cleaned_data.get("invoice_number"):
                cleaned_data["invoice_number"] = invoice.invoice_number
            if not cleaned_data.get("partner_name") and invoice.partner_name:
                cleaned_data["partner_name"] = invoice.partner_name
        return cleaned_data


def _manual_rounding_difference_message(total, invoice_amount, difference):
    return (
        f"Buchungszeilen: {format_austrian_decimal(total)} EUR · "
        f"Rechnung: {format_austrian_decimal(invoice_amount)} EUR · "
        f"Differenz: {format_austrian_decimal(difference)} EUR"
    )


class ManualInvoiceEntryFormSetBase(BaseInlineFormSet):
    def __init__(self, *args, manual_invoice=None, final=False, **kwargs):
        self.manual_invoice = manual_invoice
        self.final = final
        self.rounding_difference = Decimal("0")
        super().__init__(*args, **kwargs)

    def _active_forms(self):
        return [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]

    def clean(self):
        super().clean()
        if any(self.errors) or not self.final:
            return
        active_forms = self._active_forms()
        if not active_forms:
            raise ValidationError("Mindestens eine Buchungszeile ist erforderlich.")
        invoice_amount = (
            self.manual_invoice.gross_amount
            if self.manual_invoice is not None
            else None
        )
        if invoice_amount is None:
            return
        total = sum(
            (form.cleaned_data.get("gross_amount") or Decimal("0")
             for form in active_forms),
            Decimal("0"),
        )
        self.rounding_difference = invoice_amount - total
        if abs(self.rounding_difference) > ROUNDING_DIFFERENCE:
            raise ValidationError(
                _manual_rounding_difference_message(
                    total,
                    invoice_amount,
                    self.rounding_difference,
                )
            )

    def apply_rounding_difference(self):
        if abs(self.rounding_difference) != ROUNDING_DIFFERENCE:
            return False
        active_forms = self._active_forms()
        if not active_forms:
            return False
        target_form = active_forms[0]
        for form in active_forms[1:]:
            if abs(form.cleaned_data["gross_amount"]) > abs(
                target_form.cleaned_data["gross_amount"]
            ):
                target_form = form
        adjusted_amount = (
            target_form.cleaned_data["gross_amount"] + self.rounding_difference
        )
        target_form.cleaned_data["gross_amount"] = adjusted_amount
        target_form.instance.gross_amount = adjusted_amount
        return True

    def save(self, commit=True):
        active_forms = self._active_forms()
        for position, form in enumerate(active_forms, start=1):
            # Position is required by the model.  Set it before the parent
            # formset saves new instances; an empty hidden position field must
            # not result in NULL being written to the database.
            form.instance.position = position
            form.instance.receipt_group = RECEIPT_GROUP_PRIVATE

        objects = super().save(commit=commit)
        return objects


ManualInvoiceEntryFormSet = inlineformset_factory(
    ManualInvoice,
    ManualInvoiceEntry,
    form=ManualInvoiceEntryForm,
    formset=ManualInvoiceEntryFormSetBase,
    extra=0,
    can_delete=True,
)


class MatchingRuleBookingTemplateForm(forms.ModelForm):
    bound_field_class = MatchingRuleBoundField

    position = forms.IntegerField(
        required=False,
        min_value=1,
        label="Position",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1, "inputmode": "numeric"}
        ),
    )
    gross_amount = AustrianDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        label="Betrag",
        error_messages={"min_value": "Der Betrag muss positiv sein."},
        widget=forms.TextInput(
            attrs={"class": "form-control", "inputmode": "decimal"}
        ),
    )

    class Meta:
        model = MatchingRuleBookingTemplate
        fields = (
            "position",
            "booking_text",
            "invoice_number",
            "partner_name",
            "gross_amount",
            "vat_symbol",
            "category",
        )
        labels = {
            "position": "Position",
            "booking_text": "Buchungstext",
            "invoice_number": "Rechnungsnummer",
            "partner_name": "Lieferant/Kunde",
            "gross_amount": "Betrag",
            "vat_symbol": "USt-Symbol",
            "category": "Kategorie",
        }
        widgets = {
            "booking_text": forms.TextInput(attrs={"class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "partner_name": forms.TextInput(attrs={"class": "form-control"}),
            "vat_symbol": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = category_description_choices()
        if self.instance._state.adding:
            self.initial.setdefault("vat_symbol", DEFAULT_VAT_SYMBOL)

    def clean_position(self):
        return self.cleaned_data.get("position")


class MatchingRuleBookingTemplateBaseFormSet(BaseInlineFormSet):
    def clean(self):
        active_forms = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if not active_forms:
            return

        missing_position_forms = [
            form
            for form in active_forms
            if "position" in form.cleaned_data
            and form.cleaned_data["position"] is None
        ]
        if missing_position_forms:
            for form in missing_position_forms:
                form.add_error(
                    "position",
                    "Bitte die fehlenden Angaben im Feld „Position“ ergänzen.",
                )
            raise ValidationError(
                "Bitte die fehlenden Angaben im Feld „Position“ ergänzen."
            )

        if any(self.errors):
            return

        positions = [form.cleaned_data["position"] for form in active_forms]
        if len(positions) != len(set(positions)):
            raise ValidationError(
                "Die Angaben im Feld „Position“ müssen eindeutig sein."
            )

        super().clean()

        amounts = [form.cleaned_data.get("gross_amount") for form in active_forms]
        rest_count = sum(amount is None for amount in amounts)
        if rest_count > 1:
            raise ValidationError(
                "Es darf höchstens eine Ergebniszeile mit Restbetrag geben."
            )

        matching_rule = self.instance
        if matching_rule.match_type == MatchingRule.MatchType.REGEX:
            if rest_count != 1:
                raise ValidationError(
                    "Textmuster-Regeln benötigen genau eine Ergebniszeile mit Restbetrag."
                )
            return

        if matching_rule.match_type != MatchingRule.MatchType.EXACT:
            return
        if matching_rule.expected_amount is None:
            return

        fixed_total = sum(
            (amount for amount in amounts if amount is not None),
            Decimal("0"),
        )
        if rest_count == 1 and fixed_total >= matching_rule.expected_amount:
            raise ValidationError(
                "Die festen Beträge müssen kleiner als der erwartete Betrag sein."
            )
        elif rest_count == 0 and fixed_total != matching_rule.expected_amount:
            raise ValidationError(
                "Die Summe der Ergebniszeilen muss dem erwarteten Betrag entsprechen."
            )

    def save(self, commit=True):
        if not self.is_bound:
            return []

        active_instances = []
        deleted_instances = []

        for form in self.forms:
            if not form.cleaned_data:
                continue
            instance = form.instance
            if form.cleaned_data.get("DELETE"):
                if instance.pk:
                    deleted_instances.append(instance)
                continue

            instance = form.save(commit=False)
            instance.matching_rule = self.instance
            active_instances.append(instance)

        if commit:
            existing_instances = [
                instance for instance in active_instances if instance.pk
            ]
            temporary_position = 1000000
            for instance in existing_instances:
                instance.position = temporary_position
                temporary_position += 1
                instance.save()
            for instance in deleted_instances:
                instance.delete()

            for position, instance in enumerate(active_instances, start=1):
                instance.position = position
                instance.save()

        self.deleted_objects = deleted_instances
        return active_instances


MatchingRuleBookingTemplateFormSet = inlineformset_factory(
    MatchingRule,
    MatchingRuleBookingTemplate,
    form=MatchingRuleBookingTemplateForm,
    formset=MatchingRuleBookingTemplateBaseFormSet,
    extra=0,
    can_delete=True,
)
