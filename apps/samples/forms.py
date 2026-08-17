from django import forms
from django.forms import inlineformset_factory

from apps.core.fields import LocalizedPropertyValueField, localized_range_bound_field
from apps.core.property_number_forms import NumberPropertyValueFormMixin
from apps.core.tag_forms import TagNamesFormMixin
from apps.materials.form_widgets import material_select_widget_attrs
from apps.materials.models import Material
from apps.samples.attachment_title import default_attachment_title
from apps.samples.models import Sample, SampleAttachment, SampleProperty
from apps.samples.validators import validate_attachment_file
from apps.structures.constants import STRUCTURE_FIELD_PREFIX
from apps.structures.forms import (
    _build_dynamic_field,
    material_from_value,
)
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE
from apps.structures.sql_executor import SQLExecutor
from apps.structures.structure_decimal_forms import (
    add_structure_decimal_fields,
    apply_structure_decimal_initial,
    clean_structure_decimal_fields,
    collect_structure_decimal_sql_data,
    structure_decimal_bound_group,
    structure_decimal_field_names,
)

_BOOTSTRAP_INPUT = {'class': 'form-control'}
_BOOTSTRAP_SELECT = {'class': 'form-select'}


class SamplePropertyInlineFormSet(forms.BaseInlineFormSet):
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


