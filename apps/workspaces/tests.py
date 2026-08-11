from django.contrib.auth import get_user_model
from django.test import Client, TestCase, modify_settings
from django.urls import reverse

from apps.workspaces.models import (
    BUILTIN_GROUP_MANAGER,
    BUILTIN_GROUP_OPERATOR,
    Workspace,
    WorkspaceGroup,
    WorkspaceGroupMembership,
)
from apps.workspaces.permissions import (
    WorkspacePerm,
    can_manage_membership,
    expand_permission_bundles,
    has_workspace_perm,
)
from apps.workspaces.forms import WorkspaceForm, WorkspaceGroupForm, WorkspaceMemberAddFormSet, WorkspaceUserGroupsForm
from apps.workspaces.services import ACTIVE_WORKSPACE_SESSION_KEY, assign_user_to_groups, ensure_default_groups
from apps.workspaces.test_utils import AuthenticatedWorkspaceTestCase
from apps.materials.models import Material

User = get_user_model()


def _assign_manager(user, workspace):
    ensure_default_groups(workspace)
    assign_user_to_groups(user, workspace, [BUILTIN_GROUP_MANAGER])


def _assign_operator(user, workspace):
    ensure_default_groups(workspace)
    assign_user_to_groups(user, workspace, [BUILTIN_GROUP_OPERATOR])


def _operator_group(workspace):
    return WorkspaceGroup.objects.get(workspace=workspace, name=BUILTIN_GROUP_OPERATOR)


