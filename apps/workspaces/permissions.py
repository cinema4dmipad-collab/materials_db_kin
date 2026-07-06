from apps.workspaces.models import WorkspaceGroup, WorkspaceGroupMembership


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

PRIVILEGED_PERMISSIONS = frozenset(
    {
        WorkspacePerm.MANAGE_SETTINGS,
        WorkspacePerm.MANAGE_MEMBERS,
        WorkspacePerm.USER_MANAGE,
    }
)

PERMISSION_LABELS = {
    WorkspacePerm.VIEW: 'Просмотр пространства',
    WorkspacePerm.MANAGE_SETTINGS: 'Настройки пространства',
    WorkspacePerm.MANAGE_MEMBERS: 'Управление участниками',
    WorkspacePerm.MATERIAL_VIEW: 'Просмотр материалов',
    WorkspacePerm.MATERIAL_CREATE: 'Создание материалов',
    WorkspacePerm.MATERIAL_EDIT: 'Редактирование материалов',
    WorkspacePerm.MATERIAL_DELETE: 'Удаление материалов',
    WorkspacePerm.MATERIAL_PUBLISH: 'Публикация материалов',
    WorkspacePerm.STRUCTURE_VIEW: 'Просмотр структур',
    WorkspacePerm.STRUCTURE_CREATE: 'Создание типов структур',
    WorkspacePerm.STRUCTURE_EDIT: 'Редактирование типов структур',
    WorkspacePerm.STRUCTURE_DELETE: 'Удаление типов структур',
    WorkspacePerm.STRUCTURE_PUBLISH: 'Публикация типов структур',
    WorkspacePerm.SAMPLE_VIEW: 'Просмотр образцов',
    WorkspacePerm.SAMPLE_CREATE: 'Создание образцов',
    WorkspacePerm.SAMPLE_EDIT: 'Редактирование образцов',
    WorkspacePerm.SAMPLE_DELETE: 'Удаление образцов',
    WorkspacePerm.SCAN_VIEW: 'Просмотр сканов',
    WorkspacePerm.SCAN_CREATE: 'Загрузка сканов',
    WorkspacePerm.SCAN_EDIT: 'Редактирование сканов',
    WorkspacePerm.SCAN_DELETE: 'Удаление сканов',
    WorkspacePerm.PROPERTY_VIEW: 'Просмотр свойств',
    WorkspacePerm.PROPERTY_CREATE: 'Создание свойств',
    WorkspacePerm.PROPERTY_EDIT: 'Редактирование свойств',
    WorkspacePerm.PROPERTY_DELETE: 'Удаление свойств',
    WorkspacePerm.TAG_VIEW: 'Просмотр тегов',
    WorkspacePerm.TAG_CREATE: 'Создание тегов',
    WorkspacePerm.TAG_EDIT: 'Редактирование тегов',
    WorkspacePerm.TAG_DELETE: 'Удаление тегов',
    WorkspacePerm.USER_MANAGE: 'Управление пользователями',
}

PERMISSION_SECTIONS = (
    ('Пространство', (WorkspacePerm.VIEW, WorkspacePerm.MANAGE_SETTINGS, WorkspacePerm.MANAGE_MEMBERS)),
    (
        'Материалы',
        (
            WorkspacePerm.MATERIAL_VIEW,
            WorkspacePerm.MATERIAL_CREATE,
            WorkspacePerm.MATERIAL_EDIT,
            WorkspacePerm.MATERIAL_DELETE,
            WorkspacePerm.MATERIAL_PUBLISH,
        ),
    ),
    (
        'Структуры',
        (
            WorkspacePerm.STRUCTURE_VIEW,
            WorkspacePerm.STRUCTURE_CREATE,
            WorkspacePerm.STRUCTURE_EDIT,
            WorkspacePerm.STRUCTURE_DELETE,
            WorkspacePerm.STRUCTURE_PUBLISH,
        ),
    ),
    (
        'Образцы',
        (
            WorkspacePerm.SAMPLE_VIEW,
            WorkspacePerm.SAMPLE_CREATE,
            WorkspacePerm.SAMPLE_EDIT,
            WorkspacePerm.SAMPLE_DELETE,
        ),
    ),
    (
        'Сканы',
        (
            WorkspacePerm.SCAN_VIEW,
            WorkspacePerm.SCAN_CREATE,
            WorkspacePerm.SCAN_EDIT,
            WorkspacePerm.SCAN_DELETE,
        ),
    ),
    (
        'Справочники',
        (
            WorkspacePerm.PROPERTY_VIEW,
            WorkspacePerm.PROPERTY_CREATE,
            WorkspacePerm.PROPERTY_EDIT,
            WorkspacePerm.PROPERTY_DELETE,
            WorkspacePerm.TAG_VIEW,
            WorkspacePerm.TAG_CREATE,
            WorkspacePerm.TAG_EDIT,
            WorkspacePerm.TAG_DELETE,
        ),
    ),
    ('Администрирование', (WorkspacePerm.USER_MANAGE,)),
)