class SamplePropertyForm(NumberPropertyValueFormMixin, forms.ModelForm):
    value = LocalizedPropertyValueField(required=False)
    value_min = localized_range_bound_field(bound_label='От')
    value_max = localized_range_bound_field(bound_label='До')
    value_tolerance = localized_range_bound_field(bound_label='±')

    class Meta:
        model = SampleProperty
        fields = ['property', 'value_kind', 'value', 'value_b']
        widgets = {
            'property': forms.Select(attrs=_BOOTSTRAP_SELECT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        prop = self._resolve_property()
        self._init_number_property_fields(prop)

    def _resolve_property(self):
        if self.is_bound:
            raw = self.data.get(self.add_prefix('property'))
            if raw:
                from apps.references.models import Property

                return Property.objects.filter(pk=raw).first()
        if getattr(self.instance, 'property_id', None):
            return self.instance.property
        initial = self.initial.get('property')
        if initial is None:
            return None
        from apps.references.models import Property

        if isinstance(initial, Property):
            return initial
        return Property.objects.filter(pk=initial).first()

    def clean(self):
        cleaned_data = super().clean()
        prop = cleaned_data.get('property') or self._resolve_property()
        return self._clean_number_property(cleaned_data, prop)


SamplePropertyFormSet = inlineformset_factory(
    Sample,
    SampleProperty,
    form=SamplePropertyForm,
    fields=['property', 'value_kind', 'value', 'value_b'],
    extra=0,
    can_delete=True,
    formset=SamplePropertyInlineFormSet,
    widgets={},
)


class SampleTagsForm(TagNamesFormMixin, forms.ModelForm):
    """Только теги — для редактирования с карточки образца."""

    class Meta:
        model = Sample
        fields = []


class SampleForm(TagNamesFormMixin, forms.ModelForm):
    class Meta:
        model = Sample
        fields = ['code', 'name', 'description', 'material', 'object_type']
        labels = {
            'code': 'Код',
            'name': 'Название',
            'description': 'Описание',
            'material': 'Материал',
            'object_type': 'Тип объекта',
        }
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
            'material': forms.Select(attrs=material_select_widget_attrs(
                **{'data-sample-material-select': 'true'},
            )),
            'object_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
        }

    def __init__(self, *args, workspace=None, skip_validation=False, **kwargs):
        self.skip_validation = skip_validation
        self._active_workspace = workspace
        super().__init__(*args, workspace=workspace, **kwargs)
        from apps.materials.picker_data import materials_for_picker_queryset

        self.fields['material'].queryset = materials_for_picker_queryset(workspace)
        self.fields['material'].empty_label = '— не выбран —'

        self._initial_material_id = self.instance.material_id if self.instance else None
        self._initial_struct_type = self.instance.struct_type if self.instance else None
        self._initial_struct_type_id = self.instance.struct_type_id if self.instance else None
        self._initial_struct_props_id = self.instance.struct_props_id if self.instance else None

        self.structure_type = self._structure_type_from_material()
        self.structure_fields = []
        self.structure_decimal_fields = []
        self.structure_empty_message = ''
        self._add_structure_fields()

    def _resolve_material(self):
        if self.is_bound:
            raw = self.data.get('material')
            if raw:
                return Material.objects.filter(pk=raw).select_related('struct_type').first()
            return None
        if 'material' in self.initial and self.initial.get('material'):
            value = self.initial.get('material')
            if isinstance(value, Material):
                return value
            return Material.objects.filter(pk=value).select_related('struct_type').first()
        if self.instance and self.instance.material_id:
            return (
                Material.objects.filter(pk=self.instance.material_id)
                .select_related('struct_type')
                .first()
            )
        return None

    def _selected_material_id(self):
        material = self._resolve_material()
        return material.pk if material else None

    def _material_id_changed(self):
        selected = self._selected_material_id()
        initial = self._initial_material_id
        if selected in (None, '') or initial in (None, ''):
            return bool(selected) != bool(initial)
        return str(selected) != str(initial)

    def _structure_type_from_material(self):
        material = self._resolve_material()
        if material is None or not material.struct_type_id:
            return None
        return material.struct_type

    def _supported_structure_fields(self):
        if not self.structure_type:
            return []
        return list(
            self.structure_type.fields.exclude(field_type='ForeignKey').order_by(
                'sort_order',
                'name',
            )
        )

    def _existing_structure_values(self):
        if self.is_bound and not self.skip_validation:
            return {}
        # After material change (or apply-material re-render): copy from material.
        if self.skip_validation or self._material_id_changed():
            material = self._resolve_material()
            return (material.get_structure_params() if material else None) or {}
        # Own sample row when material unchanged.
        if self.instance.pk and self.instance.struct_props_id and self.instance.struct_type_id:
            params = self.instance.get_structure_params()
            if params:
                return params
        material = self._resolve_material()
        return (material.get_structure_params() if material else None) or {}

    def _add_structure_fields(self):
        if not self.structure_type:
            self.structure_empty_message = (
                'У выбранного материала нет типа структуры.'
                if self._resolve_material()
                else 'Выберите материал — параметры структуры подставятся автоматически.'
            )
            return

        if not self.structure_type.is_created:
            self.structure_empty_message = (
                'SQL-таблица типа структуры материала ещё не создана.'
            )
            return

        self.structure_fields = self._supported_structure_fields()
        if not self.structure_fields:
            self.structure_empty_message = 'Для типа структуры материала нет поддерживаемых полей.'
            return

        from apps.structures.decimal_places_sync import sync_structure_decimal_places_from_catalog

        sync_structure_decimal_places_from_catalog(self.structure_fields)

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
        return [
            bound_field
            for bound_field in self.visible_fields()
            if bound_field.name not in structure_field_names
        ]

    def full_clean(self):
        if self.skip_validation:
            from django.forms.utils import ErrorDict

            self._errors = ErrorDict()
            self.cleaned_data = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        material = cleaned_data.get('material')
        structure_type = material.struct_type if material and material.struct_type_id else None

        if structure_type and not structure_type.is_created:
            self.add_error(
                'material',
                'У материала тип структуры без SQL-таблицы — параметры структуры недоступны.',
            )

        self.instance.struct_props_id = None
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

    def _initial_structure_row_is_shared(self):
        if not self._initial_struct_type or not self._initial_struct_props_id:
            return False
        old_type = self._initial_struct_type
        old_row_id = self._initial_struct_props_id
        if Material.objects.filter(
            struct_type=old_type,
            struct_props_id=old_row_id,
        ).exists():
            return True
        return (
            Sample.objects.filter(
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
            raise forms.ValidationError(
                result.get('error') or 'Не удалось удалить прежние параметры структуры образца.',
            )

    def _save_structure_row(self, sample):
        material = sample.material
        structure_type = material.struct_type if material and material.struct_type_id else None
        sample.struct_type = structure_type

        if not structure_type or not structure_type.is_created or not self.structure_fields:
            sample.struct_props_id = None
            self._delete_initial_structure_row()
            return

        data = self._collect_structure_data()
        material_changed = self._material_id_changed()
        type_changed = (
            not self._initial_struct_type_id
            or str(self._initial_struct_type_id) != str(structure_type.pk)
        )
        should_update = (
            sample.pk
            and self._initial_struct_props_id
            and not material_changed
            and not type_changed
            and not self._initial_structure_row_is_shared()
        )
        if should_update:
            if SQLExecutor.get_structure_instance(
                structure_type,
                self._initial_struct_props_id,
            ) is None:
                raise forms.ValidationError('Запись параметров структуры образца не найдена.')
            result = SQLExecutor.update(structure_type, self._initial_struct_props_id, data)
            row_id = self._initial_struct_props_id
        else:
            result = SQLExecutor.insert(structure_type, data)
            row_id = result.get('id')

        if not result['success']:
            raise forms.ValidationError(
                result.get('error') or 'Не удалось сохранить параметры структуры образца.',
            )
        sample.struct_props_id = row_id
        if material_changed or type_changed:
            self._delete_initial_structure_row()

    def save(self, commit=True):
        sample = super().save(commit=False)
        if commit:
            self._save_structure_row(sample)
            sample.save()
            self.save_tags(sample)
            self.save_m2m()
        return sample


class SampleAttachmentForm(forms.ModelForm):
    class Meta:
        model = SampleAttachment
        fields = ['file', 'title', 'description']
        labels = {
            'file': 'Файл',
            'title': 'Название',
            'description': 'Описание',
        }

    def __init__(self, *args, optional=False, **kwargs):
        sample = kwargs.pop('sample', None)
        if sample and 'data' not in kwargs:
            kwargs.setdefault('initial', {})['title'] = default_attachment_title(sample)
        self.optional = optional
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css_class)
        self.fields['description'].widget.attrs.setdefault('rows', 3)
        if optional and not self.instance.pk:
            self.fields['file'].required = False
            self.fields['title'].required = False

    def has_attachment_data(self):
        return bool(
            self.data.get(self.add_prefix('title'))
            or self.data.get(self.add_prefix('description'))
            or self.files.get(self.add_prefix('file'))
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.optional and not self.instance.pk and not self.has_attachment_data():
            return cleaned_data

        if self.optional and not self.instance.pk:
            if not cleaned_data.get('file'):
                self.add_error('file', 'Выберите файл для загрузки.')
            if not cleaned_data.get('title'):
                self.add_error('title', 'Укажите название файла.')
        return cleaned_data

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            validate_attachment_file(uploaded_file)
        elif self.optional and not self.instance.pk and not self.has_attachment_data():
            return uploaded_file
        elif not self.instance.pk or not self.instance.file:
            raise forms.ValidationError('Выберите файл для загрузки.')
        return uploaded_file
