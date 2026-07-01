from apps.workspaces.models import WorkspaceMembership, WorkspaceRole


class WorkspacePerm:
    VIEW = 'workspace.view'
    MANAGE_SETTINGS = 'workspace.manage_settings'
    MANAGE_MEMBERS = 'workspace.manage_members'

    MATERIAL_VIEW = 'material.view'
    MATERIAL_CREATE = 'material.create'
    MATERIAL_EDIT = 'material.edit'
    MATERIAL_DELETE = 'material.delete'
    MATERIAL_PUBLISH = 'material.publish'

    STRUCTURE_VIEW = 'structure.view'
    STRUCTURE_CREATE = 'structure.create'
    STRUCTURE_EDIT = 'structure.edit'
    STRUCTURE_DELETE = 'structure.delete'
    STRUCTURE_PUBLISH = 'structure.publish'

    SAMPLE_VIEW = 'sample.view'
    SAMPLE_CREATE = 'sample.create'
    SAMPLE_EDIT = 'sample.edit'
    SAMPLE_DELETE = 'sample.delete'

    SCAN_VIEW = 'scan.view'
    SCAN_CREATE = 'scan.create'
    SCAN_EDIT = 'scan.edit'
    SCAN_DELETE = 'scan.delete'

    PROPERTY_VIEW = 'property.view'
    PROPERTY_CREATE = 'property.create'
    PROPERTY_EDIT = 'property.edit'
    PROPERTY_DELETE = 'property.delete'

    TAG_VIEW = 'tag.view'
    TAG_CREATE = 'tag.create'
    TAG_EDIT = 'tag.edit'
    TAG_DELETE = 'tag.delete'

    USER_MANAGE = 'user.manage'


ALL_WORKSPACE_PERMISSIONS = (
    WorkspacePerm.VIEW,
    WorkspacePerm.MANAGE_SETTINGS,
    WorkspacePerm.MANAGE_MEMBERS,
    WorkspacePerm.MATERIAL_VIEW,
    WorkspacePerm.MATERIAL_CREATE,
    WorkspacePerm.MATERIAL_EDIT,
    WorkspacePerm.MATERIAL_DELETE,
    WorkspacePerm.MATERIAL_PUBLISH,
    WorkspacePerm.STRUCTURE_VIEW,
    WorkspacePerm.STRUCTURE_CREATE,
    WorkspacePerm.STRUCTURE_EDIT,
    WorkspacePerm.STRUCTURE_DELETE,
    WorkspacePerm.STRUCTURE_PUBLISH,
    WorkspacePerm.SAMPLE_VIEW,
    WorkspacePerm.SAMPLE_CREATE,
    WorkspacePerm.SAMPLE_EDIT,
    WorkspacePerm.SAMPLE_DELETE,
    WorkspacePerm.SCAN_VIEW,
    WorkspacePerm.SCAN_CREATE,
    WorkspacePerm.SCAN_EDIT,
    WorkspacePerm.SCAN_DELETE,
    WorkspacePerm.PROPERTY_VIEW,
    WorkspacePerm.PROPERTY_CREATE,
    WorkspacePerm.PROPERTY_EDIT,
    WorkspacePerm.PROPERTY_DELETE,
    WorkspacePerm.TAG_VIEW,
    WorkspacePerm.TAG_CREATE,
    WorkspacePerm.TAG_EDIT,
    WorkspacePerm.TAG_DELETE,
    WorkspacePerm.USER_MANAGE,
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    WorkspaceRole.MANAGER: frozenset(
        {
            WorkspacePerm.VIEW,
            WorkspacePerm.MANAGE_SETTINGS,
            WorkspacePerm.MANAGE_MEMBERS,
            WorkspacePerm.MATERIAL_VIEW,
            WorkspacePerm.MATERIAL_CREATE,
            WorkspacePerm.MATERIAL_EDIT,
            WorkspacePerm.MATERIAL_DELETE,
            WorkspacePerm.MATERIAL_PUBLISH,
            WorkspacePerm.STRUCTURE_VIEW,
            WorkspacePerm.SAMPLE_VIEW,
            WorkspacePerm.SAMPLE_CREATE,
            WorkspacePerm.SAMPLE_EDIT,
            WorkspacePerm.SAMPLE_DELETE,
            WorkspacePerm.SCAN_VIEW,
            WorkspacePerm.SCAN_CREATE,
            WorkspacePerm.SCAN_EDIT,
            WorkspacePerm.SCAN_DELETE,
            WorkspacePerm.PROPERTY_VIEW,
            WorkspacePerm.TAG_VIEW,
            WorkspacePerm.TAG_CREATE,
            WorkspacePerm.TAG_EDIT,
            WorkspacePerm.TAG_DELETE,
        }
    ),
    WorkspaceRole.OPERATOR: frozenset(
        {
            WorkspacePerm.VIEW,
            WorkspacePerm.MATERIAL_VIEW,
            WorkspacePerm.MATERIAL_CREATE,
            WorkspacePerm.MATERIAL_EDIT,
            WorkspacePerm.STRUCTURE_VIEW,
            WorkspacePerm.SAMPLE_VIEW,
            WorkspacePerm.SAMPLE_CREATE,
            WorkspacePerm.SAMPLE_EDIT,
            WorkspacePerm.SCAN_VIEW,
            WorkspacePerm.SCAN_CREATE,
            WorkspacePerm.SCAN_EDIT,
            WorkspacePerm.PROPERTY_VIEW,
            WorkspacePerm.TAG_VIEW,
            WorkspacePerm.TAG_CREATE,
            WorkspacePerm.TAG_EDIT,
            WorkspacePerm.TAG_DELETE,
        }
    ),
}


