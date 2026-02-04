from django import forms
from .models import Property

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['name', 'zip_code', 'city', 'street_address', 'heating_share_percent', 'notes']
        widgets = {
            'zip_code': forms.TextInput(attrs={
                'pattern': r'\d{4,10}',
                'title': 'Bitte geben Sie 4 bis 10 Ziffern ein.',
                'class': 'form-control'
            }),
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