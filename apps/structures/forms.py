import uuid

from django import forms
from django.core.exceptions import ValidationError

from apps.structures.constants import DEFAULT_DECIMAL_PLACES, DEFAULT_MAX_DIGITS
from apps.core.fields import LocalizedDecimalField, LocalizedFloatField
from apps.core.number_utils import normalize_decimal_input, parse_decimal

from apps.materials.form_widgets import material_select_widget_attrs
from apps.materials.models import Material
from apps.structures.choice_options import choice_pairs, resolved_choice_options
from apps.structures.models import CHOICE_FIELD_TYPE, MATERIAL_LINK_FIELD_TYPE, StructureField
from apps.structures import table_storage
from apps.structures.constants import STRUCTURE_FIELD_PREFIX
from apps.structures.structure_decimal_forms import (
    add_structure_decimal_fields,
    apply_structure_decimal_initial,
    clean_structure_decimal_fields,
    collect_structure_decimal_sql_data,
    is_structure_decimal_subfield,
    structure_decimal_bound_group,
    structure_decimal_field_names,
)

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_CHECK = {'class': 'form-check-input'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}
_CHOICE_SELECT = {**_BOOTSTRAP_SELECT, 'data-choice-picker': 'true'}


class MaterialChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.code} - {obj.name}'


def material_label(material: Material) -> str:
    return f'{material.code} - {material.name}'


MATERIAL_LINK_MISSING_LABEL = 'Материал не найден'


def material_link_display(value, *, missing_label: str = MATERIAL_LINK_MISSING_LABEL) -> str:
    """Человекочитаемая подпись для MaterialLink; без сырого UUID."""
    if value in (None, ''):
        return '—'
    material = material_from_value(value)
    if material is not None:
        return material_label(material)
    return missing_label


def material_from_value(value):
    if value in (None, ''):
        return None
    if isinstance(value, Material):
        return value

    candidates = [value]
    text = str(value)
    try:
        candidates.append(uuid.UUID(text))
    except (ValueError, TypeError, AttributeError):
        pass
    if len(text) == 32:
        try:
            candidates.append(uuid.UUID(hex=text))
        except ValueError:
            pass

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            return Material.objects.get(pk=candidate)
        except (Material.DoesNotExist, ValueError, TypeError):
            continue
    return None


def _parse_default(field: StructureField):
    if not field.default_value:
        return None
    if field.field_type == 'BooleanField':
        return field.default_value.lower() in ('1', 'true', 'yes', 'да')
    if field.field_type == 'IntegerField':
        return int(field.default_value)
    if field.field_type in ('DecimalField', 'FloatField'):
        return parse_decimal(normalize_decimal_input(field.default_value))
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        return material_from_value(field.default_value)
    return field.default_value


def _build_dynamic_field(structure_field: StructureField, workspace=None) -> forms.Field:
    label = structure_field.label
    required = structure_field.is_required
    help_text = structure_field.help_text or None
    initial = _parse_default(structure_field)

    if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
        from apps.materials.picker_data import materials_for_picker_queryset

        return MaterialChoiceField(
            label=label,
            required=False,
            help_text=help_text,
            initial=initial,
            queryset=materials_for_picker_queryset(workspace),
            widget=forms.Select(attrs=material_select_widget_attrs()),
        )
    choice_options = resolved_choice_options(structure_field)
    if structure_field.field_type == CHOICE_FIELD_TYPE or choice_options:
        options = choice_pairs(choice_options)
        if initial not in (None, '') and str(initial) not in {item[0] for item in options}:
            options = [(str(initial), str(initial))] + options
        return forms.ChoiceField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial if initial not in (None,) else '',
            choices=[('', '---------')] + options,
            widget=forms.Select(attrs=_CHOICE_SELECT),
        )
    if structure_field.field_type == 'CharField':
        return forms.CharField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            max_length=structure_field.max_length or 255,
            widget=forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        )
    if structure_field.field_type == 'TextField':
        return forms.CharField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            widget=forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
        )
    if structure_field.field_type == 'IntegerField':
        return forms.IntegerField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            widget=forms.NumberInput(attrs=_BOOTSTRAP_INPUT),
        )
    if structure_field.field_type == 'DecimalField':
        return LocalizedDecimalField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            max_digits=structure_field.max_digits or DEFAULT_MAX_DIGITS,
            decimal_places=structure_field.decimal_places or DEFAULT_DECIMAL_PLACES,
        )
    if structure_field.field_type == 'FloatField':
        return LocalizedFloatField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
        )
    if structure_field.field_type == 'BooleanField':
        return forms.BooleanField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial if initial is not None else False,
            widget=forms.CheckboxInput(attrs=_BOOTSTRAP_CHECK),
        )
    if structure_field.field_type == 'DateField':
        return forms.DateField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            widget=forms.DateInput(attrs={**_BOOTSTRAP_INPUT, 'type': 'date'}),
        )
    if structure_field.field_type == 'DateTimeField':
        return forms.DateTimeField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            widget=forms.DateTimeInput(attrs={**_BOOTSTRAP_INPUT, 'type': 'datetime-local'}),
        )
    raise ValidationError(f'Неподдерживаемый тип поля: {structure_field.field_type}')


