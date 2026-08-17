from django.contrib import admin

from .models import ScanAttachment, ScanRecord


class ScanAttachmentInline(admin.TabularInline):
    model = ScanAttachment
    extra = 0
    fields = ['title', 'file', 'preview_status', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'sample', 'method', 'file_preview', 'has_preview', 'uploaded_at', 'uploaded_by']
    search_fields = ['title', 'sample__code', 'description']
    list_filter = ['method', 'uploaded_at']
    readonly_fields = ['file_preview', 'uploaded_at']
    inlines = [ScanAttachmentInline]

    @admin.display(description='Файл')
    def file_preview(self, obj):
        if obj.file:
            return obj.filename
        return '—'

    @admin.display(description='Превью', boolean=True)
    def has_preview(self, obj):
        from apps.scans.previews import has_any_preview

        return has_any_preview(obj)


@admin.register(ScanAttachment)
class ScanAttachmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'scan', 'preview_status', 'uploaded_at', 'uploaded_by']
    search_fields = ['title', 'scan__title', 'file']
    list_filter = ['preview_status', 'uploaded_at']

