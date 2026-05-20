from django import forms
from django.forms import inlineformset_factory

from apps.materials.models import Material, MaterialProperty

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}

MaterialPropertyFormSet = inlineformset_factory(
    Material,
    MaterialProperty,
    fields=['property', 'value'],
    extra=3,
    can_delete=True,
    widgets={
        'property': forms.Select(attrs=_BOOTSTRAP_SELECT),
        'value': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
    },
)


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ['code', 'name', 'description', 'created_by']
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
            'created_by': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        }
