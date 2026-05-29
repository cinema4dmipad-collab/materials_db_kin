from django import forms

from apps.references.models import Property, PropertyGroup
from apps.structures.identifiers import normalize_identifier

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}
_BOOTSTRAP_TEXTAREA = {'class': 'form-control', 'rows': 3}


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['display_name', 'name', 'unit', 'data_type', 'group', 'description']
        widgets = {
            'display_name': forms.TextInput(attrs={**_BOOTSTRAP_INPUT, 'data-property-name-source': 'true'}),
            'name': forms.TextInput(attrs={**_BOOTSTRAP_INPUT, 'data-property-name-target': 'true'}),
            'unit': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'data_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'group': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'description': forms.Textarea(attrs=_BOOTSTRAP_TEXTAREA),
        }
        labels = {
            'display_name': 'Название',
            'name': 'Код свойства',
            'unit': 'Единица измерения',
            'data_type': 'Тип данных',
            'group': 'Группа',
            'description': 'Описание',
        }
        help_texts = {
            'display_name': 'Как свойство будет отображаться в интерфейсе (на русском или английском).',
            'name': 'Заполняется автоматически из названия. Можно изменить вручную при необходимости.',
            'unit': 'Необязательно (например, МПа, г/см³).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = PropertyGroup.objects.order_by('sort_order', 'name')
        self.fields['group'].required = False
        self.fields['group'].empty_label = '— без группы —'
        self.fields['name'].required = False

    def clean(self):
        cleaned_data = super().clean()
        display_name = (cleaned_data.get('display_name') or '').strip()
        name = (cleaned_data.get('name') or '').strip()

        if not name and display_name:
            name = normalize_identifier(display_name, max_length=100)

        if not name:
            self.add_error('display_name', 'Укажите название свойства.')
        else:
            cleaned_data['name'] = name

        return cleaned_data
