from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.materials.form_widgets import material_select_widget_attrs, structure_type_select_widget_attrs
from apps.composites.models import CompositeLayer
from apps.core.fields import (
    LocalizedFloatField,
    LocalizedPropertyValueField,
    localized_range_bound_field,
)
from apps.core.property_number_forms import NumberPropertyValueFormMixin
from apps.core.property_number_value import VALUE_KIND_SCALAR
from apps.core.tag_forms import TagNamesFormMixin
from apps.materials.models import Material, MaterialProperty
from apps.materials.picker_data import materials_for_picker_queryset
from apps.materials.services import find_shared_materials_by_code, find_shared_materials_by_name
from apps.references.models import Property
from apps.structures.models import StructureType
from apps.structures.constants import STRUCTURE_FIELD_PREFIX
from apps.structures.forms import (
    MaterialChoiceField,
    _build_dynamic_field,
    material_from_value,
)
from apps.structures.structure_decimal_forms import (
    add_structure_decimal_fields,
    apply_structure_decimal_initial,
    clean_structure_decimal_fields,
    collect_structure_decimal_sql_data,
    structure_decimal_bound_group,
    structure_decimal_field_names,
)
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE
from apps.structures.sql_executor import SQLExecutor
from apps.workspaces.visibility import VisibilityMode

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_VISIBILITY_FIELD_NAMES = frozenset({'visibility_mode', 'published_workspaces'})
_BOOTSTRAP_SELECT = {'class': 'form-select'}
STRUCTURE_SERVICE_FIELDS = {'id', 'created_at', 'updated_at', 'created_by'}


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
    def __init__(self, *args, workspace=None, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['workspace'] = self.workspace
        parent = self.instance if getattr(self.instance, 'pk', None) else None
        kwargs['parent_material'] = parent
        return kwargs

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


class MaterialPropertyForm(NumberPropertyValueFormMixin, forms.ModelForm):
    value = LocalizedPropertyValueField(required=False)
    value_min = localized_range_bound_field(bound_label='От')
    value_max = localized_range_bound_field(bound_label='До')
    value_tolerance = localized_range_bound_field(bound_label='±')

    class Meta:
        model = MaterialProperty
        fields = ['property', 'value_kind', 'value', 'value_b']
        widgets = {
            'property': forms.Select(attrs=_BOOTSTRAP_SELECT),
        }

    def __init__(self, *args, workspace=None, parent_material=None, **kwargs):
        self.workspace = workspace
        self.parent_material = parent_material
        super().__init__(*args, **kwargs)
        prop = self._resolve_property()
        if prop and prop.data_type == Property.MATERIAL_LINK_DATA_TYPE:
            self._configure_material_link_value()
        elif prop and prop.data_type == Property.CHOICE_DATA_TYPE:
            self._configure_choice_value(prop)
        else:
            self._init_number_property_fields(prop)

    def _resolve_property(self):
        if self.is_bound:
            raw = self.data.get(self.add_prefix('property'))
            if raw:
                return Property.objects.filter(pk=raw).first()
        if getattr(self.instance, 'property_id', None):
            return self.instance.property
        initial = self.initial.get('property')
        if initial is None:
            return None
        if isinstance(initial, Property):
            return initial
        return Property.objects.filter(pk=initial).first()

    def _configure_material_link_value(self):
        queryset = materials_for_picker_queryset(self.workspace)
        if self.parent_material and self.parent_material.pk:
            queryset = queryset.exclude(pk=self.parent_material.pk)

        raw_value = None
        if self.is_bound:
            raw_value = self.data.get(self.add_prefix('value'))
        if raw_value in (None, ''):
            raw_value = self.initial.get('value')
        if raw_value in (None, ''):
            raw_value = getattr(self.instance, 'value', None)
        current = material_from_value(raw_value)
        if current and not queryset.filter(pk=current.pk).exists():
            queryset = (Material.objects.filter(pk=current.pk) | queryset).distinct()

        self.fields['value'] = MaterialChoiceField(
            label=self.fields['value'].label,
            required=False,
            queryset=queryset,
            initial=current,
            widget=forms.Select(attrs=material_select_widget_attrs()),
        )

    def _configure_choice_value(self, prop):
        options = [(item.value, item.label) for item in prop.choice_options()]
        raw_value = None
        if self.is_bound:
            raw_value = self.data.get(self.add_prefix('value'))
        if raw_value in (None, ''):
            raw_value = self.initial.get('value')
        if raw_value in (None, ''):
            raw_value = getattr(self.instance, 'value', None) or ''
        if raw_value and raw_value not in {item[0] for item in options}:
            options = [(raw_value, raw_value)] + options
        self.fields['value'] = forms.ChoiceField(
            label=self.fields['value'].label,
            required=False,
            choices=[('', '---------')] + options,
            initial=raw_value or '',
            widget=forms.Select(
                attrs={
                    **_BOOTSTRAP_SELECT,
                    'data-choice-picker': 'true',
                }
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        prop = cleaned_data.get('property') or self._resolve_property()
        if prop and prop.data_type == Property.MATERIAL_LINK_DATA_TYPE:
            value = cleaned_data.get('value')
            if isinstance(value, Material):
                cleaned_data['value'] = str(value.pk)
            elif value in (None, ''):
                cleaned_data['value'] = ''
            else:
                linked = material_from_value(value)
                cleaned_data['value'] = str(linked.pk) if linked else ''
            cleaned_data['value_kind'] = VALUE_KIND_SCALAR
            cleaned_data['value_b'] = None
            return cleaned_data
        if prop and prop.data_type == Property.CHOICE_DATA_TYPE:
            value = (cleaned_data.get('value') or '').strip()
            if value and not prop.choices.filter(value=value).exists():
                self.add_error('value', 'Выберите значение из списка вариантов свойства.')
            cleaned_data['value'] = value
            cleaned_data['value_kind'] = VALUE_KIND_SCALAR
            cleaned_data['value_b'] = None
            return cleaned_data
        return self._clean_number_property(cleaned_data, prop)


MaterialPropertyFormSet = inlineformset_factory(
    Material,
    MaterialProperty,
    form=MaterialPropertyForm,
    fields=['property', 'value_kind', 'value', 'value_b'],
    extra=0,
    can_delete=True,
    formset=MaterialPropertyInlineFormSet,
    widgets={},
)


def build_material_property_formset(
    *,
    workspace=None,
    instance=None,
    initial=None,
    data=None,
    prefix='properties',
):
    initial = list(initial or [])
    formset_class = inlineformset_factory(
        Material,
        MaterialProperty,
        form=MaterialPropertyForm,
        fields=['property', 'value_kind', 'value', 'value_b'],
        extra=len(initial),
        can_delete=True,
        formset=MaterialPropertyInlineFormSet,
        widgets={},
    )
    kwargs = {
        'instance': instance or Material(),
        'prefix': prefix,
        'workspace': workspace,
    }
    if data is not None:
        kwargs['data'] = data
    else:
        kwargs['initial'] = initial
    return formset_class(**kwargs)


_COMPOSITE_LAYER_FORMSET_WIDGETS = {
    'layer_number': forms.NumberInput(attrs=_LAYER_NUMBER_WIDGET),
    'material': forms.Select(
        attrs=material_select_widget_attrs(**{'data-material-picker-compact': 'true'}),
    ),
}


def build_composite_layer_formset(*, workspace, instance=None, initial=None, data=None, prefix='layers'):
    initial = list(initial or [])
    formset_class = inlineformset_factory(
        Material,
        CompositeLayer,
        form=CompositeLayerForm,
        formset=CompositeLayerFormSet,
        fk_name='parent_material',
        fields=['layer_number', 'material', 'angle', 'thickness'],
        extra=len(initial),
        can_delete=True,
        widgets=_COMPOSITE_LAYER_FORMSET_WIDGETS,
    )
    kwargs = {
        'instance': instance or Material(),
        'prefix': prefix,
        'workspace': workspace,
    }
    if data is not None:
        kwargs['data'] = data
    else:
        kwargs['initial'] = initial
    return formset_class(**kwargs)


class CompositeLayerFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, workspace=None, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        form.parent_material = self.instance
        form.layer_formset = self
        from apps.materials.picker_data import materials_for_picker_queryset

        form.fields['material'].queryset = materials_for_picker_queryset(self.workspace)
        return form

    def full_clean(self):
        self._prepare_layer_numbers_before_validation()
        super().full_clean()

    def clean(self):
        super().clean()
        if self._layers_not_allowed():
            raise ValidationError(
                'Слои недоступны для выбранного типа структуры.',
            )
        self._assign_layer_numbers()

    def _prepare_layer_numbers_before_validation(self):
        self._pending_layer_numbers = {}
        if not self.is_bound:
            return

        layer_num = 1
        for form in self.forms:
            if not self._should_number_form(form):
                continue
            self._pending_layer_numbers[id(form)] = layer_num
            layer_num += 1

    def _should_number_form(self, form):
        if not form.is_bound:
            return False

        prefix = form.add_prefix('')
        if form.data.get(f'{prefix}DELETE') in ('on', 'true', 'True', '1'):
            return False

        material = form.data.get(f'{prefix}material')
        angle = form.data.get(f'{prefix}angle', '')
        thickness = form.data.get(f'{prefix}thickness', '')
        is_empty = (
            not material
            and not str(angle).strip()
            and not str(thickness).strip()
        )
        if is_empty and not form.instance.pk:
            return False
        return not is_empty
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

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('DELETE'):
            return cleaned_data

        material = cleaned_data.get('material')
        angle = cleaned_data.get('angle')
        thickness = cleaned_data.get('thickness')
        is_empty = (
            not material
            and angle in (None, '')
            and thickness in (None, '')
        )
        if is_empty:
            return cleaned_data

        if not material:
            self.add_error('material', 'Укажите материал слоя.')
        if angle is None:
            self.add_error('angle', 'Укажите угол армирования.')
        if thickness is None:
            self.add_error('thickness', 'Укажите толщину слоя.')

        parent_material = getattr(self, 'parent_material', None)
        parent_material_id = getattr(parent_material, 'pk', None)
        if material and parent_material_id and material.pk == parent_material_id:
            self.add_error('material', 'Материал не может быть собственным слоем.')

        layer_formset = getattr(self, 'layer_formset', None)
        assigned = getattr(layer_formset, '_pending_layer_numbers', {}).get(id(self))
        if assigned is not None:
            cleaned_data['layer_number'] = assigned
            self.instance.layer_number = assigned

        return cleaned_data

    def validate_unique(self):
        layer_formset = getattr(self, 'layer_formset', None)
        parent = getattr(layer_formset, 'instance', None) if layer_formset else None
        parent_id = getattr(self.instance, 'parent_material_id', None) or getattr(parent, 'pk', None)
        layer_number = self.cleaned_data.get('layer_number')

        if not parent_id or layer_number is None:
            return

        exclude_pks = []
        if layer_formset is not None:
            exclude_pks = [
                layer_form.instance.pk
                for layer_form in layer_formset.forms
                if layer_form.instance.pk
            ]
        if self.instance.pk:
            exclude_pks.append(self.instance.pk)
        exclude_pks = list({pk for pk in exclude_pks if pk})

        conflicting = CompositeLayer.objects.filter(
            parent_material_id=parent_id,
            layer_number=layer_number,
        )
        if exclude_pks:
            conflicting = conflicting.exclude(pk__in=exclude_pks)
        if conflicting.exists():
            raise ValidationError({
                'layer_number': 'Номер слоя уже занят другим слоём этого материала.',
            })


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
        widgets=_COMPOSITE_LAYER_FORMSET_WIDGETS,
    )


class MaterialTagsForm(TagNamesFormMixin, forms.ModelForm):
    """Только теги — для редактирования с карточки материала."""

    class Meta:
        model = Material
        fields = []


class MaterialForm(TagNamesFormMixin, forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'code',
            'name',
            'description',
            'struct_type',
        ]
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
            'struct_type': forms.Select(attrs=structure_type_select_widget_attrs()),
        }

    def __init__(
        self,
        *args,
        skip_validation=False,
        workspace=None,
        show_visibility=False,
        can_publish=False,
        template_material=None,
        **kwargs,
    ):
        self.skip_validation = skip_validation
        self.show_visibility = show_visibility and can_publish
        self._active_workspace = workspace
        self._template_material = template_material
        super().__init__(*args, workspace=workspace, **kwargs)
        self._initial_struct_type_id = self.instance.struct_type_id if self.instance else None
        self._initial_struct_type = self.instance.struct_type if self.instance else None
        self._initial_struct_props_id = self.instance.struct_props_id if self.instance else None
        self.fields['struct_type'].queryset = StructureType.objects.filter(
            is_active=True,
        ).order_by('name')
        self.fields['struct_type'].empty_label = 'Без типа структуры'
        self.structure_type = self._selected_structure_type()
        self.structure_fields = []
        self.structure_decimal_fields = []
        self.structure_empty_message = ''
        self._add_structure_fields()
        if self.show_visibility:
            self._add_visibility_fields()

    def _add_visibility_fields(self):
        from apps.workspaces.models import Workspace

        self.fields['visibility_mode'] = forms.ChoiceField(
            choices=VisibilityMode.ui_choices(),
            initial=VisibilityMode.PRIVATE,
            label='Режим видимости',
            widget=forms.Select(attrs={**_BOOTSTRAP_SELECT, 'id': 'id_visibility_mode'}),
            help_text=(
                '«Только домашнее пространство» — материал виден только в текущем пространстве. '
                '«Все пространства» — материал доступен во всех активных пространствах.'
            ),
        )
        queryset = Workspace.objects.filter(is_active=True).order_by('name')
        if self._active_workspace:
            queryset = queryset.exclude(pk=self._active_workspace.pk)
        self.fields['published_workspaces'] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            required=False,
            label='Опубликовано в пространствах',
            widget=forms.SelectMultiple(
                attrs={**_BOOTSTRAP_SELECT, 'size': 6, 'id': 'id_published_workspaces'},
            ),
            help_text='Только для режима «Выбранные пространства». Домашнее пространство добавляется автоматически.',
        )

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
            if structure_field.field_type == 'DecimalField':
                add_structure_decimal_fields(self, structure_field)
                self.structure_decimal_fields.append(structure_field)
                if existing_values:
                    apply_structure_decimal_initial(self, structure_field, existing_values)
                continue
            field_name = self.structure_form_field_name(structure_field)
            self.fields[field_name] = _build_dynamic_field(
                structure_field,
                workspace=self._active_workspace,
            )
            if structure_field.name in existing_values:
                value = existing_values[structure_field.name]
                if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
                    value = material_from_value(value)
                self.fields[field_name].initial = value

    def _existing_structure_values(self):
        if self.is_bound:
            return {}
        if self._structure_type_changed():
            return {}
        template = self._template_material
        if template and self.instance._state.adding:
            selected_type_id = self._selected_structure_type_id()
            if selected_type_id and str(template.struct_type_id) == str(selected_type_id):
                params = template.get_structure_params()
                if params:
                    return params
        if not self.instance.struct_props_id:
            return {}
        return self.instance.get_structure_params() or {}

    def _structure_type_changed(self):
        selected_id = self._selected_structure_type_id()
        initial_id = self._initial_struct_type_id
        if (
            not initial_id
            and self._template_material
            and self.instance
            and self.instance._state.adding
        ):
            initial_id = self._template_material.struct_type_id
        if selected_id in (None, '') or initial_id in (None, ''):
            return bool(selected_id) != bool(initial_id)
        return str(selected_id) != str(initial_id)

    @staticmethod
    def structure_form_field_name(structure_field):
        return f'{STRUCTURE_FIELD_PREFIX}{structure_field.pk}'

    @property
    def structure_bound_fields(self):
        bound = []
        for structure_field in self.structure_fields:
            if structure_field.field_type == 'DecimalField':
                bound.append(structure_decimal_bound_group(self, structure_field))
            else:
                bound.append(self[self.structure_form_field_name(structure_field)])
        return bound

    @property
    def visibility_bound_fields(self):
        if not self.show_visibility:
            return []
        return [self['visibility_mode']]

    @property
    def base_bound_fields(self):
        structure_field_names = {
            self.structure_form_field_name(field)
            for field in self.structure_fields
            if field.field_type != 'DecimalField'
        }
        for structure_field in self.structure_decimal_fields:
            structure_field_names.update(
                structure_decimal_field_names(structure_field.pk).values()
            )
        excluded_names = structure_field_names | _VISIBILITY_FIELD_NAMES
        return [
            bound_field
            for bound_field in self.visible_fields()
            if bound_field.name not in excluded_names
        ]

    def full_clean(self):
        if self.skip_validation:
            self._errors = ErrorDict()
            self.cleaned_data = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        structure_type = cleaned_data.get('struct_type')

        if self.instance._state.adding and self._active_workspace:
            code = (cleaned_data.get('code') or '').strip()
            if code:
                duplicate_code = Material.objects.filter(
                    home_workspace=self._active_workspace,
                    code=code,
                )
                if duplicate_code.exists():
                    self.add_error(
                        'code',
                        'Материал с таким кодом уже существует в текущем пространстве.',
                    )
                elif find_shared_materials_by_code(code, self._active_workspace).exists():
                    shared_url = f"{reverse('materials:list')}?scope=shared"
                    self.add_error(
                        'code',
                        mark_safe(
                            'Материал с таким кодом уже существует среди общих материалов. '
                            f'Поищите его на вкладке «<a href="{shared_url}">Общие</a>».'
                        ),
                    )

            name = (cleaned_data.get('name') or '').strip()
            exclude_id = getattr(self._template_material, 'pk', None)
            if name and find_shared_materials_by_name(
                name,
                self._active_workspace,
                exclude_material_id=exclude_id,
            ).exists():
                shared_url = f"{reverse('materials:list')}?scope=shared"
                self.add_error(
                    'name',
                    mark_safe(
                        'Материал с таким названием уже существует. '
                        f'Поищите его на вкладке «<a href="{shared_url}">Общие</a>».'
                    ),
                )

        if not structure_type:
            self.instance.struct_props_id = None
            return cleaned_data

        self.instance.struct_props_id = None
        if not structure_type.is_created:
            self.add_error('struct_type', 'SQL-таблица для выбранного типа структуры еще не создана.')

        if self.show_visibility:
            mode = cleaned_data.get('visibility_mode')
            if mode == VisibilityMode.SELECTED_WORKSPACES:
                if not cleaned_data.get('published_workspaces'):
                    self.add_error(
                        'published_workspaces',
                        'Выберите хотя бы одно пространство.',
                    )
            elif mode != VisibilityMode.SELECTED_WORKSPACES:
                cleaned_data['published_workspaces'] = []

        for structure_field in self.structure_decimal_fields:
            cleaned_data = clean_structure_decimal_fields(
                self,
                structure_field,
                cleaned_data,
            )

        return cleaned_data

    def _collect_structure_data(self):
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
        if self.show_visibility:
            material.visibility_mode = self.cleaned_data.get(
                'visibility_mode',
                VisibilityMode.PRIVATE,
            )
        if commit:
            self._save_structure_row(material)
            material.save()
            self.save_tags(material)
            if self.show_visibility:
                if material.visibility_mode == VisibilityMode.SELECTED_WORKSPACES:
                    material.published_workspaces.set(
                        self.cleaned_data.get('published_workspaces', []),
                    )
                else:
                    material.published_workspaces.clear()
            self.save_m2m()
        return material


class MaterialVisibilityForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ('visibility_mode',)
        labels = {
            'visibility_mode': 'Режим видимости',
        }
        widgets = {
            'visibility_mode': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visibility_mode'].choices = VisibilityMode.ui_choices()


class MaterialImportForm(forms.Form):
    file = forms.FileField(
        label='Файл CSV или XLSX',
        help_text='Одна строка — одно свойство материала. Повторяйте code для нескольких свойств.',
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'accept': '.csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }
        ),
    )

    def clean_file(self):
        uploaded = self.cleaned_data['file']
        name = (getattr(uploaded, 'name', '') or '').lower()
        if not name.endswith(('.csv', '.xlsx', '.xlsm')):
            raise ValidationError('Поддерживаются только файлы CSV и XLSX.')
        return uploaded

