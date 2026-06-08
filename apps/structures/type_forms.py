from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.structures.identifiers import (
    normalize_identifier,
    preview_table_name_from_title,
    table_name_for_code,
    validate_field_column_name,
    validate_structure_code,
    validate_table_name,
)
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE, StructureField, StructureType

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}
_BOOTSTRAP_CHECK = {'class': 'form-check-input'}


class StructureTypeForm(forms.ModelForm):
    class Meta:
        model = StructureType
        fields = ['name', 'description', 'display_color', 'allow_layers', 'is_active']
        labels = {
            'name': 'Название типа',
            'description': 'Описание для операторов',
            'display_color': 'Цвет в списке материалов',
            'allow_layers': 'Разрешить слои композита',
            'is_active': 'Активен',
        }
        widgets = {
            'name': forms.TextInput(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'placeholder': 'Например: Сэндвичная панель',
                    'data-structure-code-source': 'true',
                }
            ),
            'description': forms.Textarea(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'rows': 3,
                    'placeholder': 'Кратко: для каких материалов и параметров используется этот тип.',
                }
            ),
            'display_color': forms.RadioSelect(choices=StructureType._meta.get_field('display_color').choices),
            'allow_layers': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECK),
            'is_active': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECK),
        }
        help_texts = {
            'name': (
                'Понятное название на русском. Код и имя SQL-таблицы '
                'сформируются автоматически (транслит + snake_case).'
            ),
            'display_color': (
                'Один цвет для всех материалов этого типа — инженеру проще '
                'отличать классы структур, не путая похожие материалы.'
            ),
            'allow_layers': 'Включите, если материалы этого типа могут иметь слои композита.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.generated_code = self.instance.code
            self.generated_table_name = self.instance.table_name
        else:
            name = self.initial.get('name') or self.data.get('name', '')
            self.generated_code = normalize_identifier(name, max_length=50)
            self.generated_table_name = preview_table_name_from_title(name)

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise ValidationError('Укажите название типа структуры.')
        if len(name) > 100:
            raise ValidationError('Название не длиннее 100 символов.')
        return name

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and self.instance.is_created:
            if 'name' in self.changed_data:
                self.add_error(
                    'name',
                    'Нельзя менять название после создания SQL-таблицы.',
                )
            return cleaned_data

        name = cleaned_data.get('name')
        if not name:
            return cleaned_data

        code = normalize_identifier(name, max_length=50)
        if not code:
            self.add_error(
                'name',
                'Не удалось построить код из названия. '
                'Добавьте латинские буквы или более конкретное имя.',
            )
            return cleaned_data

        try:
            code = validate_structure_code(code)
        except ValueError as exc:
            self.add_error('name', str(exc))
            return cleaned_data

        suffix = 2
        base_code = code
        code_qs = StructureType.objects.filter(code=code)
        if self.instance.pk:
            code_qs = code_qs.exclude(pk=self.instance.pk)
        while code_qs.exists():
            code = f'{base_code[:45]}_{suffix}'
            suffix += 1
            code = validate_structure_code(code)
            code_qs = StructureType.objects.filter(code=code)
            if self.instance.pk:
                code_qs = code_qs.exclude(pk=self.instance.pk)

        table_name = table_name_for_code(code)
        try:
            validate_table_name(table_name)
        except ValueError as exc:
            self.add_error('name', str(exc))
            return cleaned_data

        if StructureType.objects.filter(table_name=table_name).exclude(pk=self.instance.pk).exists():
            self.add_error('name', f'Таблица {table_name} уже используется другим типом.')

        cleaned_data['code'] = code
        cleaned_data['table_name'] = table_name
        self.generated_code = code
        self.generated_table_name = table_name
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.is_created and 'code' in self.cleaned_data:
            instance.code = self.cleaned_data['code']
        instance.table_name = (
            self.cleaned_data.get('table_name')
            or instance.table_name
            or table_name_for_code(instance.code)
        )
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StructureFieldForm(forms.ModelForm):
    class Meta:
        model = StructureField
        fields = [
            'name',
            'label',
            'field_type',
            'is_required',
            'sort_order',
            'max_length',
            'max_digits',
            'decimal_places',
            'default_value',
            'help_text',
        ]
        labels = {
            'name': 'Имя колонки',
            'label': 'Подпись в форме',
            'field_type': 'Тип данных',
            'is_required': 'Обязательное',
            'sort_order': 'Порядок',
            'max_length': 'Длина строки',
            'max_digits': 'Всего цифр',
            'decimal_places': 'Знаков после запятой',
            'default_value': 'По умолчанию',
            'help_text': 'Подсказка',
        }
        widgets = {
            'name': forms.TextInput(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'placeholder': 'thickness_mm',
                    'data-structure-field-name': 'true',
                }
            ),
            'label': forms.TextInput(
                attrs={
                    **_BOOTSTRAP_INPUT,
                    'placeholder': 'Толщина, мм',
                    'data-structure-field-label': 'true',
                }
            ),
            'field_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'is_required': forms.CheckboxInput(attrs=_BOOTSTRAP_CHECK),
            'sort_order': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 0}),
            'max_length': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 1, 'max': 4000}),
            'max_digits': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 1, 'max': 18}),
            'decimal_places': forms.NumberInput(attrs={**_BOOTSTRAP_INPUT, 'min': 0, 'max': 10}),
            'default_value': forms.TextInput(
                attrs={**_BOOTSTRAP_INPUT, 'placeholder': 'Необязательно'},
            ),
            'help_text': forms.TextInput(
                attrs={**_BOOTSTRAP_INPUT, 'placeholder': 'Текст под полем для оператора'},
            ),
        }
        help_texts = {
            'name': 'Латиница, цифры и _. Начинается с буквы. Заполняется из подписи, можно править.',
            'label': 'Как поле увидит оператор, например «Толщина обшивки, мм».',
            'field_type': 'Строка — текст; Число — целое; Десятичная — размеры с дробной частью.',
            'max_length': 'Для строки: сколько символов хранить (обычно 255).',
            'max_digits': 'Для десятичного числа: всего цифр, включая дробную часть.',
            'decimal_places': 'Сколько знаков после запятой (например 2 для 12.34).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data

        cleaned_data['foreign_key_model'] = ''
        label = (cleaned_data.get('label') or '').strip()
        name = (cleaned_data.get('name') or '').strip().lower()

        if not name and label:
            name = normalize_identifier(label, max_length=63)
            cleaned_data['name'] = name

        if not label and not name:
            return cleaned_data

        if label and not name:
            self.add_error(
                'label',
                'Не удалось построить имя колонки. Используйте буквы в подписи '
                'или задайте имя колонки вручную латиницей.',
            )
            return cleaned_data

        if name:
            try:
                cleaned_data['name'] = validate_field_column_name(name)
            except ValueError as exc:
                self.add_error('name', str(exc))

        field_type = cleaned_data.get('field_type')
        if field_type == MATERIAL_LINK_FIELD_TYPE:
            cleaned_data['max_length'] = None
            cleaned_data['max_digits'] = None
            cleaned_data['decimal_places'] = None
        elif field_type == 'CharField':
            max_length = cleaned_data.get('max_length') or 255
            if max_length < 1 or max_length > 4000:
                self.add_error('max_length', 'Длина строки — от 1 до 4000.')
        elif field_type == 'DecimalField':
            max_digits = cleaned_data.get('max_digits') or 10
            decimal_places = cleaned_data.get('decimal_places') or 2
            if max_digits < 1 or max_digits > 18:
                self.add_error('max_digits', 'Всего цифр — от 1 до 18.')
            if decimal_places < 0 or decimal_places > 10:
                self.add_error('decimal_places', 'Знаков после запятой — от 0 до 10.')
            if decimal_places > max_digits:
                self.add_error(
                    'decimal_places',
                    'Знаков после запятой не может быть больше, чем всего цифр.',
                )
        elif field_type == 'IntegerField' and cleaned_data.get('default_value'):
            try:
                int(str(cleaned_data['default_value']).strip())
            except ValueError:
                self.add_error('default_value', 'Для целого числа укажите целое значение.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.foreign_key_model = ''
        if instance.field_type == MATERIAL_LINK_FIELD_TYPE:
            instance.max_length = None
            instance.max_digits = None
            instance.decimal_places = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StructureFieldFormSet(forms.BaseInlineFormSet):
    def validate_unique(self):
        """Дубликаты имён проверяются в clean() с понятным сообщением."""

    def clean(self):
        super().clean()
        if self.instance and self.instance.is_created:
            return

        active_fields = 0
        seen_names: set[str] = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            name = (form.cleaned_data.get('name') or '').strip().lower()
            if not name:
                continue
            active_fields += 1
            if name in seen_names:
                form.add_error('name', 'Имена колонок в одном типе должны быть разными.')
            seen_names.add(name)

        if active_fields == 0:
            raise ValidationError(
                'Добавьте хотя бы одно поле. Без полей SQL-таблица не может быть создана.'
            )


StructureFieldInlineFormSet = inlineformset_factory(
    StructureType,
    StructureField,
    form=StructureFieldForm,
    formset=StructureFieldFormSet,
    extra=1,
    can_delete=True,
)


class StructureTypeDisplayColorForm(forms.ModelForm):
    class Meta:
        model = StructureType
        fields = ['display_color']
        labels = {'display_color': 'Цвет в списке материалов'}
        widgets = {'display_color': forms.RadioSelect(choices=StructureType._meta.get_field('display_color').choices)}

