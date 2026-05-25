from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.composites.models import CompositeLayer
from apps.materials.models import Material


class CompositeLayerModelTests(TestCase):
    def test_create_composite_layer_links_parent_and_layer_materials(self):
        parent = Material.objects.create(code='CMP-001', name='Carbon panel')
        layer_material = Material.objects.create(code='MAT-001', name='Carbon fiber')

        layer = CompositeLayer.objects.create(
            parent_material=parent,
            material=layer_material,
            layer_number=1,
            angle=45.0,
            thickness=0.25,
        )

        self.assertEqual(layer.parent_material, parent)
        self.assertEqual(layer.material, layer_material)
        self.assertEqual(layer.layer_number, 1)
        self.assertEqual(layer.angle, 45.0)
        self.assertEqual(layer.thickness, 0.25)
        self.assertTrue(parent.is_composite)

    def test_string_representation_includes_parent_and_layer_number(self):
        parent = Material(code='CMP-002', name='Glass laminate')
        layer_material = Material(code='MAT-002', name='Glass fiber')
        layer = CompositeLayer(parent_material=parent, material=layer_material, layer_number=2)

        self.assertEqual(str(layer), 'CMP-002 layer 2: MAT-002')

    def test_default_ordering_and_unique_layer_number_per_parent(self):
        self.assertEqual(CompositeLayer._meta.ordering, ['layer_number'])
        self.assertEqual(CompositeLayer._meta.unique_together, (('parent_material', 'layer_number'),))

    def test_prevents_parent_material_as_own_layer(self):
        material = Material.objects.create(code='CMP-003', name='Self reference')
        layer = CompositeLayer(
            parent_material=material,
            material=material,
            layer_number=1,
            angle=0.0,
            thickness=1.0,
        )

        with self.assertRaises(ValidationError):
            layer.clean()