def _supported_structure_fields(structure_type):
    return list(structure_type.fields.exclude(field_type='ForeignKey'))


def _collect_field_data(structure_type, cleaned_data):
    data = {}
    for sf in _supported_structure_fields(structure_type):
        value = cleaned_data.get(f'field_{sf.id}')
        if value is not None and value != '':
            data[sf.name] = value
        elif sf.is_required:
            data[sf.name] = value
        else:
            data[sf.name] = None
    return data


def get_dynamic_form(structure_type):
    structure_fields = _supported_structure_fields(structure_type)

    class DynamicStructureForm(StructureRecordForm):
        def __init__(self, *args, **kwargs):
            instance = kwargs.pop('instance', None)
            super().__init__(structure_type=structure_type, record=None, *args, **kwargs)
            self.fields['code'] = forms.CharField(
                label='Код структуры',
                required=True,
                widget=forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            )
            if instance is not None:
                code = getattr(instance, 'code', None)
                if code:
                    self.fields['code'].initial = code
                row_id = getattr(instance, 'dynamic_row_id', None)
                if row_id:
                    row_data = table_storage.load_field_data(structure_type, row_id)
                    self._apply_initial_values(row_data)

        def save(self, created_by=''):
            from apps.structures.sql_executor import SQLExecutor

            if not self.structure_type.is_created:
                raise ValidationError('Таблица для этого типа ещё не создана в БД.')
            data = self.collect_data()
            data['code'] = self.cleaned_data['code']
            result = SQLExecutor.insert(self.structure_type, data)
            if not result['success']:
                raise ValidationError(result.get('error') or 'Не удалось создать запись.')
            return result['id']

    return DynamicStructureForm


class StructureRecordForm(forms.Form):
    """Форма записи в SQL-таблице динамической структуры (публичный UI)."""

    def __init__(self, structure_type, record=None, workspace=None, *args, **kwargs):
        self.structure_type = structure_type
        self.record = record
        self.workspace = workspace
        super().__init__(*args, **kwargs)
        self.structure_fields = _supported_structure_fields(structure_type)
        self.structure_decimal_fields = []
        for structure_field in self.structure_fields:
            if structure_field.field_type == 'DecimalField':
                add_structure_decimal_fields(self, structure_field)
                self.structure_decimal_fields.append(structure_field)
            else:
                field = _build_dynamic_field(structure_field, workspace=workspace)
                self.fields[self.field_name(structure_field)] = field
        if record:
            self._apply_initial_values(record)

    @classmethod
    def field_name(cls, structure_field):
        return f'{STRUCTURE_FIELD_PREFIX}{structure_field.pk}'

    @property
    def bound_structure_fields(self):
        bound = []
        for structure_field in self.structure_fields:
            if structure_field.field_type == 'DecimalField':
                bound.append(structure_decimal_bound_group(self, structure_field))
            else:
                bound.append(self[self.field_name(structure_field)])
        return bound

    def _apply_initial_values(self, record):
        for structure_field in self.structure_fields:
            if structure_field.field_type == 'DecimalField':
                apply_structure_decimal_initial(self, structure_field, record)
                continue
            if structure_field.name not in record:
                continue
            value = record[structure_field.name]
            if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
                value = material_from_value(value)
            self.fields[self.field_name(structure_field)].initial = value

    def clean(self):
        cleaned_data = super().clean()
        for structure_field in self.structure_decimal_fields:
            cleaned_data = clean_structure_decimal_fields(
                self,
                structure_field,
                cleaned_data,
            )
        return cleaned_data

    def collect_data(self):
        data = {}
        for structure_field in self.structure_fields:
            if structure_field.field_type == 'DecimalField':
                data.update(
                    collect_structure_decimal_sql_data(
                        structure_field,
                        self.cleaned_data,
                    )
                )
                continue
            value = self.cleaned_data.get(self.field_name(structure_field))
            if value not in (None, '') or structure_field.is_required:
                data[structure_field.name] = value
            else:
                data[structure_field.name] = None
        return data

    def save(self, created_by=''):
        from apps.structures.sql_executor import SQLExecutor

        data = self.collect_data()
        if self.record:
            row_id = self.record['id']
            result = SQLExecutor.update(self.structure_type, row_id, data)
            if not result['success']:
                raise ValidationError(result.get('error') or 'Не удалось сохранить запись.')
            return row_id

        if created_by:
            data['created_by'] = created_by
        result = SQLExecutor.insert(self.structure_type, data)
        if not result['success']:
            raise ValidationError(result.get('error') or 'Не удалось создать запись.')
        return result['id']
