from django import forms
from django.forms import inlineformset_factory

from apps.references.constants import DEFAULT_PROPERTY_DECIMAL_PLACES, MAX_PROPERTY_DECIMAL_PLACES
from apps.references.models import Property, PropertyChoice, PropertyGroup
from apps.structures.identifiers import normalize_identifier

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}
_BOOTSTRAP_TEXTAREA = {'class': 'form-control', 'rows': 3}


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ['display_name', 'name', 'data_type', 'decimal_places', 'unit', 'group', 'description']
        widgets = {
            'display_name': forms.TextInput(attrs={**_BOOTSTRAP_INPUT, 'data-property-name-source': 'true'}),
            'name': forms.TextInput(attrs={**_BOOTSTRAP_INPUT, 'data-property-name-target': 'true'}),
            'decimal_places': forms.NumberInput(
                attrs={**_BOOTSTRAP_INPUT, 'min': 0, 'max': MAX_PROPERTY_DECIMAL_PLACES},
            ),
            'unit': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'data_type': forms.Select(attrs={**_BOOTSTRAP_SELECT, 'data-property-data-type': 'true'}),
            'group': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'description': forms.Textarea(attrs=_BOOTSTRAP_TEXTAREA),
        }
        labels = {
            'display_name': 'Название',
            'name': 'Код свойства',
            'decimal_places': 'Знаков после запятой',
            'unit': 'Единица измерения',
            'data_type': 'Тип данных',
            'group': 'Группа',
            'description': 'Описание',
        }
        help_texts = {
            'display_name': 'Как свойство будет отображаться в интерфейсе (на русском или английском).',
            'name': 'Заполняется автоматически из названия. Можно изменить вручную при необходимости.',
            'decimal_places': 'Только для типа «Число». Сколько знаков показывать при вводе и просмотре (0–10).',
            'unit': 'Необязательно (например, МПа, г/см³). Для типов «Материал» и «Выбор из списка» не используется.',
            'data_type': (
                '«Материал» — ссылка на другой материал. '
                '«Выбор из списка» — набор вариантов, который задаётся ниже.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = PropertyGroup.objects.order_by('sort_order', 'name')
        self.fields['group'].required = False
        self.fields['group'].empty_label = '— без группы —'
        self.fields['name'].required = False
        if not self.instance.pk and (self.initial.get('data_type') or 'number') == 'number':
            self.fields['decimal_places'].initial = DEFAULT_PROPERTY_DECIMAL_PLACES

    def clean(self):
        cleaned_data = super().clean()
        display_name = (cleaned_data.get('display_name') or '').strip()
        name = (cleaned_data.get('name') or '').strip()
        data_type = cleaned_data.get('data_type')

        if not name and display_name:
            name = normalize_identifier(display_name, max_length=100)

        if not name:
            self.add_error('display_name', 'Укажите название свойства.')
        else:
            cleaned_data['name'] = name

        if data_type == 'number':
            decimal_places = cleaned_data.get('decimal_places')
            if decimal_places in (None, ''):
                cleaned_data['decimal_places'] = DEFAULT_PROPERTY_DECIMAL_PLACES
            elif decimal_places < 0 or decimal_places > MAX_PROPERTY_DECIMAL_PLACES:
                self.add_error(
                    'decimal_places',
                    f'Знаков после запятой — от 0 до {MAX_PROPERTY_DECIMAL_PLACES}.',
                )
        else:
            cleaned_data['decimal_places'] = None

        if data_type in {
            Property.MATERIAL_LINK_DATA_TYPE,
            Property.CHOICE_DATA_TYPE,
        }:
            cleaned_data['unit'] = ''

        return cleaned_data


class PropertyChoiceForm(forms.ModelForm):
    class Meta:
        model = PropertyChoice
        fields = ['label', 'value', 'sort_order']
        labels = {
            'label': 'Название',
            'value': 'Код',
            'sort_order': 'Порядок',
        }
        widgets = {
            'label': forms.TextInput(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'data-choice-label': 'true',
                }
            ),
            'value': forms.TextInput(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'data-choice-value': 'true',
                }
            ),
            'sort_order': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['value'].required = False
        self.fields['sort_order'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data

        label = (cleaned_data.get('label') or '').strip()
        value = (cleaned_data.get('value') or '').strip()
        if not label and not value:
            return cleaned_data

        if not label:
            self.add_error('label', 'Укажите название варианта.')
            return cleaned_data

        cleaned_data['label'] = label
        if not value:
            value = normalize_identifier(label, max_length=100)
        if not value:
            self.add_error(
                'value',
                'Не удалось построить код. Задайте код вручную латиницей.',
            )
            return cleaned_data
        cleaned_data['value'] = value
        if cleaned_data.get('sort_order') in (None, ''):
            cleaned_data['sort_order'] = 0
        return cleaned_data


class PropertyChoiceFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        property_form = getattr(self, 'property_form', None)
        data_type = None
        if property_form is not None:
            data_type = property_form.cleaned_data.get('data_type')
        if data_type is None and self.instance.pk:
            data_type = self.instance.data_type

        if data_type != Property.CHOICE_DATA_TYPE:
            return

        seen_values: set[str] = set()
        active_count = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            label = (form.cleaned_data.get('label') or '').strip()
            value = (form.cleaned_data.get('value') or '').strip()
            if not label and not value:
                continue
            active_count += 1
            key = value.lower()
            if key in seen_values:
                form.add_error('value', 'Коды вариантов в одном свойстве должны быть разными.')
            seen_values.add(key)

        if active_count == 0:
            raise forms.ValidationError(
                'Для типа «Выбор из списка» добавьте хотя бы один вариант.'
            )


PropertyChoiceInlineFormSet = inlineformset_factory(
    Property,
    PropertyChoice,
    form=PropertyChoiceForm,
    formset=PropertyChoiceFormSet,
    extra=1,
    can_delete=True,
)


def build_property_choice_formset(*, instance=None, data=None, prefix='choices'):
    kwargs = {'instance': instance or Property(), 'prefix': prefix}
    if data is not None:
        kwargs['data'] = data
    formset = PropertyChoiceInlineFormSet(**kwargs)
    if instance is None or not instance.pk:
        if data is None and formset.total_form_count() == 0:
            # Ensure empty template management form works; extra rows added via JS.
            pass
    return formset
