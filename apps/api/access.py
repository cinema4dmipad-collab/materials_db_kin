from http import HTTPStatus
from uuid import UUID

from dmr.errors import ErrorType, format_error
from dmr.response import APIError
from django.http import HttpRequest

from apps.workspaces.models import Workspace
from apps.workspaces.permissions import has_workspace_perm
from apps.workspaces.services import (
    get_user_workspaces,
    materials_visible_in,
    samples_visible_in,
    scans_visible_in,
    user_has_workspace_access,
)

WORKSPACE_HEADER = 'X-Workspace-Id'


def api_error(
    message: str,
    status: HTTPStatus,
    *,
    error_type: ErrorType = ErrorType.user_msg,
) -> APIError:
    return APIError(
        format_error(message, error_type=error_type),
        status_code=status,
    )


def require_workspace(request: HttpRequest) -> Workspace:
    raw = request.headers.get(WORKSPACE_HEADER) or request.META.get(
        'HTTP_X_WORKSPACE_ID',
        '',
    )
    raw = (raw or '').strip()
    if not raw:
        raise api_error(
            f'Заголовок {WORKSPACE_HEADER} обязателен.',
            HTTPStatus.BAD_REQUEST,
        )
    try:
        workspace_id = UUID(raw)
    except ValueError as exc:
        raise api_error(
            f'Некорректный {WORKSPACE_HEADER}.',
            HTTPStatus.BAD_REQUEST,
        ) from exc

    workspace = Workspace.objects.filter(pk=workspace_id, is_active=True).first()
    user = request.user
    if (
        workspace is None
        or not user
        or not user.is_authenticated
        or not user_has_workspace_access(user, workspace)
    ):
        raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
    return workspace


def require_perm(user, workspace: Workspace, codename: str) -> None:
    if not has_workspace_perm(user, workspace, codename):
        raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)


def user_workspaces_qs(user):
    return get_user_workspaces(user)


def materials_qs(workspace):
    return materials_visible_in(workspace).select_related(
        'struct_type',
        'manufacturer',
        'availability',
        'technology',
        'home_workspace',
    )


def samples_qs(workspace):
    return samples_visible_in(workspace).select_related('material', 'workspace')


def scans_qs(workspace):
    return scans_visible_in(workspace).select_related('sample', 'workspace')
