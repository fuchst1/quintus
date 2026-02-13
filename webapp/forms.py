from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.forms import inlineformset_factory, modelformset_factory
from .models import (
    BankTransaktion,
    BetriebskostenBeleg,
    BetriebskostenGruppe,
    Buchung,
    Datei,
    LeaseAgreement,
    Manager,
    Meter,
    MeterReading,
    Ownership,
    Owner,
    Property,
    VpiIndexValue,
    Tenant,
    Unit,
    ReminderRuleConfig,
)
from .services.files import DateiService

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            "name",
            "manager",
            "zip_code",
            "city",
            "street_address",
            "heating_share_percent",
            "notes",
        ]
        widgets = {
            'zip_code': forms.TextInput(attrs={
                'pattern': '[0-9]{4,5}', # Einfache HTML-Syntax ohne r''
                'title': 'Bitte geben Sie 4 bis 5 Ziffern ein.',
                'class': 'form-control',
                'inputmode': 'numeric' # Öffnet auf Handys direkt die Zahlentastatur
            }),
            "manager": forms.Select(attrs={"class": "form-select"}),
            'heating_share_percent': forms.NumberInput(attrs={
                'min': '55',
                'max': '85',
                'step': '1', 
                'class': 'form-control'
            }),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ManagerForm(forms.ModelForm):
    class Meta:
        model = Manager
        fields = [
            "company_name",
            "contact_person",
            "email",
            "phone",
            "website",
            "account_number",
            "tax_mode",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "website": forms.URLInput(attrs={"class": "form-control"}),
            "account_number": forms.TextInput(attrs={"class": "form-control"}),
            "tax_mode": forms.Select(attrs={"class": "form-select"}),
        }


class OwnerForm(forms.ModelForm):
    class Meta:
        model = Owner
        fields = [
            "name",
            "email",
            "phone",
            "street_address",
            "zip_code",
            "city",
            "iban",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "street_address": forms.TextInput(attrs={"class": "form-control"}),
            "zip_code": forms.TextInput(attrs={
                "pattern": "[0-9]{4,5}",
                "title": "Bitte geben Sie 4 bis 5 Ziffern ein.",
                "class": "form-control",
                "inputmode": "numeric",
            }),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "iban": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class TenantForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )

    class Meta:
        model = Tenant
        fields = [
            "salutation",
            "first_name",
            "last_name",
            "date_of_birth",
            "email",
            "phone",
            "iban",
            "notes",
        ]
        widgets = {
            "salutation": forms.Select(attrs={"class": "form-select"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "iban": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class LeaseAgreementForm(forms.ModelForm):
    entry_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    exit_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    last_index_adjustment = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )

    class Meta:
        model = LeaseAgreement
        fields = [
            "unit",
            "tenants",
            "manager",
            "status",
            "entry_date",
            "exit_date",
            "index_type",
            "last_index_adjustment",
            "index_base_value",
            "net_rent",
            "operating_costs_net",
            "heating_costs_net",
            "deposit",
        ]
        widgets = {
            "unit": forms.Select(attrs={"class": "form-select"}),
            "tenants": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
            "manager": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "index_type": forms.Select(attrs={"class": "form-select"}),
            "index_base_value": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "net_rent": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "operating_costs_net": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "heating_costs_net": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "deposit": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        entry_date = cleaned_data.get("entry_date")
        exit_date = cleaned_data.get("exit_date")
        if entry_date and exit_date and exit_date < entry_date:
            self.add_error("exit_date", "Auszugsdatum darf nicht vor dem Einzugsdatum liegen.")
        return cleaned_data


class ReminderRuleConfigForm(forms.ModelForm):
    class Meta:
        model = ReminderRuleConfig
        fields = ["title", "lead_months", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "lead_months": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "60", "step": "1"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


ReminderRuleConfigFormSet = modelformset_factory(
    ReminderRuleConfig,
    form=ReminderRuleConfigForm,
    extra=0,
    can_delete=False,
)


class VpiIndexValueForm(forms.ModelForm):
    month = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )

    class Meta:
        model = VpiIndexValue
        fields = [
            "month",
            "index_value",
            "is_released",
            "released_at",
            "note",
        ]
        widgets = {
            "index_value": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "is_released": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "released_at": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean_month(self):
        value = self.cleaned_data["month"]
        if value.day != 1:
            raise forms.ValidationError("Monat muss auf den 1. des Monats gesetzt sein.")
        return value


VpiIndexValueFormSet = modelformset_factory(
    VpiIndexValue,
    form=VpiIndexValueForm,
    extra=1,
    can_delete=False,
)


class MeterForm(forms.ModelForm):
    class Meta:
        model = Meter
        fields = [
            "meter_number",
            "meter_type",
            "unit_of_measure",
            "kind",
            "property",
            "unit",
            "is_main_meter",
            "description",
        ]
        widgets = {
            "meter_number": forms.TextInput(attrs={"class": "form-control"}),
            "meter_type": forms.Select(attrs={"class": "form-select"}),
            "unit_of_measure": forms.Select(attrs={"class": "form-select"}),
            "kind": forms.Select(attrs={"class": "form-select"}),
            "property": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "is_main_meter": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class MeterReadingForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    meter = forms.ModelChoiceField(
        queryset=Meter.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Zähler",
    )

    class Meta:
        model = MeterReading
        fields = ["meter", "date", "value", "note"]
        widgets = {
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meter"].queryset = (
            Meter.objects.select_related("unit")
            .annotate(_unit_name=Coalesce("unit__name", Value(""), output_field=CharField()))
            .order_by("_unit_name", "meter_type", "meter_number")
        )
        self.fields["meter"].label_from_instance = self._meter_label
        if not self.is_bound and not self.instance.pk:
            self.fields["date"].initial = timezone.now().date()

    @staticmethod
    def _meter_label(meter: Meter) -> str:
        if meter.unit:
            unit_label = meter.unit.name
        else:
            unit_label = "Haus"
        return f"{unit_label} · {meter.get_meter_type_display()}"


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = [
            "property",
            "unit_type",
            "door_number",
            "name",
            "usable_area",
            "operating_cost_share",
        ]
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "unit_type": forms.Select(attrs={"class": "form-select"}),
            "door_number": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "usable_area": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }),
            "operating_cost_share": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        unit_type = cleaned_data.get("unit_type")
        usable_area = cleaned_data.get("usable_area")
        operating_cost_share = cleaned_data.get("operating_cost_share")
        if unit_type in (Unit.UnitType.APARTMENT, Unit.UnitType.COMMERCIAL):
            if not usable_area:
                self.add_error("usable_area", "Nutzfläche ist für diesen Einheitstyp erforderlich.")
            if not operating_cost_share:
                self.add_error("operating_cost_share", "Betriebskostenanteil ist für diesen Einheitstyp erforderlich.")
        return cleaned_data


class OwnershipForm(forms.ModelForm):
    class Meta:
        model = Ownership
        fields = ["owner", "share_percent"]
        widgets = {
            "owner": forms.Select(attrs={"class": "form-select"}),
            "share_percent": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "1",
                "min": "0",
                "max": "100",
            }),
        }


PropertyOwnershipFormSet = inlineformset_factory(
    Property,
    Ownership,
    form=OwnershipForm,
    fields=["owner", "share_percent"],
    extra=1,
    can_delete=True,
)


class BankImportForm(forms.Form):
    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": "application/json",
            }
        ),
    )


