from django.test import TestCase
from django.urls import reverse

from apps.references.forms import PropertyForm
from apps.references.models import Property, PropertyGroup


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


class PropertyViewsTests(TestCase):    def setUp(self):
        self.group = PropertyGroup.objects.create(name='Mechanical', sort_order=1)
        self.property = Property.objects.create(
            name='density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
            group=self.group,
        )

    def test_property_list_renders(self):
        response = self.client.get(reverse('references:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Density')
        self.assertContains(response, 'density')

    def test_property_create_view(self):
        response = self.client.post(
            reverse('references:create'),
            {
                'display_name': 'Предел прочности',
                'name': '',
                'unit': 'МПа',
                'data_type': 'number',
                'group': str(self.group.pk),
                'description': 'Test property',
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Property.objects.get(name='predel_prochnosti')
        self.assertEqual(created.display_name, 'Предел прочности')
        self.assertEqual(created.group, self.group)
    def test_property_update_view(self):
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

    def test_property_delete_view(self):
        response = self.client.post(
            reverse('references:delete', kwargs={'pk': self.property.pk}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Property.objects.filter(pk=self.property.pk).exists())
