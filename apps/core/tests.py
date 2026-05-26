from django.test import TestCase
from django.urls import reverse

from apps.structures.models import StructureType


class DashboardThemeTests(TestCase):
    def test_dashboard_includes_keenetica_theme_css(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'keenetica-theme.css')

    def test_dashboard_navbar_brand(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'KEENETICA')
        self.assertContains(response, 'navbar-keenetica')


class DashboardStructuresCountTests(TestCase):
    def test_structures_count_zero_when_no_active_types(self):
        StructureType.objects.create(
            name='Inactive',
            code='inactive',
            is_active=False,
        )
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'Структуры')
        self.assertContains(response, '>0<', html=False)

    def test_structures_count_only_active_types(self):
        StructureType.objects.create(name='Active A', code='active_a', is_active=True)
        StructureType.objects.create(name='Active B', code='active_b', is_active=True)
        StructureType.objects.create(name='Inactive', code='inactive_x', is_active=False)

        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, 'Структуры')
        self.assertContains(response, '>2<', html=False)

    def test_dashboard_links_to_structures_select_type(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, reverse('structures:select_type'))