class DateiUploadForm(forms.Form):
    target_app_label = forms.CharField(widget=forms.HiddenInput())
    target_model = forms.CharField(widget=forms.HiddenInput())
    target_object_id = forms.IntegerField(widget=forms.HiddenInput())
    file = forms.FileField(
        label="Datei",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png",
            }
        ),
    )
    kategorie = forms.ChoiceField(
        label="Kategorie",
        choices=Datei.Kategorie.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    beschreibung = forms.CharField(
        required=False,
        label="Beschreibung",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop("user", None)
        self.target_object = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        app_label = cleaned_data.get("target_app_label")
        model_name = cleaned_data.get("target_model")
        object_id = cleaned_data.get("target_object_id")
        upload = cleaned_data.get("file")
        kategorie = cleaned_data.get("kategorie")

        if app_label and model_name and object_id:
            try:
                self.target_object = DateiService.resolve_target_object(
                    app_label=app_label,
                    model_name=model_name,
                    object_id=object_id,
                )
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages) from exc
        else:
            raise forms.ValidationError("Bitte ein gültiges Zielobjekt angeben.")

        if upload and kategorie:
            try:
                DateiService.validate_upload(uploaded_file=upload, kategorie=kategorie)
            except ValidationError as exc:
                self.add_error("file", exc)

        return cleaned_data

    def save(self) -> Datei:
        if not self.is_valid():
            raise ValueError("DateiUploadForm kann nur mit validen Daten gespeichert werden.")
        return DateiService.upload(
            uploaded_file=self.cleaned_data["file"],
            kategorie=self.cleaned_data["kategorie"],
            target_object=self.target_object,
            beschreibung=self.cleaned_data.get("beschreibung", ""),
        )


class BuchungForm(forms.ModelForm):
    liegenschaft = forms.ModelChoiceField(
        queryset=Property.objects.all(),
        required=True,
        label="Liegenschaft",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    datum = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )

    class Meta:
        model = Buchung
        fields = [
            "liegenschaft",
            "einheit",
            "typ",
            "kategorie",
            "buchungstext",
            "datum",
            "netto",
            "ust_prozent",
            "brutto",
            "is_settlement_adjustment",
            "storniert_von",
        ]
        widgets = {
            "typ": forms.Select(attrs={"class": "form-select"}),
            "kategorie": forms.Select(attrs={"class": "form-select"}),
            "buchungstext": forms.TextInput(attrs={"class": "form-control"}),
            "netto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ust_prozent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "brutto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "is_settlement_adjustment": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "storniert_von": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.prefill_mietervertrag_id = kwargs.pop("mietervertrag_prefill_id", None)
        super().__init__(*args, **kwargs)
        self.fields["einheit"].required = False
        self.fields["einheit"].widget.attrs.setdefault("class", "form-select")
        property_id = None
        if self.is_bound:
            property_id = self.data.get("liegenschaft") or self.initial.get("liegenschaft")
        elif self.initial.get("liegenschaft"):
            property_id = self.initial.get("liegenschaft")
        elif self.instance.pk and self.instance.einheit_id:
            property_id = self.instance.einheit.property_id
            self.initial["liegenschaft"] = property_id

        if property_id:
            self.fields["einheit"].queryset = Unit.objects.filter(
                property_id=property_id
            ).order_by("door_number", "name")
        else:
            self.fields["einheit"].queryset = Unit.objects.none()
        if not self.is_bound and not self.instance.pk:
            self.fields["datum"].initial = timezone.now().date()
        self.fields["brutto"].widget.attrs["readonly"] = "readonly"

    def clean(self):
        cleaned_data = super().clean()
        liegenschaft = cleaned_data.get("liegenschaft")
        einheit = cleaned_data.get("einheit")
        netto = cleaned_data.get("netto")
        ust_prozent = cleaned_data.get("ust_prozent")
        prefill_lease = None
        if self.prefill_mietervertrag_id:
            prefill_lease = (
                LeaseAgreement.objects.select_related("unit")
                .filter(pk=self.prefill_mietervertrag_id)
                .first()
            )
        if liegenschaft and einheit and einheit.property_id != liegenschaft.id:
            self.add_error("einheit", "Die Einheit gehört nicht zur gewählten Liegenschaft.")
        if einheit:
            if prefill_lease and prefill_lease.unit_id == einheit.id:
                cleaned_data["mietervertrag"] = prefill_lease
                self.instance.mietervertrag = prefill_lease
            elif self.instance.pk and self.instance.mietervertrag and einheit == self.instance.einheit:
                cleaned_data["mietervertrag"] = self.instance.mietervertrag
            else:
                active_leases = LeaseAgreement.objects.filter(
                    unit=einheit,
                    status=LeaseAgreement.Status.AKTIV,
                )
                if active_leases.count() == 1:
                    mietervertrag = active_leases.first()
                    cleaned_data["mietervertrag"] = mietervertrag
                    self.instance.mietervertrag = mietervertrag
                elif active_leases.count() == 0:
                    self.add_error(
                        "einheit",
                        "Für diese Einheit gibt es keinen laufenden Mietvertrag.",
                    )
                else:
                    self.add_error(
                        "einheit",
                        "Für diese Einheit gibt es mehrere laufende Mietverträge.",
                    )
        else:
            cleaned_data["mietervertrag"] = None
            self.instance.mietervertrag = None
        if netto is None or ust_prozent is None:
            return cleaned_data
        brutto = (
            netto + (netto * ust_prozent / Decimal("100"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned_data["brutto"] = brutto
        self.instance.brutto = brutto
        return cleaned_data


class BetriebskostenBelegForm(forms.ModelForm):
    datum = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    ust_betrag = forms.DecimalField(
        required=False,
        disabled=True,
        decimal_places=2,
        max_digits=12,
        label="USt-Betrag",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = BetriebskostenBeleg
        fields = [
            "liegenschaft",
            "bk_art",
            "ausgabengruppe",
            "datum",
            "netto",
            "ust_prozent",
            "ust_betrag",
            "brutto",
            "buchungstext",
        ]
        widgets = {
            "liegenschaft": forms.Select(attrs={"class": "form-select"}),
            "bk_art": forms.Select(attrs={"class": "form-select"}),
            "ausgabengruppe": forms.Select(attrs={"class": "form-select"}),
            "netto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ust_prozent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "brutto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "buchungstext": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        group_queryset = BetriebskostenGruppe.objects.filter(is_active=True).order_by("sort_order", "name", "id")
        if self.instance.pk and self.instance.ausgabengruppe_id:
            group_queryset = BetriebskostenGruppe.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.ausgabengruppe_id)
            ).order_by("sort_order", "name", "id")
        self.fields["ausgabengruppe"].queryset = group_queryset
        if not self.is_bound and not self.instance.pk:
            self.fields["datum"].initial = timezone.now().date()
            self.fields["ust_prozent"].initial = Decimal("20.00")
            ungrouped, _created = BetriebskostenGruppe.get_or_create_ungrouped()
            self.fields["ausgabengruppe"].initial = ungrouped.pk
        if self.instance.pk and self.instance.netto is not None and self.instance.ust_prozent is not None:
            self.fields["ust_betrag"].initial = self._calculate_ust_betrag(
                self.instance.netto,
                self.instance.ust_prozent,
            )

    @staticmethod
    def _calculate_ust_betrag(netto: Decimal, ust_prozent: Decimal) -> Decimal:
        return (netto * ust_prozent / Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def clean(self):
        return super().clean()


class BetriebskostenGruppeForm(forms.ModelForm):
    class Meta:
        model = BetriebskostenGruppe
        fields = ["name", "sort_order", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