DEFAULT_GROUP_PERMISSIONS = {
    'manager': frozenset(
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
    'operator': frozenset(
        {
            WorkspacePerm.VIEW,
            WorkspacePerm.MATERIAL_VIEW,
            WorkspacePerm.MATERIAL_CREATE,
            WorkspacePerm.MATERIAL_EDIT,
            WorkspacePerm.MATERIAL_PUBLISH,
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
    return is_system_admin(user)


def can_manage_global_tags(user, workspace=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_system_admin(user):
        return True
    if workspace is None:
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.TAG_EDIT)


def can_manage_tag(user, tag, workspace) -> bool:
    if not user or not user.is_authenticated or tag is None:
        return False
    if tag.is_global:
        return can_manage_global_tags(user, workspace)
    if workspace is None or tag.workspace_id != workspace.pk:
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.TAG_EDIT)


def is_system_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


def get_user_groups(user, workspace):
    if not user or not user.is_authenticated or workspace is None:
        return WorkspaceGroup.objects.none()
    return WorkspaceGroup.objects.filter(
        workspace=workspace,
        memberships__user=user,
    ).distinct()


def get_user_permissions(user, workspace) -> frozenset:
    if not user or not user.is_authenticated:
        return frozenset()
    if is_system_admin(user):
        return frozenset(ALL_WORKSPACE_PERMISSIONS)
    if workspace is None:
        return frozenset()
    permissions = set()
    for group in get_user_groups(user, workspace):
        permissions.update(group.permission_set())
    return frozenset(permissions)


def user_has_workspace_access(user, workspace) -> bool:
    if is_system_admin(user):
        return True
    if workspace is None:
        return False
    return WorkspaceGroupMembership.objects.filter(
        group__workspace=workspace,
        user=user,
    ).exists()


def has_workspace_perm(user, workspace, codename: str) -> bool:
    if codename not in ALL_WORKSPACE_PERMISSIONS:
        return False
    return codename in get_user_permissions(user, workspace)


def is_editable_in_workspace(user, obj, workspace) -> bool:
    if is_system_admin(user):
        return True
    if obj is None or workspace is None:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_EDIT):
        return False
    return obj.is_editable_in(workspace)


def can_edit_structure_records(user, structure_type, workspace) -> bool:
    if is_system_admin(user):
        return True
    if structure_type is None or workspace is None:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_EDIT):
        return False
    if not structure_type.is_visible_in(workspace):
        return False
    if structure_type.home_workspace_id is None:
        return True
    return structure_type.home_workspace_id == workspace.pk


def can_delete_in_workspace(user, obj, workspace) -> bool:
    if not is_editable_in_workspace(user, obj, workspace):
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_DELETE)


def can_manage_structure_types(user) -> bool:
    return is_system_admin(user)


def can_manage_groups(user, workspace) -> bool:
    return is_system_admin(user)


def group_has_privileged_permissions(group) -> bool:
    if group is None:
        return False
    return bool(group.permission_set() & PRIVILEGED_PERMISSIONS)


def user_has_privileged_groups(user, workspace) -> bool:
    return any(group_has_privileged_permissions(group) for group in get_user_groups(user, workspace))


def can_assign_group(user, workspace, group) -> bool:
    if not user or not user.is_authenticated or group is None or workspace is None:
        return False
    if is_system_admin(user):
        return True
    if group.workspace_id != workspace.pk:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MANAGE_MEMBERS):
        return False
    return not group_has_privileged_permissions(group)


def can_manage_membership(user, target_user, workspace) -> bool:
    if not user or not user.is_authenticated or target_user is None or workspace is None:
        return False
    if is_system_admin(user):
        return True
    if not has_workspace_perm(user, workspace, WorkspacePerm.MANAGE_MEMBERS):
        return False
    return not user_has_privileged_groups(target_user, workspace)
