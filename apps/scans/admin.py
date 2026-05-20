from django.contrib import admin

from .models import ScanRecord


@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'sample', 'status', 'created_at']
    search_fields = ['title', 'sample__code']
    list_filter = ['status', 'created_at']
