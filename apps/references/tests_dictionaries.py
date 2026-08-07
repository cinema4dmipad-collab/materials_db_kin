from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.materials.models import Material
from apps.references.dictionaries import resolve_dictionary_item
from apps.references.models import Availability, Manufacturer, Technology
from apps.workspaces.models import BUILTIN_GROUP_OPERATOR, Workspace
from apps.workspaces.services import assign_user_to_groups, ensure_default_groups, ensure_legacy_workspace
from apps.workspaces.test_utils import login_test_client

User = get_user_model()


class MaterialMetadataDictionaryTests(TestCase):
    def setUp(self):
        self.workspace = ensure_legacy_workspace()
        self.manufacturer = Manufacturer.objects.get(code='toray')
        self.availability = Availability.objects.get(code='in_stock')
        self.technology = Technology.objects.get(code='fabric')

    def test_seed_dictionaries_exist(self):
        self.assertTrue(Manufacturer.objects.exists())
        self.assertTrue(Availability.objects.exists())
        self.assertTrue(Technology.objects.exists())

    def test_resolve_by_name_and_code(self):
        self.assertEqual(
            resolve_dictionary_item(Manufacturer, 'Toray').pk,
            self.manufacturer.pk,
        )
        self.assertEqual(
            resolve_dictionary_item(Manufacturer, 'toray').pk,
            self.manufacturer.pk,
        )
        self.assertIsNone(resolve_dictionary_item(Manufacturer, 'unknown-vendor'))

    def test_material_form_and_list_filter(self):
        Material.objects.create(
            code='META-001',
            name='Meta fabric',
            home_workspace=self.workspace,
            manufacturer=self.manufacturer,
            availability=self.availability,
            technology=self.technology,
        )
        Material.objects.create(
            code='META-002',
            name='Other',
            home_workspace=self.workspace,
        )

        list_page = self.client.get(reverse('materials:list'))
        self.assertEqual(list_page.status_code, 200)
        self.assertContains(list_page, 'Производитель')
        self.assertContains(list_page, 'Доступность')
        self.assertContains(list_page, 'Технология')

        filtered = self.client.get(
            reverse('materials:list'),
            {'manufacturer': str(self.manufacturer.pk)},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, 'META-001')
        self.assertNotContains(filtered, 'META-002')

        detail = self.client.get(
            reverse('materials:detail', args=[Material.objects.get(code='META-001').pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Toray')
        self.assertContains(detail, 'В наличии')
        self.assertContains(detail, 'Ткань')


class DictionaryUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(slug='dict-ws', name='Dict WS')
        cls.admin = User.objects.create_superuser('dict-admin', password='pass-123')
        cls.operator = User.objects.create_user('dict-operator', password='pass-123')
        ensure_default_groups(cls.workspace)
        assign_user_to_groups(cls.operator, cls.workspace, [BUILTIN_GROUP_OPERATOR])

    def setUp(self):
        self.client = Client()

    def test_hub_and_list_visible_to_operator(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        hub = self.client.get(reverse('references:dictionary_hub'))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, 'Производители')
        self.assertContains(hub, reverse('references:dictionary_list', kwargs={'slug': 'manufacturers'}))

        listing = self.client.get(
            reverse('references:dictionary_list', kwargs={'slug': 'manufacturers'})
        )
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Toray')
        self.assertNotContains(
            listing,
            reverse('references:dictionary_create', kwargs={'slug': 'manufacturers'}),
        )

    def test_operator_cannot_create(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:dictionary_create', kwargs={'slug': 'manufacturers'}),
            {
                'name': 'Forbidden Co',
                'code': '',
                'description': '',
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Manufacturer.objects.filter(name='Forbidden Co').exists())

    def test_admin_can_create_edit_delete(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        create = self.client.post(
            reverse('references:dictionary_create', kwargs={'slug': 'technologies'}),
            {
                'name': 'RTM',
                'code': '',
                'description': 'Resin transfer',
            },
        )
        self.assertEqual(create.status_code, 302)
        item = Technology.objects.get(name='RTM')
        self.assertEqual(item.code, 'rtm')

        edit = self.client.post(
            reverse(
                'references:dictionary_edit',
                kwargs={'slug': 'technologies', 'pk': item.pk},
            ),
            {
                'name': 'RTM+',
                'code': 'rtm',
                'description': 'Updated',
            },
        )
        self.assertEqual(edit.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.name, 'RTM+')
        self.assertEqual(item.description, 'Updated')

        delete = self.client.post(
            reverse(
                'references:dictionary_delete',
                kwargs={'slug': 'technologies', 'pk': item.pk},
            )
        )
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(Technology.objects.filter(pk=item.pk).exists())

    def test_dictionary_bulk_delete(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        a = Manufacturer.objects.create(name='Bulk A', code='bulk-a')
        b = Manufacturer.objects.create(name='Bulk B', code='bulk-b')
        list_url = reverse('references:dictionary_list', kwargs={'slug': 'manufacturers'})
        bulk_url = reverse(
            'references:dictionary_bulk_delete', kwargs={'slug': 'manufacturers'}
        )

        listing = self.client.get(list_url)
        self.assertContains(listing, 'data-list-bulk-toggle')
        self.assertContains(listing, bulk_url)

        confirm = self.client.post(bulk_url, {'ids': [str(a.pk), str(b.pk)]})
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, 'Bulk A')
        self.assertContains(confirm, 'Bulk B')

        done = self.client.post(
            bulk_url,
            {'ids': [str(a.pk), str(b.pk)], 'confirm': '1'},
        )
        self.assertRedirects(done, list_url)
        self.assertFalse(Manufacturer.objects.filter(pk=a.pk).exists())
        self.assertFalse(Manufacturer.objects.filter(pk=b.pk).exists())

    def test_dictionary_forms_have_no_status_order(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        for slug in ('manufacturers', 'availabilities', 'technologies'):
            listing = self.client.get(
                reverse('references:dictionary_list', kwargs={'slug': slug})
            )
            self.assertEqual(listing.status_code, 200)
            self.assertNotContains(listing, '>Статус<')
            self.assertNotContains(listing, '>Порядок<')

            create_page = self.client.get(
                reverse('references:dictionary_create', kwargs={'slug': slug})
            )
            self.assertEqual(create_page.status_code, 200)
            self.assertNotContains(create_page, 'id_is_active')
            self.assertNotContains(create_page, 'id_sort_order')

        create = self.client.post(
            reverse('references:dictionary_create', kwargs={'slug': 'manufacturers'}),
            {
                'name': 'Solvay',
                'code': '',
                'description': '',
            },
        )
        self.assertEqual(create.status_code, 302)
        created = Manufacturer.objects.get(name='Solvay')
        self.assertEqual(created.code, 'solvay')
        self.assertFalse(hasattr(Manufacturer, 'is_active'))
        self.assertFalse(hasattr(Availability, 'sort_order'))
        self.assertFalse(hasattr(Technology, 'is_active'))

    def test_unknown_dictionary_404(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.get(
            reverse('references:dictionary_list', kwargs={'slug': 'unknown'})
        )
        self.assertEqual(response.status_code, 404)
