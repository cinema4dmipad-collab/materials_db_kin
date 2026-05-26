from django.contrib import admin

from .models import CompositeLayer


@admin.register(CompositeLayer)
class CompositeLayerAdmin(admin.ModelAdmin):
    list_display = ['parent_material', 'layer_number', 'material', 'angle', 'thickness']
    list_filter = ['parent_material']