def can_manage_properties(user) -> bool:
    """Справочник свойств — общий каталог; управление только у admin."""
    return is_system_admin(user)


def can_manage_global_tags(user) -> bool:
    """Общие теги — глобальный справочник; управление только у admin."""
    return is_system_admin(user)


def can_manage_tag(user, tag, workspace) -> bool:
    """Admin — любой тег; остальные — только теги своего пространства."""
    if not user or not user.is_authenticated or tag is None:
        return False
    if tag.is_global:
        return is_system_admin(user)
    if workspace is None or tag.workspace_id != workspace.pk:
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.TAG_EDIT)


def is_system_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


def get_membership_role(user, workspace) -> str | None:
    if not user or not user.is_authenticated or workspace is None:
        return None
    membership = (
        WorkspaceMembership.objects.filter(user=user, workspace=workspace)
        .values_list('role', flat=True)
        .first()
    )
    return membership


def has_workspace_perm(user, workspace, codename: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if codename not in ALL_WORKSPACE_PERMISSIONS:
        return False
    if is_system_admin(user):
        return True
    if workspace is None:
        return False
    role = get_membership_role(user, workspace)
    if role is None:
        return False
    return codename in ROLE_PERMISSIONS.get(role, frozenset())


def is_editable_in_workspace(user, obj, workspace) -> bool:
    """Admin — любой материал; остальные — только home_workspace активного WS."""
    if is_system_admin(user):
        return True
    if obj is None or workspace is None:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_EDIT):
        return False
    return obj.is_editable_in(workspace)


def can_delete_in_workspace(user, obj, workspace) -> bool:
    if not is_editable_in_workspace(user, obj, workspace):
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_DELETE)


def can_manage_structure_types(user) -> bool:
    """Типы структур — общий каталог; управление только у admin."""
    return is_system_admin(user)


def can_manage_membership(user, membership) -> bool:
    """Admin управляет всеми участниками; менеджер — только операторами."""
    if not user or not user.is_authenticated or membership is None:
        return False
    if is_system_admin(user):
        return True
    return membership.role == WorkspaceRole.OPERATOR
