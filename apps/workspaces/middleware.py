from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse

from apps.workspaces.models import BUILTIN_GROUP_MANAGER
from apps.workspaces.permissions import (
    can_manage_global_groups,
    can_manage_global_users,
    can_manage_global_workspaces,
)
from apps.workspaces.services import (
    ACTIVE_WORKSPACE_SESSION_KEY,
    assign_user_to_groups,
    ensure_default_groups,
    ensure_legacy_workspace,
    get_user_groups,
    resolve_active_workspace_for_user,
    user_has_workspace_access,
)

TEST_AUTOMATION_USERNAME = 'test-automation'

_EXEMPT_URL_NAMES = frozenset(
    {
        'accounts:login',
        'accounts:logout',
        'accounts:profile',
        'accounts:profile_edit',
        'accounts:password_change',
        'accounts:token_create',
        'accounts:token_update',
        'accounts:token_rotate',
        'accounts:token_revoke',
        'accounts:token_dismiss_secret',
        'workspaces:select',
        'workspaces:switch',
        'core:debug',
        'core:help',
        'administration:backups',
        'administration:backup_manual',
        'administration:backup_restore',
        'administration:backup_cancel_running',
        'administration:backup_delete_dump',
        'administration:backup_download',
    }
)
_EXEMPT_PATH_PREFIXES = ('/admin/', '/api/')


def _is_exempt_request(request) -> bool:
    path = request.path
    static_url = settings.STATIC_URL
    if static_url and path.startswith(static_url):
        return True
    media_url = getattr(settings, 'MEDIA_URL', None)
    if media_url and path.startswith(media_url):
        return True
    for prefix in _EXEMPT_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    match = getattr(request, 'resolver_match', None)
    if match is None:
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return False
    url_name = match.url_name or ''
    if match.namespace:
        url_name = f'{match.namespace}:{url_name}'
    return url_name in _EXEMPT_URL_NAMES


_ADMIN_USER_URL_NAMES = frozenset(
    {
        'admin_users',
        'admin_user_create',
        'admin_user_edit',
        'admin_user_memberships',
    }
)
_ADMIN_WORKSPACE_URL_NAMES = frozenset(
    {
        'admin_workspaces',
        'admin_workspace_create',
        'admin_workspace_edit',
        'admin_workspace_delete',
    }
)
_WORKSPACE_GROUP_URL_NAMES = frozenset(
    {
        'groups',
        'group_create',
        'group_edit',
        'group_delete',
    }
)


def _route_allowed_without_active_workspace(request, user) -> bool:
    match = getattr(request, 'resolver_match', None)
    if match is None:
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return False

    namespace = match.namespace or ''
    url_name = match.url_name or ''

    if namespace == 'administration':
        if url_name in _ADMIN_USER_URL_NAMES:
            return can_manage_global_users(user)
        if url_name in _ADMIN_WORKSPACE_URL_NAMES:
            return can_manage_global_workspaces(user)
        return False

    if namespace == 'workspaces' and url_name in _WORKSPACE_GROUP_URL_NAMES:
        return can_manage_global_groups(user)

    return False


class WorkspaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_workspace = None
        request.workspace_user_groups = []

        if _is_exempt_request(request):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)

        active_workspace = resolve_active_workspace_for_user(request, user)
        if active_workspace is None:
            if _route_allowed_without_active_workspace(request, user):
                return self.get_response(request)
            return HttpResponseRedirect(reverse('workspaces:select'))

        if active_workspace is not None:
            if not user_has_workspace_access(user, active_workspace):
                request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
                return HttpResponseRedirect(reverse('workspaces:select'))
            request.active_workspace = active_workspace
            request.workspace_user_groups = list(get_user_groups(user, active_workspace))

        return self.get_response(request)


class TestAutoLoginMiddleware:
    """Автовход в тестах для legacy-набора данных."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.TESTING and not request.user.is_authenticated:
            user_model = get_user_model()
            user, _ = user_model.objects.get_or_create(
                username=TEST_AUTOMATION_USERNAME,
                defaults={'is_staff': True},
            )
            workspace = ensure_legacy_workspace()
            ensure_default_groups(workspace)
            assign_user_to_groups(user, workspace, [BUILTIN_GROUP_MANAGER])
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session[ACTIVE_WORKSPACE_SESSION_KEY] = str(workspace.pk)
        return self.get_response(request)
