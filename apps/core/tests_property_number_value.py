from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from apps.core.fields import LocalizedDecimalWidget
from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
    effective_bounds,
    format_property_number_display,
    sync_number_property_instance,
)

from apps.materials.forms import MaterialPropertyForm
from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property
from apps.workspaces.models import Workspace


class LocalizedDecimalWidgetMultiValueTests(SimpleTestCase):
    def test_prefers_first_non_empty_when_duplicate_names(self):
        data = QueryDict(mutable=True)
        data.setlist('properties-0-value', ['2.10', ''])
        widget = LocalizedDecimalWidget()
        self.assertEqual(widget.value_from_datadict(data, {}, 'properties-0-value'), '2.10')


class PropertyNumberValueFormatTests(SimpleTestCase):
    def test_format_scalar(self):
        text = format_property_number_display(
            value_kind=VALUE_KIND_SCALAR,
            value=Decimal('1250'),
            decimal_places=2,
        )
        self.assertEqual(text, '1250,00')

    def test_format_closed_range(self):
        text = format_property_number_display(
            value_kind=VALUE_KIND_RANGE,
            value=Decimal('900'),
            value_b=Decimal('1900'),
            decimal_places=2,
        )
        self.assertEqual(text, '900,00–1900,00')

    def test_format_tolerance(self):
        text = format_property_number_display(
            value_kind=VALUE_KIND_TOLERANCE,
            value=Decimal('0.27'),
            value_b=Decimal('0.035'),
            decimal_places=3,
        )
        self.assertEqual(text, '0,270±0,035')

    def test_effective_bounds_tolerance(self):
        low, high = effective_bounds(
            VALUE_KIND_TOLERANCE,
            Decimal('0.27'),
            Decimal('0.035'),
        )
        self.assertEqual(low, Decimal('0.235'))
        self.assertEqual(high, Decimal('0.305'))


class PropertyNumberValueCleanTests(SimpleTestCase):
    def test_clean_range(self):
        data = clean_number_property_fields(
            value_kind=VALUE_KIND_RANGE,
            value='',
            value_min='900',
            value_max='1900',
            decimal_places=2,
        )
        self.assertEqual(data['value_kind'], VALUE_KIND_RANGE)
        self.assertEqual(data['value'], '900')
        self.assertEqual(data['value_b'], Decimal('1900'))

    def test_clean_range_rejects_inverted_bounds(self):
        with self.assertRaises(ValidationError):
            clean_number_property_fields(
                value_kind=VALUE_KIND_RANGE,
                value='',
                value_min='1900',
                value_max='900',
                decimal_places=2,
            )

    def test_clean_scalar(self):
        data = clean_number_property_fields(
            value_kind=VALUE_KIND_SCALAR,
            value='1,25',
            value_min='',
            value_max='',
            decimal_places=2,
        )
        self.assertEqual(data['value'], '1.25')
        self.assertIsNone(data['value_b'])

    def test_clean_tolerance(self):
        data = clean_number_property_fields(
            value_kind=VALUE_KIND_TOLERANCE,
            value='0,27',
            value_min='',
            value_max='',
            value_tolerance='0,035',
            decimal_places=3,
        )
        self.assertEqual(data['value_kind'], VALUE_KIND_TOLERANCE)
        self.assertEqual(data['value'], '0.27')
        self.assertEqual(data['value_b'], Decimal('0.035'))


class MaterialPropertyRangeFormTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(slug='range-ws', name='Range WS')
        self.material = Material.objects.create(
            code='MAT-RANGE',
            name='Range material',
            home_workspace=self.workspace,
        )
        self.property = Property.objects.create(
            name='strength',
            display_name='Strength',
            unit='MPa',
            data_type='number',
            decimal_places=2,
        )

    def test_form_saves_closed_range(self):
        form = MaterialPropertyForm(
            data={
                'property': str(self.property.pk),
                'value_kind': VALUE_KIND_RANGE,
                'value': '',
                'value_min': '900',
                'value_max': '1900',
                'is_range': 'on',
            },
            workspace=self.workspace,
        )
        self.assertTrue(form.is_valid(), form.errors)
        link = form.save(commit=False)
        link.material = self.material
        link.save()
        link.refresh_from_db()
        self.assertEqual(link.value_kind, VALUE_KIND_RANGE)
        self.assertEqual(link.value, '900')
        self.assertEqual(link.value_b, Decimal('1900'))
        self.assertEqual(link.display_value(), '900,00–1900,00')

    def test_form_saves_tolerance(self):
        tolerance_property = Property.objects.create(
            name='thickness_tol',
            display_name='Thickness',
            unit='mm',
            data_type='number',
            decimal_places=3,
        )
        form = MaterialPropertyForm(
            data={
                'property': str(tolerance_property.pk),
                'value_kind': VALUE_KIND_TOLERANCE,
                'value': '0,27',
                'value_tolerance': '0,035',
                'is_tolerance': 'on',
            },
            workspace=self.workspace,
        )
        self.assertTrue(form.is_valid(), form.errors)
        link = form.save(commit=False)
        link.material = self.material
        link.save()
        link.refresh_from_db()
        self.assertEqual(link.value_kind, VALUE_KIND_TOLERANCE)
        self.assertEqual(link.value, '0.27')
        self.assertEqual(link.value_b, Decimal('0.035'))
        self.assertEqual(link.display_value(), '0,270±0,035')

    def test_sync_number_property_instance_for_scalar(self):
        link = MaterialProperty(
            material=self.material,
            property=self.property,
            value_kind=VALUE_KIND_SCALAR,
            value='1.25',
            value_b=Decimal('9'),
        )
        sync_number_property_instance(link)
        self.assertEqual(link.value, '1.25')
        self.assertIsNone(link.value_b)
