from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.references.forms import PropertyForm
from apps.references.models import Property, PropertyGroup
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.test_utils import login_test_client

User = get_user_model()


class PropertyFormTests(TestCase):
    def test_generates_name_from_russian_display_name(self):
        form = PropertyForm(
            data={
                'display_name': 'Предел прочности',
                'name': '',
                'unit': 'МПа',
                'data_type': 'number',
                'group': '',
                'description': '',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['name'], 'predel_prochnosti')


class PropertyViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = PropertyGroup.objects.create(name='Mechanical', sort_order=1)
        cls.property = Property.objects.create(
            name='density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
            group=cls.group,
        )
        cls.workspace = Workspace.objects.create(slug='prop-ws', name='Prop WS')
        cls.admin = User.objects.create_superuser('prop-admin', password='pass-123')
        cls.operator = User.objects.create_user('prop-operator', password='pass-123')
        WorkspaceMembership.objects.create(
            workspace=cls.workspace,
            user=cls.operator,
            role=WorkspaceRole.OPERATOR,
        )

    def setUp(self):
        self.client = Client()

    def _property_payload(self, **overrides):
        data = {
            'display_name': 'Предел прочности',
            'name': '',
            'unit': 'МПа',
            'data_type': 'number',
            'group': str(self.group.pk),
            'description': 'Test property',
        }
        data.update(overrides)
        return data

    def test_property_list_renders_for_operator(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        response = self.client.get(reverse('references:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Density')
        self.assertNotContains(response, reverse('references:create'))

    def test_operator_cannot_create_property(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        response = self.client.post(reverse('references:create'), self._property_payload())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Property.objects.filter(name='predel_prochnosti').exists())

    def test_property_create_view(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.post(reverse('references:create'), self._property_payload())

        self.assertEqual(response.status_code, 302)
        created = Property.objects.get(name='predel_prochnosti')
        self.assertEqual(created.display_name, 'Предел прочности')
        self.assertEqual(created.group, self.group)

    def test_property_create_redirects_to_next_with_open_properties(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        next_url = reverse('structures:type_create')
        response = self.client.post(
            f"{reverse('references:create')}?next={next_url}",
            {
                **self._property_payload(
                    display_name='Young modulus',
                    name='young_modulus',
                    unit='GPa',
                    description='',
                ),
                'next': next_url,
            },
        )

        created = Property.objects.get(name='young_modulus')
        self.assertRedirects(
            response,
            f'{next_url}?created_property={created.pk}&open_properties=1',
            fetch_redirect_response=False,
        )

    def test_property_create_redirects_to_material_form_with_created_property(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        next_url = reverse('materials:create')
        response = self.client.post(
            f"{reverse('references:create')}?next={next_url}",
            {
                **self._property_payload(
                    display_name='Shear modulus',
                    name='shear_modulus',
                    unit='GPa',
                    description='',
                ),
                'next': next_url,
            },
        )

        created = Property.objects.get(name='shear_modulus')
        self.assertRedirects(
            response,
            f'{next_url}?created_property={created.pk}&open_properties=1',
            fetch_redirect_response=False,
        )

        follow_response = self.client.get(response.url)
        self.assertEqual(follow_response.status_code, 200)
        self.assertContains(follow_response, f'"property_id": "{created.pk}"')
        self.assertContains(follow_response, 'Shear modulus')

    def test_property_update_view(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:edit', kwargs={'pk': self.property.pk}),
            {
                'name': 'density',
                'display_name': 'Mass density',
                'unit': 'kg/m3',
                'data_type': 'number',
                'group': str(self.group.pk),
                'description': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.property.refresh_from_db()
        self.assertEqual(self.property.display_name, 'Mass density')
        self.assertEqual(self.property.unit, 'kg/m3')

    def test_operator_cannot_update_property(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:edit', kwargs={'pk': self.property.pk}),
            {
                'name': 'density',
                'display_name': 'Mass density',
                'unit': 'kg/m3',
                'data_type': 'number',
                'group': str(self.group.pk),
                'description': '',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.property.refresh_from_db()
        self.assertEqual(self.property.display_name, 'Density')

    def test_property_delete_view(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:delete', kwargs={'pk': self.property.pk}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Property.objects.filter(pk=self.property.pk).exists())

    def test_operator_cannot_delete_property(self):
        login_test_client(self.client, user=self.operator, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:delete', kwargs={'pk': self.property.pk}),
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Property.objects.filter(pk=self.property.pk).exists())
