from django.urls import reverse

from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm, is_system_admin
from apps.workspaces.services import get_active_workspace, get_user_workspaces


def workspace_navigation(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    active_workspace = getattr(request, 'active_workspace', None) or get_active_workspace(request)
    workspace_user_groups = getattr(request, 'workspace_user_groups', [])
    user_workspaces = get_user_workspaces(user)

    def can(codename):
        if active_workspace is None:
            return False
        return has_workspace_perm(user, active_workspace, codename)

    main_nav_items = [
        {
            'label': 'Материалы',
            'url': reverse('materials:list'),
            'visible': can(WorkspacePerm.MATERIAL_VIEW),
            'is_active': lambda n, u: n == 'materials',
        },
        {
            'label': 'Свойства',
            'url': reverse('references:list'),
            'visible': can(WorkspacePerm.PROPERTY_VIEW),
            'is_active': lambda n, u: n == 'references',
        },
        {
            'label': 'Теги',
            'url': reverse('core:tag_list'),
            'visible': can(WorkspacePerm.TAG_VIEW),
            'is_active': lambda n, u: n == 'core' and u.startswith('tag_'),
        },
        {
            'label': 'Структуры',
            'url': reverse('structures:select_type'),
            'visible': can(WorkspacePerm.STRUCTURE_VIEW),
            'is_active': lambda n, u: n == 'structures',
        },
        {
            'label': 'Образцы',
            'url': reverse('samples:list'),
            'visible': can(WorkspacePerm.SAMPLE_VIEW),
            'is_active': lambda n, u: n in ('samples', 'attachments'),
        },
        {
            'label': 'Сканы',
            'url': reverse('scans_all'),
            'visible': can(WorkspacePerm.SCAN_VIEW),
            'is_active': lambda n, u: u == 'scans_all' or n == 'scans',
        },
        {
            'label': 'Справка',
            'url': reverse('core:help'),
            'visible': True,
            'is_active': lambda n, u: n == 'core' and u == 'help',
        },
    ]

    match = getattr(request, 'resolver_match', None)
    nav_namespace = getattr(match, 'namespace', '') or ''
    nav_url_name = getattr(match, 'url_name', '') or ''

    def _admin_active(*url_names):
        return nav_namespace == 'administration' and nav_url_name in url_names

    for item in main_nav_items:
        item['active'] = item.pop('is_active')(nav_namespace, nav_url_name)

    nav_sections = []
    workspace_items = []
    if can(WorkspacePerm.MANAGE_SETTINGS) and active_workspace:
        workspace_items.append(
            {
                'label': 'Настройки',
                'url': reverse('workspaces:settings', kwargs={'pk': active_workspace.pk}),
                'active': nav_namespace == 'workspaces' and nav_url_name == 'settings',
                'visible': True,
            }
        )
    if can(WorkspacePerm.MANAGE_MEMBERS) and active_workspace:
        workspace_items.append(
            {
                'label': 'Участники',
                'url': reverse('workspaces:members', kwargs={'pk': active_workspace.pk}),
                'active': nav_namespace == 'workspaces' and nav_url_name in (
                    'members',
                    'member_edit',
                    'member_delete',
                    'member_add',
                ),
                'visible': True,
            }
        )
    if workspace_items:
        nav_sections.append({'title': 'Пространство', 'items': workspace_items})

    admin_items = []
    if is_system_admin(user) and active_workspace:
        admin_items.append(
            {
                'label': 'Пользователи',
                'url': reverse('administration:admin_users'),
                'active': _admin_active('admin_users', 'admin_user_create', 'admin_user_edit', 'admin_user_memberships'),
                'visible': True,
            }
        )
        admin_items.append(
            {
                'label': 'Пространства',
                'url': reverse('administration:admin_workspaces'),
                'active': _admin_active(
                    'admin_workspaces',
                    'admin_workspace_create',
                    'admin_workspace_edit',
                    'admin_workspace_delete',
                ),
                'visible': True,
            }
        )
        admin_items.append(
            {
                'label': 'Группы',
                'url': reverse('workspaces:groups', kwargs={'pk': active_workspace.pk}),
                'active': nav_namespace == 'workspaces' and nav_url_name in (
                    'groups',
                    'group_create',
                    'group_edit',
                    'group_delete',
                ),
                'visible': True,
            }
        )
    if admin_items:
        nav_sections.append({'title': 'Администрирование', 'items': admin_items})

    return {
        'active_workspace': active_workspace,
        'workspace_user_groups': workspace_user_groups,
        'user_workspaces': user_workspaces,
        'main_nav_items': main_nav_items,
        'workspace_nav_sections': nav_sections,
        'can_manage_workspace_settings': can(WorkspacePerm.MANAGE_SETTINGS),
        'can_manage_workspace_members': can(WorkspacePerm.MANAGE_MEMBERS),
        'is_system_admin': is_system_admin(user),
    }
