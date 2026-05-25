from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.materials.models import Material
from apps.structures.models import (
    MATERIAL_LINK_FIELD_TYPE,
    StructureField,
    StructureFieldValue,
    StructureInstance,
)
from apps.structures import table_storage

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_CHECK = {'class': 'form-check-input'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}


class MaterialChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.code} - {obj.name}'


def material_label(material: Material) -> str:
    return f'{material.code} - {material.name}'


def material_from_value(value):
    if value in (None, ''):
        return None
    if isinstance(value, Material):
        return value
    try:
        return Material.objects.get(pk=value)
    except (Material.DoesNotExist, ValueError, TypeError):
        return None


def _parse_default(field: StructureField):
    if not field.default_value:
        return None
    if field.field_type == 'BooleanField':
        return field.default_value.lower() in ('1', 'true', 'yes', 'да')
    if field.field_type == 'IntegerField':
        return int(field.default_value)
    if field.field_type in ('DecimalField', 'FloatField'):
        return Decimal(field.default_value)
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        return material_from_value(field.default_value)
    return field.default_value


def _build_dynamic_field(structure_field: StructureField) -> forms.Field:
    label = structure_field.label
    required = structure_field.is_required
    help_text = structure_field.help_text or None
    initial = _parse_default(structure_field)

    if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
        return MaterialChoiceField(
            label=label,
            required=False,
            help_text=help_text,
            initial=initial,
            queryset=Material.objects.order_by('code'),
            widget=forms.Select(attrs=_BOOTSTRAP_SELECT),
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
        return forms.DecimalField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            max_digits=structure_field.max_digits or 10,
            decimal_places=structure_field.decimal_places or 2,
            widget=forms.NumberInput(attrs=_BOOTSTRAP_INPUT),
        )
    if structure_field.field_type == 'FloatField':
        return forms.FloatField(
            label=label,
            required=required,
            help_text=help_text,
            initial=initial,
            widget=forms.NumberInput(attrs=_BOOTSTRAP_INPUT),
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


def _save_field_value(field_value: StructureFieldValue, structure_field: StructureField, value):
    field_type = structure_field.field_type
    field_value.value_text = ''
    field_value.value_number = None
    field_value.value_integer = None
    field_value.value_boolean = None
    field_value.value_date = None
    field_value.value_datetime = None
    field_value.value_fk_id = None

    if value is None or value == '':
        field_value.save()
        return

    if field_type in ('CharField', 'TextField'):
        field_value.value_text = str(value)
    elif field_type == 'IntegerField':
        field_value.value_integer = int(value)
    elif field_type in ('DecimalField', 'FloatField'):
        field_value.value_number = Decimal(str(value))
    elif field_type == 'BooleanField':
        field_value.value_boolean = bool(value)
    elif field_type == 'DateField':
        field_value.value_date = value
    elif field_type == 'DateTimeField':
        field_value.value_datetime = value
    elif field_type == MATERIAL_LINK_FIELD_TYPE:
        field_value.value_fk_id = getattr(value, 'pk', value)
    field_value.save()


def _get_eav_form(structure_type):
    structure_fields = _supported_structure_fields(structure_type)

    class DynamicStructureForm(forms.ModelForm):
        class Meta:
            model = StructureInstance
            fields = ['code']
            widgets = {'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT)}

        def __init__(self, *args, **kwargs):
            self.structure_type = structure_type
            super().__init__(*args, **kwargs)
            for sf in structure_fields:
                self.fields[f'field_{sf.id}'] = _build_dynamic_field(sf)
            if self.instance and self.instance.pk:
                self._load_existing_values()

        def _load_existing_values(self):
            values = {fv.field_id: fv for fv in self.instance.values.select_related('field')}
            for sf in structure_fields:
                fv = values.get(sf.id)
                if fv:
                    value = fv.get_value()
                    if sf.field_type == MATERIAL_LINK_FIELD_TYPE:
                        value = material_from_value(value)
                    self.fields[f'field_{sf.id}'].initial = value

        def save(self, commit=True):
            instance = super().save(commit=False)
            instance.structure_type = self.structure_type
            if commit:
                instance.save()
            for sf in structure_fields:
                value = self.cleaned_data.get(f'field_{sf.id}')
                field_value, _ = StructureFieldValue.objects.get_or_create(
                    instance=instance, field=sf
                )
                _save_field_value(field_value, sf, value)
            return instance

    return DynamicStructureForm


def _get_table_form(structure_type):
    structure_fields = _supported_structure_fields(structure_type)

    class DynamicTableForm(forms.ModelForm):
        class Meta:
            model = StructureInstance
            fields = ['code']
            widgets = {'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT)}

        def __init__(self, *args, **kwargs):
            self.structure_type = structure_type
            super().__init__(*args, **kwargs)
            for sf in structure_fields:
                self.fields[f'field_{sf.id}'] = _build_dynamic_field(sf)
            if self.instance and self.instance.pk and self.instance.dynamic_row_id:
                row_data = table_storage.load_field_data(
                    structure_type, self.instance.dynamic_row_id
                )
                for sf in structure_fields:
                    if sf.name in row_data:
                        value = row_data[sf.name]
                        if sf.field_type == MATERIAL_LINK_FIELD_TYPE:
                            value = material_from_value(value)
                        self.fields[f'field_{sf.id}'].initial = value

        def save(self, commit=True):
            if not self.structure_type.is_created:
                raise ValidationError('Таблица для этого типа ещё не создана в БД.')

            field_data = _collect_field_data(self.structure_type, self.cleaned_data)
            code = self.cleaned_data['code']

            if self.instance and self.instance.pk and self.instance.dynamic_row_id:
                table_storage.update_row(
                    self.structure_type,
                    self.instance.dynamic_row_id,
                    field_data,
                    code=code,
                )
                self.instance.code = code
                if commit:
                    self.instance.save()
                return self.instance

            row_id = table_storage.insert_row(
                self.structure_type, code, field_data
            )
            instance = StructureInstance(
                structure_type=self.structure_type,
                code=code,
                dynamic_row_id=row_id,
            )
            if commit:
                instance.save()
            return instance

    return DynamicTableForm


def get_dynamic_form(structure_type):
    if structure_type.is_created:
        return _get_table_form(structure_type)
    return _get_eav_form(structure_type)
