from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.core.property_number_value import VALUE_KIND_SCALAR
from apps.materials.imports.staging import MATCH_ALWAYS_CREATE, build_staging_draft
from apps.materials.imports.wide import load_wide_table
from apps.materials.models import Material, MaterialProperty
from apps.materials.tests_import import create_import_structure_type
from apps.references.models import Property, PropertyGroup
from apps.samples.imports.service import SampleImporter
from apps.samples.models import Sample, SampleProperty
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import get_row, insert_row
from apps.workspaces.services import ensure_legacy_workspace


class SampleImportServiceTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        self.structure_type, self.density_field = create_import_structure_type(
            code='sample_import_fabric',
            table_name='structures_sample_import_fabric',
        )
        group = PropertyGroup.objects.create(name='Sample import group', sort_order=1)
        self.extra_prop = Property.objects.create(
            name='manufacturer_note',
            display_name='Примечание',
            data_type='string',
            group=group,
        )
        row_id = insert_row(
            self.structure_type,
            'MAT-SMP-IMP',
            {self.density_field.name: '260'},
            allow_empty_null=True,
        )
        self.material = Material.objects.create(
            code='MAT-SMP-IMP',
            name='Материал для импорта образцов',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=self.extra_prop,
            value_kind=VALUE_KIND_SCALAR,
            value='С материала',
        )
        self.csv = (
            Path(__file__).resolve().parent
            / 'fixtures'
            / 'import_examples'
            / 'samples_wide_demo.csv'
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_hybrid_import_copies_material_and_overlays_mapped_fields(self):
        table = load_wide_table(self.csv, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': 'material.tags', 'parse': 'auto'},
            '2': {'target': f'structure:{self.density_field.name}', 'parse': 'auto'},
            '3': {'target': 'sample.object_type', 'parse': 'text'},
            '4': {'target': f'property:{self.extra_prop.pk}', 'parse': 'text'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_ALWAYS_CREATE,
            structure_type_id=str(self.structure_type.pk),
            occupied_codes=set(
                Sample.objects.filter(workspace=self.workspace).values_list('code', flat=True)
            ),
        )
        report = SampleImporter(
            workspace=self.workspace,
            material=self.material,
        ).import_drafts(drafts, structure_type=self.structure_type)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.materials_created, 2)
        sample = Sample.objects.get(name='Образец демо', workspace=self.workspace)
        self.assertEqual(sample.material_id, self.material.pk)
        self.assertEqual(sample.object_type, 'test')
        self.assertEqual(sample.description, '')
        self.assertNotEqual(str(sample.struct_props_id), str(self.material.struct_props_id))
        row = get_row(self.structure_type, sample.struct_props_id)
        self.assertIsNotNone(row)
        self.assertEqual(str(row[self.density_field.name]).rstrip('0').rstrip('.'), '280')
        material_row = get_row(self.structure_type, self.material.struct_props_id)
        self.assertEqual(str(material_row[self.density_field.name]).rstrip('0').rstrip('.'), '260')
        self.assertEqual(
            SampleProperty.objects.get(sample=sample, property=self.extra_prop).value,
            'Из импорта',
        )
        self.assertTrue(sample.tags.filter(name='партия::А').exists())
        self.assertFalse(sample.tags.filter(name='статус::на проверке').exists())


class SampleImportUITests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        self.structure_type, self.density_field = create_import_structure_type(
            code='sample_ui_import_fabric',
            table_name='structures_sample_ui_import_fabric',
        )
        group = PropertyGroup.objects.create(name='Sample UI import group', sort_order=1)
        self.extra_prop = Property.objects.create(
            name='note_ui',
            display_name='Примечание',
            data_type='string',
            group=group,
        )
        row_id = insert_row(
            self.structure_type,
            'MAT-SMP-UI-IMP',
            {self.density_field.name: '110'},
            allow_empty_null=True,
        )
        self.material = Material.objects.create(
            code='MAT-SMP-UI-IMP',
            name='UI material for sample import',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=self.extra_prop,
            value_kind=VALUE_KIND_SCALAR,
            value='база',
        )
        self.csv = (
            Path(__file__).resolve().parent
            / 'fixtures'
            / 'import_examples'
            / 'samples_wide_demo.csv'
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_import_page_renders(self):
        response = self.client.get(reverse('samples:import'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Импорт образцов')
        self.assertContains(response, 'Вперёд')

    def test_list_has_import_button(self):
        response = self.client.get(reverse('samples:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('samples:import'))

    def test_configure_requires_material(self):
        with self.csv.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'samples_wide_demo.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('samples:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        configure = self.client.get(reverse('samples:import'), {'step': 'configure'})
        self.assertEqual(configure.status_code, 200)
        self.assertContains(configure, 'Лист и материал')
        self.assertContains(configure, 'name="material_id"')
        denied = self.client.post(
            reverse('samples:import'),
            {
                'action': 'configure',
                'sheet': 'CSV',
                'header_row': '1',
                'group_row': '',
            },
        )
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.context['step'], 'configure')
        self.assertTrue(denied.context['show_material_error'])

    def test_mapping_shows_structure_fields_and_material_properties(self):
        with self.csv.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'samples_wide_demo.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('samples:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        mapping = self.client.post(
            reverse('samples:import'),
            {
                'action': 'configure',
                'sheet': 'CSV',
                'header_row': '1',
                'group_row': '',
                'material_id': str(self.material.pk),
            },
        )
        self.assertEqual(mapping.status_code, 200)
        self.assertEqual(mapping.context['step'], 'mapping')
        targets = {row['target'] for row in mapping.context['field_mapping_rows']}
        self.assertIn('material.name', targets)
        self.assertIn(f'structure:{self.density_field.name}', targets)
        self.assertIn(f'property:{self.extra_prop.pk}', targets)
        self.assertIn('sample.object_type', targets)
        self.assertContains(mapping, self.density_field.label)
        self.assertContains(mapping, 'Примечание')

    def test_sample_import_session_does_not_share_material_keys(self):
        with self.csv.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'samples_wide_demo.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.client.post(
            reverse('samples:import'),
            {'action': 'upload', 'file': uploaded},
        )
        session = self.client.session
        self.assertTrue(session.get('sample_import_temp_path'))
        self.assertFalse(session.get('material_import_temp_path'))

    def test_apply_creates_samples(self):
        with self.csv.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'samples_wide_demo.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.client.post(
            reverse('samples:import'),
            {'action': 'upload', 'file': uploaded},
        )
        mapping_page = self.client.post(
            reverse('samples:import'),
            {
                'action': 'configure',
                'sheet': 'CSV',
                'header_row': '1',
                'group_row': '',
                'material_id': str(self.material.pk),
            },
        )
        self.assertEqual(mapping_page.context['step'], 'mapping')
        post = {
            'action': 'map_preview',
            'map_0': 'material.name',
            'parse_0': 'auto',
            'map_1': 'material.tags',
            'parse_1': 'auto',
            'map_2': f'structure:{self.density_field.name}',
            'parse_2': 'auto',
            'map_3': 'sample.object_type',
            'parse_3': 'text',
            'map_4': f'property:{self.extra_prop.pk}',
            'parse_4': 'text',
        }
        preview = self.client.post(reverse('samples:import'), post)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context['step'], 'review')
        apply_response = self.client.post(
            reverse('samples:import'),
            {'action': 'review_apply', 'review_marker': '1'},
        )
        self.assertEqual(apply_response.status_code, 302)
        self.assertEqual(apply_response.url, reverse('samples:list'))
        self.assertEqual(Sample.objects.filter(material=self.material).count(), 2)
        sample = Sample.objects.get(name='Образец демо')
        self.assertEqual(sample.object_type, 'test')
        self.assertEqual(
            SampleProperty.objects.get(sample=sample, property=self.extra_prop).value,
            'Из импорта',
        )
