from django.contrib import admin

from .models import Material, MaterialProperty


class MaterialPropertyInline(admin.TabularInline):
    model = MaterialProperty
    extra = 1


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'created_at']
    search_fields = ['code', 'name']
    list_filter = ['created_at']
    inlines = [MaterialPropertyInline]


@admin.register(MaterialProperty)
class MaterialPropertyAdmin(admin.ModelAdmin):
    list_display = ['material', 'property', 'value']
    search_fields = ['material__code', 'property__name']
