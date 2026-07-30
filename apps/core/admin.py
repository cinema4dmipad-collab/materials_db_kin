from django.contrib import admin

from apps.core.models import BackupRun, BackupSettings, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'workspace', 'created_at')
    list_filter = ('workspace',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(BackupSettings)
class BackupSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'enabled',
        'schedule_hour',
        'schedule_minute',
        'retention_count',
        'updated_at',
        'updated_by',
    )

    def has_add_permission(self, request):
        return not BackupSettings.objects.filter(pk=1).exists()


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = (
        'started_at',
        'finished_at',
        'trigger',
        'status',
        'filename',
        'size_bytes',
        'created_by',
    )
    list_filter = ('trigger', 'status')
    search_fields = ('filename', 'error_message')
    readonly_fields = (
        'started_at',
        'finished_at',
        'trigger',
        'status',
        'filename',
        'size_bytes',
        'error_message',
        'created_by',
    )
    ordering = ('-started_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
