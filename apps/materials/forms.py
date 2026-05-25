from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.forms import inlineformset_factory

from apps.materials.models import Material, MaterialProperty
from apps.structures.models import StructureType
from apps.structures.forms import _build_dynamic_field, material_from_value
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE
from apps.structures.sql_executor import SQLExecutor

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}
STRUCTURE_SERVICE_FIELDS = {'id', 'created_at', 'updated_at', 'created_by'}
STRUCTURE_FIELD_PREFIX = 'structure_field_'


def structure_instance_label(instance: dict) -> str:
    record_id = str(instance.get('id') or '')
    code = instance.get('code')
    if code:
        return str(code)

    for field_name, value in instance.items():
        if field_name not in STRUCTURE_SERVICE_FIELDS and value not in (None, ''):
            return str(value)
    return record_id[:8]

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
        fields = [
            'code',
            'name',
            'description',
            'struct_type',
            'created_by',
        ]
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
            'struct_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'created_by': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_struct_type_id = self.instance.struct_type_id if self.instance else None
        self._initial_struct_type = self.instance.struct_type if self.instance else None
        self._initial_struct_props_id = self.instance.struct_props_id if self.instance else None
        self.structure_type = self._selected_structure_type()
        self.structure_fields = []
        self.structure_empty_message = ''
        self._add_structure_fields()

    def _selected_structure_type_id(self):
        if self.is_bound and 'struct_type' in self.data:
            value = self.data.get('struct_type')
        elif 'struct_type' in self.initial:
            value = self.initial.get('struct_type')
        elif self.instance and self.instance.pk:
            value = self.instance.struct_type_id
        else:
            value = None
        return getattr(value, 'pk', value)

    def _selected_structure_type(self):
        structure_type_id = self._selected_structure_type_id()
        if not structure_type_id:
            return None

        try:
            return StructureType.objects.get(pk=structure_type_id)
        except (StructureType.DoesNotExist, ValueError, DjangoValidationError):
            return None

    def _supported_structure_fields(self):
        if not self.structure_type:
            return []
        return list(
            self.structure_type.fields.exclude(field_type='ForeignKey').order_by(
                'sort_order',
                'name',
            )
        )

    def _add_structure_fields(self):
        if not self.structure_type:
            self.structure_empty_message = 'Выберите тип структуры, чтобы заполнить параметры.'
            return

        self.structure_fields = self._supported_structure_fields()
        if not self.structure_fields:
            self.structure_empty_message = 'Для выбранного типа структуры нет поддерживаемых полей.'
            return

        existing_values = self._existing_structure_values()
        for structure_field in self.structure_fields:
            field_name = self.structure_form_field_name(structure_field)
            self.fields[field_name] = _build_dynamic_field(structure_field)
            if structure_field.name in existing_values:
                value = existing_values[structure_field.name]
                if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
                    value = material_from_value(value)
                self.fields[field_name].initial = value

    def _existing_structure_values(self):
        if self.is_bound:
            return {}
        if (
            not self.instance
            or not self.instance.pk
            or not self.instance.struct_props_id
            or self._structure_type_changed()
        ):
            return {}
        return self.instance.get_structure_params() or {}

    def _structure_type_changed(self):
        selected_id = self._selected_structure_type_id()
        initial_id = self._initial_struct_type_id
        if selected_id in (None, '') or initial_id in (None, ''):
            return bool(selected_id) != bool(initial_id)
        return str(selected_id) != str(initial_id)

    @staticmethod
    def structure_form_field_name(structure_field):
        return f'{STRUCTURE_FIELD_PREFIX}{structure_field.pk}'

    @property
    def structure_bound_fields(self):
        return [self[self.structure_form_field_name(field)] for field in self.structure_fields]

    @property
    def base_bound_fields(self):
        structure_field_names = {
            self.structure_form_field_name(field)
            for field in self.structure_fields
        }
        return [
            bound_field
            for bound_field in self.visible_fields()
            if bound_field.name not in structure_field_names
        ]

    def clean(self):
        cleaned_data = super().clean()
        structure_type = cleaned_data.get('struct_type')

        if not structure_type:
            self.instance.struct_props_id = None
            return cleaned_data

        self.instance.struct_props_id = None
        if not structure_type.is_created:
            self.add_error('struct_type', 'SQL-таблица для выбранного типа структуры еще не создана.')

        return cleaned_data

    def _collect_structure_data(self):
        data = {}
        for structure_field in self.structure_fields:
            field_name = self.structure_form_field_name(structure_field)
            value = self.cleaned_data.get(field_name)
            if value not in (None, '') or structure_field.is_required:
                data[structure_field.name] = value
            else:
                data[structure_field.name] = None
        return data

    def _save_structure_row(self, material):
        structure_type = material.struct_type
        if not structure_type:
            material.struct_props_id = None
            self._delete_initial_structure_row()
            return

        data = self._collect_structure_data()
        should_update = (
            material.pk
            and self._initial_struct_props_id
            and not self._structure_type_changed()
            and not self._initial_structure_row_is_shared()
        )
        if should_update:
            if SQLExecutor.get_structure_instance(structure_type, self._initial_struct_props_id) is None:
                raise forms.ValidationError('Запись параметров структуры не найдена.')
            result = SQLExecutor.update(structure_type, self._initial_struct_props_id, data)
            row_id = self._initial_struct_props_id
        else:
            result = SQLExecutor.insert(structure_type, data)
            row_id = result.get('id')

        if not result['success']:
            raise forms.ValidationError(result.get('error') or 'Не удалось сохранить параметры структуры.')
        material.struct_props_id = row_id
        if self._structure_type_changed():
            self._delete_initial_structure_row()

    def _initial_structure_row_is_shared(self):
        if not self._initial_struct_type or not self._initial_struct_props_id:
            return False

        old_type = self._initial_struct_type
        old_row_id = self._initial_struct_props_id
        return (
            Material.objects.filter(
                struct_type=old_type,
                struct_props_id=old_row_id,
            )
            .exclude(pk=self.instance.pk)
            .exists()
        )

    def _delete_initial_structure_row(self):
        if not self._initial_struct_type or not self._initial_struct_props_id:
            return
        if self._initial_structure_row_is_shared():
            return
        result = SQLExecutor.delete(self._initial_struct_type, self._initial_struct_props_id)
        if not result['success']:
            raise forms.ValidationError(result.get('error') or 'Не удалось удалить прежние параметры структуры.')

    def save(self, commit=True):
        material = super().save(commit=False)
        if commit:
            self._save_structure_row(material)
            material.save()
            self.save_m2m()
        return material
