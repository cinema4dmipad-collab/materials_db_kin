from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.composites.layer_diagram import build_layer_diagram
from apps.composites.models import CompositeLayer, LAYERS_NOT_ALLOWED_ERROR
from apps.materials.models import Material
from apps.structures.models import StructureType


class CompositeLayerModelTests(TestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Composite panel',
            code='composite_panel',
            allow_layers=True,
        )

    def test_create_composite_layer_links_parent_and_layer_materials(self):
        parent = Material.objects.create(
            code='CMP-001',
            name='Carbon panel',
            struct_type=self.structure_type,
        )
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
        parent = Material(code='CMP-002', name='Glass laminate', struct_type=self.structure_type)
        layer_material = Material(code='MAT-002', name='Glass fiber')
        layer = CompositeLayer(parent_material=parent, material=layer_material, layer_number=2)

        self.assertEqual(str(layer), 'CMP-002 layer 2: MAT-002')

    def test_default_ordering_and_unique_layer_number_per_parent(self):
        self.assertEqual(CompositeLayer._meta.ordering, ['layer_number'])
        self.assertEqual(CompositeLayer._meta.unique_together, (('parent_material', 'layer_number'),))

    def test_prevents_parent_material_as_own_layer(self):
        material = Material.objects.create(
            code='CMP-003',
            name='Self reference',
            struct_type=self.structure_type,
        )
        layer = CompositeLayer(
            parent_material=material,
            material=material,
            layer_number=1,
            angle=0.0,
            thickness=1.0,
        )

        with self.assertRaises(ValidationError):
            layer.clean()

    def test_rejects_layer_when_structure_type_disallows_layers(self):
        alloy_type = StructureType.objects.create(
            name='Alloy',
            code='alloy',
            allow_layers=False,
        )
        parent = Material.objects.create(
            code='CMP-004',
            name='Alloy material',
            struct_type=alloy_type,
        )
        layer_material = Material.objects.create(code='MAT-004', name='Layer material')
        layer = CompositeLayer(
            parent_material=parent,
            material=layer_material,
            layer_number=1,
            angle=0.0,
            thickness=1.0,
        )

        with self.assertRaises(ValidationError) as ctx:
            layer.full_clean()

        self.assertIn('parent_material', ctx.exception.message_dict)
        self.assertEqual(
            ctx.exception.message_dict['parent_material'][0],
            LAYERS_NOT_ALLOWED_ERROR,
        )

    def test_rejects_layer_when_parent_has_no_structure_type(self):
        parent = Material.objects.create(code='CMP-005', name='Plain material')
        layer_material = Material.objects.create(code='MAT-005', name='Layer material')
        layer = CompositeLayer(
            parent_material=parent,
            material=layer_material,
            layer_number=1,
            angle=0.0,
            thickness=1.0,
        )

        with self.assertRaises(ValidationError):
            layer.save()


class CompositeLayerDiagramTests(TestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Composite panel',
            code='composite_panel_diagram',
            allow_layers=True,
        )
        self.parent = Material.objects.create(
            code='CMP-DIAGRAM-001',
            name='Composite panel',
            struct_type=self.structure_type,
        )
        self.layer_material_a = Material.objects.create(code='MAT-DIA-A', name='Carbon fiber')
        self.layer_material_b = Material.objects.create(code='MAT-DIA-B', name='Glass fiber')

    def test_build_layer_diagram_returns_none_for_empty_layers(self):
        self.assertIsNone(build_layer_diagram([]))

    def test_build_layer_diagram_builds_proportional_stack(self):
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=1,
            angle=0,
            thickness=0.2,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_b,
            layer_number=2,
            angle=45,
            thickness=0.8,
        )

        diagram = build_layer_diagram(self.parent.composite_layers.all())

        self.assertIsNotNone(diagram)
        self.assertEqual(len(diagram['layers']), 2)
        self.assertAlmostEqual(diagram['total_thickness'], 1.0)
        self.assertGreater(diagram['layers'][1]['flex_grow'], diagram['layers'][0]['flex_grow'])
        self.assertEqual(diagram['layers'][0]['material_label'], 'MAT-DIA-A - Carbon fiber')
        self.assertEqual(diagram['layer_count'], 2)
        self.assertEqual(diagram['layers'][0]['color'], '#0066FF')
        self.assertEqual(diagram['layers'][1]['color'], '#FF5500')
        self.assertEqual(len(diagram['material_legend']), 2)
        self.assertEqual(diagram['layers'][1]['angle'], '45')

    def test_build_layer_diagram_uses_distinct_colors_for_repeated_material_layers(self):
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=1,
            angle=0,
            thickness=0.2,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=2,
            angle=90,
            thickness=0.2,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=3,
            angle=45,
            thickness=0.2,
        )

        diagram = build_layer_diagram(self.parent.composite_layers.all())

        self.assertEqual(len(diagram['material_legend']), 1)
        self.assertEqual(diagram['material_legend'][0]['color'], '#0066FF')
        colors = [item['color'] for item in diagram['layers']]
        self.assertEqual(colors, ['#0066FF', '#FF5500', '#00B050'])
