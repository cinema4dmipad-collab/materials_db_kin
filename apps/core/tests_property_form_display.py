from django.test import TestCase

from apps.core.property_form_display import enrich_property_form_display, form_property_id
from apps.materials.forms import MaterialPropertyForm
from apps.materials.models import MaterialProperty
from apps.references.models import Property


class PropertyFormDisplayTests(TestCase):
    def test_form_property_id_uses_instance_property_id(self):
        prop = Property.objects.create(
            name='linked_density',
            display_name='Linked density',
            unit='MPa',
            data_type='number',
        )
        form = MaterialPropertyForm(instance=MaterialProperty(property=prop))
        self.assertEqual(form_property_id(form), str(prop.pk))

    def test_enrich_sets_unit_from_property_field(self):
        prop = Property.objects.create(
            name='density_display',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        form = MaterialPropertyForm(initial={'property': prop.pk, 'value': '1.0'})
        enrich_property_form_display(form)
        self.assertEqual(form.property_unit, 'g/cm3')
        self.assertEqual(form.property_label, 'Density')

    def test_enrich_sets_unit_from_legacy_display_name(self):
        prop = Property.objects.create(
            name='plotnost_legacy',
            display_name='Плотность, г/см³',
            unit='',
            data_type='number',
        )
        form = MaterialPropertyForm(initial={'property': prop.pk, 'value': '1.0'})
        enrich_property_form_display(form)
        self.assertEqual(form.property_unit, 'г/см³')
        self.assertEqual(form.property_label, 'Плотность')
