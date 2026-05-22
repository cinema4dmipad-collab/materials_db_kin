from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import path, reverse

from .models import Material, MaterialProperty
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor


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


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = '__all__'
        widgets = {
            'struct_props_id': forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['struct_props_id']
        structure_load_url = reverse('admin:materials_material_load_structure_instances')
        field.widget = forms.Select(
            choices=self._structure_instance_choices(),
            attrs={'data-load-url': structure_load_url},
        )

    def _selected_structure_type_id(self):
        value = self.data.get('struct_type') if self.data else None
        if not value:
            value = self.initial.get('struct_type')
        if not value and self.instance and self.instance.pk:
            value = self.instance.struct_type_id
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

    def _selected_structure_props_id(self):
        value = self.data.get('struct_props_id') if self.data else None
        if not value:
            value = self.initial.get('struct_props_id')
        if not value and self.instance and self.instance.pk:
            value = self.instance.struct_props_id
        return getattr(value, 'pk', value)


class MaterialPropertyInline(admin.TabularInline):
    model = MaterialProperty
    extra = 1


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    form = MaterialForm
    list_display = ['code', 'name', 'struct_type', 'struct_props_preview', 'created_at']
    search_fields = ['code', 'name']
    list_filter = ['struct_type', 'created_at']
    readonly_fields = ['struct_props_preview']
    inlines = [MaterialPropertyInline]

    class Media:
        js = ['admin/js/dynamic_structure.js']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'ajax/load-structure-instances/',
                self.admin_site.admin_view(self.load_structure_instances),
                name='materials_material_load_structure_instances',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Параметры структуры')
    def struct_props_preview(self, obj):
        if not obj or not obj.pk:
            return '-'
        params = obj.get_structure_params()
        if not params:
            return '-'

        preview = [
            f'{key}: {value}'
            for key, value in params.items()
            if key not in STRUCTURE_SERVICE_FIELDS and value not in (None, '')
        ]
        return ', '.join(preview[:3]) or '-'

    def load_structure_instances(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        structure_type_id = request.GET.get('structure_type_id')
        if not structure_type_id:
            return JsonResponse({'instances': []})

        try:
            structure_type = StructureType.objects.get(pk=structure_type_id)
        except (StructureType.DoesNotExist, ValueError):
            return JsonResponse({'instances': []})

        instances = [
            {'id': str(instance['id']), 'name': structure_instance_label(instance)}
            for instance in SQLExecutor.get_structure_instances(structure_type, limit=100)
        ]
        return JsonResponse({'instances': instances})


@admin.register(MaterialProperty)
class MaterialPropertyAdmin(admin.ModelAdmin):
    list_display = ['material', 'property', 'value']
    search_fields = ['material__code', 'property__name']
