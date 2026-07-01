from django.db.models import Q

from apps.workspaces.models import (
    BUILTIN_GROUP_MANAGER,
    BUILTIN_GROUP_OPERATOR,
    Workspace,
    WorkspaceGroup,
    WorkspaceGroupMembership,
)
from apps.workspaces.permissions import DEFAULT_GROUP_PERMISSIONS

ACTIVE_WORKSPACE_SESSION_KEY = 'active_workspace_id'
LEGACY_WORKSPACE_SLUG = 'legacy'


def _model_has_field(model, field_name: str) -> bool:
    return any(field.name == field_name for field in model._meta.get_fields())


def get_active_workspace(request):
    workspace_id = request.session.get(ACTIVE_WORKSPACE_SESSION_KEY)
    if not workspace_id:
        return None
    try:
        return Workspace.objects.get(pk=workspace_id, is_active=True)
    except (Workspace.DoesNotExist, ValueError, TypeError):
        return None


def set_active_workspace(request, workspace) -> None:
    if workspace is None:
        request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        return
    request.session[ACTIVE_WORKSPACE_SESSION_KEY] = str(workspace.pk)


def get_user_workspaces(user):
    if not user or not user.is_authenticated:
        return Workspace.objects.none()
    if user.is_superuser:
        return Workspace.objects.filter(is_active=True).order_by('name')
    return (
        Workspace.objects.filter(
            is_active=True,
            groups__memberships__user=user,
        )
        .distinct()
        .order_by('name')
    )


def get_user_groups(user, workspace):
    from apps.workspaces.permissions import get_user_groups as _get_user_groups

    return _get_user_groups(user, workspace)


def user_has_workspace_access(user, workspace) -> bool:
    from apps.workspaces.permissions import user_has_workspace_access as _user_has_workspace_access

    return _user_has_workspace_access(user, workspace)


def ensure_default_groups(workspace):
    manager_group, _ = WorkspaceGroup.objects.get_or_create(
        workspace=workspace,
        name=BUILTIN_GROUP_MANAGER,
        defaults={
            'description': 'Полный доступ к управлению пространством и данными.',
            'permissions': sorted(DEFAULT_GROUP_PERMISSIONS['manager']),
            'is_builtin': True,
        },
    )
    operator_group, _ = WorkspaceGroup.objects.get_or_create(
        workspace=workspace,
        name=BUILTIN_GROUP_OPERATOR,
        defaults={
            'description': 'Работа с материалами, образцами и сканами без администрирования.',
            'permissions': sorted(DEFAULT_GROUP_PERMISSIONS['operator']),
            'is_builtin': True,
        },
    )
    return manager_group, operator_group


def assign_user_to_groups(user, workspace, group_names):
    groups = WorkspaceGroup.objects.filter(workspace=workspace, name__in=group_names)
    for group in groups:
        WorkspaceGroupMembership.objects.get_or_create(group=group, user=user)


def assign_user_to_selected_groups(user, groups):
    by_workspace = {}
    for group in groups:
        by_workspace.setdefault(group.workspace_id, []).append(group.name)
    for workspace_id, group_names in by_workspace.items():
        assign_user_to_groups(user, Workspace.objects.get(pk=workspace_id), group_names)


def set_user_groups(user, workspace, group_names):
    WorkspaceGroupMembership.objects.filter(
        group__workspace=workspace,
        user=user,
    ).delete()
    assign_user_to_groups(user, workspace, group_names)


def ensure_legacy_workspace():
    workspace, _created = Workspace.objects.get_or_create(
        slug=LEGACY_WORKSPACE_SLUG,
        defaults={
            'name': 'Legacy',
            'description': 'Пространство по умолчанию для данных до миграции на workspaces.',
            'is_active': True,
        },
    )
    ensure_default_groups(workspace)
    return workspace


def materials_visible_in(workspace):
    from apps.materials.models import Material

    if workspace is None:
        return Material.objects.none()
    if not _model_has_field(Material, 'home_workspace'):
        return Material.objects.all()
    visibility_filter = (
        Q(home_workspace=workspace)
        | Q(visibility_mode='all_workspaces')
        | Q(visibility_mode='selected_workspaces', published_workspaces=workspace)
    )
    return Material.objects.filter(visibility_filter).distinct()


def materials_owned_by(workspace):
    from apps.materials.models import Material

    if workspace is None:
        return Material.objects.none()
    if not _model_has_field(Material, 'home_workspace'):
        return Material.objects.all()
    return Material.objects.filter(home_workspace=workspace)


def materials_shared_in(workspace):
    from apps.materials.models import Material
    from apps.workspaces.visibility import VisibilityMode

    if workspace is None:
        return Material.objects.none()
    published_filter = (
        Q(visibility_mode=VisibilityMode.ALL_WORKSPACES)
        | Q(
            visibility_mode=VisibilityMode.SELECTED_WORKSPACES,
            published_workspaces=workspace,
        )
    )
    return (
        Material.objects.filter(published_filter)
        .select_related('home_workspace')
        .distinct()
    )


def structure_types_visible_in(workspace):
    from apps.structures.models import StructureType

    if workspace is None:
        return StructureType.objects.none()
    return StructureType.objects.filter(is_active=True)


def tags_in_workspace(workspace):
    from apps.core.models import Tag

    if workspace is None:
        return Tag.objects.filter(workspace__isnull=True)
    if not _model_has_field(Tag, 'workspace'):
        return Tag.objects.all()
    return Tag.objects.filter(Q(workspace=workspace) | Q(workspace__isnull=True))


def samples_in_workspace(workspace):
    from apps.samples.models import Sample

    if workspace is None:
        return Sample.objects.none()
    if _model_has_field(Sample, 'workspace'):
        return Sample.objects.filter(workspace=workspace)
    return Sample.objects.all()


def scans_in_workspace(workspace):
    from apps.samples.models import Sample
    from apps.scans.models import ScanRecord

    if workspace is None:
        return ScanRecord.objects.none()
    if _model_has_field(ScanRecord, 'workspace'):
        return ScanRecord.objects.filter(workspace=workspace)
    if _model_has_field(Sample, 'workspace'):
        return ScanRecord.objects.filter(sample__workspace=workspace)
    return ScanRecord.objects.all()
