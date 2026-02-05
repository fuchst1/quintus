from django import forms
from django.forms import inlineformset_factory
from .models import LeaseAgreement, Manager, Meter, MeterReading, Property, Ownership, Owner, Tenant, Unit

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
            "tax_mode",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "website": forms.URLInput(attrs={"class": "form-control"}),
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


class MeterForm(forms.ModelForm):
    class Meta:
        model = Meter
        fields = [
            "meter_number",
            "meter_type",
            "kind",
            "property",
            "unit",
            "is_main_meter",
            "description",
        ]
        widgets = {
            "meter_number": forms.TextInput(attrs={"class": "form-control"}),
            "meter_type": forms.Select(attrs={"class": "form-select"}),
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

    class Meta:
        model = MeterReading
        fields = ["meter", "date", "value", "note"]
        widgets = {
            "meter": forms.Select(attrs={"class": "form-select"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


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
