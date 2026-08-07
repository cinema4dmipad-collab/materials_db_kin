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
        bookmark = UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.MATERIAL,
            entity_id=self.material.pk,
            label=self.material.name,
        )
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'Закладки')
        self.assertContains(response, self.material.name)
        self.assertContains(response, reverse('core:bookmark_remove', kwargs={'pk': bookmark.pk}))
        self.assertContains(response, 'Удалить закладку')

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

    def test_page_bookmark_with_custom_name(self):
        page_url = reverse('materials:detail', kwargs={'pk': self.material.pk})
        before = self.client.get(page_url)
        self.assertContains(before, 'bi-bookmark-plus')
        self.assertContains(before, '>В закладки<')
        self.assertNotContains(before, 'app-topbar__bookmark-btn is-bookmarked')

        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Мой материал',
                'url': page_url,
                'icon': 'bi-question-circle',
                'icon_color': '#e76f51',
                'next': page_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        bookmark = UserBookmark.objects.get(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.PAGE,
        )
        self.assertEqual(bookmark.label, 'Мой материал')
        self.assertEqual(bookmark.url, page_url.rstrip('/') or '/')
        self.assertEqual(bookmark.icon, 'bi-question-circle')
        self.assertEqual(bookmark.icon_color, '#E76F51')

        listing = self.client.get(reverse('core:bookmark_list'))
        self.assertContains(listing, 'Мой материал')
        self.assertContains(listing, 'Страница')
        self.assertContains(listing, bookmark.url)
        self.assertContains(listing, 'bi-question-circle')
        self.assertContains(listing, 'color: #E76F51')

        dashboard = self.client.get(reverse('core:dashboard'))
        self.assertContains(dashboard, 'Мой материал')
        self.assertContains(dashboard, 'bi-question-circle')
        self.assertContains(dashboard, 'color: #E76F51')

        material_page = self.client.get(page_url)
        self.assertContains(material_page, 'app-topbar__bookmark-btn is-bookmarked')
        self.assertContains(material_page, 'bi-bookmark-fill')
        self.assertContains(material_page, 'Страница в закладках')
        self.assertNotContains(material_page, 'bi-bookmark-plus')

    def test_entity_bookmark_blocks_duplicate_page_pin(self):
        detail_url = reverse('materials:detail', kwargs={'pk': self.material.pk})
        UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.MATERIAL,
            entity_id=self.material.pk,
            label=self.material.name,
        )
        page = self.client.get(detail_url)
        self.assertContains(page, 'В закладках')
        self.assertContains(page, 'уже есть в закладках')
        self.assertNotContains(page, 'bi-bookmark-plus')

        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Duplicate page pin',
                'url': detail_url,
                'icon': 'bi-star',
                'next': detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

    def test_stock_nav_pages_cannot_be_bookmarked(self):
        materials_url = reverse('materials:list')
        dashboard_url = reverse('core:dashboard')

        materials_page = self.client.get(materials_url)
        self.assertContains(materials_page, 'В меню')
        self.assertContains(materials_page, 'is-stock-nav')
        self.assertContains(materials_page, 'уже есть в боковом меню')

        dashboard_page = self.client.get(dashboard_url)
        self.assertContains(dashboard_page, 'В меню')
        self.assertContains(dashboard_page, 'is-stock-nav')

        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Материалы дубль',
                'url': materials_url,
                'icon': 'bi-box-seam',
                'next': materials_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

        # Redundant stock pins are cleaned when bookmarks are listed.
        from apps.core.bookmarks import page_bookmark_entity_id, normalize_page_bookmark_url

        normalized = normalize_page_bookmark_url(materials_url)
        UserBookmark.objects.create(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.PAGE,
            entity_id=page_bookmark_entity_id(normalized),
            url=normalized,
            label='Old materials pin',
            icon='bi-box-seam',
        )
        listing = self.client.get(reverse('core:bookmark_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )
        self.assertNotContains(listing, 'Old materials pin')

    def test_workspace_and_admin_stock_nav_cannot_be_bookmarked(self):
        from django.contrib.auth import get_user_model

        from apps.workspaces.test_utils import login_test_client

        settings_url = reverse('workspaces:settings', kwargs={'pk': self.workspace.pk})
        members_url = reverse('workspaces:members', kwargs={'pk': self.workspace.pk})
        users_url = reverse('administration:admin_users')

        settings_page = self.client.get(settings_url)
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, 'В меню')
        self.assertContains(settings_page, 'is-stock-nav')

        members_page = self.client.get(members_url)
        self.assertEqual(members_page.status_code, 200)
        self.assertContains(members_page, 'В меню')

        for url, label in (
            (settings_url, 'Настройки дубль'),
            (members_url, 'Участники дубль'),
        ):
            response = self.client.post(
                reverse('core:bookmark_page_save'),
                {
                    'label': label,
                    'url': url,
                    'icon': 'bi-gear',
                    'next': url,
                },
            )
            self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

        User = get_user_model()
        admin = User.objects.create_superuser('bookmark-admin', password='pass-123')
        login_test_client(self.client, user=admin, workspace=self.workspace, password='pass-123')
        users_page = self.client.get(users_url)
        self.assertEqual(users_page.status_code, 200)
        self.assertContains(users_page, 'В меню')
        self.assertContains(users_page, 'is-stock-nav')

        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Пользователи дубль',
                'url': users_url,
                'icon': 'bi-person-badge',
                'next': users_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=admin,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

    def test_page_bookmark_rejects_invalid_icon_color(self):
        page_url = reverse('materials:detail', kwargs={'pk': self.material.pk})
        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Bad color',
                'url': page_url,
                'icon': 'bi-star',
                'icon_color': 'red',
                'next': page_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

    def test_page_bookmark_rejects_external_url(self):
        response = self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Bad',
                'url': 'https://example.com/materials/custom/',
                'next': '/',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserBookmark.objects.filter(
                user=self.user,
                entity_type=BookmarkEntityType.PAGE,
            ).exists()
        )

    def test_page_bookmark_dedupes_slash_and_hash_variants(self):
        page_url = reverse('materials:detail', kwargs={'pk': self.material.pk})
        self.client.post(
            reverse('core:bookmark_page_save'),
            {'label': 'Mat A', 'url': page_url, 'icon': 'bi-star', 'next': '/'},
        )
        self.client.post(
            reverse('core:bookmark_page_save'),
            {
                'label': 'Mat B',
                'url': page_url.rstrip('/') + '/#section',
                'icon': 'bi-house',
                'next': '/',
            },
        )
        pages = UserBookmark.objects.filter(
            user=self.user,
            workspace=self.workspace,
            entity_type=BookmarkEntityType.PAGE,
        )
        self.assertEqual(pages.count(), 1)
        bookmark = pages.get()
        self.assertEqual(bookmark.label, 'Mat B')
        self.assertEqual(bookmark.icon, 'bi-house')
        self.assertFalse(bookmark.url.endswith('/'))
        self.assertNotIn('#', bookmark.url)


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

        listing = self.client.get(reverse('core:bookmark_list'))
        self.assertContains(listing, 'Fiber A')

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
