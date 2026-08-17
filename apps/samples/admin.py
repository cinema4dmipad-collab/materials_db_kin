from django.contrib import admin

from apps.scans.models import ScanRecord
from .models import Sample, SampleAttachment


class ScanInline(admin.TabularInline):
    model = ScanRecord
    extra = 0
    fields = ['title', 'method', 'file', 'uploaded_at']
    readonly_fields = ['uploaded_at']


class SampleAttachmentInline(admin.TabularInline):
    model = SampleAttachment
    extra = 0
    fields = ['title', 'file', 'description', 'uploaded_at']
    readonly_fields = ['uploaded_at']


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'material', 'object_type', 'created_by', 'created_at']
    search_fields = ['code', 'name', 'description', 'material__code']
    list_filter = ['object_type', 'material']
    inlines = [ScanInline, SampleAttachmentInline]


@admin.register(SampleAttachment)
class SampleAttachmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'sample', 'uploaded_at']
    search_fields = ['title', 'sample__code', 'description']
    list_filter = ['uploaded_at']
