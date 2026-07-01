from django.db.models import Q

from apps.workspaces.models import Workspace, WorkspaceMembership

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
        Workspace.objects.filter(is_active=True, memberships__user=user)
        .distinct()
        .order_by('name')
    )


def get_workspace_membership(user, workspace):
    if not user or not user.is_authenticated or workspace is None:
        return None
    try:
        return WorkspaceMembership.objects.get(user=user, workspace=workspace)
    except WorkspaceMembership.DoesNotExist:
        return None


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
    """Опубликованные материалы, доступные в пространстве (свои и из других WS)."""
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
    """Общий каталог типов структур — видны во всех пространствах."""
    from apps.structures.models import StructureType

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


def ensure_legacy_workspace():
    workspace, _created = Workspace.objects.get_or_create(
        slug=LEGACY_WORKSPACE_SLUG,
        defaults={
            'name': 'Legacy',
            'description': 'Пространство по умолчанию для данных до миграции на workspaces.',
            'is_active': True,
        },
    )
    return workspace
