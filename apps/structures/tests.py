import io
import uuid
from decimal import Decimal
from unittest import mock

from django import forms
from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from apps.structures import table_storage
from apps.materials.models import Material
from apps.structures.admin import (
    StructureFieldAdmin,
    StructureFieldAdminForm,
    StructureFieldInline,
)
from apps.structures.forms import get_dynamic_form
from apps.structures.models import (
    MATERIAL_LINK_FIELD_TYPE,
    StructureField,
    StructureType,
)
from apps.structures.identifiers import (
    normalize_identifier,
    preview_table_name_from_title,
    validate_field_column_name,
    validate_structure_code,
    validate_table_name,
)
from apps.structures.sql_executor import SQLExecutor
from apps.structures.property_mapping import (
    property_to_structure_field_data,
    structure_column_name_from_property,
    structure_field_label_from_property,
)
from apps.structures.type_forms import StructureFieldForm, StructureTypeForm


from apps.references.models import Property, PropertyGroup


class PropertyMappingTests(TestCase):
    def setUp(self):
        self.group = PropertyGroup.objects.create(name='Mechanical', sort_order=1)

    def test_property_maps_to_decimal_field_with_unit_in_label(self):
        prop = Property.objects.create(
            name='tensile_strength',
            display_name='Предел прочности',
            unit='МПа',
            data_type='number',
            group=self.group,
        )

        data = property_to_structure_field_data(prop)

        self.assertEqual(data['field_type'], 'DecimalField')
        self.assertEqual(data['label'], 'Предел прочности, МПа')
        self.assertEqual(data['name'], 'tensile_strength')
        self.assertEqual(data['decimal_places'], 2)
        self.assertEqual(data['max_digits'], 10)

    def test_property_maps_to_decimal_field_with_custom_decimal_places(self):
        prop = Property.objects.create(
            name='density',
            display_name='Плотность',
            unit='g/cm3',
            data_type='number',
            decimal_places=2,
            group=self.group,
        )

        data = property_to_structure_field_data(prop)

        self.assertEqual(data['decimal_places'], 2)

    def test_property_string_maps_to_char_field(self):
        prop = Property.objects.create(
            name='surface_finish',
            display_name='Отделка поверхности',
            data_type='string',
        )

        self.assertEqual(property_to_structure_field_data(prop)['field_type'], 'CharField')

    def test_property_choice_maps_to_choice_field_with_options(self):
        from apps.references.models import PropertyChoice

        prop = Property.objects.create(
            name='weave_type',
            display_name='Тип сплетения',
            data_type='choice',
        )
        PropertyChoice.objects.create(property=prop, label='Саржа', value='twill', sort_order=0)
        PropertyChoice.objects.create(property=prop, label='Полотно', value='plain', sort_order=1)

        data = property_to_structure_field_data(prop)
        self.assertEqual(data['field_type'], 'ChoiceField')
        self.assertEqual(data['data_type'], 'choice')
        self.assertEqual(
            data['choices'],
            [
                {'value': 'twill', 'label': 'Саржа'},
                {'value': 'plain', 'label': 'Полотно'},
            ],
        )
        self.assertEqual(data['choice_options'], data['choices'])

    def test_reserved_sql_name_gets_safe_suffix(self):
        prop = Property.objects.create(
            name='select',
            display_name='Select',
            data_type='number',
        )

        self.assertEqual(structure_column_name_from_property(prop), 'select_value')

    def test_structure_field_label_without_unit(self):
        prop = Property.objects.create(
            name='density',
            display_name='Плотность',
            data_type='number',
        )
        self.assertEqual(structure_field_label_from_property(prop), 'Плотность')


