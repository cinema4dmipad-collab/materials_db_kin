from django.contrib import admin

from .models import Property, PropertyChoice, PropertyGroup


@admin.register(PropertyGroup)
class PropertyGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order']
    list_editable = ['sort_order']


class PropertyChoiceInline(admin.TabularInline):
    model = PropertyChoice
    extra = 1
    fields = ['label', 'value', 'sort_order']


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'unit', 'data_type', 'group']
    list_filter = ['data_type', 'group']
    search_fields = ['display_name', 'name']
    inlines = [PropertyChoiceInline]
