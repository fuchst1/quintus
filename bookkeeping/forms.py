from django import forms

from bookkeeping.models import Bankkonto, Kostenstelle, Mandant
from bookkeeping.services.chart_of_accounts import ReferenceValidationError, import_chart_of_accounts


class MandantForm(forms.ModelForm):
    class Meta:
        model = Mandant
        fields = ["name", "kurzname", "steuerliche_id", "waehrung", "aktiv"]


class BankkontoForm(forms.ModelForm):
    class Meta:
        model = Bankkonto
        fields = ["mandant", "iban_normalisiert", "bezeichnung", "waehrung", "aktiv_von", "aktiv_bis"]


class KostenstelleForm(forms.ModelForm):
    class Meta:
        model = Kostenstelle
        fields = ["mandant", "code", "bezeichnung", "external_source", "external_id", "aktiv_von", "aktiv_bis"]


class KontenplanImportForm(forms.Form):
    mandant = forms.ModelChoiceField(queryset=Mandant.objects.none(), label="Mandant")
    bezeichnung = forms.CharField(max_length=255, label="Bezeichnung")
    gueltig_ab = forms.DateField(label="Gültig ab", widget=forms.DateInput(attrs={"type": "date"}))
    vorlage_datei = forms.FileField(label="Excel-Originalvorlage")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mandant"].queryset = Mandant.objects.filter(aktiv=True).order_by("name")

    def clean_vorlage_datei(self):
        uploaded_file = self.cleaned_data["vorlage_datei"]
        if not uploaded_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Bitte eine XLSX-Datei auswählen.")
        return uploaded_file

    def save(self, *, user=None):
        try:
            return import_chart_of_accounts(
                mandant=self.cleaned_data["mandant"],
                bezeichnung=self.cleaned_data["bezeichnung"],
                gueltig_ab=self.cleaned_data["gueltig_ab"],
                uploaded_file=self.cleaned_data["vorlage_datei"],
                user=user,
            )
        except ReferenceValidationError as exc:
            self.add_error("vorlage_datei", str(exc))
            return None
