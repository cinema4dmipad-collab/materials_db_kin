import io
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory, TransactionTestCase

from apps.structures import table_storage
from apps.structures.admin import (
    StructureFieldAdmin,
    StructureFieldAdminForm,
    StructureFieldInline,
)
from apps.structures.dynamic_models import REGISTERED_MODELS
from apps.structures.forms import get_dynamic_form
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class PermissiveAdminUser:
    is_active = True
    is_staff = True

    def has_perm(self, perm):
        return True


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

    def _mark_field_as_legacy_foreign_key(self, field):
        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {SQLExecutor.quote_identifier(StructureField._meta.db_table)} '
                f'SET {SQLExecutor.quote_identifier("field_type")} = %s '
                f'WHERE {SQLExecutor.quote_identifier("id")} = %s',
                ['ForeignKey', field.pk],
            )
        field.refresh_from_db()
        return field

    def _add_material_fk_field(self, *, legacy=True, **overrides):
        values = {
            'structure_type': self.structure_type,
            'name': 'material',
            'label': 'Material',
            'field_type': 'CharField',
            'is_required': True,
            'sort_order': 4,
        }
        values.update(overrides)
        field = StructureField.objects.create(**values)
        if legacy:
            self._mark_field_as_legacy_foreign_key(field)
        return field

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

    def test_create_table_rejects_already_created_type(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        result = SQLExecutor.create_table(self.structure_type)

        self.assertFalse(result['success'])
        self.assertIn('уже создана', result['error'])

    def test_create_table_uses_fresh_structure_type_state(self):
        stale_structure_type = self.structure_type
        StructureType.objects.filter(pk=stale_structure_type.pk).update(is_created=True)

        result = SQLExecutor.create_table(stale_structure_type)

        self.assertFalse(result['success'])
        self.assertIn('уже создана', result['error'])
        self.assertFalse(SQLExecutor.table_exists(stale_structure_type))

    def test_create_table_rejects_type_without_fields(self):
        empty_type = StructureType.objects.create(
            name='Empty Structure',
            code='empty_structure',
            table_name='structures_empty_structure',
        )

        result = SQLExecutor.create_table(empty_type)
        empty_type.refresh_from_db()

        self.assertFalse(result['success'])
        self.assertIn('нет полей', result['error'])
        self.assertFalse(empty_type.is_created)

    def test_structure_field_validation_rejects_create_change_and_delete_when_created(self):
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        new_field = StructureField(
            structure_type=self.structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            sort_order=4,
        )
        with self.assertRaises(ValidationError):
            new_field.full_clean()
        with self.assertRaises(ValidationError):
            new_field.save()

        field.label = 'Changed title'
        with self.assertRaises(ValidationError):
            field.save()

        with self.assertRaises(ValidationError):
            field.delete()
        self.assertTrue(StructureField.objects.filter(pk=field.pk).exists())

    def test_structure_field_validation_uses_fresh_structure_type_state(self):
        stale_structure_type = self.structure_type
        StructureType.objects.filter(pk=stale_structure_type.pk).update(is_created=True)

        new_field = StructureField(
            structure_type=stale_structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            sort_order=4,
        )

        with self.assertRaises(ValidationError):
            new_field.full_clean()

    def test_structure_field_bulk_create_rejects_created_structure_type(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        with self.assertRaises(ValidationError):
            StructureField.objects.bulk_create(
                [
                    StructureField(
                        structure_type=self.structure_type,
                        name='status',
                        label='Status',
                        field_type='CharField',
                        sort_order=4,
                    )
                ]
            )

        self.assertFalse(self.structure_type.fields.filter(name='status').exists())

    def test_structure_field_bulk_update_rejects_created_structure_type(self):
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        field.label = 'Changed title'

        with self.assertRaises(ValidationError):
            StructureField.objects.bulk_update([field], ['label'])

        field.refresh_from_db()
        self.assertEqual(field.label, 'Title')

    def test_structure_field_queryset_update_rejects_created_structure_type(self):
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        with self.assertRaises(ValidationError):
            StructureField.objects.filter(pk=field.pk).update(label='Changed title')

        field.refresh_from_db()
        self.assertEqual(field.label, 'Title')

    def test_structure_field_queryset_delete_rejects_created_structure_type(self):
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        with self.assertRaises(ValidationError):
            StructureField.objects.filter(pk=field.pk).delete()

        self.assertTrue(StructureField.objects.filter(pk=field.pk).exists())

    def test_structure_field_inline_is_locked_when_table_created(self):
        site = AdminSite()
        inline = StructureFieldInline(StructureType, site)
        self.structure_type.is_created = True

        self.assertFalse(inline.has_add_permission(None, self.structure_type))
        self.assertFalse(inline.has_change_permission(None, self.structure_type))
        self.assertFalse(inline.has_delete_permission(None, self.structure_type))
        self.assertEqual(inline.get_extra(None, self.structure_type), 0)
        self.assertEqual(set(inline.get_readonly_fields(None, self.structure_type)), set(inline.fields))

    def test_foreign_key_is_not_supported_field_type_choice(self):
        field_type_values = [value for value, _ in StructureField.FIELD_TYPES]
        self.assertNotIn('ForeignKey', field_type_values)

        site = AdminSite()
        admin_model = StructureFieldAdmin(StructureField, site)
        request = RequestFactory().get('/')
        request.user = PermissiveAdminUser()

        form_class = admin_model.get_form(request)
        form = form_class()

        form_choice_values = [value for value, _ in form.fields['field_type'].choices]
        self.assertNotIn('ForeignKey', form_choice_values)

    def test_structure_field_admin_form_hides_foreign_key_target(self):
        form = StructureFieldAdminForm(
            data={
                'structure_type': self.structure_type.pk,
                'name': 'notes',
                'label': 'Notes',
                'field_type': 'TextField',
                'foreign_key_model': '',
                'sort_order': 4,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('foreign_key_model', form.fields)

        form_with_stale_target = StructureFieldAdminForm(
            data={
                'structure_type': self.structure_type.pk,
                'name': 'code',
                'label': 'Code',
                'field_type': 'CharField',
                'foreign_key_model': 'materials.Material',
                'sort_order': 5,
            }
        )

        self.assertTrue(form_with_stale_target.is_valid(), form_with_stale_target.errors)
        self.assertEqual(form_with_stale_target.cleaned_data['foreign_key_model'], '')

        stale_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='stale_code',
            label='Stale code',
            field_type='CharField',
            foreign_key_model='materials.Material',
            sort_order=6,
        )
        update_form = StructureFieldAdminForm(
            data={
                'structure_type': self.structure_type.pk,
                'name': 'stale_code',
                'label': 'Stale code updated',
                'field_type': 'CharField',
                'sort_order': 6,
            },
            instance=stale_field,
        )
        self.assertTrue(update_form.is_valid(), update_form.errors)

        update_form.save()
        stale_field.refresh_from_db()
        self.assertEqual(stale_field.foreign_key_model, '')

    def test_structure_field_inline_form_hides_foreign_key_target(self):
        site = AdminSite()
        inline = StructureFieldInline(StructureType, site)
        request = RequestFactory().get('/')
        request.user = PermissiveAdminUser()

        formset_class = inline.get_formset(request, self.structure_type)
        form = formset_class.form()

        self.assertNotIn('foreign_key_model', form.fields)

    def test_structure_field_admin_locks_created_structure_type(self):
        site = AdminSite()
        admin_model = StructureFieldAdmin(StructureField, site)
        factory = RequestFactory()
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        get_request = factory.get('/', {'structure_type': self.structure_type.pk})
        get_request.user = PermissiveAdminUser()
        post_request = factory.post('/', {'structure_type': self.structure_type.pk})
        post_request.user = PermissiveAdminUser()
        actions_request = factory.get('/')
        actions_request.user = PermissiveAdminUser()

        self.assertFalse(admin_model.has_add_permission(get_request))
        self.assertFalse(admin_model.has_add_permission(post_request))
        self.assertFalse(admin_model.has_change_permission(actions_request, field))
        self.assertFalse(admin_model.has_delete_permission(actions_request, field))
        self.assertNotIn('delete_selected', admin_model.get_actions(actions_request))

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

        offset_rows = SQLExecutor.get_all(self.structure_type, limit=None, offset=1)
        self.assertTrue(offset_rows['success'], offset_rows.get('error'))
        self.assertEqual(offset_rows['total'], 2)
        self.assertEqual(len(offset_rows['records']), 1)

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

    def test_unlimited_offset_pagination_uses_postgresql_compatible_sql(self):
        with mock.patch.object(connection, 'vendor', 'postgresql'):
            clause, params = SQLExecutor._pagination_clause(limit=None, offset=5)

        self.assertEqual(clause, ' LIMIT ALL OFFSET %s')
        self.assertEqual(params, [5])

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
        self.assertEqual(Decimal(str(row['record']['thickness'])), Decimal('2.50'))

    def test_create_table_rejects_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field()

        create_result = SQLExecutor.create_table(self.structure_type)

        self.assertFalse(create_result['success'])
        self.assertIn('ForeignKey dynamic fields are not supported', create_result['error'])
        self.assertIn('Material.struct_type/struct_props_id', create_result['error'])
        self.assertFalse(SQLExecutor.table_exists(self.structure_type))
        self.assertEqual(fk_field.field_type, 'ForeignKey')

    def test_dynamic_form_excludes_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field()

        form_class = get_dynamic_form(self.structure_type)
        form = form_class()

        self.assertNotIn(f'field_{fk_field.id}', form.fields)

    def test_table_storage_excludes_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field(legacy=False, is_required=False)
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        self._mark_field_as_legacy_foreign_key(fk_field)

        row_id = table_storage.insert_row(
            self.structure_type,
            'row-code',
            {'title': 'Storage row', fk_field.name: '00000000-0000-0000-0000-000000000000'},
        )

        loaded = table_storage.load_field_data(self.structure_type, row_id)
        display_values = {
            display_value.field.name: display_value.get_value()
            for display_value in table_storage.get_display_values(self.structure_type, row_id)
        }

        self.assertEqual(loaded['title'], 'Storage row')
        self.assertNotIn(fk_field.name, loaded)
        self.assertNotIn(fk_field.name, display_values)

    def test_dynamic_table_form_excludes_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field(legacy=False, is_required=False)
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        self._mark_field_as_legacy_foreign_key(fk_field)

        form_class = get_dynamic_form(self.structure_type)
        form = form_class()

        self.assertNotIn(f'field_{fk_field.id}', form.fields)

    def test_dynamic_table_form_saves_without_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field(legacy=False, is_required=False)
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        self._mark_field_as_legacy_foreign_key(fk_field)

        form_class = get_dynamic_form(self.structure_type)
        form = form_class(
            data={
                'code': 'form-row',
                f'field_{self.structure_type.fields.get(name="title").id}': 'Form row',
                f'field_{fk_field.id}': '00000000-0000-0000-0000-000000000000',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save()
        loaded = table_storage.load_field_data(self.structure_type, instance.dynamic_row_id)
        self.assertEqual(loaded['title'], 'Form row')
        self.assertNotIn(fk_field.name, loaded)

    def test_add_column_rejects_legacy_foreign_key_field(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        fk_field = StructureField(
            structure_type=self.structure_type,
            name='material',
            label='Material',
            field_type='ForeignKey',
            is_required=True,
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, fk_field)

        self.assertFalse(result['success'])
        self.assertIn('ForeignKey dynamic fields are not supported', result['error'])
        self.assertIn('Material.struct_type/struct_props_id', result['error'])

    def test_add_required_column_with_default_backfills_non_empty_table(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Existing panel'},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        new_field = StructureField(
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

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT {SQLExecutor.quote_identifier("status")} '
                f'FROM {SQLExecutor.quote_identifier(self.structure_type.table_name)} '
                f'WHERE {SQLExecutor.quote_identifier("id")} = %s',
                [insert_result['id']],
            )
            self.assertEqual(cursor.fetchone()[0], 'draft')

    def test_add_required_column_without_default_rejects_non_empty_table(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Existing panel'},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        new_field = StructureField(
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
        new_field = StructureField(
            structure_type=self.structure_type,
            name='notes',
            label='Notes',
            field_type='TextField',
            sort_order=4,
        )

        result = SQLExecutor.add_column(self.structure_type, new_field)
        self.assertTrue(result['success'], result.get('error'))

        with connection.cursor() as cursor:
            cursor.execute(f'SELECT * FROM {SQLExecutor.quote_identifier(self.structure_type.table_name)} LIMIT 0')
            columns = [column[0] for column in cursor.description]
        self.assertIn('notes', columns)

        dangerous_type = StructureType.objects.create(
            name='Dangerous',
            code='dangerous',
            table_name='structures_danger; DROP TABLE structures_test_panel',
        )
        self.assertFalse(SQLExecutor.create_table(dangerous_type)['success'])

        dangerous_field = StructureField(
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
