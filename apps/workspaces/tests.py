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
