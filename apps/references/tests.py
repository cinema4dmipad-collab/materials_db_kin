from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.references.forms import PropertyForm
from apps.references.models import Property, PropertyChoice, PropertyGroup
from apps.workspaces.models import BUILTIN_GROUP_OPERATOR, Workspace
from apps.workspaces.services import assign_user_to_groups, ensure_default_groups
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

    def test_material_link_data_type_clears_unit(self):
        form = PropertyForm(
            data={
                'display_name': 'Базовый материал',
                'name': 'base_material',
                'unit': 'should-be-cleared',
                'data_type': 'material_link',
                'group': '',
                'description': '',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['data_type'], 'material_link')
        self.assertEqual(form.cleaned_data['unit'], '')

    def test_choice_data_type_clears_unit(self):
        form = PropertyForm(
            data={
                'display_name': 'Тип сплетения',
                'name': 'weave_type',
                'unit': 'should-be-cleared',
                'data_type': 'choice',
                'group': '',
                'description': '',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['data_type'], 'choice')
        self.assertEqual(form.cleaned_data['unit'], '')

    def test_effective_unit_uses_unit_field(self):
        prop = Property(
            display_name='Плотность',
            name='density',
            unit='g/cm3',
        )
        self.assertEqual(prop.effective_unit(), 'g/cm3')
        self.assertEqual(prop.label_with_unit(), 'Плотность, g/cm3')

    def test_effective_unit_parses_legacy_display_name(self):
        prop = Property(
            display_name='Плотность, г/см³',
            name='plotnost',
            unit='',
        )
        self.assertEqual(prop.effective_unit(), 'г/см³')
        self.assertEqual(prop.base_display_name(), 'Плотность')
        self.assertEqual(prop.label_with_unit(), 'Плотность, г/см³')

    def test_effective_unit_does_not_split_arbitrary_commas(self):
        prop = Property(
            display_name='Foo, bar and baz',
            name='foo_bar',
            unit='',
        )
        self.assertEqual(prop.effective_unit(), '')


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
        ensure_default_groups(cls.workspace)
        assign_user_to_groups(cls.operator, cls.workspace, [BUILTIN_GROUP_OPERATOR])

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

    def _choice_formset_payload(self, *options):
        data = {
            'choices-TOTAL_FORMS': str(len(options)),
            'choices-INITIAL_FORMS': '0',
            'choices-MIN_NUM_FORMS': '0',
            'choices-MAX_NUM_FORMS': '1000',
        }
        for index, option in enumerate(options):
            data[f'choices-{index}-label'] = option['label']
            data[f'choices-{index}-value'] = option.get('value', '')
            data[f'choices-{index}-sort_order'] = str(option.get('sort_order', index))
            data[f'choices-{index}-DELETE'] = ''
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

    def test_property_create_choice_with_options(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:create'),
            {
                **self._property_payload(
                    display_name='Тип сплетения',
                    name='weave_type',
                    unit='',
                    data_type='choice',
                    description='',
                ),
                **self._choice_formset_payload(
                    {'label': 'Саржа', 'value': 'twill', 'sort_order': 0},
                    {'label': 'Полотно', 'value': 'plain', 'sort_order': 1},
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Property.objects.get(name='weave_type')
        self.assertEqual(created.data_type, 'choice')
        self.assertEqual(created.unit, '')
        labels = list(created.choices.order_by('sort_order').values_list('label', 'value'))
        self.assertEqual(labels, [('Саржа', 'twill'), ('Полотно', 'plain')])

    def test_property_create_choice_requires_options(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        response = self.client.post(
            reverse('references:create'),
            {
                **self._property_payload(
                    display_name='Пустой выбор',
                    name='empty_choice',
                    unit='',
                    data_type='choice',
                    description='',
                ),
                **self._choice_formset_payload(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Property.objects.filter(name='empty_choice').exists())
        self.assertContains(response, 'хотя бы один вариант')

    def test_property_update_clears_choices_when_type_changes(self):
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass-123')
        choice_prop = Property.objects.create(
            name='old_choice',
            display_name='Old choice',
            data_type='choice',
            group=self.group,
        )
        PropertyChoice.objects.create(
            property=choice_prop,
            label='A',
            value='a',
            sort_order=0,
        )
        response = self.client.post(
            reverse('references:edit', kwargs={'pk': choice_prop.pk}),
            {
                'name': 'old_choice',
                'display_name': 'Now string',
                'unit': '',
                'data_type': 'string',
                'group': str(self.group.pk),
                'description': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        choice_prop.refresh_from_db()
        self.assertEqual(choice_prop.data_type, 'string')
        self.assertEqual(choice_prop.choices.count(), 0)
