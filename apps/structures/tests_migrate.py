from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase
from django.urls import reverse

from apps.materials.models import Material
from apps.structures.diagnostics import SEVERITY_ERROR, run_structure_normalization_diagnostics
from apps.structures.migrate_service import (
    migrate_materials,
    suggest_field_mapping,
    supported_fields,
    validate_mapping,
)
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import get_row, insert_row
from apps.workspaces.services import ensure_legacy_workspace
from apps.workspaces.test_utils import login_test_client

User = get_user_model()


class StructureMigrateServiceTests(TransactionTestCase):
    def setUp(self):
        self.workspace = ensure_legacy_workspace()
        self.source = StructureType.objects.create(
            name='Migrate Source',
            code='migrate_src',
            table_name='structures_migrate_src',
        )
        StructureField.objects.create(
            structure_type=self.source,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
            max_length=255,
        )
        StructureField.objects.create(
            structure_type=self.source,
            name='thickness',
            label='Thickness',
            field_type='DecimalField',
            is_required=False,
            sort_order=2,
            max_digits=10,
            decimal_places=2,
        )
        self.target = StructureType.objects.create(
            name='Migrate Target',
            code='migrate_tgt',
            table_name='structures_migrate_tgt',
        )
        StructureField.objects.create(
            structure_type=self.target,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
            max_length=255,
        )
        StructureField.objects.create(
            structure_type=self.target,
            name='notes',
            label='Notes',
            field_type='CharField',
            is_required=False,
            sort_order=2,
            max_length=255,
        )
        self.assertTrue(SQLExecutor.create_table(self.source)['success'])
        self.assertTrue(SQLExecutor.create_table(self.target)['success'])

    def tearDown(self):
        Material.objects.filter(code__startswith='MAT-MIG').delete()
        for code, table in (
            ('migrate_src', 'structures_migrate_src'),
            ('migrate_tgt', 'structures_migrate_tgt'),
        ):
            st = StructureType.objects.filter(code=code).first()
            if st is not None:
                if st.is_created:
                    SQLExecutor.drop_table(st)
                st.delete()
            elif SQLExecutor.table_exists(table):
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS {table}')

    def test_suggest_maps_identical_names_only(self):
        rows = suggest_field_mapping(self.source, self.target)
        by_target = {r.target.name: r for r in rows}
        self.assertEqual(by_target['title'].source_name, 'title')
        self.assertTrue(by_target['title'].auto)
        self.assertEqual(by_target['notes'].source_name, '')
        self.assertFalse(by_target['notes'].auto)

    def test_supported_fields_lists_every_target_field(self):
        StructureField.objects.create(
            structure_type=self.target,
            name='linked_mat',
            label='Linked',
            field_type='MaterialLink',
            is_required=False,
            sort_order=9,
        )
        StructureField.objects.create(
            structure_type=self.target,
            name='kind',
            label='Kind',
            field_type='ChoiceField',
            is_required=False,
            sort_order=10,
            choice_options='a\nb',
        )
        names = {f.name for f in supported_fields(self.target)}
        self.assertEqual(names, {'title', 'notes', 'linked_mat', 'kind'})
        rows = suggest_field_mapping(self.source, self.target)
        self.assertEqual({r.target.name for r in rows}, names)

    def test_migrate_copies_mapped_fields_and_optional_delete(self):
        row_id = insert_row(
            self.source,
            'MAT-MIG-1',
            {'title': 'Panel A', 'thickness': '1.50'},
        )
        material = Material.objects.create(
            code='MAT-MIG-1',
            name='Migrate me',
            home_workspace=self.workspace,
            struct_type=self.source,
            struct_props_id=row_id,
        )
        mapping = {'title': 'title', 'notes': ''}
        self.assertEqual(validate_mapping(self.source, self.target, mapping), [])

        stats = migrate_materials(
            source=self.source,
            target=self.target,
            mapping=mapping,
            delete_source=True,
        )
        self.assertEqual(stats['migrated'], 1)
        self.assertTrue(stats['deleted_source_type'])

        material.refresh_from_db()
        self.assertEqual(material.struct_type_id, self.target.pk)
        self.assertIsNotNone(material.struct_props_id)
        new_row = get_row(self.target, material.struct_props_id)
        self.assertIsNotNone(new_row)
        self.assertEqual(new_row.get('title'), 'Panel A')

        self.assertFalse(StructureType.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(SQLExecutor.table_exists('structures_migrate_src'))


class StructureMigrateViewsTests(TransactionTestCase):
    def setUp(self):
        self.workspace = ensure_legacy_workspace()
        self.admin = User.objects.create_superuser('mig-admin', password='pass')
        self.client = Client()
        login_test_client(self.client, user=self.admin, workspace=self.workspace, password='pass')

        self.source = StructureType.objects.create(
            name='UI Mig Src',
            code='ui_mig_src',
            table_name='structures_ui_mig_src',
        )
        StructureField.objects.create(
            structure_type=self.source,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
            max_length=255,
        )
        self.target = StructureType.objects.create(
            name='UI Mig Tgt',
            code='ui_mig_tgt',
            table_name='structures_ui_mig_tgt',
        )
        StructureField.objects.create(
            structure_type=self.target,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
            max_length=255,
        )
        src_create = SQLExecutor.create_table(self.source)
        self.assertTrue(src_create['success'], src_create.get('error'))
        tgt_create = SQLExecutor.create_table(self.target)
        self.assertTrue(tgt_create['success'], tgt_create.get('error'))
        row_id = insert_row(self.source, 'MAT-UI-MIG', {'title': 'T'})
        Material.objects.create(
            code='MAT-UI-MIG',
            name='UI mig',
            home_workspace=self.workspace,
            struct_type=self.source,
            struct_props_id=row_id,
        )

    def tearDown(self):
        Material.objects.filter(code='MAT-UI-MIG').delete()
        for code, table in (
            ('ui_mig_src', 'structures_ui_mig_src'),
            ('ui_mig_tgt', 'structures_ui_mig_tgt'),
        ):
            st = StructureType.objects.filter(code=code).first()
            if st is not None:
                if st.is_created:
                    SQLExecutor.drop_table(st)
                st.delete()
            elif SQLExecutor.table_exists(table):
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS {table}')

    def test_wizard_migrates_materials(self):
        select = self.client.post(
            reverse('structures:migrate'),
            {
                'action': 'select',
                'source_id': str(self.source.pk),
                'target_id': str(self.target.pk),
            },
        )
        self.assertRedirects(select, f'{reverse("structures:migrate")}?step=map')

        map_page = self.client.get(f'{reverse("structures:migrate")}?step=map')
        self.assertEqual(map_page.status_code, 200)
        self.assertContains(map_page, 'Поля целевой структуры')
        self.assertContains(map_page, 'Поля исходной структуры')
        self.assertNotContains(map_page, 'Авто по имени')
        self.assertContains(map_page, 'name="map_title"')
        self.assertContains(map_page, 'structure_migrate_mapping.js')

        mapped = self.client.post(
            reverse('structures:migrate'),
            {'action': 'map', 'map_title': 'title'},
        )
        self.assertRedirects(mapped, f'{reverse("structures:migrate")}?step=confirm')

        done = self.client.post(
            reverse('structures:migrate'),
            {'action': 'confirm', 'delete_source': 'on'},
        )
        self.assertRedirects(done, reverse('structures:type_manage', args=[self.target.code]))
        material = Material.objects.get(code='MAT-UI-MIG')
        self.assertEqual(material.struct_type_id, self.target.pk)
        self.assertFalse(StructureType.objects.filter(code='ui_mig_src').exists())

    def test_diagnostics_page(self):
        response = self.client.get(reverse('structures:diagnostics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Диагностика нормализации')

    def test_diagnostics_finds_orphan_props_id(self):
        material = Material.objects.get(code='MAT-UI-MIG')
        import uuid

        material.struct_props_id = uuid.uuid4()
        material.save(update_fields=['struct_props_id'])
        issues = run_structure_normalization_diagnostics()
        codes = {i.code for i in issues if i.severity == SEVERITY_ERROR}
        self.assertIn('orphan_struct_props_id', codes)

    def test_diagnostics_detects_rename_drift_and_repairs(self):
        from django.db import connection

        from apps.structures.models import MATERIAL_LINK_FIELD_TYPE

        matrix = StructureField.objects.create(
            structure_type=self.source,
            name='matrix',
            label='Matrix',
            field_type=MATERIAL_LINK_FIELD_TYPE,
            foreign_key_model='materials.Material',
            is_required=False,
            sort_order=2,
        )
        # Simulate metadata rename without ALTER TABLE (manager blocks ORM update).
        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {StructureField._meta.db_table} SET name = %s WHERE id = %s',
                ['matrix_mat', str(matrix.pk)],
            )

        StructureField.objects.create(
            structure_type=self.source,
            name='reinf_mat',
            label='Reinforcement',
            field_type=MATERIAL_LINK_FIELD_TYPE,
            foreign_key_model='materials.Material',
            is_required=False,
            sort_order=3,
        )

        issues = run_structure_normalization_diagnostics()
        codes = {i.code for i in issues if i.structure_code == self.source.code}
        self.assertIn('rename_column_suggested', codes)
        self.assertIn('field_without_catalog_property', codes)
        suggestion = next(
            i for i in issues if i.code == 'rename_column_suggested' and i.structure_code == self.source.code
        )
        self.assertEqual(suggestion.repair['old_name'], 'matrix')
        self.assertEqual(suggestion.repair['new_name'], 'matrix_mat')

        repair = self.client.post(
            reverse('structures:diagnostics'),
            {
                'action': 'rename_column',
                'structure_code': self.source.code,
                'old_name': 'matrix',
                'new_name': 'matrix_mat',
            },
        )
        self.assertRedirects(repair, reverse('structures:diagnostics'))
        self.assertTrue(SQLExecutor.column_exists(self.source, 'matrix_mat'))
        self.assertFalse(SQLExecutor.column_exists(self.source, 'matrix'))

        issues_after = run_structure_normalization_diagnostics()
        codes_after = {
            i.code
            for i in issues_after
            if i.structure_code == self.source.code and i.code == 'rename_column_suggested'
        }
        self.assertFalse(codes_after)
