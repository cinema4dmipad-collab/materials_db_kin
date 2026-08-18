from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase

from apps.composites.layer_diagram import (
    ANGLE_SCALE_MAX,
    ANGLE_SCALE_MIN,
    build_layer_diagram,
    diverging_blue_white_red,
    signed_fiber_angle,
)
from apps.composites.models import CompositeLayer, LAYERS_NOT_ALLOWED_ERROR
from apps.composites.layer_symmetry import (
    expand_symmetric_layer_objects,
    expand_symmetric_sequence,
    format_layer_count_label,
    format_mirror_note,
    mirrored_layer_count,
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

    def test_symmetric_count_labels(self):
        self.assertEqual(mirrored_layer_count(8), 8)
        self.assertEqual(mirrored_layer_count(5), 4)
        self.assertEqual(mirrored_layer_count(1), 0)
        self.assertEqual(format_layer_count_label(8), '8 сл.')
        self.assertEqual(
            format_layer_count_label(8, symmetric=True),
            '16 сл.',
        )
        self.assertEqual(
            format_layer_count_label(5, symmetric=True),
            '9 сл.',
        )
        self.assertEqual(format_mirror_note(8), '+ 8 симметричных слоёв')
        self.assertEqual(format_mirror_note(1), '')

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
            angle=-90,
            thickness=0.5,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_b,
            layer_number=2,
            angle=0,
            thickness=0.5,
        )
        CompositeLayer.objects.create(
            parent_material=self.parent,
            material=self.layer_material_a,
            layer_number=3,
            angle=90,
            thickness=0.5,
        )
        diagram = build_layer_diagram(
            self.parent.composite_layers.all(),
            color_by='angle',
        )
        self.assertEqual(diagram['legend_mode'], 'angle')
        self.assertEqual(diagram['scale']['min'], ANGLE_SCALE_MIN)
        self.assertEqual(diagram['scale']['max'], ANGLE_SCALE_MAX)
        self.assertEqual(diagram['scale']['min_label'], '−90 °')
        self.assertEqual(diagram['scale']['mid_label'], '0 °')
        self.assertEqual(diagram['scale']['max_label'], '+90 °')
        self.assertEqual(diagram['layers'][0]['color'], '#0066FF')
        self.assertEqual(diagram['layers'][1]['color'], '#FFFFFF')
        self.assertEqual(diagram['layers'][2]['color'], '#E60026')

    def test_angle_legend_keeps_fixed_limits_when_all_layers_are_zero(self):
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
            angle=0,
            thickness=0.2,
        )
        diagram = build_layer_diagram(
            self.parent.composite_layers.all(),
            color_by='angle',
        )
        self.assertEqual(diagram['scale']['min'], -90)
        self.assertEqual(diagram['scale']['max'], 90)
        self.assertEqual(diagram['layers'][0]['color'], '#FFFFFF')
        self.assertEqual(diagram['layers'][1]['color'], '#FFFFFF')

    def test_signed_fiber_angle_wraps_to_plus_minus_90(self):
        self.assertEqual(signed_fiber_angle(0), 0)
        self.assertEqual(signed_fiber_angle(90), 90)
        self.assertEqual(signed_fiber_angle(-90), -90)
        self.assertEqual(signed_fiber_angle(135), -45)
        self.assertEqual(signed_fiber_angle(180), 0)
        self.assertEqual(signed_fiber_angle(-180), 0)

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
        diagram = build_layer_diagram(
            expanded,
            symmetric=True,
            defining_count=3,
        )
        self.assertEqual(diagram['layer_count'], 5)
        self.assertEqual(diagram['defining_count'], 3)
        self.assertEqual(diagram['mirror_count'], 2)
        self.assertTrue(diagram['symmetric'])
        self.assertEqual(diagram['layer_count_label'], '5 сл.')
        self.assertAlmostEqual(diagram['total_thickness'], 0.9)
        codes = [item['material_code'] for item in diagram['layers']]
        self.assertEqual(codes, ['MAT-DIA-A', 'MAT-DIA-B', 'MAT-DIA-A', 'MAT-DIA-B', 'MAT-DIA-A'])
        self.assertEqual([item['angle'] for item in diagram['layers']], ['0', '45', '90', '45', '0'])
        self.assertEqual(diagram['reinforcement_formula'], '(0/+45)/(90/+45)/(0)')


