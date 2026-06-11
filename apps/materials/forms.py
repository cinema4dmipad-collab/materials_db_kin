from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.materials.form_widgets import material_select_widget_attrs
from apps.composites.models import CompositeLayer
from apps.core.fields import (
    LocalizedFloatField,
    LocalizedPropertyValueField,
    clean_localized_number_value,
)
from apps.core.tag_forms import TagNamesFormMixin
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

_LAYER_NUMBER_WIDGET = {
    'class': 'form-control layer-number-field',
    'readonly': True,
}


class MaterialPropertyInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = {}
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            prop = form.cleaned_data.get('property')
            if not prop:
                continue
            if prop.pk in seen:
                form.add_error(
                    'property',
                    'Это свойство уже указано в другой строке.',
                )
            else:
                seen[prop.pk] = True


class MaterialPropertyForm(forms.ModelForm):
    value = LocalizedPropertyValueField(required=False)

    class Meta:
        model = MaterialProperty
        fields = ['property', 'value']
        widgets = {
            'property': forms.Select(attrs=_BOOTSTRAP_SELECT),
        }

    def clean(self):
        cleaned_data = super().clean()
        clean_localized_number_value(self)
        return cleaned_data


MaterialPropertyFormSet = inlineformset_factory(
    Material,
    MaterialProperty,
    form=MaterialPropertyForm,
    fields=['property', 'value'],
    extra=0,
    can_delete=True,
    formset=MaterialPropertyInlineFormSet,
    widgets={},
)


class CompositeLayerFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if self._layers_not_allowed():
            raise ValidationError(
                'Слои недоступны для выбранного типа структуры.',
            )
        self._assign_layer_numbers()

    def _layers_not_allowed(self):
        if not self.instance or not self.instance.pk:
            return False
        if self.instance.supports_layers:
            return False
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            if form.instance.pk or not self._is_empty_form(form):
                return True
        return False

    def save(self, commit=True):
        self._assign_layer_numbers()
        return super().save(commit=commit)

    def _assign_layer_numbers(self):
        layer_num = 1
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            if not form.instance.pk and self._is_empty_form(form):
                continue
            form.cleaned_data['layer_number'] = layer_num
            form.instance.layer_number = layer_num
            layer_num += 1

    def _is_empty_form(self, form):
        cleaned_data = form.cleaned_data
        material = cleaned_data.get('material')
        angle = cleaned_data.get('angle')
        thickness = cleaned_data.get('thickness')
        return (
            not material
            and angle in (None, '')
            and thickness in (None, '')
        )


class CompositeLayerForm(forms.ModelForm):
    angle = LocalizedFloatField(label='Угол армирования, °', required=False)
    thickness = LocalizedFloatField(label='Толщина, мм', required=False)

    class Meta:
        model = CompositeLayer
        fields = ['layer_number', 'material', 'angle', 'thickness']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['layer_number'].required = False


def get_composite_layer_formset():
    return inlineformset_factory(
        Material,
        CompositeLayer,
        form=CompositeLayerForm,
        formset=CompositeLayerFormSet,
        fk_name='parent_material',
        fields=['layer_number', 'material', 'angle', 'thickness'],
        extra=0,
        can_delete=True,
        widgets={
            'layer_number': forms.NumberInput(attrs=_LAYER_NUMBER_WIDGET),
            'material': forms.Select(attrs=material_select_widget_attrs()),
        },
    )


class MaterialForm(TagNamesFormMixin, forms.ModelForm):
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
        except (StructureType.DoesNotExist, ValueError, ValidationError):
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
            self.save_tags(material)
            self.save_m2m()
        return material
