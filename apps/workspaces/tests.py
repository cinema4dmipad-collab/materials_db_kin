from django.contrib.auth import get_user_model
from django.test import Client, TestCase, modify_settings
from django.urls import reverse

from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.permissions import WorkspacePerm, can_manage_membership, has_workspace_perm
from apps.workspaces.services import ACTIVE_WORKSPACE_SESSION_KEY
from apps.workspaces.test_utils import AuthenticatedWorkspaceTestCase
from apps.materials.models import Material

User = get_user_model()


@modify_settings(MIDDLEWARE={'remove': 'apps.workspaces.middleware.TestAutoLoginMiddleware'})
class AnonymousRedirectTests(TestCase):
    def test_dashboard_redirects_to_login(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_materials_list_redirects_to_login(self):
        response = self.client.get(reverse('materials:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_logout_via_post(self):
        user = User.objects.create_user('logout-user', password='pass-123')
        self.client.login(username='logout-user', password='pass-123')
        response = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class UserProfileTests(AuthenticatedWorkspaceTestCase):
    def test_profile_page_shows_username(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.workspace.name)

    def test_profile_link_in_topbar(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, reverse('accounts:profile'))
        self.assertContains(response, 'app-topbar__user-btn')


    def test_profile_accessible_without_active_workspace(self):
        other = Workspace.objects.create(slug='ws-b-profile', name='Space B')
        WorkspaceMembership.objects.create(
            workspace=other,
            user=self.user,
            role=WorkspaceRole.OPERATOR,
        )
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()

        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)

        help_response = self.client.get(reverse('core:help'))
        self.assertEqual(help_response.status_code, 200)


class WorkspaceSelectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('select-user', password='pass-123')
        self.workspace = Workspace.objects.create(slug='ws-a', name='Пространство A')
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.MANAGER,
        )
        self.client = Client()
        self.client.login(username='select-user', password='pass-123')

    def test_authenticated_user_without_workspace_redirects_to_select(self):
        other = Workspace.objects.create(slug='ws-b', name='Пространство B')
        WorkspaceMembership.objects.create(
            workspace=other,
            user=self.user,
            role=WorkspaceRole.OPERATOR,
        )
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('workspaces:select'))

    def test_select_page_accessible_without_active_workspace(self):
        response = self.client.get(reverse('workspaces:select'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пространство A')

    def test_auto_select_when_user_has_single_workspace(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get(ACTIVE_WORKSPACE_SESSION_KEY), str(self.workspace.pk))


class PermissionTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(slug='perm-ws', name='Perm')
        self.manager = User.objects.create_user('manager', password='pass')
        self.operator = User.objects.create_user('operator', password='pass')
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.operator,
            role=WorkspaceRole.OPERATOR,
        )

    def test_manager_can_manage_settings(self):
        self.assertTrue(
            has_workspace_perm(self.manager, self.workspace, WorkspacePerm.MANAGE_SETTINGS)
        )

    def test_manager_can_manage_members(self):
        self.assertTrue(
            has_workspace_perm(self.manager, self.workspace, WorkspacePerm.MANAGE_MEMBERS)
        )

    def test_operator_cannot_manage_members(self):
        self.assertFalse(
            has_workspace_perm(self.operator, self.workspace, WorkspacePerm.MANAGE_MEMBERS)
        )

    def test_operator_cannot_manage_settings(self):
        self.assertFalse(
            has_workspace_perm(self.operator, self.workspace, WorkspacePerm.MANAGE_SETTINGS)
        )

    def test_operator_can_view_materials(self):
        self.assertTrue(
            has_workspace_perm(self.operator, self.workspace, WorkspacePerm.MATERIAL_VIEW)
        )

    def test_superuser_has_all_permissions(self):
        admin = User.objects.create_superuser('admin', password='pass')
        self.assertTrue(has_workspace_perm(admin, self.workspace, WorkspacePerm.USER_MANAGE))

    def test_superuser_can_edit_foreign_object(self):
        from apps.workspaces.permissions import is_editable_in_workspace

        admin = User.objects.create_superuser('admin', password='pass')
        other_ws = Workspace.objects.create(slug='foreign-ws', name='Foreign')
        material = Material.objects.create(
            code='MAT-FOREIGN',
            name='Foreign material',
            home_workspace=other_ws,
        )
        self.assertFalse(material.is_editable_in(self.workspace))
        self.assertTrue(is_editable_in_workspace(admin, material, self.workspace))

    def test_material_without_home_workspace_is_not_editable(self):
        from apps.workspaces.permissions import is_editable_in_workspace

        material = Material.objects.create(
            code='MAT-LEGACY',
            name='Legacy material',
            home_workspace=None,
        )
        self.assertFalse(material.is_editable_in(self.workspace))
        self.assertFalse(
            is_editable_in_workspace(self.operator, material, self.workspace)
        )


@modify_settings(MIDDLEWARE={'remove': 'apps.workspaces.middleware.TestAutoLoginMiddleware'})
class MaterialEditAccessTests(TestCase):
    def setUp(self):
        self.password = 'pass-123'
        self.workspace = Workspace.objects.create(slug='ws-home', name='Home WS')
        self.other_workspace = Workspace.objects.create(slug='ws-other', name='Other WS')
        self.operator = User.objects.create_user('material-operator', password=self.password)
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.operator,
            role=WorkspaceRole.OPERATOR,
        )
        self.own_material = Material.objects.create(
            code='MAT-OWN',
            name='Own material',
            home_workspace=self.workspace,
        )
        self.shared_material = Material.objects.create(
            code='MAT-SHARED',
            name='Shared material',
            home_workspace=self.other_workspace,
            visibility_mode='all_workspaces',
        )
        self.client = Client()
        self.client.login(username=self.operator.username, password=self.password)
        session = self.client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.pk)
        session.save()

    def test_operator_can_edit_own_workspace_material(self):
        response = self.client.get(
            reverse('materials:edit', kwargs={'pk': self.own_material.pk}),
        )
        self.assertEqual(response.status_code, 200)

    def test_operator_cannot_edit_shared_material(self):
        response = self.client.get(
            reverse('materials:edit', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 403)

    def test_operator_sees_readonly_shared_material_detail(self):
        response = self.client.get(
            reverse('materials:detail', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Редактирование недоступно')
        self.assertNotContains(response, reverse('materials:edit', kwargs={'pk': self.shared_material.pk}))

    def test_shared_material_list_has_no_edit_button(self):
        response = self.client.get(reverse('materials:list'), {'scope': 'shared'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.shared_material.code)
        self.assertNotContains(
            response,
            reverse('materials:edit', kwargs={'pk': self.shared_material.pk}),
        )

    def test_own_published_material_appears_in_shared_tab(self):
        own_published = Material.objects.create(
            code='MAT-PUB',
            name='Own published material',
            home_workspace=self.workspace,
            visibility_mode='all_workspaces',
        )
        response = self.client.get(reverse('materials:list'), {'scope': 'shared'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_published.code)
        response = self.client.get(reverse('materials:edit', kwargs={'pk': own_published.pk}))
        self.assertEqual(response.status_code, 200)

    def test_operator_can_clone_shared_material_to_workspace(self):
        response = self.client.post(
            reverse('materials:clone', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 302)
        clone = Material.objects.get(home_workspace=self.workspace, code='MAT-SHARED')
        self.assertEqual(clone.name, self.shared_material.name)
        self.assertEqual(clone.visibility_mode, 'private')
        self.assertRedirects(response, reverse('materials:detail', kwargs={'pk': clone.pk}))

    def test_shared_material_list_shows_clone_action(self):
        response = self.client.get(reverse('materials:list'), {'scope': 'shared'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('materials:clone', kwargs={'pk': self.shared_material.pk}))


class MaterialsPickerDataTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(slug='ws-picker', name='Picker WS')
        self.other_workspace = Workspace.objects.create(slug='ws-other-picker', name='Other WS')

    def test_materials_for_picker_assigns_scopes(self):
        from apps.materials.picker_data import (
            MATERIAL_PICKER_SCOPE_SHARED,
            MATERIAL_PICKER_SCOPE_WORKSPACE,
            materials_for_picker,
        )

        Material.objects.create(
            code='OWN-PICKER',
            name='Own material',
            home_workspace=self.workspace,
            visibility_mode='private',
        )
        Material.objects.create(
            code='SHR-PICKER',
            name='Shared material',
            home_workspace=self.other_workspace,
            visibility_mode='all_workspaces',
        )
        Material.objects.create(
            code='PUB-PICKER',
            name='Published own',
            home_workspace=self.workspace,
            visibility_mode='all_workspaces',
        )

        picker = materials_for_picker(self.workspace)
        by_code = {item['code']: item['scopes'] for item in picker}

        self.assertEqual(by_code['OWN-PICKER'], [MATERIAL_PICKER_SCOPE_WORKSPACE])
        self.assertEqual(by_code['SHR-PICKER'], [MATERIAL_PICKER_SCOPE_SHARED])
        self.assertEqual(
            by_code['PUB-PICKER'],
            [MATERIAL_PICKER_SCOPE_WORKSPACE, MATERIAL_PICKER_SCOPE_SHARED],
        )


class AuthenticatedAccessTests(AuthenticatedWorkspaceTestCase):
    def test_dashboard_accessible_with_workspace(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_switch_workspace(self):
        other = Workspace.objects.create(slug='ws-b', name='Пространство B')
        WorkspaceMembership.objects.create(
            workspace=other,
            user=self.user,
            role=WorkspaceRole.OPERATOR,
        )
        # Без активного WS middleware раньше блокировал POST /workspaces/switch/.
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()
        response = self.client.post(
            reverse('workspaces:switch', kwargs={'pk': other.pk}),
            {'next': reverse('core:dashboard')},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get(ACTIVE_WORKSPACE_SESSION_KEY), str(other.pk))
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)


class WorkspaceMemberAccessTests(AuthenticatedWorkspaceTestCase):
    def test_manager_can_open_members_page(self):
        response = self.client.get(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Добавить участника')

    def test_manager_can_add_operator(self):
        operator = User.objects.create_user('new-operator', password='pass')
        response = self.client.post(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk}),
            {'user': operator.pk, 'role': WorkspaceRole.OPERATOR},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=operator,
                role=WorkspaceRole.OPERATOR,
            ).exists()
        )

    def test_manager_cannot_manage_manager_membership(self):
        other_manager = User.objects.create_user('other-manager', password='pass')
        membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=other_manager,
            role=WorkspaceRole.MANAGER,
        )
        self.assertFalse(can_manage_membership(self.user, membership))