class StructureIdentifierTests(TestCase):
    def test_transliterate_russian_title(self):
        self.assertEqual(normalize_identifier('Сэндвичная панель'), 'sendvichnaya_panel')
        self.assertEqual(
            preview_table_name_from_title('Сэндвичная панель'),
            'structures_sendvichnaya_panel',
        )

    def test_reject_sql_reserved_word(self):
        with self.assertRaises(ValueError):
            validate_structure_code('select')

    def test_reject_reserved_table_column_name(self):
        with self.assertRaises(ValueError):
            validate_field_column_name('created_at')

    def test_validate_table_name_requires_structures_prefix(self):
        with self.assertRaises(ValueError):
            validate_table_name('my_custom_table')

    def test_validate_table_name_rejects_sql_injection(self):
        with self.assertRaises(ValueError):
            validate_table_name('structures_danger; DROP TABLE users;--')

    def test_structure_type_form_accepts_custom_table_name(self):
        form = StructureTypeForm(
            data={
                'name': 'UI Sandwich',
                'description': '',
                'display_color': '#007679',
                'table_name': 'structures_custom_panel',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['table_name'], 'structures_custom_panel')

    def test_structure_type_form_rejects_invalid_display_color(self):
        form = StructureTypeForm(
            data={
                'name': 'UI Sandwich',
                'description': '',
                'display_color': 'red',
                'table_name': 'structures_custom_panel',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('display_color', form.errors)

    def test_structure_type_form_rejects_invalid_table_name(self):
        form = StructureTypeForm(
            data={
                'name': 'UI Sandwich',
                'description': '',
                'display_color': '#007679',
                'table_name': 'structures_bad-name',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('table_name', form.errors)

    def test_structure_type_form_generates_code_from_name(self):
        form = StructureTypeForm(
            data={
                'name': 'UI Sandwich',
                'description': '',
                'display_color': '#007679',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['code'], 'ui_sandwich')
        self.assertEqual(form.cleaned_data['table_name'], 'structures_ui_sandwich')

    def test_structure_field_form_generates_column_from_label(self):
        form = StructureFieldForm(
            data={
                'label': 'Толщина, мм',
                'name': '',
                'field_type': 'DecimalField',
                'sort_order': '1',
                'max_digits': '10',
                'decimal_places': '2',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['name'], 'tolschina_mm')

    def test_structure_field_form_rejects_duplicate_reserved_name(self):
        form = StructureFieldForm(
            data={
                'label': 'ID',
                'name': 'id',
                'field_type': 'IntegerField',
                'sort_order': '1',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_structure_field_form_rejects_integer_default_with_decimal(self):
        form = StructureFieldForm(
            data={
                'label': 'Количество',
                'name': 'count',
                'field_type': 'IntegerField',
                'default_value': '1.5',
                'sort_order': '1',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('default_value', form.errors)
        self.assertIn('без дробной части', form.errors['default_value'][0])

    def test_structure_field_form_accepts_decimal_default_with_dot(self):
        form = StructureFieldForm(
            data={
                'label': 'Толщина',
                'name': 'thickness',
                'field_type': 'DecimalField',
                'default_value': '12.34',
                'sort_order': '1',
                'max_digits': '10',
                'decimal_places': '2',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_structure_field_form_accepts_decimal_default_with_comma(self):
        form = StructureFieldForm(
            data={
                'label': 'Толщина',
                'name': 'thickness',
                'field_type': 'DecimalField',
                'default_value': '12,34',
                'sort_order': '1',
                'max_digits': '10',
                'decimal_places': '2',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_structure_field_form_clears_numeric_params_for_material_link(self):
        form = StructureFieldForm(
            data={
                'label': 'Материал',
                'name': 'material_ref',
                'field_type': MATERIAL_LINK_FIELD_TYPE,
                'default_value': 'ignored',
                'max_length': '255',
                'max_digits': '10',
                'decimal_places': '2',
                'sort_order': '1',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['max_length'])
        self.assertIsNone(form.cleaned_data['max_digits'])
        self.assertIsNone(form.cleaned_data['decimal_places'])
        self.assertEqual(form.cleaned_data['default_value'], '')


class PermissiveAdminUser:
    is_active = True
    is_staff = True

    def has_perm(self, perm):
        return True


class PublicStructureRecordViewsTests(TransactionTestCase):
    def setUp(self):
        from apps.workspaces.services import ensure_legacy_workspace

        self.workspace = ensure_legacy_workspace()
        self.structure_type = StructureType.objects.create(
            name='Public Panel',
            code='public_panel',
            table_name='structures_public_panel',
            description='Public UI type',
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
            label='Thickness, mm',
            field_type='DecimalField',
            max_digits=8,
            decimal_places=2,
            sort_order=2,
        )
        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def _field_name(self, field_name):
        field = self.structure_type.fields.get(name=field_name)
        return f'structure_field_{field.pk}'

    def test_select_type_shows_create_and_list_links(self):
        response = self.client.get(reverse('structures:select_type'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Public Panel')
        self.assertContains(response, reverse('structures:list', args=[self.structure_type.code]))
        self.assertContains(response, reverse('structures:type_manage', args=[self.structure_type.code]))
        self.assertContains(response, 'bi-gear')
        self.assertNotContains(response, 'structures_public_panel')

    def test_create_list_detail_edit_delete_flow(self):
        create_url = reverse('structures:create', args=[self.structure_type.code])
        create_response = self.client.post(
            create_url,
            {
                self._field_name('title'): 'Panel A',
                self._field_name('thickness'): '12.50',
            },
        )
        self.assertEqual(create_response.status_code, 302)

        records = SQLExecutor.get_structure_instances(self.structure_type)
        self.assertEqual(len(records), 1)
        row_id = records[0]['id']

        material = Material.objects.create(
            code='MAT-PANEL-A',
            name='Panel A material',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        list_response = self.client.get(
            reverse('structures:list', args=[self.structure_type.code])
        )
        self.assertContains(list_response, 'Panel A material')
        self.assertContains(list_response, 'MAT-PANEL-A')
        self.assertContains(list_response, 'structure-materials-grid')
        self.assertContains(list_response, '12,50')

        detail_response = self.client.get(
            reverse('structures:detail', args=[self.structure_type.code, row_id])
        )
        self.assertContains(detail_response, 'Panel A')
        self.assertContains(detail_response, '12,50')

        edit_response = self.client.post(
            reverse('structures:edit', args=[self.structure_type.code, row_id]),
            {
                self._field_name('title'): 'Panel B',
                self._field_name('thickness'): '9.75',
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        updated = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(updated['title'], 'Panel B')

        material.delete()
        delete_response = self.client.post(
            reverse('structures:delete', args=[self.structure_type.code, row_id])
        )
        self.assertRedirects(
            delete_response,
            reverse('structures:list', args=[self.structure_type.code]),
        )
        self.assertEqual(SQLExecutor.get_structure_instances(self.structure_type), [])

    def test_delete_blocked_when_material_links_row(self):
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Linked panel', 'thickness': '1.00'},
        )['id']
        Material.objects.create(
            code='MAT-LINK-STRUCT',
            name='Linked material',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        delete_response = self.client.post(
            reverse('structures:delete', args=[self.structure_type.code, row_id])
        )
        self.assertRedirects(
            delete_response,
            reverse('structures:detail', args=[self.structure_type.code, row_id]),
        )
        self.assertIsNotNone(SQLExecutor.get_structure_instance(self.structure_type, row_id))

    def test_detail_shows_material_expand_for_material_link(self):
        material = Material.objects.create(code='MAT-EXPAND', name='Expandable material')
        link_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='linked_material',
            label='Linked material',
            field_type=MATERIAL_LINK_FIELD_TYPE,
            foreign_key_model='materials.Material',
            sort_order=3,
        )

        row_id = SQLExecutor.insert(
            self.structure_type,
            {
                'title': 'Panel with link',
                'thickness': '3.00',
                'linked_material': material,
            },
        )['id']

        response = self.client.get(
            reverse('structures:detail', args=[self.structure_type.code, row_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Expandable material')
        self.assertContains(response, 'structure-material-expand')
        self.assertContains(response, 'Развернуть')
        self.assertContains(response, f'data-material-id="{material.pk}"')
        self.assertContains(response, f'id="structure-material-preview-{link_field.pk}"')
        self.assertContains(response, 'structure_material_expand.js')
        self.assertContains(
            response,
            reverse(
                'materials:properties_json',
                kwargs={'pk': '00000000-0000-0000-0000-000000000000'},
            ),
        )

    def test_structure_record_display_label_prefers_linked_material_name(self):
        from apps.structures.table_storage import structure_record_display_label

        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Panel A', 'thickness': '78.00'},
        )['id']
        material = Material.objects.create(
            code='MAT-DISPLAY-LABEL',
            name='Полотно',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)

        self.assertEqual(
            structure_record_display_label(record, self.structure_type),
            'Полотно',
        )
        self.assertEqual(
            structure_record_display_label(
                record,
                self.structure_type,
                linked_materials=[{'pk': material.pk, 'code': material.code, 'name': material.name}],
            ),
            'Полотно',
        )

    def test_list_shows_materials_structure_grid(self):
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Linked panel', 'thickness': '4.00'},
        )['id']
        material = Material.objects.create(
            code='MAT-LIST-EXPAND',
            name='List expandable material',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.get(
            reverse('structures:list', args=[self.structure_type.code])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'List expandable material')
        self.assertContains(response, 'MAT-LIST-EXPAND')
        self.assertContains(response, 'structure-materials-grid')
        self.assertContains(response, 'Linked panel')
        self.assertContains(response, '4,00')
        self.assertContains(response, 'Thickness')
        self.assertContains(response, 'structure-materials-grid__col-unit')
        self.assertContains(response, '>mm<')
        self.assertContains(response, reverse('materials:detail', args=[material.pk]))
        self.assertNotContains(response, 'structure-material-expand')
        self.assertNotContains(response, 'structure_material_expand.js')

    def test_list_search_filters_by_tag_without_showing_tags(self):
        from apps.core.models import Tag

        tagged_row = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Tagged panel', 'thickness': '1.00'},
        )['id']
        other_row = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Other panel', 'thickness': '2.00'},
        )['id']
        tagged = Material.objects.create(
            code='MAT-TAGGED',
            name='Tagged material',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=tagged_row,
        )
        Material.objects.create(
            code='MAT-OTHER',
            name='Other material',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=other_row,
        )
        tag = Tag.objects.create(
            name='кевлар-тест',
            slug='kevlar-test',
            workspace=self.workspace,
        )
        tagged.tags.add(tag)

        response = self.client.get(
            reverse('structures:list', args=[self.structure_type.code]),
            {'q': 'кевлар'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tagged material')
        self.assertContains(response, 'MAT-TAGGED')
        self.assertNotContains(response, 'Other material')
        self.assertNotContains(response, 'MAT-OTHER')
        self.assertNotContains(response, 'кевлар-тест')

    def test_list_shows_only_home_workspace_materials(self):
        from apps.workspaces.models import Workspace
        from apps.workspaces.visibility import VisibilityMode

        local_row = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Local panel', 'thickness': '1.00'},
        )['id']
        shared_row = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Shared panel', 'thickness': '2.00'},
        )['id']
        other = Workspace.objects.create(slug='other-struct-ws', name='Other struct WS')
        Material.objects.create(
            code='MAT-LOCAL-WS',
            name='Local workspace material',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
            struct_props_id=local_row,
        )
        Material.objects.create(
            code='MAT-SHARED-WS',
            name='Shared workspace material',
            home_workspace=other,
            visibility_mode=VisibilityMode.ALL_WORKSPACES,
            struct_type=self.structure_type,
            struct_props_id=shared_row,
        )

        response = self.client.get(
            reverse('structures:list', args=[self.structure_type.code])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Local workspace material')
        self.assertContains(response, 'MAT-LOCAL-WS')
        self.assertNotContains(response, 'Shared workspace material')
        self.assertNotContains(response, 'MAT-SHARED-WS')

    def test_list_allows_type_without_created_table(self):
        draft_type = StructureType.objects.create(
            name='Draft Panel',
            code='draft_panel',
            table_name='structures_draft_panel',
            is_active=True,
        )
        StructureField.objects.create(
            structure_type=draft_type,
            name='title',
            label='Title',
            field_type='CharField',
            sort_order=1,
        )

        response = self.client.get(reverse('structures:list', args=[draft_type.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ещё не создана')
        self.assertContains(response, reverse('structures:type_manage', args=[draft_type.code]))

    def test_create_requires_created_table(self):
        draft_type = StructureType.objects.create(
            name='Draft Panel Create',
            code='draft_panel_create',
            table_name='structures_draft_panel_create',
            is_active=True,
        )
        StructureField.objects.create(
            structure_type=draft_type,
            name='title',
            label='Title',
            field_type='CharField',
            sort_order=1,
        )

        response = self.client.get(reverse('structures:create', args=[draft_type.code]))
        self.assertRedirects(
            response,
            reverse('structures:type_manage', args=[draft_type.code]),
        )


class PublicStructureTypeManageViewsTests(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.workspaces.services import ensure_legacy_workspace
        from apps.workspaces.test_utils import login_test_client

        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser('struct-admin', password='pass')
        legacy = ensure_legacy_workspace()
        login_test_client(self.client, user=self.admin, workspace=legacy, password='pass')

    def tearDown(self):
        for structure_type in StructureType.objects.filter(code__startswith='ui_'):
            if structure_type.is_created:
                SQLExecutor.drop_table(structure_type)
            structure_type.delete()

    def test_type_create_form_includes_property_picker(self):
        Property.objects.create(
            name='density',
            display_name='Плотность',
            unit='г/см³',
            data_type='number',
        )
        response = self.client.get(reverse('structures:type_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'add-from-properties-btn')
        self.assertNotContains(response, 'add-material-link-btn')
        self.assertContains(response, 'structure-field-empty')
        self.assertContains(response, 'reference-properties-data')

    def test_create_type_and_sql_table_from_public_ui(self):
        create_url = reverse('structures:type_create')
        response = self.client.post(
            create_url,
            {
                'name': 'UI Sandwich',
                'description': 'Created from public UI',
                'display_color': '#6A8FC0',
                'allow_layers': 'on',
                'fields-TOTAL_FORMS': '1',
                'fields-INITIAL_FORMS': '0',
                'fields-MIN_NUM_FORMS': '0',
                'fields-MAX_NUM_FORMS': '1000',
                'fields-0-name': '',
                'fields-0-label': 'Title',
                'fields-0-field_type': 'CharField',
                'fields-0-is_required': 'on',
                'fields-0-sort_order': '1',
                'fields-0-max_length': '255',
            },
        )
        self.assertEqual(response.status_code, 302)
        structure_type = StructureType.objects.get(code='ui_sandwich')
        self.assertFalse(structure_type.is_created)
        self.assertEqual(structure_type.display_color, '#6A8FC0')
        self.assertEqual(structure_type.fields.count(), 1)

        manage_url = reverse('structures:type_manage', args=[structure_type.code])
        self.assertRedirects(response, f'{manage_url}?prompt_create_table=1')
        manage_response = self.client.get(f'{manage_url}?prompt_create_table=1')
        self.assertContains(manage_response, 'create-table-prompt-modal')
        self.assertContains(manage_response, 'сохранён')
        self.assertContains(manage_response, 'create-table/')

        table_response = self.client.post(
            reverse('structures:type_create_table', args=[structure_type.code])
        )
        self.assertRedirects(table_response, manage_url)
        structure_type.refresh_from_db()
        self.assertTrue(structure_type.is_created)
        self.assertTrue(SQLExecutor.table_exists(structure_type))

        records_response = self.client.get(
            reverse('structures:list', args=[structure_type.code])
        )
        self.assertEqual(records_response.status_code, 200)

    def test_create_type_without_fields_and_sql_table(self):
        create_url = reverse('structures:type_create')
        response = self.client.post(
            create_url,
            {
                'name': 'UI Empty',
                'description': '',
                'display_color': '#6A8FC0',
                'fields-TOTAL_FORMS': '0',
                'fields-INITIAL_FORMS': '0',
                'fields-MIN_NUM_FORMS': '0',
                'fields-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertEqual(response.status_code, 302)
        structure_type = StructureType.objects.get(code='ui_empty')
        self.assertEqual(structure_type.fields.count(), 0)

        table_response = self.client.post(
            reverse('structures:type_create_table', args=[structure_type.code])
        )
        self.assertRedirects(
            table_response,
            reverse('structures:type_manage', args=[structure_type.code]),
        )
        structure_type.refresh_from_db()
        self.assertTrue(structure_type.is_created)
        self.assertTrue(SQLExecutor.table_exists(structure_type))

    def test_create_table_with_custom_table_name_via_post(self):
        structure_type = StructureType.objects.create(
            name='UI Custom Table',
            code='ui_custom_table',
            display_color='#6A8FC0',
        )
        table_response = self.client.post(
            reverse('structures:type_create_table', args=[structure_type.code]),
            {'table_name': 'structures_ui_custom_name'},
        )
        self.assertRedirects(
            table_response,
            reverse('structures:type_manage', args=[structure_type.code]),
        )
        structure_type.refresh_from_db()
        self.assertTrue(structure_type.is_created)
        self.assertEqual(structure_type.table_name, 'structures_ui_custom_name')
        self.assertTrue(SQLExecutor.table_exists(structure_type))

    def test_create_table_rejects_invalid_table_name_via_post(self):
        structure_type = StructureType.objects.create(
            name='UI Bad Table',
            code='ui_bad_table',
            display_color='#6A8FC0',
        )
        table_response = self.client.post(
            reverse('structures:type_create_table', args=[structure_type.code]),
            {'table_name': 'structures_bad;drop'},
            follow=True,
        )
        structure_type.refresh_from_db()
        self.assertFalse(structure_type.is_created)
        self.assertContains(table_response, 'snake_case')

    def test_manage_page_prompts_create_table_for_existing_unsaved_type(self):
        structure_type = StructureType.objects.create(
            name='UI Prompt Existing',
            code='ui_prompt_existing',
            display_color='#6A8FC0',
        )
        manage_url = reverse('structures:type_manage', args=[structure_type.code])
        response = self.client.get(manage_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'create-table-prompt-modal')
        self.assertContains(response, 'SQL-таблица ещё не создана')
        self.assertNotContains(response, 'сохранён')

    def test_drop_table_from_public_ui(self):
        structure_type = StructureType.objects.create(
            name='UI Drop',
            code='ui_type_drop',
            table_name='structures_ui_type_drop',
        )
        StructureField.objects.create(
            structure_type=structure_type,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
        )
        self.assertTrue(SQLExecutor.create_table(structure_type)['success'])

        drop_get = self.client.get(reverse('structures:type_drop_table', args=[structure_type.code]))
        self.assertEqual(drop_get.status_code, 200)

        drop_post = self.client.post(reverse('structures:type_drop_table', args=[structure_type.code]))
        self.assertRedirects(
            drop_post,
            reverse('structures:type_manage', args=[structure_type.code]),
        )
        structure_type.refresh_from_db()
        self.assertFalse(structure_type.is_created)
        self.assertFalse(SQLExecutor.table_exists(structure_type))

    def test_create_table_shows_error_for_invalid_integer_default(self):
        structure_type = StructureType.objects.create(
            name='UI Bad Default',
            code='ui_bad_default',
            table_name='structures_ui_bad_default',
        )
        StructureField.objects.create(
            structure_type=structure_type,
            name='count',
            label='Количество',
            field_type='IntegerField',
            default_value='2.5',
            sort_order=1,
        )

        response = self.client.post(
            reverse('structures:type_create_table', args=[structure_type.code]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'без дробной части')
        structure_type.refresh_from_db()
        self.assertFalse(structure_type.is_created)

    def test_reject_duplicate_field_names_in_formset(self):
        create_url = reverse('structures:type_create')
        response = self.client.post(
            create_url,
            {
                'name': 'UI Duplicate Fields',
                'description': '',
                'display_color': '#007679',
                'fields-TOTAL_FORMS': '2',
                'fields-INITIAL_FORMS': '0',
                'fields-MIN_NUM_FORMS': '0',
                'fields-MAX_NUM_FORMS': '1000',
                'fields-0-name': 'width_mm',
                'fields-0-label': 'Width',
                'fields-0-field_type': 'DecimalField',
                'fields-0-sort_order': '1',
                'fields-0-max_digits': '10',
                'fields-0-decimal_places': '2',
                'fields-1-name': 'width_mm',
                'fields-1-label': 'Width copy',
                'fields-1-field_type': 'DecimalField',
                'fields-1-sort_order': '2',
                'fields-1-max_digits': '10',
                'fields-1-decimal_places': '2',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StructureType.objects.filter(name='UI Duplicate Fields').exists())
        self.assertContains(response, 'разными', status_code=200)

    def test_update_display_color_on_manage_page(self):
        structure_type = StructureType.objects.create(
            name='UI Color',
            code='ui_color_type',
            display_color='#007679',
        )
        manage_url = reverse('structures:type_manage', args=[structure_type.code])
        response = self.client.post(manage_url, {'display_color': '#8B5CF6'})
        self.assertRedirects(response, manage_url)
        structure_type.refresh_from_db()
        self.assertEqual(structure_type.display_color, '#8B5CF6')


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
        self.assertEqual(set(apps.all_models['structures']), before_models)
        with self.assertRaises(LookupError):
            apps.get_model('structures', 'dynamic_test_panel')

        result = SQLExecutor.drop_table(self.structure_type)
        self.structure_type.refresh_from_db()

        self.assertEqual(result, {'success': True, 'error': None})
        self.assertFalse(self.structure_type.is_created)
        self.assertFalse(SQLExecutor.table_exists(self.structure_type))

    def test_create_table_rejects_decimal_default_exceeding_precision(self):
        StructureField.objects.filter(structure_type=self.structure_type, name='thickness').update(
            default_value='123.456',
            max_digits=5,
            decimal_places=2,
        )

        result = SQLExecutor.create_table(self.structure_type)

        self.assertFalse(result['success'])
        self.assertIn('знаков после запятой', result['error'])

    def test_create_table_rejects_integer_default_with_decimal_point(self):
        StructureField.objects.create(
            structure_type=self.structure_type,
            name='ratio',
            label='Ratio',
            field_type='IntegerField',
            default_value='1.5',
            sort_order=4,
        )

        result = SQLExecutor.create_table(self.structure_type)

        self.assertFalse(result['success'])
        self.assertIn('без дробной части', result['error'])

    def test_create_table_accepts_decimal_default_with_dot(self):
        StructureField.objects.filter(structure_type=self.structure_type, name='thickness').update(
            default_value='12.34',
        )

        result = SQLExecutor.create_table(self.structure_type)

        self.assertTrue(result['success'], result.get('error'))

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

    def test_create_table_allows_type_without_fields(self):
        empty_type = StructureType.objects.create(
            name='Empty Structure',
            code='empty_structure',
            table_name='structures_empty_structure',
        )

        result = SQLExecutor.create_table(empty_type)
        empty_type.refresh_from_db()

        self.assertTrue(result['success'])
        self.assertTrue(empty_type.is_created)
        self.assertTrue(SQLExecutor.table_exists(empty_type))
        SQLExecutor.drop_table(empty_type)

    def test_structure_field_allows_create_but_rejects_change_and_delete_when_created(self):
        field = self.structure_type.fields.get(name='title')
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        new_field = StructureField(
            structure_type=self.structure_type,
            name='status',
            label='Status',
            field_type='CharField',
            sort_order=4,
        )
        new_field.full_clean()
        new_field.save()
        self.assertTrue(self.structure_type.fields.filter(name='status').exists())
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT * FROM {SQLExecutor.quote_identifier(self.structure_type.table_name)} LIMIT 0'
            )
            columns = [column[0] for column in cursor.description]
        self.assertIn('status', columns)

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
        # Table flag is set but physical table may be missing — add_column should fail.
        with self.assertRaises(ValidationError):
            new_field.save()

    def test_structure_field_bulk_create_adds_column_for_created_structure_type(self):
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

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

        self.assertTrue(self.structure_type.fields.filter(name='status').exists())
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT * FROM {SQLExecutor.quote_identifier(self.structure_type.table_name)} LIMIT 0'
            )
            columns = [column[0] for column in cursor.description]
        self.assertIn('status', columns)

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

    def test_structure_field_inline_allows_add_but_locks_change_delete_when_created(self):
        site = AdminSite()
        inline = StructureFieldInline(StructureType, site)
        self.structure_type.is_created = True
        request = RequestFactory().get('/')
        request.user = PermissiveAdminUser()

        self.assertTrue(inline.has_add_permission(request, self.structure_type))
        self.assertFalse(inline.has_change_permission(request, self.structure_type))
        self.assertFalse(inline.has_delete_permission(request, self.structure_type))
        self.assertEqual(inline.get_extra(request, self.structure_type), 1)

    def test_field_type_choices_include_material_link_but_not_foreign_key(self):
        field_type_values = [value for value, _ in StructureField.FIELD_TYPES]
        self.assertIn('MaterialLink', field_type_values)
        self.assertIn('ChoiceField', field_type_values)
        self.assertNotIn('ForeignKey', field_type_values)

        site = AdminSite()
        admin_model = StructureFieldAdmin(StructureField, site)
        request = RequestFactory().get('/')
        request.user = PermissiveAdminUser()

        form_class = admin_model.get_form(request)
        form = form_class()

        form_choice_values = [value for value, _ in form.fields['field_type'].choices]
        self.assertIn('MaterialLink', form_choice_values)
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

    def test_structure_field_admin_form_normalizes_material_link_parameters(self):
        form = StructureFieldAdminForm(
            data={
                'structure_type': self.structure_type.pk,
                'name': 'skin_material',
                'label': 'Skin material',
                'field_type': 'MaterialLink',
                'is_required': True,
                'foreign_key_model': 'materials.Material',
                'max_length': 255,
                'max_digits': 10,
                'decimal_places': 2,
                'sort_order': 4,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        field = form.save()

        self.assertEqual(field.field_type, 'MaterialLink')
        self.assertEqual(field.foreign_key_model, '')
        self.assertIsNone(field.max_length)
        self.assertIsNone(field.max_digits)
        self.assertIsNone(field.decimal_places)

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

        self.assertTrue(admin_model.has_add_permission(get_request))
        self.assertTrue(admin_model.has_add_permission(post_request))
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

    def test_material_link_create_table_roundtrip_and_on_delete_set_null(self):
        material = Material.objects.create(code='MAT-LINK-001', name='Linked material')
        replacement = Material.objects.create(code='MAT-LINK-002', name='Replacement material')
        link_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='skin_material',
            label='Skin material',
            field_type='MaterialLink',
            is_required=True,
            max_length=255,
            max_digits=10,
            decimal_places=2,
            foreign_key_model='materials.Material',
            sort_order=4,
        )

        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

        expected_type = 'UUID' if connection.vendor == 'postgresql' else 'TEXT'
        self.assertEqual(SQLExecutor._field_sql_type(link_field), expected_type)
        with mock.patch.object(connection, 'vendor', 'postgresql'):
            self.assertEqual(SQLExecutor._field_sql_type(link_field), 'UUID')
        with mock.patch.object(connection, 'vendor', 'sqlite'):
            self.assertEqual(SQLExecutor._field_sql_type(link_field), 'TEXT')
        column_sql = SQLExecutor._column_definition(link_field)
        self.assertIn('REFERENCES', column_sql)
        self.assertIn(SQLExecutor.quote_identifier('materials_material'), column_sql)
        self.assertIn('ON DELETE SET NULL', column_sql)
        self.assertIn('NULL', column_sql)
        self.assertNotIn('NOT NULL', column_sql)

        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute(
                    f'PRAGMA foreign_key_list({SQLExecutor.quote_identifier(self.structure_type.table_name)})'
                )
                foreign_keys = cursor.fetchall()
            self.assertTrue(
                any(
                    row[2] == 'materials_material'
                    and row[3] == 'skin_material'
                    and row[4] == 'id'
                    and row[6].upper() == 'SET NULL'
                    for row in foreign_keys
                ),
                foreign_keys,
            )

        insert_result = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Linked panel', 'skin_material': material},
        )
        self.assertTrue(insert_result['success'], insert_result.get('error'))
        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertEqual(str(row['record']['skin_material']), str(material.pk))

        update_result = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'skin_material': str(replacement.pk)},
        )
        self.assertTrue(update_result['success'], update_result.get('error'))
        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertEqual(str(row['record']['skin_material']), str(replacement.pk))

        update_result = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'skin_material': ''},
        )
        self.assertTrue(update_result['success'], update_result.get('error'))
        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertIsNone(row['record']['skin_material'])

        update_result = SQLExecutor.update(
            self.structure_type,
            insert_result['id'],
            {'skin_material': replacement.pk},
        )
        self.assertTrue(update_result['success'], update_result.get('error'))
        replacement.delete()
        row = SQLExecutor.get_by_id(self.structure_type, insert_result['id'])
        self.assertIsNone(row['record']['skin_material'])

        blank_insert = SQLExecutor.insert(self.structure_type, {'title': 'Blank link panel'})
        self.assertTrue(blank_insert['success'], blank_insert.get('error'))
        blank_row = SQLExecutor.get_by_id(self.structure_type, blank_insert['id'])
        self.assertIsNone(blank_row['record']['skin_material'])

    def test_structure_record_label_resolves_material_link_and_skips_broken(self):
        from apps.structures.forms import MATERIAL_LINK_MISSING_LABEL, material_link_display
        from apps.structures.table_storage import structure_record_label

        material = Material.objects.create(code='MAT-LABEL-001', name='Label material')
        link_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='skin_material',
            label='Skin material',
            field_type='MaterialLink',
            sort_order=0,
        )
        title_field = self.structure_type.fields.get(name='title')
        title_field.sort_order = 1
        title_field.save(update_fields=['sort_order'])
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])

        resolved_id = table_storage.insert_row(
            self.structure_type,
            'resolved-row',
            {'skin_material': material.pk, 'title': 'Fallback title'},
        )
        fallback_id = table_storage.insert_row(
            self.structure_type,
            'fallback-row',
            {'title': 'Visible title'},
        )

        resolved = table_storage.get_row(self.structure_type, resolved_id)
        fallback = table_storage.get_row(self.structure_type, fallback_id)

        self.assertEqual(
            structure_record_label(resolved, self.structure_type),
            'MAT-LABEL-001 - Label material',
        )
        self.assertEqual(
            structure_record_label(fallback, self.structure_type),
            'Visible title',
        )
        empty_record_id = uuid.uuid4()
        self.assertEqual(
            structure_record_label({'id': empty_record_id}, self.structure_type),
            f'Запись {str(empty_record_id)[:8]}…',
        )

        missing_id = uuid.uuid4()
        link_display = table_storage.DisplayValue(link_field, missing_id)
        self.assertEqual(link_display.get_value(), MATERIAL_LINK_MISSING_LABEL)
        self.assertEqual(material_link_display(missing_id), MATERIAL_LINK_MISSING_LABEL)
        self.assertIsNone(link_display.material_pk)

        resolved_display = next(
            item for item in table_storage.get_display_values(self.structure_type, resolved_id)
            if item.field.name == link_field.name
        )
        self.assertEqual(resolved_display.material_pk, str(material.pk))

    def test_material_link_dynamic_table_form_uses_material_choice_and_initial_object(self):
        material = Material.objects.create(code='MAT-FORM-001', name='Form material')
        other_material = Material.objects.create(code='MAT-FORM-002', name='Other material')
        link_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='skin_material',
            label='Skin material',
            field_type='MaterialLink',
            sort_order=4,
        )
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        row_id = table_storage.insert_row(
            self.structure_type,
            'row-code',
            {'title': 'Form panel', 'skin_material': material.pk},
        )

        form_class = get_dynamic_form(self.structure_type)
        form = form_class()
        form_field = form.fields[f'structure_field_{link_field.pk}']

        self.assertIsInstance(form_field, forms.ModelChoiceField)
        self.assertFalse(form_field.required)
        self.assertEqual(list(form_field.queryset), [material, other_material])
        self.assertEqual(form_field.label_from_instance(material), 'MAT-FORM-001 - Form material')

    def test_choice_field_dynamic_form_uses_select_with_options(self):
        from apps.structures.forms import _build_dynamic_field
        from apps.structures.models import CHOICE_FIELD_TYPE

        choice_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='weave_type',
            label='Тип сплетения',
            field_type=CHOICE_FIELD_TYPE,
            choice_options=[
                {'value': 'twill', 'label': 'Саржа'},
                {'value': 'plain', 'label': 'Полотно'},
            ],
            sort_order=4,
        )
        form_field = _build_dynamic_field(choice_field)
        self.assertIsInstance(form_field, forms.ChoiceField)
        self.assertEqual(
            list(form_field.choices),
            [('', '---------'), ('twill', 'Саржа'), ('plain', 'Полотно')],
        )
        self.assertEqual(form_field.widget.attrs.get('data-choice-picker'), 'true')

    def test_char_field_falls_back_to_reference_choice_property(self):
        from apps.references.models import Property, PropertyChoice
        from apps.structures.forms import _build_dynamic_field

        prop = Property.objects.create(
            name='legacy_weave',
            display_name='Тип сплетения',
            data_type='choice',
        )
        PropertyChoice.objects.create(property=prop, label='Саржа', value='twill', sort_order=0)
        char_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='legacy_weave',
            label='Тип сплетения',
            field_type='CharField',
            sort_order=4,
        )
        form_field = _build_dynamic_field(char_field)
        self.assertIsInstance(form_field, forms.ChoiceField)
        self.assertIn(('twill', 'Саржа'), list(form_field.choices))

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

        self.assertNotIn(f'structure_field_{fk_field.pk}', form.fields)

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

        self.assertNotIn(f'structure_field_{fk_field.pk}', form.fields)

    def test_dynamic_table_form_saves_without_legacy_foreign_key_field(self):
        fk_field = self._add_material_fk_field(legacy=False, is_required=False)
        self.assertTrue(SQLExecutor.create_table(self.structure_type)['success'])
        self._mark_field_as_legacy_foreign_key(fk_field)

        title_field = self.structure_type.fields.get(name='title')
        form_class = get_dynamic_form(self.structure_type)
        form = form_class(
            data={
                'code': 'form-row',
                f'structure_field_{title_field.pk}': 'Form row',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        row_id = form.save()
        loaded = table_storage.load_field_data(self.structure_type, row_id)
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


class StructureDecimalRangeTests(TransactionTestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Decimal range panel',
            code='decimal_range_panel',
            table_name='structures_decimal_range_panel',
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
        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def _field_name(self, field_name):
        field = self.structure_type.fields.get(name=field_name)
        return f'structure_field_{field.pk}'

    def _decimal_post_data(self, field_name, *, scalar='', min_value='', max_value='', tolerance_value='', is_range=False, is_tolerance=False):
        field = self.structure_type.fields.get(name=field_name)
        base = f'structure_field_{field.pk}'
        data = {
            base: scalar,
            f'{base}__min': min_value,
            f'{base}__max': max_value,
            f'{base}__tolerance': tolerance_value,
        }
        if is_range:
            data[f'{base}__is_range'] = 'on'
        if is_tolerance:
            data[f'{base}__is_tolerance'] = 'on'
        return data

    def test_create_table_creates_decimal_companion_columns(self):
        for column_name in (
            'thickness',
            'thickness__kind',
            'thickness__b',
        ):
            self.assertTrue(
                SQLExecutor.column_exists(self.structure_type, column_name),
                column_name,
            )

    def test_insert_scalar_writes_companion_columns(self):
        from apps.core.property_number_value import VALUE_KIND_SCALAR
        from apps.structures.decimal_range import pack_decimal_field_data

        packed = pack_decimal_field_data(
            'thickness',
            value_kind=VALUE_KIND_SCALAR,
            value='12.50',
            value_b=None,
        )
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Scalar panel', **packed},
        )['id']
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(record['thickness__kind'], 'scalar')
        self.assertEqual(str(record['thickness']), '12.50')
        self.assertIsNone(record['thickness__b'])

    def test_insert_range_writes_companion_columns(self):
        from apps.core.property_number_value import VALUE_KIND_RANGE
        from apps.structures.decimal_range import pack_decimal_field_data

        packed = pack_decimal_field_data(
            'thickness',
            value_kind=VALUE_KIND_RANGE,
            value='900',
            value_b='1900',
        )
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Range panel', **packed},
        )['id']
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(record['thickness__kind'], 'range')
        self.assertEqual(str(record['thickness']), '900.00')
        self.assertEqual(str(record['thickness__b']), '1900.00')

    def test_backfill_populates_companion_columns_for_legacy_scalar(self):
        table_name = SQLExecutor.quote_identifier(self.structure_type.table_name)
        row_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {table_name} '
                f'({SQLExecutor.quote_identifier("id")}, '
                f'{SQLExecutor.quote_identifier("title")}, '
                f'{SQLExecutor.quote_identifier("thickness")}) '
                f'VALUES (%s, %s, %s)',
                [row_id, 'Legacy panel', '7.25'],
            )

        result = SQLExecutor.backfill_decimal_companion_columns(self.structure_type)
        self.assertTrue(result['success'], result.get('error'))
        self.assertEqual(result['updated'], 1)

        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(record['thickness__kind'], 'scalar')
        self.assertEqual(str(record['thickness']), '7.25')
        self.assertIsNone(record['thickness__b'])

    def test_insert_tolerance_writes_companion_columns(self):
        from apps.core.property_number_value import VALUE_KIND_TOLERANCE
        from apps.structures.decimal_range import pack_decimal_field_data

        packed = pack_decimal_field_data(
            'thickness',
            value_kind=VALUE_KIND_TOLERANCE,
            value=Decimal('0.27'),
            value_b=Decimal('0.03'),
        )
        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Tolerance panel', **packed},
        )['id']
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(record['thickness__kind'], 'tolerance')
        self.assertEqual(str(record['thickness']), '0.27')
        self.assertEqual(str(record['thickness__b']), '0.03')

    def test_structure_record_form_saves_decimal_tolerance(self):
        create_url = reverse('structures:create', args=[self.structure_type.code])
        post_data = {
            self._field_name('title'): 'Tolerance form panel',
            **self._decimal_post_data(
                'thickness',
                scalar='0,27',
                tolerance_value='0,03',
                is_tolerance=True,
            ),
        }
        response = self.client.post(create_url, post_data)
        self.assertEqual(response.status_code, 302)

        records = SQLExecutor.get_structure_instances(self.structure_type)
        record = records[0]
        self.assertEqual(record['thickness__kind'], 'tolerance')
        self.assertEqual(str(record['thickness__b']), '0.03')

        detail_response = self.client.get(
            reverse('structures:detail', args=[self.structure_type.code, record['id']])
        )
        self.assertContains(detail_response, '0,27±0,03')

    def test_insert_auto_adds_missing_companion_columns(self):
        table_name = SQLExecutor.quote_identifier(self.structure_type.table_name)
        with connection.cursor() as cursor:
            for column_name in (
                'thickness__kind',
                'thickness__b',
            ):
                cursor.execute(
                    f'ALTER TABLE {table_name} DROP COLUMN '
                    f'{SQLExecutor.quote_identifier(column_name)}'
                )

        row_id = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Legacy auto-migrate', 'thickness': '1.50'},
        )['id']
        self.assertTrue(SQLExecutor.column_exists(self.structure_type, 'thickness__kind'))
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(str(record['thickness']), '1.50')

    def test_migrate_structure_decimal_ranges_command(self):
        table_name = SQLExecutor.quote_identifier(self.structure_type.table_name)
        with connection.cursor() as cursor:
            for column_name in (
                'thickness__kind',
                'thickness__b',
            ):
                if SQLExecutor.column_exists(self.structure_type, column_name):
                    cursor.execute(
                        f'ALTER TABLE {table_name} DROP COLUMN '
                        f'{SQLExecutor.quote_identifier(column_name)}'
                    )
            row_id = str(uuid.uuid4())
            cursor.execute(
                f'INSERT INTO {table_name} '
                f'({SQLExecutor.quote_identifier("id")}, '
                f'{SQLExecutor.quote_identifier("title")}, '
                f'{SQLExecutor.quote_identifier("thickness")}) '
                f'VALUES (%s, %s, %s)',
                [row_id, 'Migrate panel', '3.50'],
            )

        output = io.StringIO()
        call_command('migrate_structure_decimal_ranges', stdout=output)

        for column_name in (
            'thickness',
            'thickness__kind',
            'thickness__b',
        ):
            self.assertTrue(SQLExecutor.column_exists(self.structure_type, column_name))
        record = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(record['thickness__kind'], 'scalar')
        self.assertEqual(str(record['thickness']), '3.50')
        self.assertIn('Готово', output.getvalue())

    def test_structure_record_form_saves_decimal_range(self):
        create_url = reverse('structures:create', args=[self.structure_type.code])
        post_data = {
            self._field_name('title'): 'Range form panel',
            **self._decimal_post_data(
                'thickness',
                min_value='1.25',
                max_value='3.25',
                is_range=True,
            ),
        }
        response = self.client.post(create_url, post_data)
        self.assertEqual(response.status_code, 302)

        records = SQLExecutor.get_structure_instances(self.structure_type)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record['thickness__kind'], 'range')
        self.assertEqual(str(record['thickness']), '1.25')
        self.assertEqual(str(record['thickness__b']), '3.25')

        detail_response = self.client.get(
            reverse('structures:detail', args=[self.structure_type.code, record['id']])
        )
        self.assertContains(detail_response, '1,25')
        self.assertContains(detail_response, '3,25')
