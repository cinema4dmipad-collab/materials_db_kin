from django.contrib import admin

from .models import Sample


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'material', 'object_type', 'created_at']
    search_fields = ['code', 'name', 'material__code']
    list_filter = ['object_type', 'material']