def _manager_group(workspace):
    return WorkspaceGroup.objects.get(workspace=workspace, name=BUILTIN_GROUP_MANAGER)


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
        _assign_operator(self.user, other)
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()

        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)

        help_response = self.client.get(reverse('core:help'))
        self.assertEqual(help_response.status_code, 200)

    def test_profile_edit_page_updates_user_fields(self):
        response = self.client.post(
            reverse('accounts:profile_edit'),
            {
                'email': 'updated@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
            },
        )
        self.assertRedirects(response, reverse('accounts:profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.first_name, 'Иван')
        self.assertEqual(self.user.last_name, 'Петров')

    def test_profile_edit_accessible_without_active_workspace(self):
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()

        response = self.client.get(reverse('accounts:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Редактирование профиля')

    def test_password_change_updates_credentials(self):
        response = self.client.post(
            reverse('accounts:password_change'),
            {
                'old_password': self.password,
                'new_password1': 'new-pass-456',
                'new_password2': 'new-pass-456',
            },
        )
        self.assertRedirects(response, reverse('accounts:profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('new-pass-456'))

    def test_profile_page_has_edit_links(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertContains(response, reverse('accounts:profile_edit'))
        self.assertContains(response, reverse('accounts:password_change'))
        self.assertContains(response, 'Редактировать')


class WorkspaceSelectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('select-user', password='pass-123')
        self.workspace = Workspace.objects.create(slug='ws-a', name='Пространство A')
        _assign_manager(self.user, self.workspace)
        self.client = Client()
        self.client.login(username='select-user', password='pass-123')

    def test_authenticated_user_without_workspace_redirects_to_select(self):
        other = Workspace.objects.create(slug='ws-b', name='Пространство B')
        _assign_operator(self.user, other)
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

    def test_login_redirects_to_select_with_multiple_workspaces(self):
        other = Workspace.objects.create(slug='ws-b', name='Пространство B')
        _assign_operator(self.user, other)
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'select-user', 'password': 'pass-123'},
        )
        self.assertRedirects(response, reverse('workspaces:select'))

    def test_sidebar_hides_workspace_sections_without_active_workspace(self):
        other = Workspace.objects.create(slug='ws-b-nav', name='Пространство B')
        _assign_operator(self.user, other)
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()

        response = self.client.get(reverse('workspaces:select'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('materials:list'))
        self.assertContains(response, 'Пространство не выбрано')
        self.assertContains(response, 'Выберите рабочее пространство на главном экране')
        self.assertContains(response, 'workspace-select__grid')
        self.assertContains(response, reverse('core:help'))
        self.assertNotContains(response, 'Администрирование')

    def test_system_admin_sees_admin_section_without_active_workspace(self):
        admin = User.objects.create_superuser('select-admin', password='pass-123')
        other = Workspace.objects.create(slug='ws-b-admin', name='Пространство B')
        _assign_manager(admin, self.workspace)
        _assign_manager(admin, other)
        self.client.login(username='select-admin', password='pass-123')
        session = self.client.session
        session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        session.save()

        response = self.client.get(reverse('workspaces:select'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Администрирование')
        self.assertContains(response, reverse('administration:admin_users'))
        self.assertContains(response, reverse('administration:admin_workspaces'))
        self.assertNotContains(response, reverse('materials:list'))

    def test_system_admin_can_open_admin_users_without_active_workspace(self):
        admin = User.objects.create_superuser('admin-no-ws', password='pass-123')
        Workspace.objects.create(slug='ws-admin-only', name='Admin WS')
        self.client.login(username='admin-no-ws', password='pass-123')

        response = self.client.get(reverse('administration:admin_users'))
        self.assertEqual(response.status_code, 200)


class PermissionTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(slug='perm-ws', name='Perm')
        self.manager = User.objects.create_user('manager', password='pass')
        self.operator = User.objects.create_user('operator', password='pass')
        _assign_manager(self.manager, self.workspace)
        _assign_operator(self.operator, self.workspace)

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

    def test_operator_can_publish_materials(self):
        self.assertTrue(
            has_workspace_perm(self.operator, self.workspace, WorkspacePerm.MATERIAL_PUBLISH)
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

    def test_union_permissions_from_two_groups(self):
        custom = WorkspaceGroup.objects.create(
            workspace=self.workspace,
            name='Редактор материалов',
            permissions=['workspace.view', 'material.delete'],
        )
        assign_user_to_groups(self.operator, self.workspace, [BUILTIN_GROUP_OPERATOR, custom.name])
        self.assertTrue(
            has_workspace_perm(self.operator, self.workspace, WorkspacePerm.MATERIAL_DELETE)
        )


@modify_settings(MIDDLEWARE={'remove': 'apps.workspaces.middleware.TestAutoLoginMiddleware'})
class MaterialEditAccessTests(TestCase):
    def setUp(self):
        self.password = 'pass-123'
        self.workspace = Workspace.objects.create(slug='ws-home', name='Home WS')
        self.other_workspace = Workspace.objects.create(slug='ws-other', name='Other WS')
        self.operator = User.objects.create_user('material-operator', password=self.password)
        _assign_operator(self.operator, self.workspace)
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

    def test_operator_can_link_shared_material_to_workspace(self):
        response = self.client.post(
            reverse('materials:link', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Material.objects.filter(home_workspace=self.workspace, code='MAT-SHARED').exists(),
        )
        from apps.workspaces.models import WorkspaceMaterialLink

        self.assertTrue(
            WorkspaceMaterialLink.objects.filter(
                workspace=self.workspace,
                material=self.shared_material,
            ).exists(),
        )
        self.assertRedirects(
            response,
            reverse('materials:detail', kwargs={'pk': self.shared_material.pk}),
        )

    def test_linked_material_appears_in_workspace_tab(self):
        from apps.workspaces.models import WorkspaceMaterialLink

        WorkspaceMaterialLink.objects.create(
            workspace=self.workspace,
            material=self.shared_material,
        )
        response = self.client.get(reverse('materials:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.shared_material.code)
        self.assertContains(response, 'Ссылка')

    def test_linked_material_detail_shows_link_notice(self):
        from apps.workspaces.models import WorkspaceMaterialLink

        WorkspaceMaterialLink.objects.create(
            workspace=self.workspace,
            material=self.shared_material,
        )
        response = self.client.get(
            reverse('materials:detail', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'добавлен в пространство как')
        self.assertContains(response, 'ссылка')
        self.assertContains(response, self.other_workspace.name)
        self.assertNotContains(response, reverse('materials:visibility', kwargs={'pk': self.shared_material.pk}))
        self.assertContains(response, 'Видимость ссылочного материала настраивается в исходном пространстве')
        self.assertNotContains(response, 'entity-detail-tags-form')
        self.assertNotIn('tags_form', response.context)

    def test_shared_readonly_material_detail_hides_tags_form(self):
        response = self.client.get(
            reverse('materials:detail', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['material_is_readonly'])
        self.assertNotContains(response, 'entity-detail-tags-form')
        self.assertNotIn('tags_form', response.context)

    def test_linked_material_visibility_page_is_forbidden(self):
        from apps.workspaces.models import WorkspaceMaterialLink

        WorkspaceMaterialLink.objects.create(
            workspace=self.workspace,
            material=self.shared_material,
        )
        response = self.client.get(
            reverse('materials:visibility', kwargs={'pk': self.shared_material.pk}),
        )
        self.assertEqual(response.status_code, 403)

    def test_shared_material_list_shows_link_action(self):
        response = self.client.get(reverse('materials:list'), {'scope': 'shared'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('materials:link', kwargs={'pk': self.shared_material.pk}))

    def test_create_material_warns_about_existing_shared_name(self):
        response = self.client.post(
            reverse('materials:create'),
            {
                'code': 'MAT-NEW',
                'name': self.shared_material.name,
                'description': '',
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Материал с таким названием уже существует')
        self.assertContains(response, 'scope=shared')
        self.assertFalse(Material.objects.filter(code='MAT-NEW').exists())

    def test_create_material_warns_about_existing_shared_code(self):
        response = self.client.post(
            reverse('materials:create'),
            {
                'code': self.shared_material.code,
                'name': 'Another material name',
                'description': '',
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Материал с таким кодом уже существует среди общих материалов')
        self.assertContains(response, 'scope=shared')
        self.assertContains(response, '<a href="/materials/?scope=shared">Общие</a>', html=False)
        self.assertNotContains(response, '&lt;a href')
        self.assertFalse(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Another material name',
            ).exists(),
        )

    def test_create_page_has_create_based_on_button(self):
        response = self.client.get(reverse('materials:create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'create-based-on-btn')
        self.assertContains(response, 'Создать на основе')

    def test_create_based_on_prefills_form_from_shared_material(self):
        response = self.client.get(
            reverse('materials:create'),
            {'based_on': str(self.shared_material.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создание на основе материала')
        self.assertContains(response, self.shared_material.code)
        self.assertContains(response, f'value="{self.shared_material.code}"', html=False)
        self.assertContains(response, f'value="{self.shared_material.name}"', html=False)

    def test_create_based_on_prefills_form_from_own_workspace_material(self):
        response = self.client.get(
            reverse('materials:create'),
            {'based_on': str(self.own_material.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создание на основе материала')
        self.assertContains(response, self.own_material.code)
        self.assertContains(response, f'value="{self.own_material.code}"', html=False)
        self.assertContains(response, f'value="{self.own_material.name}"', html=False)

    def test_create_based_on_rejects_duplicate_code_in_workspace(self):
        response = self.client.post(
            reverse('materials:create'),
            {
                'based_on': str(self.shared_material.pk),
                'code': self.own_material.code,
                'name': 'Another name',
                'description': '',
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Материал с таким кодом уже существует')
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Another name',
            ).count(),
            0,
        )

    def test_create_based_on_allows_same_name_as_template(self):
        response = self.client.post(
            reverse('materials:create'),
            {
                'based_on': str(self.shared_material.pk),
                'code': 'MAT-COPY-UNIQUE',
                'name': self.shared_material.name,
                'description': self.shared_material.description,
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Material.objects.get(
            home_workspace=self.workspace,
            code='MAT-COPY-UNIQUE',
        )
        self.assertEqual(created.name, self.shared_material.name)

    def test_create_based_on_rejects_duplicate_code_in_shared_materials(self):
        response = self.client.post(
            reverse('materials:create'),
            {
                'based_on': str(self.shared_material.pk),
                'code': self.shared_material.code,
                'name': 'Another name',
                'description': '',
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Материал с таким кодом уже существует среди общих материалов')
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Another name',
            ).count(),
            0,
        )

    def test_create_based_on_prefills_properties(self):
        from apps.materials.models import MaterialProperty
        from apps.references.models import Property

        density = Property.objects.create(
            name='density_based_on',
            display_name='Плотность',
            unit='g/cm3',
            data_type='number',
        )
        MaterialProperty.objects.create(
            material=self.shared_material,
            property=density,
            value='1.55',
        )

        response = self.client.get(
            reverse('materials:create'),
            {'based_on': str(self.shared_material.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Плотность')
        self.assertContains(response, 'g/cm3')
        self.assertContains(response, 'value="1,55"', html=False)

    def test_create_based_on_prefills_composite_layers(self):
        from apps.composites.models import CompositeLayer
        from apps.structures.models import StructureType

        structure_type = StructureType.objects.create(
            name='Layered panel based on',
            code='layered_based_on',
            table_name='layered_based_on_table',
            allow_layers=True,
            is_created=True,
        )
        self.shared_material.struct_type = structure_type
        self.shared_material.save(update_fields=['struct_type'])
        CompositeLayer.objects.create(
            parent_material=self.shared_material,
            material=self.own_material,
            layer_number=1,
            angle=45,
            thickness=0.2,
        )

        response = self.client.get(
            reverse('materials:create'),
            {'based_on': str(self.shared_material.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Слои композита')
        self.assertContains(response, self.own_material.code)
        self.assertContains(response, 'value="45,0"', html=False)
        self.assertContains(response, 'value="0,2"', html=False)

    def test_create_based_on_does_not_copy_samples_or_attachments(self):
        from apps.samples.models import Sample

        Sample.objects.create(
            material=self.shared_material,
            code='SMP-SOURCE',
            name='Source sample',
            workspace=self.other_workspace,
        )

        response = self.client.post(
            reverse('materials:create'),
            {
                'based_on': str(self.shared_material.pk),
                'code': 'MAT-NO-COPY',
                'name': 'Copy without children',
                'description': '',
                'struct_type': '',
                'visibility_mode': 'private',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Material.objects.get(home_workspace=self.workspace, code='MAT-NO-COPY')
        self.assertEqual(created.samples.count(), 0)
        self.assertEqual(created.attachments.count(), 0)

    def test_shared_material_shows_samples_from_home_workspace(self):
        from apps.samples.models import Sample

        sample = Sample.objects.create(
            material=self.shared_material,
            code='SMP-SHARED',
            name='Shared sample',
            workspace=self.other_workspace,
        )
        Sample.objects.create(
            material=self.shared_material,
            code='SMP-LOCAL',
            name='Local-only sample',
            workspace=self.workspace,
        )

        response = self.client.get(
            reverse('material_samples:list', kwargs={'material_pk': self.shared_material.pk}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sample.code)
        self.assertNotContains(response, 'SMP-LOCAL')
        self.assertNotContains(response, reverse('samples:create'))

    def test_shared_material_sample_detail_is_accessible(self):
        from apps.samples.models import Sample

        sample = Sample.objects.create(
            material=self.shared_material,
            code='SMP-DETAIL',
            name='Shared sample detail',
            workspace=self.other_workspace,
        )
        response = self.client.get(reverse('samples:detail', kwargs={'pk': sample.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sample.code)

    def test_legacy_material_sample_detail_is_accessible(self):
        from apps.samples.models import Sample

        legacy_material = Material.objects.create(
            code='MAT-LEGACY',
            name='Legacy shared material',
            visibility_mode='all_workspaces',
        )
        sample = Sample.objects.create(
            material=legacy_material,
            code='SMP-LEGACY',
            name='Legacy sample',
        )
        response = self.client.get(reverse('samples:detail', kwargs={'pk': sample.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sample.code)

    def test_shared_material_shows_attachments_from_home_workspace(self):
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        from apps.materials.models import MaterialAttachment

        media_root = tempfile.mkdtemp()
        try:
            with override_settings(
                MEDIA_ROOT=media_root,
                STORAGES={
                    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
                },
            ):
                attachment = MaterialAttachment.objects.create(
                    material=self.shared_material,
                    workspace=self.other_workspace,
                    title='Shared attachment',
                    file=SimpleUploadedFile('shared.txt', b'shared'),
                )
                MaterialAttachment.objects.create(
                    material=self.shared_material,
                    workspace=self.workspace,
                    title='Local attachment',
                    file=SimpleUploadedFile('local.txt', b'local'),
                )

                response = self.client.get(
                    reverse('material_attachments:list', kwargs={'material_pk': self.shared_material.pk}),
                )
        finally:
            shutil.rmtree(media_root, ignore_errors=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, attachment.title)
        self.assertNotContains(response, 'Local attachment')
        self.assertNotContains(
            response,
            reverse('material_attachments:create', kwargs={'material_pk': self.shared_material.pk}),
        )


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
        _assign_operator(self.user, other)
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

    def test_switch_workspace_from_member_edit_redirects_to_members(self):
        other = Workspace.objects.create(slug='ws-switch-edit', name='Пространство для switch')
        ensure_default_groups(other)
        _assign_manager(self.user, other)
        operator = User.objects.create_user('switch-edit-op', password='pass')
        _assign_operator(operator, self.workspace)
        edit_url = reverse(
            'workspaces:member_edit',
            kwargs={'pk': self.workspace.pk, 'user_id': operator.pk},
        )
        response = self.client.post(
            reverse('workspaces:switch', kwargs={'pk': other.pk}),
            {'next': edit_url},
        )
        self.assertRedirects(
            response,
            reverse('workspaces:members', kwargs={'pk': other.pk}),
            fetch_redirect_response=False,
        )


class WorkspaceMemberAccessTests(AuthenticatedWorkspaceTestCase):
    def test_manager_can_open_members_page(self):
        response = self.client.get(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Добавить участников')

    def test_members_list_marks_current_user_as_you(self):
        response = self.client.get(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Вы<')
        self.assertContains(response, f'({self.user.username})')

    def test_manager_cannot_save_empty_member_list(self):
        User.objects.create_user('spare-for-empty-test', password='pass')
        response = self.client.post(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk}),
            {
                'members-TOTAL_FORMS': '0',
                'members-INITIAL_FORMS': '0',
                'members-MIN_NUM_FORMS': '0',
                'members-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Добавьте хотя бы одного участника')

    def test_manager_can_add_operator(self):
        operator = User.objects.create_user('new-operator', password='pass')
        operator_group = _operator_group(self.workspace)
        response = self.client.post(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk}),
            {
                'members-TOTAL_FORMS': '1',
                'members-INITIAL_FORMS': '0',
                'members-MIN_NUM_FORMS': '0',
                'members-MAX_NUM_FORMS': '1000',
                'members-0-user': str(operator.pk),
                'members-0-groups': str(operator_group.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            WorkspaceGroupMembership.objects.filter(
                group=operator_group,
                user=operator,
            ).exists()
        )

    def test_manager_redirected_from_member_edit_of_inactive_workspace(self):
        other = Workspace.objects.create(slug='ws-other-members', name='Другое пространство')
        ensure_default_groups(other)
        _assign_manager(self.user, other)
        operator = User.objects.create_user('other-ws-operator', password='pass')
        _assign_operator(operator, other)
        response = self.client.get(
            reverse(
                'workspaces:member_edit',
                kwargs={'pk': other.pk, 'user_id': operator.pk},
            ),
        )
        self.assertRedirects(
            response,
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk}),
        )
        follow = self.client.get(
            reverse(
                'workspaces:member_edit',
                kwargs={'pk': other.pk, 'user_id': operator.pk},
            ),
            follow=True,
        )
        self.assertContains(follow, 'Открыт список участников')
        self.assertNotContains(follow, 'Группы участника other-ws-operator')

    def test_manager_can_open_member_edit_page(self):
        operator = User.objects.create_user('edit-operator', password='pass')
        _assign_operator(operator, self.workspace)
        response = self.client.get(
            reverse(
                'workspaces:member_edit',
                kwargs={'pk': self.workspace.pk, 'user_id': operator.pk},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Группы участника edit-operator')
        self.assertContains(response, 'group-picker-widget')
        operator_group = _operator_group(self.workspace)
        self.assertContains(
            response,
            f'value="{operator_group.pk}"',
        )
        self.assertRegex(
            response.content.decode(),
            rf'value="{operator_group.pk}"[^>]*checked|checked[^>]*value="{operator_group.pk}"',
        )

    def test_member_edit_form_initializes_current_groups(self):
        operator = User.objects.create_user('edit-operator-form', password='pass')
        _assign_operator(operator, self.workspace)
        form = WorkspaceUserGroupsForm(
            workspace=self.workspace,
            acting_user=self.user,
            target_user=operator,
        )
        operator_group = _operator_group(self.workspace)
        self.assertEqual(
            set(str(value) for value in form['groups'].value()),
            {str(operator_group.pk)},
        )
        selected = [
            str(widget.data['value'].value if hasattr(widget.data['value'], 'value') else widget.data['value'])
            for widget in form['groups'].subwidgets
            if widget.data.get('selected')
        ]
        self.assertEqual(selected, [str(operator_group.pk)])
        User.objects.create_user('spare-for-groups-test', password='pass')
        formset = WorkspaceMemberAddFormSet(
            workspace=self.workspace,
            acting_user=self.user,
            prefix='members',
        )
        group_names = list(
            formset.empty_form.fields['groups'].queryset.values_list('name', flat=True)
        )
        self.assertIn(BUILTIN_GROUP_OPERATOR, group_names)

    def test_members_page_includes_group_choices_in_add_template(self):
        User.objects.create_user('spare-for-template-test', password='pass')
        response = self.client.get(
            reverse('workspaces:members', kwargs={'pk': self.workspace.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BUILTIN_GROUP_OPERATOR)
        self.assertContains(response, 'members-__prefix__-groups')

    def test_manager_cannot_manage_manager_membership(self):
        other_manager = User.objects.create_user('other-manager', password='pass')
        _assign_manager(other_manager, self.workspace)
        self.assertFalse(can_manage_membership(self.user, other_manager, self.workspace))


class WorkspaceGroupAccessTests(AuthenticatedWorkspaceTestCase):
    def test_manager_cannot_open_groups_page(self):
        response = self.client.get(reverse('workspaces:groups', kwargs={'pk': self.workspace.pk}))
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_create_custom_group(self):
        response = self.client.post(
            reverse('workspaces:group_create', kwargs={'pk': self.workspace.pk}),
            {
                'name': 'Аналитики',
                'description': 'Только просмотр',
                'permission_bundles': ['materials'],
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            WorkspaceGroup.objects.filter(workspace=self.workspace, name='Аналитики').exists()
        )

    def test_system_admin_can_open_groups_page(self):
        admin = User.objects.create_superuser('groups-admin', password=self.password)
        self.client.login(username=admin.username, password=self.password)
        session = self.client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.pk)
        session.save()
        response = self.client.get(reverse('workspaces:groups', kwargs={'pk': self.workspace.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BUILTIN_GROUP_MANAGER)

    def test_system_admin_can_create_custom_group(self):
        admin = User.objects.create_superuser('groups-admin-create', password=self.password)
        self.client.login(username=admin.username, password=self.password)
        session = self.client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.pk)
        session.save()
        response = self.client.post(
            reverse('workspaces:group_create', kwargs={'pk': self.workspace.pk}),
            {
                'name': 'Аналитики',
                'description': 'Только просмотр',
                'permission_bundles': ['materials'],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            WorkspaceGroup.objects.filter(workspace=self.workspace, name='Аналитики').exists()
        )
        group = WorkspaceGroup.objects.get(workspace=self.workspace, name='Аналитики')
        self.assertEqual(
            set(group.permissions),
            set(expand_permission_bundles(['materials'])),
        )


class WorkspaceGroupFormTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(slug='bundle-ws', name='Bundle WS')

    def test_materials_bundle_expands_to_all_material_permissions(self):
        form = WorkspaceGroupForm(
            data={
                'name': 'Материалисты',
                'description': '',
                'permission_bundles': ['materials'],
            },
            workspace=self.workspace,
        )
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        self.assertIn(WorkspacePerm.VIEW, group.permissions)
        self.assertIn(WorkspacePerm.MATERIAL_VIEW, group.permissions)
        self.assertIn(WorkspacePerm.MATERIAL_DELETE, group.permissions)
        self.assertIn(WorkspacePerm.MATERIAL_PUBLISH, group.permissions)

    def test_existing_partial_permissions_map_to_bundles(self):
        group = WorkspaceGroup.objects.create(
            workspace=self.workspace,
            name='Legacy',
            permissions=[WorkspacePerm.VIEW, WorkspacePerm.MATERIAL_VIEW],
        )
        form = WorkspaceGroupForm(instance=group, workspace=self.workspace)
        self.assertIn('materials', form.initial['permission_bundles'])
        self.assertNotIn('workspace_access', form.initial['permission_bundles'])

    def test_create_workspace_form_hides_is_active(self):
        form = WorkspaceForm()
        self.assertNotIn('is_active', form.fields)


@modify_settings(MIDDLEWARE={'remove': 'apps.workspaces.middleware.TestAutoLoginMiddleware'})
class AdminWorkspaceManagementTests(TestCase):
    def setUp(self):
        self.password = 'admin-pass'
        self.admin = User.objects.create_superuser('sysadmin', password=self.password)
        self.workspace = Workspace.objects.create(
            slug='ws-admin-test',
            name='Admin test workspace',
        )
        ensure_default_groups(self.workspace)
        self.client = Client()
        self.client.login(username=self.admin.username, password=self.password)
        session = self.client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.pk)
        session.save()

    def test_admin_workspace_list(self):
        response = self.client.get(reverse('administration:admin_workspaces'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ws-admin-test')
        self.assertContains(response, reverse('administration:admin_workspace_create'))

    def test_operator_cannot_access_admin_workspace_list(self):
        operator = User.objects.create_user('plain-user', password=self.password)
        _assign_operator(operator, self.workspace)
        self.client.login(username=operator.username, password=self.password)
        response = self.client.get(reverse('administration:admin_workspaces'))
        self.assertEqual(response.status_code, 403)

    def test_operator_cannot_create_users(self):
        operator = User.objects.create_user('plain-user', password=self.password)
        _assign_operator(operator, self.workspace)
        self.client.login(username=operator.username, password=self.password)
        response = self.client.get(reverse('administration:admin_user_create'))
        self.assertEqual(response.status_code, 403)
        create_response = self.client.post(
            reverse('administration:admin_user_create'),
            {
                'username': 'blocked-user',
                'email': 'blocked@example.com',
                'password1': self.password,
                'password2': self.password,
            },
        )
        self.assertEqual(create_response.status_code, 403)
        self.assertFalse(User.objects.filter(username='blocked-user').exists())

    def test_admin_can_create_edit_and_manage_members(self):
        create_response = self.client.post(
            reverse('administration:admin_workspace_create'),
            {
                'slug': 'ws-new',
                'name': 'New workspace',
                'description': 'Test',
            },
        )
        self.assertEqual(create_response.status_code, 302)
        created = Workspace.objects.get(slug='ws-new')
        self.assertTrue(created.is_active)

        edit_response = self.client.post(
            reverse('administration:admin_workspace_edit', kwargs={'pk': created.pk}),
            {
                'slug': 'ws-new',
                'name': 'Renamed workspace',
                'description': 'Updated',
                'is_active': 'on',
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        created.refresh_from_db()
        self.assertEqual(created.name, 'Renamed workspace')

        operator = User.objects.create_user('ws-operator', password=self.password)
        manager_group = _manager_group(created)
        members_response = self.client.post(
            reverse('workspaces:members', kwargs={'pk': created.pk}),
            {
                'members-TOTAL_FORMS': '1',
                'members-INITIAL_FORMS': '0',
                'members-MIN_NUM_FORMS': '0',
                'members-MAX_NUM_FORMS': '1000',
                'members-0-user': str(operator.pk),
                'members-0-groups': str(manager_group.pk),
            },
        )
        self.assertEqual(members_response.status_code, 302)
        self.assertTrue(
            WorkspaceGroupMembership.objects.filter(
                group=manager_group,
                user=operator,
            ).exists()
        )

    def test_admin_can_create_user(self):
        response = self.client.post(
            reverse('administration:admin_user_create'),
            {
                'username': 'created-user',
                'email': 'created-user@example.com',
                'first_name': 'Created',
                'last_name': 'User',
                'password1': self.password,
                'password2': self.password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='created-user').exists())

    def test_admin_user_create_form_has_no_groups_section(self):
        response = self.client.get(reverse('administration:admin_user_create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Назначить группы')
        self.assertNotContains(response, 'name="groups"')

    def test_memberships_page_shows_empty_state_for_user_without_groups(self):
        target = User.objects.create_user('global-assign-user', password=self.password)
        page_response = self.client.get(
            reverse('administration:admin_user_memberships', kwargs={'pk': target.pk}),
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'Группы пока не назначены.')

    def test_admin_can_add_more_groups_to_existing_member(self):
        target = User.objects.create_user('existing-member', password=self.password)
        operator_group = _operator_group(self.workspace)
        custom_group = WorkspaceGroup.objects.create(
            workspace=self.workspace,
            name='Аналитики',
            permissions=['workspace.view', 'material.view'],
        )
        assign_user_to_groups(target, self.workspace, [BUILTIN_GROUP_OPERATOR])

        response = self.client.post(
            reverse('administration:admin_user_memberships', kwargs={'pk': target.pk}),
            {'groups': [str(custom_group.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            WorkspaceGroupMembership.objects.filter(group=operator_group, user=target).exists()
        )
        self.assertTrue(
            WorkspaceGroupMembership.objects.filter(group=custom_group, user=target).exists()
        )

    def test_admin_can_delete_empty_workspace(self):
        empty = Workspace.objects.create(slug='ws-empty', name='Empty workspace')
        response = self.client.post(
            reverse('administration:admin_workspace_delete', kwargs={'pk': empty.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Workspace.objects.filter(pk=empty.pk).exists())
