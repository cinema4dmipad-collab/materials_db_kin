from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse

from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.services import (
    ACTIVE_WORKSPACE_SESSION_KEY,
    LEGACY_WORKSPACE_SLUG,
    ensure_legacy_workspace,
    get_active_workspace,
    get_user_workspaces,
    get_workspace_membership,
    set_active_workspace,
)

TEST_AUTOMATION_USERNAME = 'test-automation'

_EXEMPT_URL_NAMES = frozenset(
    {
        'accounts:login',
        'accounts:logout',
        'workspaces:select',
        'workspaces:switch',
        'core:debug',
    }
)
_EXEMPT_PATH_PREFIXES = ('/admin/',)


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


class WorkspaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_workspace = None
        request.workspace_membership = None

        if _is_exempt_request(request):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)

        active_workspace = get_active_workspace(request)
        if active_workspace is None:
            workspaces = list(get_user_workspaces(user))
            if len(workspaces) == 1:
                set_active_workspace(request, workspaces[0])
                active_workspace = workspaces[0]
            elif not workspaces:
                if user.is_superuser:
                    legacy = Workspace.objects.filter(
                        slug=LEGACY_WORKSPACE_SLUG,
                        is_active=True,
                    ).first()
                    if legacy:
                        set_active_workspace(request, legacy)
                        active_workspace = legacy
                else:
                    return HttpResponseRedirect(reverse('workspaces:select'))
            else:
                return HttpResponseRedirect(reverse('workspaces:select'))

        if active_workspace is not None:
            membership = get_workspace_membership(user, active_workspace)
            if membership is None and not user.is_superuser:
                request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
                return HttpResponseRedirect(reverse('workspaces:select'))
            request.active_workspace = active_workspace
            request.workspace_membership = membership

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
            WorkspaceMembership.objects.get_or_create(
                workspace=workspace,
                user=user,
                defaults={'role': WorkspaceRole.MANAGER},
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session[ACTIVE_WORKSPACE_SESSION_KEY] = str(workspace.pk)
        return self.get_response(request)
