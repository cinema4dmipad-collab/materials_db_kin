from django import forms
from django.forms import inlineformset_factory

from apps.materials.models import Material, MaterialProperty
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor

_BOOTSTRAP_INPUT = {'class': 'form-control'}
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
            'struct_props_id',
            'created_by',
        ]
        widgets = {
            'code': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
            'description': forms.Textarea(attrs={**_BOOTSTRAP_INPUT, 'rows': 3}),
            'struct_type': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'struct_props_id': forms.Select(attrs=_BOOTSTRAP_SELECT),
            'created_by': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        }

    def __init__(self, *args, **kwargs):
        structure_load_url = kwargs.pop('structure_load_url', None)
        super().__init__(*args, **kwargs)
        attrs = {**_BOOTSTRAP_SELECT}
        if structure_load_url:
            attrs['data-load-url'] = structure_load_url

        self.fields['struct_props_id'].widget = forms.Select(
            choices=self._structure_instance_choices(),
            attrs=attrs,
        )

    def _selected_structure_type_id(self):
        value = self.data.get('struct_type') if self.data else None
        if not value:
            value = self.initial.get('struct_type')
        if not value and self.instance and self.instance.pk:
            value = self.instance.struct_type_id
        return getattr(value, 'pk', value)

    def _selected_structure_props_id(self):
        value = self.data.get('struct_props_id') if self.data else None
        if not value:
            value = self.initial.get('struct_props_id')
        if not value and self.instance and self.instance.pk:
            value = self.instance.struct_props_id
        return getattr(value, 'pk', value)

    def _structure_instance_choices(self):
        choices = [('', '---------')]
        structure_type_id = self._selected_structure_type_id()
        if not structure_type_id:
            return choices

        try:
            structure_type = StructureType.objects.get(pk=structure_type_id)
        except (StructureType.DoesNotExist, ValueError):
            return choices

        selected_id = self._selected_structure_props_id()
        instances = SQLExecutor.get_structure_instances(structure_type, limit=100)
        seen_ids = {str(instance['id']) for instance in instances}

        if selected_id and str(selected_id) not in seen_ids:
            selected_instance = SQLExecutor.get_structure_instance(structure_type, selected_id)
            if selected_instance:
                instances.append(selected_instance)

        choices.extend((str(instance['id']), structure_instance_label(instance)) for instance in instances)
        return choices
