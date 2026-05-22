from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.structures.models import (
    StructureField,
    StructureFieldValue,
    StructureInstance,
    StructureType,
)
from apps.structures.sql_executor import SQLExecutor


class StructureFieldInline(admin.TabularInline):
    model = StructureField
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
        'foreign_key_model',
    ]


class StructureFieldValueInline(admin.TabularInline):
    model = StructureFieldValue
    extra = 0
    readonly_fields = ['field']


@admin.register(StructureType)
class StructureTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'table_name', 'code', 'is_created', 'is_active', 'created_at']
    list_filter = ['is_created', 'is_active']
    search_fields = ['name', 'code', 'table_name']
    prepopulated_fields = {'code': ('name',)}
    readonly_fields = ['table_name', 'is_created']
    inlines = [StructureFieldInline]
    actions = ['create_table_action']

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


@admin.register(StructureInstance)
class StructureInstanceAdmin(admin.ModelAdmin):
    list_display = ['code', 'structure_type', 'dynamic_row_id', 'created_at']
    search_fields = ['code']
    list_filter = ['structure_type']
    inlines = [StructureFieldValueInline]


@admin.register(StructureField)
class StructureFieldAdmin(admin.ModelAdmin):
    list_display = ['structure_type', 'name', 'label', 'field_type', 'is_required', 'sort_order']
    list_filter = ['structure_type', 'field_type']
    search_fields = ['name', 'label']


@admin.register(StructureFieldValue)
class StructureFieldValueAdmin(admin.ModelAdmin):
    list_display = ['instance', 'field', 'get_display_value']
    list_filter = ['field__structure_type']

    @admin.display(description='Значение')
    def get_display_value(self, obj):
        return obj.get_value()
