from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import Tag
from apps.core.tag_utils import (
    normalize_tag_name,
    tag_slug_from_name,
    validate_tag_color,
    validate_tag_names,
)

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_TEXTAREA = {'class': 'form-control', 'rows': 3}
_BOOTSTRAP_CHECKBOX = {'class': 'form-check-input'}


class TagForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        label='Общий тег',
        help_text='Доступен во всех пространствах.',
        widget=forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
    )

    def __init__(self, *args, workspace=None, allow_global=False, **kwargs):
        self.workspace = workspace
        self.allow_global = allow_global
        super().__init__(*args, **kwargs)
        if not allow_global:
            self.fields.pop('is_global', None)
        elif self.instance.pk and not self.instance._state.adding and self.instance.is_global:
            self.fields['is_global'].initial = True
            self.fields['is_global'].disabled = True
        else:
            self.fields['is_global'].initial = False
        self.fields['color'].widget = forms.TextInput(
            attrs={**_BOOTSTRAP_INPUT, 'placeholder': '#336699', 'maxlength': '7'},
        )

    class Meta:
        model = Tag
        fields = ['name', 'description', 'color', 'is_archived']
        widgets = {
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs=_BOOTSTRAP_TEXTAREA),
            'is_archived': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECKBOX),
        }
        labels = {
            'name': 'Название',
            'description': 'Описание',
            'color': 'Цвет',
            'is_archived': 'В архиве',
        }
        help_texts = {
            'name': (
                'Уникально в пределах области тега. '
                'Для взаимоисключающих меток используйте «область::значение».'
            ),
            'description': 'Когда и зачем ставить этот тег.',
            'is_archived': 'Скрывает тег из выбора, но сохраняет на уже помеченных записях.',
        }

    def clean_name(self):
        name = normalize_tag_name(self.cleaned_data.get('name', ''))
        if not name:
            raise ValidationError('Укажите название тега.')
        validate_tag_names([name])
        return name

    def clean_color(self):
        color = (self.cleaned_data.get('color') or '').strip()
        validate_tag_color(color)
        return color.upper() if color else ''

    def clean_is_global(self):
        if not self.allow_global:
            return False
        if self.instance.pk and not self.instance._state.adding and self.instance.is_global:
            return True
        return bool(self.cleaned_data.get('is_global'))

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        if not name:
            return cleaned_data

        is_global = cleaned_data.get('is_global', False)
        slug = tag_slug_from_name(name)
        if is_global:
            queryset = Tag.objects.filter(slug=slug, workspace__isnull=True)
        elif self.workspace is None:
            self.add_error('name', 'Выберите активное пространство для тега пространства.')
            return cleaned_data
        else:
            queryset = Tag.objects.filter(slug=slug, workspace=self.workspace)

        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            existing = queryset.first()
            scope = 'глобальных тегов' if is_global else 'этого пространства'
            self.add_error('name', f'Тег «{existing.name}» уже существует среди {scope}.')
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = tag_slug_from_name(instance.name)
        is_global = self.cleaned_data.get('is_global', False)
        if is_global:
            instance.workspace = None
        elif self.workspace is not None:
            instance.workspace = self.workspace
        if commit:
            instance.save()
        return instance
