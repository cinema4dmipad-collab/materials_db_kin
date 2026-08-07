from django.contrib import admin

from .models import ScanRecord

@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'sample', 'method', 'file_preview', 'has_preview', 'uploaded_at', 'uploaded_by']
    search_fields = ['title', 'sample__code', 'description']
    list_filter = ['method', 'uploaded_at']
    readonly_fields = ['file_preview', 'uploaded_at']

    @admin.display(description='Файл')
    def file_preview(self, obj):
        if obj.file:
            return obj.filename
        return '—'

    @admin.display(description='Превью', boolean=True)
    def has_preview(self, obj):
        return bool(obj.preview)
