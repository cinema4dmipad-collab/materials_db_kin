from django.contrib import admin

from apps.workspaces.models import Workspace, WorkspaceGroup, WorkspaceGroupMembership


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(WorkspaceGroup)
class WorkspaceGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'is_builtin')
    list_filter = ('is_builtin', 'workspace')
    search_fields = ('name', 'workspace__name', 'workspace__slug')


@admin.register(WorkspaceGroupMembership)
class WorkspaceGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'workspace')
    list_filter = ('group__workspace',)
    search_fields = ('user__username', 'group__name', 'group__workspace__name')
    autocomplete_fields = ('user', 'group')

    @admin.display(description='Пространство')
    def workspace(self, obj):
        return obj.group.workspace
