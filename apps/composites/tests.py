from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.composites.layer_diagram import (
    build_layer_diagram,
    diverging_blue_white_red,
)
from apps.composites.models import CompositeLayer, LAYERS_NOT_ALLOWED_ERROR
from apps.composites.layer_symmetry import (
    expand_symmetric_layer_objects,
    expand_symmetric_sequence,
)
from apps.composites.thickness_distribute import (
    ThicknessDistributeError,
    distribute_thicknesses,
)
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
        self.assertFalse(layer.thickness_locked)
        self.assertTrue(parent.is_composite)

    def test_distribute_thicknesses_splits_unlocked_equally(self):
        result = distribute_thicknesses(
            [0.1, 0.1, 0.1, 0.1],
            [False, True, False, False],
            1.0,
        )
        self.assertEqual(result[1], 0.1)
        self.assertAlmostEqual(sum(result), 1.0, places=4)
        self.assertAlmostEqual(result[0], result[2], places=4)
        self.assertAlmostEqual(result[0], result[3], places=4)

    def test_distribute_thicknesses_rejects_all_locked(self):
        with self.assertRaises(ThicknessDistributeError):
            distribute_thicknesses([0.2, 0.3], [True, True], 0.5)

    def test_expand_symmetric_even_mirrors_all_layers(self):
        self.assertEqual(
            expand_symmetric_sequence(['A', 'B']),
            ['A', 'B', 'B', 'A'],
        )

    def test_expand_symmetric_odd_keeps_last_as_center(self):
        self.assertEqual(
            expand_symmetric_sequence(['A', 'B', 'C']),
            ['A', 'B', 'C', 'B', 'A'],
        )

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
        self.assertEqual(diagram['legend_mode'], 'material')
        self.assertEqual(len(diagram['legend_modes']), 3)

    def test_diverging_scale_goes_blue_white_red(self):
        self.assertEqual(diverging_blue_white_red(0.0), '#0066FF')
        self.assertEqual(diverging_blue_white_red(0.5), '#FFFFFF')
        self.assertEqual(diverging_blue_white_red(1.0), '#E60026')

    def test_build_layer_diagram_colors_by_thickness(self):
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
        diagram = build_layer_diagram(
            self.parent.composite_layers.all(),
            color_by='thickness',
        )
        self.assertEqual(diagram['legend_mode'], 'thickness')
        self.assertEqual(diagram['layers'][0]['color'], '#0066FF')
        self.assertEqual(diagram['layers'][1]['color'], '#E60026')
        self.assertIsNotNone(diagram['scale'])
        self.assertEqual(diagram['scale']['unit'], 'мм')

    def test_build_layer_diagram_colors_by_angle(self):
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=1,
            angle=0,
            thickness=0.5,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_b,
            layer_number=2,
            angle=90,
            thickness=0.5,
        )
        diagram = build_layer_diagram(
            self.parent.composite_layers.all(),
            color_by='angle',
        )
        self.assertEqual(diagram['legend_mode'], 'angle')
        self.assertEqual(diagram['layers'][0]['color'], '#0066FF')
        self.assertEqual(diagram['layers'][1]['color'], '#E60026')

    def test_build_layer_diagram_uses_same_color_for_repeated_material_layers(self):
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
        self.assertEqual(colors, ['#0066FF', '#0066FF', '#0066FF'])

    def test_symmetric_expand_builds_odd_center_stack(self):
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=1,
            angle=0,
            thickness=0.1,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_b,
            layer_number=2,
            angle=45,
            thickness=0.2,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=3,
            angle=90,
            thickness=0.3,
        )
        expanded = expand_symmetric_layer_objects(
            self.parent.composite_layers.order_by('layer_number')
        )
        diagram = build_layer_diagram(expanded)
        self.assertEqual(diagram['layer_count'], 5)
        self.assertAlmostEqual(diagram['total_thickness'], 0.9)
        codes = [item['material_code'] for item in diagram['layers']]
        self.assertEqual(codes, ['MAT-DIA-A', 'MAT-DIA-B', 'MAT-DIA-A', 'MAT-DIA-B', 'MAT-DIA-A'])
        self.assertEqual([item['angle'] for item in diagram['layers']], ['0', '45', '90', '45', '0'])
