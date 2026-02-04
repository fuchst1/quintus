from django import forms
from .models import Property

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['name', 'zip_code', 'city', 'street_address', 'heating_share_percent', 'notes']
        widgets = {
            # Das 'pattern' Attribut sorgt für die Browser-Validierung VOR dem Senden
            'zip_code': forms.TextInput(attrs={
                'pattern': r'\d{4,5}',
                'title': 'Bitte geben Sie 4 bis 5 Ziffern ein.'
            }),
            # 'number' sorgt bei mobilen Geräten direkt für die Zifferntastatur
            'heating_share_percent': forms.NumberInput(attrs={
                'min': '55',
                'max': '85',
                'step': '1'
            }),
        }