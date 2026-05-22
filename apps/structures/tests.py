import io

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase

from apps.structures.dynamic_models import REGISTERED_MODELS
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class SQLOnlyDynamicStructureTests(TransactionTestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Test Panel',
            code='test_panel',
            table_name='structures_test_panel',
        )
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
        )
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='thickness',
            label='Thickness',
            field_type='DecimalField',
            max_digits=8,
            decimal_places=2,
            sort_order=2,
        )
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='is_active',
            label='Is active',
            field_type='BooleanField',
            sort_order=3,
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)
        REGISTERED_MODELS.clear()

    def test_create_and_drop_table_without_registering_model(self):
        before_models = set(apps.all_models['structures'])

        result = SQLExecutor.create_table(self.structure_type)
        self.structure_type.refresh_from_db()

        self.assertEqual(result, {'success': True, 'error': None})
        self.assertTrue(self.structure_type.is_created)
        self.assertTrue(SQLExecutor.table_exists(self.structure_type))
        self.assertEqual(REGISTERED_MODELS, {})
        self.assertEqual(set(apps.all_models['structures']), before_models)
        with self.assertRaises(LookupError):
            apps.get_model('structures', 'dynamic_test_panel')

        result = SQLExecutor.drop_table(self.structure_type)
        self.structure_type.refresh_from_db()

        self.assertEqual(result, {'success': True, 'error': None})
        self.assertFalse(self.structure_type.is_created)
        self.assertFalse(SQLExecutor.table_exists(self.structure_type))

    def test_sql_executor_and_table_storage_crud_roundtrip(self):
        from apps.structures import table_storage

        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

        insert_result = SQLExecutor.insert(
            self.structure_type,
            {
                'title': 'A panel',
                'thickness': '12.50',
                'is_active': True,
                'created_by': 'tester',
            },
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))

        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertTrue(row['success'], row.get('error'))
        self.assertEqual(row['record']['title'], 'A panel')
        self.assertEqual(row['record']['created_by'], 'tester')

        update_result = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'title': 'Updated panel', 'is_active': False},
        )
        self.assertTrue(update_result['success'], update_result.get('error'))

        stored = table_storage.get_row(self.structure_type, insert_result['id'])
        self.assertIsNotNone(stored)
        self.assertEqual(stored['title'], 'Updated panel')

        storage_id = table_storage.insert_row(
            self.structure_type,
            'row-code',
            {'title': 'Storage panel', 'thickness': '2.25', 'is_active': True},
            created_by='storage-user',
        )
        loaded = table_storage.load_field_data(self.structure_type, storage_id)
        self.assertEqual(loaded['title'], 'Storage panel')
        self.assertIn(str(loaded['is_active']).lower(), {'1', 'true'})

        all_rows = SQLExecutor.get_all(self.structure_type)
        self.assertTrue(all_rows['success'], all_rows.get('error'))
        self.assertEqual(all_rows['total'], 2)

        table_storage.update_row(
            self.structure_type,
            storage_id,
            {'title': 'Storage updated', 'thickness': '3.50', 'is_active': False},
        )
        self.assertEqual(table_storage.get_row(self.structure_type, storage_id)['title'], 'Storage updated')

        table_storage.delete_table_row(self.structure_type, storage_id)
        self.assertIsNone(table_storage.get_row(self.structure_type, storage_id))

        delete_result = SQLExecutor.delete(self.structure_type, insert_result['id'])
        self.assertTrue(delete_result['success'], delete_result.get('error'))
        self.assertEqual(SQLExecutor.get_all(self.structure_type)['total'], 0)

    def test_insert_uses_field_default_value_when_field_is_absent(self):
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            is_required=True,
            default_value='draft',
            sort_order=4,
        )
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='sort_rank',
            label='Sort rank',
            field_type='IntegerField',
            default_value='7',
            sort_order=5,
        )
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        insert_result = SQLExecutor.insert(
            self.structure_type,
            {
                'title': 'Defaulted panel',
                'created_by': 'tester',
            },
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))

        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertTrue(row['success'], row.get('error'))
        self.assertEqual(row['record']['status'], 'draft')
        self.assertEqual(row['record']['sort_rank'], 7)

    def test_table_storage_insert_uses_defaults_for_absent_fields(self):
        from apps.structures import table_storage

        StructureField.objects.create(
            structure_type=self.structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            is_required=True,
            default_value='draft',
            sort_order=4,
        )
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        row_id = table_storage.insert_row(
            self.structure_type,
            'row-code',
            {'title': 'Storage defaulted'},
        )

        loaded = table_storage.load_field_data(self.structure_type, row_id)
        self.assertEqual(loaded['status'], 'draft')

    def test_insert_requires_required_non_fk_field_without_default(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        result = SQLExecutor.insert(self.structure_type, {'thickness': '1.25'})

        self.assertFalse(result['success'])
        self.assertIn('title', result['error'])
        self.assertIn('required', result['error'])

    def test_update_rejects_empty_required_values_and_preserves_omitted_fields(self):
        from apps.structures import table_storage

        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Original panel', 'thickness': '1.25', 'is_active': True},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))

        rejected = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'title': ''},
        )
        self.assertFalse(rejected['success'])
        self.assertIn('title', rejected['error'])
        self.assertIn('required', rejected['error'])

        table_storage.update_row(
            self.structure_type,
            insert_result['id'],
            {'thickness': '2.50'},
        )
        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertTrue(row['success'], row.get('error'))
        self.assertEqual(row['record']['title'], 'Original panel')
        self.assertEqual(str(row['record']['thickness']), '2.5')

    def test_required_foreign_key_fields_do_not_create_sql_columns(self):
        from apps.structures import table_storage

        StructureField.objects.create(
            structure_type=self.structure_type,
            name='related_item',
            label='Related item',
            field_type='ForeignKey',
            is_required=True,
            foreign_key_model='structures.StructureType',
            sort_order=4,
        )

        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

        row_id = table_storage.insert_row(
            self.structure_type,
            'row-code',
            {'title': 'FK metadata only'},
        )
        row = table_storage.get_row(self.structure_type, row_id)
        self.assertIsNotNone(row)
        self.assertEqual(row['title'], 'FK metadata only')
        self.assertNotIn('related_item', row)
        display_field_names = [
            display_value.field.name
            for display_value in table_storage.get_display_values(self.structure_type, row_id)
        ]
        self.assertIn('title', display_field_names)
        self.assertNotIn('related_item', display_field_names)

        all_rows = SQLExecutor.get_all(self.structure_type)
        self.assertTrue(all_rows['success'], all_rows.get('error'))
        self.assertEqual(all_rows['total'], 1)
        self.assertNotIn('related_item', all_rows['records'][0])

    def test_add_column_ignores_foreign_key_fields(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        fk_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='related_item',
            label='Related item',
            field_type='ForeignKey',
            is_required=True,
            foreign_key_model='structures.StructureType',
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, fk_field)

        self.assertEqual(result, {'success': True, 'error': None})
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM {SQLExecutor.quote_identifier(self.structure_type.table_name)} LIMIT 0')
            columns = [column[0] for column in cursor.description]
        self.assertNotIn('related_item', columns)

    def test_add_required_column_with_default_backfills_non_empty_table(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Existing panel'},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        new_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            is_required=True,
            default_value='draft',
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, new_field)
        self.assertTrue(result['success'], result.get('error'))

        existing_row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertTrue(existing_row['success'], existing_row.get('error'))
        self.assertEqual(existing_row['record']['status'], 'draft')

        rejected = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'status': None},
        )
        self.assertFalse(rejected['success'])
        self.assertIn('status', rejected['error'])
        self.assertIn('required', rejected['error'])

    def test_add_required_column_without_default_rejects_non_empty_table(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Existing panel'},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        new_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='required_code',
            label='Required code',
            field_type='CharField',
            is_required=True,
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, new_field)

        self.assertFalse(result['success'])
        self.assertIn('default_value', result['error'])

    def test_add_column_and_identifier_rejection(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        new_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='notes',
            label='Notes',
            field_type='TextField',
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, new_field)
        self.assertTrue(result['success'], result.get('error'))

        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'With notes', 'notes': 'Created after ALTER TABLE'},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        self.assertEqual(
            SQLExecutor.get_by_id(self.structure_type, insert_result['id'])['record']['notes'],
            'Created after ALTER TABLE',
        )

        dangerous_type = StructureType.objects.create(
            name='Dangerous',
            code='dangerous',
            table_name='structures_danger; DROP TABLE structures_test_panel',
        )
        self.assertFalse(SQLExecutor.create_table(dangerous_type)['success'])

        dangerous_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='bad;column',
            label='Bad column',
            field_type='TextField',
        )
        self.assertFalse(SQLExecutor.add_column(self.structure_type, dangerous_field)['success'])

    def test_generation_helpers_fail_clearly(self):
        from apps.structures.services import append_generated_model, generate_model_code

        with self.assertRaises(ImproperlyConfigured):
            generate_model_code(self.structure_type)
        with self.assertRaises(ImproperlyConfigured):
            append_generated_model(self.structure_type)

    def test_sync_structure_tables_uses_sql_executor(self):
        output = io.StringIO()

        call_command('sync_structure_tables', stdout=output)
        self.structure_type.refresh_from_db()

        self.assertTrue(self.structure_type.is_created)
        self.assertTrue(SQLExecutor.table_exists(self.structure_type))
        self.assertIn('Готово. Создано таблиц: 1', output.getvalue())

    def test_generate_structure_model_is_disabled(self):
        with self.assertRaisesMessage(
            CommandError, 'Dynamic Django model generation is disabled'
        ):
            call_command('generate_structure_model', self.structure_type.pk)
