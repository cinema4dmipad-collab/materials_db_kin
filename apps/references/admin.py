from django.contrib import admin

from .models import Availability, Manufacturer, Property, PropertyChoice, PropertyGroup, Technology


class DictionaryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code', 'description']
    ordering = ['name']


@admin.register(Manufacturer)
class ManufacturerAdmin(DictionaryAdmin):
    pass


@admin.register(Availability)
class AvailabilityAdmin(DictionaryAdmin):
    pass


@admin.register(Technology)
class TechnologyAdmin(DictionaryAdmin):
    pass


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
