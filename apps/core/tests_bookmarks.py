from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.core.models import BookmarkEntityType, UserBookmark
from apps.materials.models import Material
from apps.samples.models import Sample
from apps.scans.models import ScanRecord
from apps.workspaces.test_utils import (
    AuthenticatedWorkspaceTestCase,
    create_test_material,
    create_test_sample,
    create_test_scan,
)


class UserBookmarkTests(AuthenticatedWorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.material = create_test_material(
            code='BM-MAT',
            name='Bookmark material',
            home_workspace=self.workspace,
        )
        self.sample = create_test_sample(
            code='BM-SMP',
            name='Bookmark sample',
            material=self.material,
            workspace=self.workspace,
        )
        self.scan = create_test_scan(
            sample=self.sample,
            workspace=self.workspace,
            title='Bookmark scan',
        )

    def test_toggle_material_bookmark(self):
        toggle_url = reverse('core:bookmark_toggle')
        detail_url = reverse('materials:detail', kwargs={'pk': self.material.pk})

        response = self.client.post(
            toggle_url,
            {
                'entity_type': BookmarkEntityType.MATERIAL,
                'entity_id': str(self.material.pk),
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserBookmark.objects.filter(
                user=self.user,
                workspace=self.workspace,
                entity_type=BookmarkEntityType.MATERIAL,
                entity_id=self.material.pk,
            ).exists()
        )

        detail = self.client.get(detail_url)
        self.assertContains(detail, 'Убрать из закладок')

        response = self.client.post(
            toggle_url,
            {
                'entity_type': BookmarkEntityType.MATERIAL,
                'entity_id': str(self.material.pk),
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                workspace=self.workspace,
                entity_type=BookmarkEntityType.MATERIAL,
                entity_id=self.material.pk,
            ).exists()
        )

    def test_sidebar_shows_bookmark_section(self):
        UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.MATERIAL,
            entity_id=self.material.pk,
            label=self.material.name,
        )
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'Закладки')
        self.assertContains(response, self.material.name)

    def test_bookmark_list_page(self):
        UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.SAMPLE,
            entity_id=self.sample.pk,
            label=self.sample.code,
        )
        response = self.client.get(reverse('core:bookmark_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sample.code)
        self.assertContains(response, 'Образец')

    def test_stale_bookmark_removed_from_list(self):
        bookmark = UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.MATERIAL,
            entity_id=self.material.pk,
            label='gone',
        )
        self.material.delete()
        response = self.client.get(reverse('core:bookmark_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'gone')
        self.assertFalse(UserBookmark.objects.filter(pk=bookmark.pk).exists())

    def test_scan_bookmark_requires_parent_context(self):
        toggle_url = reverse('core:bookmark_toggle')
        detail_url = reverse(
            'scans:detail',
            kwargs={'sample_pk': self.sample.pk, 'pk': self.scan.pk},
        )
        response = self.client.post(
            toggle_url,
            {
                'entity_type': BookmarkEntityType.SCAN,
                'entity_id': str(self.scan.pk),
                'parent_id': str(self.sample.pk),
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        bookmark = UserBookmark.objects.get(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.SCAN,
            entity_id=self.scan.pk,
        )
        self.assertEqual(bookmark.parent_id, self.sample.pk)


class StructureRecordBookmarkTests(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.structures.models import StructureField, StructureType
        from apps.structures.sql_executor import SQLExecutor
        from apps.workspaces.models import BUILTIN_GROUP_MANAGER
        from apps.workspaces.services import ACTIVE_WORKSPACE_SESSION_KEY, ensure_legacy_workspace
        from apps.workspaces.test_utils import assign_user_to_groups_by_name, legacy_workspace

        self.workspace = legacy_workspace()
        User = get_user_model()
        self.user = User.objects.create_user('struct-bookmark', password='test-pass-123')
        assign_user_to_groups_by_name(self.user, self.workspace, BUILTIN_GROUP_MANAGER)
        self.client.login(username='struct-bookmark', password='test-pass-123')
        session = self.client.session
        session[ACTIVE_WORKSPACE_SESSION_KEY] = str(self.workspace.pk)
        session.save()

        self.structure_type = StructureType.objects.create(
            name='Bookmark weave',
            code='bm_weave',
            table_name='structures_bm_weave',
        )
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
        )
        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'id': '00000000-0000-4000-8000-000000000001', 'title': 'Fiber A', 'created_by': ''},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        self.record_id = '00000000-0000-4000-8000-000000000001'

    def tearDown(self):
        from apps.structures.sql_executor import SQLExecutor

        SQLExecutor.drop_table(self.structure_type)

    def test_toggle_structure_record_bookmark(self):
        detail_url = reverse(
            'structures:detail',
            kwargs={'type_code': self.structure_type.code, 'pk': self.record_id},
        )
        toggle_url = reverse('core:bookmark_toggle')
        response = self.client.post(
            toggle_url,
            {
                'entity_type': BookmarkEntityType.STRUCTURE_RECORD,
                'entity_id': self.record_id,
                'context_slug': self.structure_type.code,
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        bookmark = UserBookmark.objects.get(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.STRUCTURE_RECORD,
            entity_id=self.record_id,
        )
        self.assertEqual(bookmark.context_slug, self.structure_type.code)
        self.assertEqual(bookmark.label, 'Fiber A')

        detail = self.client.get(detail_url)
        self.assertContains(detail, 'Убрать из закладок')

        sidebar = self.client.get(reverse('core:dashboard'))
        self.assertContains(sidebar, 'Fiber A')
        self.assertContains(sidebar, 'Bookmark weave')

    def test_structure_record_bookmark_uses_linked_material_name(self):
        from apps.materials.models import Material
        from apps.structures.models import StructureField
        from apps.structures.sql_executor import SQLExecutor

        StructureField.objects.create(
            structure_type=self.structure_type,
            name='thickness',
            label='Thickness',
            field_type='DecimalField',
            max_digits=8,
            decimal_places=2,
            sort_order=2,
        )
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Hidden title', 'thickness': '78.00'},
        )['id']
        material = Material.objects.create(
            code='MAT-BM-WEAVE',
            name='Полотно',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        detail_url = reverse(
            'structures:detail',
            kwargs={'type_code': self.structure_type.code, 'pk': row_id},
        )
        response = self.client.post(
            reverse('core:bookmark_toggle'),
            {
                'entity_type': BookmarkEntityType.STRUCTURE_RECORD,
                'entity_id': row_id,
                'context_slug': self.structure_type.code,
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)

        bookmark = UserBookmark.objects.get(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.STRUCTURE_RECORD,
            entity_id=row_id,
        )
        self.assertEqual(bookmark.label, 'Полотно')

        sidebar = self.client.get(reverse('core:dashboard'))
        self.assertContains(sidebar, 'Полотно')
        self.assertNotContains(sidebar, '>78,00<')
        self.assertNotContains(sidebar, '>Hidden title<')

    def test_toggle_structure_type_bookmark_opens_material_create(self):
        from apps.core.bookmarks import resolve_bookmark, structure_type_bookmark_entity_id

        toggle_url = reverse('core:bookmark_toggle')
        manage_url = reverse('structures:type_manage', args=[self.structure_type.code])
        bookmark_entity_id = structure_type_bookmark_entity_id(self.structure_type.code)
        response = self.client.post(
            toggle_url,
            {
                'entity_type': BookmarkEntityType.STRUCTURE_TYPE,
                'entity_id': bookmark_entity_id,
                'context_slug': self.structure_type.code,
                'next': manage_url,
            },
        )
        self.assertEqual(response.status_code, 302)

        bookmark = UserBookmark.objects.get(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.STRUCTURE_TYPE,
            entity_id=bookmark_entity_id,
        )
        self.assertEqual(bookmark.label, 'Bookmark weave')
        self.assertEqual(bookmark.context_slug, self.structure_type.code)

        resolved = resolve_bookmark(bookmark, workspace=self.workspace)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.label, 'Bookmark weave')
        self.assertEqual(resolved.subtitle, 'Создать материал')
        self.assertIn(
            f"struct_type={self.structure_type.pk}",
            resolved.url,
        )
        self.assertTrue(resolved.url.startswith(reverse('materials:create')))

        sidebar = self.client.get(reverse('core:dashboard'))
        self.assertContains(sidebar, 'Bookmark weave')
        self.assertContains(sidebar, reverse('materials:create'))
        self.assertContains(sidebar, f'struct_type={self.structure_type.pk}')
