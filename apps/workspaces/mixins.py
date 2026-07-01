from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from apps.workspaces.models import Workspace
from apps.workspaces.permissions import WorkspacePerm, can_manage_groups, has_workspace_perm, is_system_admin
from apps.workspaces.services import get_active_workspace


class LoginRequiredMixin(DjangoLoginRequiredMixin):
    pass


class WorkspaceRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        workspace = getattr(request, 'active_workspace', None) or get_active_workspace(request)
        if workspace is None and not request.user.is_superuser:
            return redirect('workspaces:select')
        return super().dispatch(request, *args, **kwargs)


class PermissionRequiredMixin(LoginRequiredMixin):
    permission_codename = None

    def dispatch(self, request, *args, **kwargs):
        codename = self.get_permission_codename()
        workspace = getattr(request, 'active_workspace', None) or get_active_workspace(request)
        if not has_workspace_perm(request.user, workspace, codename):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_permission_codename(self):
        if not self.permission_codename:
            raise ImproperlyConfigured(
                f'{self.__class__.__name__} requires permission_codename.'
            )
        return self.permission_codename


class SystemAdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not is_system_admin(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class WorkspaceMemberManageMixin(LoginRequiredMixin):
    """Admin — любое пространство; менеджер — только активное."""

    def dispatch(self, request, *args, **kwargs):
        self.workspace = get_object_or_404(Workspace, pk=kwargs['pk'])
        if not has_workspace_perm(request.user, self.workspace, WorkspacePerm.MANAGE_MEMBERS):
            raise PermissionDenied
        if not is_system_admin(request.user):
            active_workspace = getattr(request, 'active_workspace', None) or get_active_workspace(
                request
            )
            if active_workspace is None or active_workspace.pk != self.workspace.pk:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class WorkspaceGroupManageMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        self.workspace = get_object_or_404(Workspace, pk=kwargs['pk'])
        if not can_manage_groups(request.user, self.workspace):
            raise PermissionDenied
        if not is_system_admin(request.user):
            active_workspace = getattr(request, 'active_workspace', None) or get_active_workspace(
                request
            )
            if active_workspace is None or active_workspace.pk != self.workspace.pk:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AppViewMixin(LoginRequiredMixin, WorkspaceRequiredMixin):
    pass


def workspace_login_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        workspace = getattr(request, 'active_workspace', None) or get_active_workspace(request)
        if workspace is None and not request.user.is_superuser:
            return redirect('workspaces:select')
        return view_func(request, *args, **kwargs)

    return _wrapped_view