class ReinforcementFormulaTests(TestCase):
    def test_empty_sequence(self):
        from apps.composites.reinforcement_formula import build_reinforcement_formula

        self.assertEqual(build_reinforcement_formula([]), '')

    def test_unidirectional_pairs_from_density_table(self):
        from apps.composites.reinforcement_formula import build_reinforcement_formula

        self.assertEqual(build_reinforcement_formula([0] * 16), '(0/0)8')

    def test_cross_ply_symmetric_halves_from_density_table(self):
        from apps.composites.reinforcement_formula import build_reinforcement_formula

        angles = [0, 90] * 4 + [90, 0] * 4
        self.assertEqual(build_reinforcement_formula(angles), '(0/90)4/(90/0)4')

    def test_nested_quad_blocks_from_density_table(self):
        from apps.composites.reinforcement_formula import build_reinforcement_formula

        defining = [0, 90, 45, -45] * 2
        mirror = [-45, 45, 90, 0] * 2
        self.assertEqual(
            build_reinforcement_formula(defining + mirror),
            '((0/90)/(+45/-45))2/((-45/+45)/(90/0))2',
        )

    def test_signed_ply_angles(self):
        from apps.composites.reinforcement_formula import format_ply_angle

        self.assertEqual(format_ply_angle(0), '0')
        self.assertEqual(format_ply_angle(90), '90')
        self.assertEqual(format_ply_angle(45), '+45')
        self.assertEqual(format_ply_angle(-45), '-45')

    def test_odd_leftover_ply(self):
        from apps.composites.reinforcement_formula import build_reinforcement_formula

        self.assertEqual(build_reinforcement_formula([0, 90, 0]), '(0/90)/(0)')


class LayerMaterialThicknessTests(TransactionTestCase):
    def setUp(self):
        from apps.workspaces.services import ensure_legacy_workspace

        self.workspace = ensure_legacy_workspace()
        self.mono = StructureType.objects.create(
            name='Монослой',
            code='monolayer_thickness_test',
            table_name='structures_monolayer_thickness_test',
        )
        from apps.structures.models import StructureField

        StructureField.objects.create(
            structure_type=self.mono,
            name='thickness',
            label='Толщина, мм',
            field_type='DecimalField',
            max_digits=8,
            decimal_places=2,
            sort_order=1,
        )
        from apps.structures.sql_executor import SQLExecutor

        created = SQLExecutor.create_table(self.mono)
        self.assertTrue(created['success'], created.get('error'))

    def tearDown(self):
        from apps.structures.sql_executor import SQLExecutor

        SQLExecutor.drop_table(self.mono)

    def test_picker_uses_structure_thickness(self):
        from apps.materials.layer_thickness import layer_thickness_mm_by_material_id
        from apps.materials.picker_data import materials_for_picker
        from apps.structures.sql_executor import SQLExecutor

        row_id = SQLExecutor.insert(self.mono, {'thickness': '0.25'})['id']
        ply = Material.objects.create(
            code='PLY-THK-001',
            name='Prepreg ply',
            home_workspace=self.workspace,
            struct_type=self.mono,
            struct_props_id=row_id,
        )

        mapped = layer_thickness_mm_by_material_id([ply])
        self.assertAlmostEqual(mapped[ply.pk], 0.25)
        item = next(
            row for row in materials_for_picker(self.workspace) if row['code'] == 'PLY-THK-001'
        )
        self.assertAlmostEqual(item['thickness_mm'], 0.25)

    def test_matches_russian_thickness_label_on_other_column_name(self):
        from apps.materials.layer_thickness import is_thickness_field
        from apps.structures.models import StructureField

        field = StructureField(
            name='ply_gauge',
            label='Толщина, мм',
            field_type='DecimalField',
        )
        self.assertTrue(is_thickness_field(field))
        self.assertFalse(
            is_thickness_field(
                StructureField(name='width', label='Ширина, мм', field_type='DecimalField')
            )
        )

    def test_falls_back_to_reference_property(self):
        from apps.materials.layer_thickness import layer_thickness_mm_by_material_id
        from apps.materials.models import MaterialProperty
        from apps.references.models import Property

        ply = Material.objects.create(
            code='PLY-PROP-THK',
            name='Property ply',
            home_workspace=self.workspace,
        )
        prop = Property.objects.create(
            name='ply_thickness_prop_test',
            display_name='Толщина, мм',
            unit='мм',
            data_type='number',
        )
        MaterialProperty.objects.create(material=ply, property=prop, value='0.125')

        mapped = layer_thickness_mm_by_material_id([ply])
        self.assertAlmostEqual(mapped[ply.pk], 0.125)

    def test_structure_thickness_wins_over_property(self):
        from apps.materials.layer_thickness import layer_thickness_mm_by_material_id
        from apps.materials.models import MaterialProperty
        from apps.references.models import Property
        from apps.structures.sql_executor import SQLExecutor

        row_id = SQLExecutor.insert(self.mono, {'thickness': '0.20'})['id']
        ply = Material.objects.create(
            code='PLY-BOTH-THK',
            name='Both sources ply',
            home_workspace=self.workspace,
            struct_type=self.mono,
            struct_props_id=row_id,
        )
        prop = Property.objects.create(
            name='ply_thickness_override_test',
            display_name='Толщина',
            data_type='number',
        )
        MaterialProperty.objects.create(material=ply, property=prop, value='0.99')

        mapped = layer_thickness_mm_by_material_id([ply])
        self.assertAlmostEqual(mapped[ply.pk], 0.20)
