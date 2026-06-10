from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.structures.default_values import validate_structure_field_default
from apps.structures.models import (
    MATERIAL_LINK_FIELD_TYPE,
    STRUCTURE_FIELD_LOCK_ERROR,
    StructureField,
    StructureType,
)
from apps.structures.sql_executor import SQLExecutor


class StructureFieldAdminForm(forms.ModelForm):
    class Meta:
        model = StructureField
        exclude = ['foreign_key_model']

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['foreign_key_model'] = ''
        if cleaned_data.get('field_type') == MATERIAL_LINK_FIELD_TYPE:
            cleaned_data['max_length'] = None
            cleaned_data['max_digits'] = None
            cleaned_data['decimal_places'] = None

        default_value = (cleaned_data.get('default_value') or '').strip()
        field_type = cleaned_data.get('field_type')
        if default_value and field_type:
            try:
                validate_structure_field_default(
                    field_type=field_type,
                    default_value=default_value,
                    label=(cleaned_data.get('label') or '').strip(),
                    name=(cleaned_data.get('name') or '').strip(),
                    max_digits=cleaned_data.get('max_digits'),
                    decimal_places=cleaned_data.get('decimal_places'),
                )
            except ValueError as exc:
                self.add_error('default_value', str(exc))
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


class StructureFieldInline(admin.TabularInline):
    model = StructureField
    form = StructureFieldAdminForm
    extra = 1
    fields = [
        'name',
        'label',
        'field_type',
        'is_required',
        'sort_order',
        'max_length',
        'max_digits',
        'decimal_places',
    ]

    def _is_locked(self, obj):
        return bool(obj and obj.is_created)

    def has_add_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if self._is_locked(obj):
            return list(self.fields)
        return super().get_readonly_fields(request, obj)

    def get_extra(self, request, obj=None, **kwargs):
        if self._is_locked(obj):
            return 0
        return super().get_extra(request, obj, **kwargs)

    def get_max_num(self, request, obj=None, **kwargs):
        if self._is_locked(obj):
            return obj.fields.count()
        return super().get_max_num(request, obj, **kwargs)


@admin.register(StructureType)
class StructureTypeAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'table_name',
        'code',
        'allow_layers',
        'is_created',
        'is_active',
        'create_table_button',
        'created_at',
    ]
    list_filter = ['allow_layers', 'is_created', 'is_active']
    search_fields = ['name', 'code', 'table_name']
    prepopulated_fields = {'code': ('name',)}
    readonly_fields = ['table_name', 'is_created']
    inlines = [StructureFieldInline]
    actions = ['create_table_action']
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'table_name', 'description', 'display_color', 'allow_layers', 'is_active'),
        }),
        ('Статус', {
            'fields': ('is_created',),
        }),
    )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        structure_type = self.get_object(request, object_id)
        if structure_type and structure_type.is_created:
            messages.warning(
                request,
                'SQL-таблица уже создана: поля структуры доступны только для чтения.',
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/create-table/',
                self.admin_site.admin_view(self.create_table_view),
                name='structures_structuretype_create_table',
            ),
            path(
                '<path:object_id>/drop-table/',
                self.admin_site.admin_view(self.drop_table_view),
                name='structures_structuretype_drop_table',
            ),
        ]
        return custom + urls

    def create_table_button(self, obj):
        if not obj.pk:
            return '—'
        if obj.is_created:
            return format_html('<span class="text-success">Таблица создана</span>')
        url = reverse('admin:structures_structuretype_create_table', args=[obj.pk])
        return format_html('<a class="button" href="{}">Создать таблицу в БД</a>', url)

    create_table_button.short_description = 'Таблица'

    def create_table_view(self, request, object_id):
        structure_type = StructureType.objects.get(pk=object_id)
        result = SQLExecutor.create_table(structure_type)
        if result['success']:
            messages.success(request, f'Таблица {structure_type.table_name} создана.')
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
        return redirect('admin:structures_structuretype_change', object_id)

    def drop_table_view(self, request, object_id):
        structure_type = StructureType.objects.get(pk=object_id)
        result = SQLExecutor.drop_table(structure_type)
        if result['success']:
            messages.success(request, f'Таблица {structure_type.table_name} удалена.')
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
        return redirect('admin:structures_structuretype_change', object_id)

    @admin.action(description='Создать таблицы для выбранных типов')
    def create_table_action(self, request, queryset):
        created = 0
        for st in queryset.filter(is_created=False):
            result = SQLExecutor.create_table(st)
            if result['success']:
                created += 1
            else:
                self.message_user(
                    request, f'{st.name}: {result["error"]}', level=messages.ERROR
                )
        if created:
            self.message_user(request, f'Создано таблиц: {created}', level=messages.SUCCESS)


@admin.register(StructureField)
class StructureFieldAdmin(admin.ModelAdmin):
    form = StructureFieldAdminForm
    list_display = ['structure_type', 'name', 'label', 'field_type', 'is_required', 'sort_order']
    list_filter = ['structure_type', 'field_type']
    search_fields = ['name', 'label']

    def _request_structure_type_id(self, request):
        if request is None:
            return None
        return request.POST.get('structure_type') or request.GET.get('structure_type')

    def _is_structure_type_locked(self, structure_type_id):
        if not structure_type_id:
            return False
        return StructureType.objects.filter(pk=structure_type_id, is_created=True).exists()

    def _is_field_locked(self, obj):
        return bool(
            obj
            and obj.pk
            and StructureField.objects.filter(
                pk=obj.pk, structure_type__is_created=True
            ).exists()
        )

    def has_add_permission(self, request):
        if self._is_structure_type_locked(self._request_structure_type_id(request)):
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if self._is_field_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_field_locked(obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except ValidationError:
            self.message_user(request, STRUCTURE_FIELD_LOCK_ERROR, level=messages.ERROR)

    def delete_queryset(self, request, queryset):
        try:
            super().delete_queryset(request, queryset)
        except ValidationError:
            self.message_user(request, STRUCTURE_FIELD_LOCK_ERROR, level=messages.ERROR)


