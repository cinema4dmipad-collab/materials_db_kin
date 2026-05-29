import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django import forms
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.composites.models import CompositeLayer
from apps.materials.admin import CompositeLayerInline, MaterialAdmin, MaterialForm
from apps.materials.forms import CompositeLayerFormSet, MaterialForm as PublicMaterialForm
from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property, PropertyGroup
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor

urlpatterns = []


class MaterialStructureLinkTests(TransactionTestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Test Panel',
            code='material_panel',
            table_name='structures_material_panel',
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
        self.skin_material_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='skin_material',
            label='Skin material',
            field_type='MaterialLink',
            sort_order=3,
        )
        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))
        self.created_structure_types = [self.structure_type]

    def tearDown(self):
        for structure_type in reversed(self.created_structure_types):
            SQLExecutor.drop_table(structure_type)

    def create_structure_type(self, name='Second Panel', code='second_panel', table_name='structures_second_panel'):
        structure_type = StructureType.objects.create(
            name=name,
            code=code,
            table_name=table_name,
        )
        StructureField.objects.create(
            structure_type=structure_type,
            name='title',
            label='Title',
            field_type='CharField',
            is_required=True,
            sort_order=1,
        )
        StructureField.objects.create(
            structure_type=structure_type,
            name='thickness',
            label='Thickness',
            field_type='DecimalField',
            max_digits=8,
            decimal_places=2,
            sort_order=2,
        )
        create_result = SQLExecutor.create_table(structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))
        self.created_structure_types.append(structure_type)
        return structure_type

    def structure_field_data(self, structure_type, **overrides):
        data = {
            'title': 'Public panel',
            'thickness': '12.50',
            'skin_material': '',
        }
        data.update(overrides)
        return {
            f'structure_field_{field.pk}': data[field.name]
            for field in structure_type.fields.exclude(field_type='ForeignKey')
        }

    def insert_structure_row(self, **overrides):
        data = {'title': 'Panel A', 'thickness': '12.50', 'skin_material': ''}
        data.update(overrides)
        result = SQLExecutor.insert(self.structure_type, data)
        self.assertTrue(result['success'], result.get('error'))
        return result['id']

    def test_get_structure_params_returns_dynamic_row(self):
        row_id = self.insert_structure_row(title='Laminate')
        material = Material.objects.create(
            code='MAT-001',
            name='Material with structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        params = material.get_structure_params()

        self.assertIsNotNone(params)
        self.assertEqual(str(params['id']), row_id)
        self.assertEqual(params['title'], 'Laminate')

    def test_get_structure_params_returns_none_for_missing_link_or_row(self):
        material = Material.objects.create(code='MAT-002', name='Plain material')
        self.assertIsNone(material.get_structure_params())

        material.struct_type = self.structure_type
        material.struct_props_id = uuid.uuid4()
        self.assertIsNone(material.get_structure_params())

    def test_material_type_proxy_flags_reflect_structure_and_layers(self):
        plain_material = Material.objects.create(code='MAT-TYPE-001', name='Plain material')
        simple_material = Material(
            code='MAT-TYPE-002',
            name='Simple material',
            struct_type=self.structure_type,
        )
        composite_material = Material.objects.create(
            code='MAT-TYPE-003',
            name='Composite material',
            struct_type=self.structure_type,
        )
        self.structure_type.allow_layers = True
        self.structure_type.save(update_fields=['allow_layers'])
        layer_material = Material.objects.create(
            code='MAT-TYPE-LAYER-001',
            name='Layer material',
        )
        CompositeLayer.objects.create(
            parent_material=composite_material,
            material=layer_material,
            layer_number=1,
            angle=45,
            thickness='0.25',
        )

        self.assertFalse(plain_material.is_composite)
        self.assertFalse(plain_material.is_simple)
        self.assertFalse(simple_material.is_composite)
        self.assertTrue(simple_material.is_simple)
        self.assertTrue(composite_material.is_composite)
        self.assertTrue(composite_material.is_simple)

    def test_clean_rejects_structure_row_without_type(self):
        material = Material(
            code='MAT-003',
            name='Broken material',
            struct_props_id=uuid.uuid4(),
        )

        with self.assertRaises(ValidationError) as ctx:
            material.full_clean()

        self.assertIn('struct_type', ctx.exception.message_dict)

    def test_clean_rejects_missing_dynamic_row(self):
        material = Material(
            code='MAT-004',
            name='Missing row material',
            struct_type=self.structure_type,
            struct_props_id=uuid.uuid4(),
        )

        with self.assertRaises(ValidationError) as ctx:
            material.full_clean()

        self.assertIn('struct_props_id', ctx.exception.message_dict)

    def test_clean_rejects_not_created_structure_type(self):
        structure_type = StructureType.objects.create(
            name='Draft Panel',
            code='draft_panel',
            table_name='structures_draft_panel',
        )
        material = Material(
            code='MAT-005',
            name='Draft row material',
            struct_type=structure_type,
            struct_props_id=uuid.uuid4(),
        )

        with self.assertRaises(ValidationError) as ctx:
            material.full_clean()

        self.assertIn('struct_type', ctx.exception.message_dict)

    def test_sql_executor_structure_instance_helpers(self):
        row_id = self.insert_structure_row(title='Helper row')

        rows = SQLExecutor.get_structure_instances(self.structure_type)
        row = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        missing = SQLExecutor.get_structure_instance(self.structure_type, uuid.uuid4())

        self.assertEqual([str(record['id']) for record in rows], [row_id])
        self.assertEqual(row['title'], 'Helper row')
        self.assertIsNone(missing)

    def test_sql_executor_structure_instances_no_arg_returns_more_than_default_page(self):
        for index in range(105):
            self.insert_structure_row(title=f'Helper row {index:03d}')

        rows = SQLExecutor.get_structure_instances(self.structure_type)

        self.assertEqual(len(rows), 105)

    def test_sql_executor_structure_helpers_return_empty_for_not_created_type(self):
        structure_type = StructureType.objects.create(
            name='Draft Helpers',
            code='draft_helpers',
            table_name='structures_draft_helpers',
        )

        self.assertEqual(SQLExecutor.get_structure_instances(structure_type), [])
        self.assertIsNone(SQLExecutor.get_structure_instance(structure_type, uuid.uuid4()))

    def test_detail_page_shows_material_and_linked_structure_properties(self):
        density_group = PropertyGroup.objects.create(
            name='Physical properties',
            sort_order=1,
        )
        density = Property.objects.create(
            name='density_detail',
            display_name='Density',
            unit='g/cm3',
            group=density_group,
        )
        row_id = self.insert_structure_row(title='Laminate panel', thickness='18.75')
        material = Material.objects.create(
            code='MAT-DETAIL-001',
            name='Detailed material',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        MaterialProperty.objects.create(material=material, property=density, value='1.55')

        response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Свойства')
        self.assertContains(response, 'Density')
        self.assertContains(response, '1.55')
        self.assertContains(response, 'g/cm3')
        self.assertContains(response, 'Параметры структуры')
        self.assertContains(response, 'Test Panel')
        self.assertContains(response, 'Title')
        self.assertContains(response, 'Laminate panel')
        self.assertContains(response, 'Thickness')
        self.assertContains(response, '18,75')

    def test_detail_page_ignores_service_columns_and_stale_foreign_key_fields(self):
        row_id = self.insert_structure_row(title='Visible panel')
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO structures_structurefield
                    (structure_type_id, name, label, field_type, is_required, default_value,
                     help_text, sort_order, max_digits, decimal_places, max_length,
                     foreign_key_model)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    self.structure_type.pk,
                    'legacy_parent',
                    'Legacy parent',
                    'ForeignKey',
                    False,
                    '',
                    '',
                    3,
                    10,
                    2,
                    255,
                    'materials.Material',
                ],
            )
        material = Material.objects.create(
            code='MAT-DETAIL-002',
            name='Detail ignores stale fields',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Title')
        self.assertNotContains(response, 'Legacy parent')
        self.assertNotContains(response, '<td>id</td>', html=True)
        self.assertNotContains(response, '<td>created_at</td>', html=True)
        self.assertNotContains(response, '<td>updated_at</td>', html=True)
        self.assertNotContains(response, '<td>created_by</td>', html=True)

    def test_detail_page_without_linked_structure_shows_empty_state(self):
        material = Material.objects.create(code='MAT-DETAIL-003', name='Plain detail material')

        response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Параметры структуры')
        self.assertContains(response, 'Структура не выбрана.')

    def test_detail_page_missing_structure_row_shows_helpful_message(self):
        material = Material.objects.create(
            code='MAT-DETAIL-004',
            name='Missing row detail material',
            struct_type=self.structure_type,
            struct_props_id=uuid.uuid4(),
        )

        response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Запись параметров структуры не найдена.')

    def test_detail_page_shows_zero_structure_values(self):
        row_id = self.insert_structure_row(title='Zero thickness panel', thickness='0.00')
        material = Material.objects.create(
            code='MAT-DETAIL-005',
            name='Zero value detail material',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<td>0,00</td>', html=True)

    def test_material_list_displays_structure_type(self):
        Material.objects.create(code='MAT-LIST-001', name='Plain material')
        Material.objects.create(
            code='MAT-LIST-002',
            name='Structured material',
            struct_type=self.structure_type,
        )

        response = self.client.get(reverse('materials:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Тип структуры')
        self.assertContains(response, 'Test Panel')
        self.assertContains(response, 'MAT-LIST-001')
        self.assertContains(response, 'MAT-LIST-002')


class MaterialAdminStructureLinkTests(MaterialStructureLinkTests):
    def test_material_admin_uses_composite_layer_inline_without_material_type_column(self):
        inline = CompositeLayerInline(Material, AdminSite())
        material = Material.objects.create(
            code='MAT-ADMIN-LAYERS-001',
            name='Material with layers',
            struct_type=self.structure_type,
        )
        self.structure_type.allow_layers = True
        self.structure_type.save(update_fields=['allow_layers'])
        admin_model = MaterialAdmin(Material, AdminSite())
        request = RequestFactory().get('/')

        self.assertNotIn('material_type', MaterialAdmin.list_display)
        self.assertFalse(hasattr(MaterialAdmin, 'material_type'))
        self.assertNotIn(CompositeLayerInline, MaterialAdmin.inlines)
        self.assertIn(
            CompositeLayerInline,
            admin_model.get_inlines(request, material),
        )
        self.assertEqual(inline.fk_name, 'parent_material')
        self.assertEqual(
            list(inline.fields),
            ['layer_number', 'material', 'angle', 'thickness'],
        )
        self.assertEqual(inline.extra, 0)
        self.assertEqual(inline.formset, CompositeLayerFormSet)

    def test_material_form_populates_structure_instance_choices(self):
        row_id = self.insert_structure_row(title='Visible row')

        form = MaterialForm(data={'struct_type': str(self.structure_type.pk)})
        props_field = form.fields['struct_props_id']

        choices = list(props_field.widget.choices)
        self.assertIn((str(row_id), 'Visible row'), choices)
        self.assertEqual(
            props_field.widget.attrs['data-load-url'],
            reverse('admin:materials_material_load_structure_instances'),
        )

    def test_material_form_existing_instance_includes_selected_row_outside_first_page(self):
        selected_row_id = self.insert_structure_row(title='Selected row')
        for index in range(105):
            self.insert_structure_row(title=f'Visible row {index:03d}')
        material = Material.objects.create(
            code='MAT-006',
            name='Material with selected structure',
            struct_type=self.structure_type,
            struct_props_id=selected_row_id,
        )

        form = MaterialForm(instance=material)

        choices = list(form.fields['struct_props_id'].widget.choices)
        self.assertIn((str(selected_row_id), 'Selected row'), choices)

    def test_material_form_rejects_missing_dynamic_row(self):
        form = MaterialForm(
            data={
                'code': 'MAT-007',
                'name': 'Invalid material',
                'struct_type': str(self.structure_type.pk),
                'struct_props_id': str(uuid.uuid4()),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('struct_props_id', form.errors)

    def test_admin_ajax_returns_structure_instances(self):
        row_id = self.insert_structure_row(title='Ajax row')
        admin_model = MaterialAdmin(Material, AdminSite())
        request = RequestFactory().get(
            '/',
            {'structure_type_id': str(self.structure_type.pk)},
        )
        request.user = get_user_model().objects.create_superuser(
            username='material-admin',
            password='password',
        )

        response = admin_model.load_structure_instances(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {'instances': [{'id': str(row_id), 'name': 'Ajax row'}]},
        )

    def test_admin_ajax_wrapped_url_denies_staff_without_material_permissions(self):
        user = get_user_model().objects.create_user(
            username='staff-without-material-perms',
            password='password',
            is_staff=True,
        )
        self.client.force_login(user)
        url = reverse('admin:materials_material_load_structure_instances')

        response = self.client.get(url, {'structure_type_id': str(self.structure_type.pk)})

        self.assertEqual(response.status_code, 403)


class PublicMaterialFormStructureLinkTests(MaterialStructureLinkTests):
    def setUp(self):
        super().setUp()
        self.structure_type.allow_layers = True
        self.structure_type.save(update_fields=['allow_layers'])

    def _formset_management_data(self):
        return {
            'properties-TOTAL_FORMS': '0',
            'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
        }

    def _layer_formset_management_data(self, total='1', initial='0'):
        return {
            'layers-TOTAL_FORMS': total,
            'layers-INITIAL_FORMS': initial,
            'layers-MIN_NUM_FORMS': '0',
            'layers-MAX_NUM_FORMS': '1000',
        }

    def _layer_formset_data(self, material, prefix='layers-0', **overrides):
        data = {
            f'{prefix}-layer_number': '1',
            f'{prefix}-material': str(material.pk),
            f'{prefix}-angle': '45',
            f'{prefix}-thickness': '0.25',
        }
        data.update(overrides)
        return data

    def _property_formset_management_data(self, total='1', initial='0'):
        return {
            'properties-TOTAL_FORMS': total,
            'properties-INITIAL_FORMS': initial,
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
        }

    def _property_formset_data(self, property_obj, prefix='properties-0', **overrides):
        data = {
            f'{prefix}-property': str(property_obj.pk),
            f'{prefix}-value': '1.55',
        }
        data.update(overrides)
        return data

    def _post_data(self, **overrides):
        data = {
            'code': 'MAT-PUBLIC-001',
            'name': 'Public material',
            'description': 'Created from public form',
            'struct_type': str(self.structure_type.pk),
            'created_by': 'tester',
        }
        data.update(self.structure_field_data(self.structure_type))
        data.update(self._formset_management_data())
        data.update(self._layer_formset_management_data(total='0'))
        data.update(overrides)
        return data

    def test_public_material_form_includes_structure_fields_not_props_id(self):
        form = PublicMaterialForm(data={'struct_type': str(self.structure_type.pk)})

        self.assertIn('struct_type', form.fields)
        self.assertNotIn('struct_props_id', form.fields)
        self.assertIn('structure_field_{}'.format(self.structure_type.fields.get(name='title').pk), form.fields)
        self.assertIn(
            'structure_field_{}'.format(self.structure_type.fields.get(name='thickness').pk),
            form.fields,
        )
        self.assertEqual(
            form.fields['structure_field_{}'.format(self.structure_type.fields.get(name='title').pk)].label,
            'Title',
        )
        self.assertEqual(
            form.fields[
                'structure_field_{}'.format(self.structure_type.fields.get(name='thickness').pk)
            ].label,
            'Thickness',
        )
        material_field = form.fields[f'structure_field_{self.skin_material_field.pk}']
        self.assertIsInstance(material_field, forms.ModelChoiceField)
        self.assertEqual(list(material_field.queryset), list(Material.objects.order_by('code')))
        self.assertFalse(material_field.required)

    @override_settings(ROOT_URLCONF='apps.materials.tests')
    def test_public_material_form_renders_without_admin_url_namespace(self):
        form = PublicMaterialForm()

        rendered = form.as_p()

        self.assertNotIn('name="struct_props_id"', rendered)
        self.assertNotIn('data-load-url', rendered)

    def test_public_material_create_view_saves_dynamic_row_and_detail_shows_values(self):
        linked_material = Material.objects.create(
            code='MAT-LINKED-001',
            name='Linked material',
        )
        response = self.client.post(
            reverse('materials:create'),
            self._post_data(**{f'structure_field_{self.skin_material_field.pk}': str(linked_material.pk)}),
        )

        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        self.assertEqual(material.struct_type, self.structure_type)
        self.assertIsNotNone(material.struct_props_id)
        params = material.get_structure_params()
        self.assertEqual(params['title'], 'Public panel')
        self.assertEqual(str(params['thickness']), '12.50')
        self.assertEqual(str(params['skin_material']), str(linked_material.pk))

        detail_response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))
        self.assertContains(detail_response, 'Title')
        self.assertContains(detail_response, 'Public panel')
        self.assertContains(detail_response, 'Thickness')
        self.assertContains(detail_response, '12,50')
        self.assertContains(detail_response, 'Skin material')
        self.assertContains(detail_response, 'MAT-LINKED-001 - Linked material')

    def test_public_material_create_view_saves_property_formset(self):
        density = Property.objects.create(
            name='density_create',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )

        response = self.client.post(
            reverse('materials:create'),
            self._post_data(
                **self._property_formset_management_data(),
                **self._property_formset_data(density),
            ),
        )

        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        link = MaterialProperty.objects.get(material=material, property=density)
        self.assertEqual(link.value, '1.55')

    def test_public_material_update_view_saves_new_property(self):
        density = Property.objects.create(
            name='density_update',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-PROP-001',
            name='Public material without properties',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-PROP-001',
                name='Public material without properties',
                **self._property_formset_management_data(),
                **self._property_formset_data(density, **{'properties-0-value': '2.10'}),
            ),
        )

        self.assertEqual(response.status_code, 302)
        link = MaterialProperty.objects.get(material=material, property=density)
        self.assertEqual(link.value, '2.10')

    def test_public_material_create_view_saves_layer_formset_and_detail_shows_layers(self):
        layer_material = Material.objects.create(
            code='MAT-LAYER-001',
            name='Layer material',
        )

        response = self.client.post(
            reverse('materials:create'),
            self._post_data(
                **self._layer_formset_management_data(),
                **self._layer_formset_data(layer_material),
            ),
        )

        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        layer = CompositeLayer.objects.get(parent_material=material)
        self.assertEqual(layer.layer_number, 1)
        self.assertEqual(layer.material, layer_material)
        self.assertEqual(layer.angle, 45)
        self.assertEqual(str(layer.thickness), '0.25')

        detail_response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))
        self.assertContains(detail_response, 'Слои')
        self.assertContains(detail_response, 'composite-layer-diagram')
        self.assertContains(detail_response, 'Схема укладки')
        self.assertContains(detail_response, 'composite-thickness-summary')
        self.assertContains(detail_response, 'Σt =')
        self.assertContains(detail_response, 'layer-stack-column')
        self.assertContains(detail_response, 'layer-material-legend')
        self.assertContains(detail_response, 'flex:')
        self.assertContains(detail_response, 'background-color:')
        self.assertContains(detail_response, 'composite_layer_diagram.css')
        self.assertContains(detail_response, 'MAT-LAYER-001 - Layer material')
        self.assertContains(detail_response, '45')
        self.assertContains(detail_response, '0,25')

    def test_public_material_create_view_auto_numbers_multiple_layers(self):
        first_layer_material = Material.objects.create(
            code='MAT-LAYER-AUTO-001',
            name='First layer material',
        )
        second_layer_material = Material.objects.create(
            code='MAT-LAYER-AUTO-002',
            name='Second layer material',
        )

        response = self.client.post(
            reverse('materials:create'),
            self._post_data(
                **self._layer_formset_management_data(total='2'),
                **self._layer_formset_data(
                    first_layer_material,
                    prefix='layers-0',
                    **{'layers-0-layer_number': ''},
                ),
                **self._layer_formset_data(
                    second_layer_material,
                    prefix='layers-1',
                    **{
                        'layers-1-layer_number': '',
                        'layers-1-angle': '90',
                        'layers-1-thickness': '0.50',
                    },
                ),
            ),
        )

        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        layers = list(
            CompositeLayer.objects.filter(parent_material=material).order_by('layer_number')
        )
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[0].layer_number, 1)
        self.assertEqual(layers[0].material, first_layer_material)
        self.assertEqual(layers[1].layer_number, 2)
        self.assertEqual(layers[1].material, second_layer_material)

    def test_public_material_create_view_hides_layers_when_structure_type_disallows(self):
        self.structure_type.allow_layers = False
        self.structure_type.save(update_fields=['allow_layers'])
        layer_material = Material.objects.create(
            code='MAT-LAYER-HIDDEN-001',
            name='Layer material',
        )

        create_response = self.client.get(
            reverse('materials:create'),
            {'struct_type': str(self.structure_type.pk)},
        )
        self.assertNotContains(create_response, 'Добавить слой')

        post_response = self.client.post(
            reverse('materials:create'),
            self._post_data(
                **self._layer_formset_management_data(),
                **self._layer_formset_data(layer_material),
            ),
        )

        self.assertEqual(post_response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        self.assertFalse(material.supports_layers)
        self.assertFalse(CompositeLayer.objects.filter(parent_material=material).exists())

        with self.assertRaises(ValidationError):
            CompositeLayer.objects.create(
                parent_material=material,
                material=layer_material,
                layer_number=1,
                angle=45,
                thickness=0.25,
            )

    def test_public_material_update_prefills_and_updates_existing_dynamic_row(self):
        row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        linked_material = Material.objects.create(
            code='MAT-LINKED-002',
            name='Prefilled material',
        )
        SQLExecutor.update(
            self.structure_type,
            row_id,
            {'skin_material': linked_material.pk},
        )
        material = Material.objects.create(
            code='MAT-PUBLIC-002',
            name='Public material with existing structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        form = PublicMaterialForm(instance=material)
        title_field = self.structure_type.fields.get(name='title')
        thickness_field = self.structure_type.fields.get(name='thickness')

        self.assertEqual(form.fields[f'structure_field_{title_field.pk}'].initial, 'Original panel')
        self.assertEqual(str(form.fields[f'structure_field_{thickness_field.pk}'].initial), '8.25')
        self.assertEqual(
            form.fields[f'structure_field_{self.skin_material_field.pk}'].initial,
            linked_material,
        )

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-002',
                name='Updated public material',
                **{
                    f'structure_field_{title_field.pk}': 'Updated panel',
                    f'structure_field_{thickness_field.pk}': '9.75',
                },
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        self.assertEqual(str(material.struct_props_id), row_id)
        params = material.get_structure_params()
        self.assertEqual(params['title'], 'Updated panel')
        self.assertEqual(str(params['thickness']), '9.75')

    def test_public_material_update_view_saves_layer_formset(self):
        row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        original_layer_material = Material.objects.create(
            code='MAT-LAYER-ORIGINAL-001',
            name='Original layer material',
        )
        updated_layer_material = Material.objects.create(
            code='MAT-LAYER-UPDATED-001',
            name='Updated layer material',
        )
        material = Material.objects.create(
            code='MAT-PUBLIC-LAYER-001',
            name='Public material with layers',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        layer = CompositeLayer.objects.create(
            parent_material=material,
            material=original_layer_material,
            layer_number=1,
            angle=0,
            thickness='0.10',
        )

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-LAYER-001',
                name='Updated public material with layers',
                **self._layer_formset_management_data(initial='1'),
                **self._layer_formset_data(
                    updated_layer_material,
                    **{
                        'layers-0-id': str(layer.pk),
                        'layers-0-angle': '90',
                        'layers-0-thickness': '0.50',
                    },
                ),
            ),
        )

        self.assertEqual(response.status_code, 302)
        layer.refresh_from_db()
        self.assertEqual(layer.material, updated_layer_material)
        self.assertEqual(layer.angle, 90)
        self.assertEqual(layer.thickness, 0.5)

    def test_public_material_update_shared_row_creates_new_dynamic_row(self):
        row_id = self.insert_structure_row(title='Shared panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-001',
            name='Public material with shared structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        other_material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-002',
            name='Other material with shared structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        title_field = self.structure_type.fields.get(name='title')
        thickness_field = self.structure_type.fields.get(name='thickness')

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-SHARED-001',
                name='Edited shared public material',
                **{
                    f'structure_field_{title_field.pk}': 'Edited panel',
                    f'structure_field_{thickness_field.pk}': '9.75',
                },
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        other_material.refresh_from_db()
        self.assertNotEqual(str(material.struct_props_id), row_id)
        self.assertEqual(str(other_material.struct_props_id), row_id)

        old_params = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertEqual(old_params['title'], 'Shared panel')
        self.assertEqual(str(old_params['thickness']), '8.25')

        new_params = material.get_structure_params()
        self.assertEqual(new_params['title'], 'Edited panel')
        self.assertEqual(str(new_params['thickness']), '9.75')

    def test_public_material_update_can_clear_structure_and_deletes_dynamic_row(self):
        row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-003',
            name='Public material with clearable structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-003',
                name='Public material without structure',
                struct_type='',
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        self.assertIsNone(material.struct_type)
        self.assertIsNone(material.struct_props_id)
        self.assertIsNone(SQLExecutor.get_structure_instance(self.structure_type, row_id))

    def test_public_material_update_clear_shared_row_keeps_old_dynamic_row(self):
        row_id = self.insert_structure_row(title='Shared panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-003',
            name='Public material with clearable shared structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        other_material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-004',
            name='Other material with clearable shared structure',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-SHARED-003',
                name='Public material without shared structure',
                struct_type='',
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        other_material.refresh_from_db()
        self.assertIsNone(material.struct_type)
        self.assertIsNone(material.struct_props_id)
        self.assertEqual(str(other_material.struct_props_id), row_id)

        old_params = SQLExecutor.get_structure_instance(self.structure_type, row_id)
        self.assertIsNotNone(old_params)
        self.assertEqual(old_params['title'], 'Shared panel')

    def test_public_material_update_can_change_structure_and_deletes_old_dynamic_row(self):
        old_row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-004',
            name='Public material with replaceable structure',
            struct_type=self.structure_type,
            struct_props_id=old_row_id,
        )
        new_structure_type = self.create_structure_type()

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-004',
                name='Public material with second structure',
                struct_type=str(new_structure_type.pk),
                **self.structure_field_data(
                    new_structure_type,
                    title='Replacement panel',
                    thickness='3.50',
                ),
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        self.assertEqual(material.struct_type, new_structure_type)
        self.assertIsNotNone(material.struct_props_id)
        self.assertIsNone(SQLExecutor.get_structure_instance(self.structure_type, old_row_id))
        params = material.get_structure_params()
        self.assertEqual(params['title'], 'Replacement panel')
        self.assertEqual(str(params['thickness']), '3.50')

    def test_public_material_update_change_shared_row_keeps_old_dynamic_row(self):
        old_row_id = self.insert_structure_row(title='Shared panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-005',
            name='Public material with replaceable shared structure',
            struct_type=self.structure_type,
            struct_props_id=old_row_id,
        )
        other_material = Material.objects.create(
            code='MAT-PUBLIC-SHARED-006',
            name='Other material with replaceable shared structure',
            struct_type=self.structure_type,
            struct_props_id=old_row_id,
        )
        new_structure_type = self.create_structure_type()

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-SHARED-005',
                name='Public material with replacement shared structure',
                struct_type=str(new_structure_type.pk),
                **self.structure_field_data(
                    new_structure_type,
                    title='Replacement panel',
                    thickness='3.50',
                ),
            ),
        )

        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        other_material.refresh_from_db()
        self.assertEqual(material.struct_type, new_structure_type)
        self.assertIsNotNone(material.struct_props_id)
        self.assertEqual(str(other_material.struct_props_id), old_row_id)

        old_params = SQLExecutor.get_structure_instance(self.structure_type, old_row_id)
        self.assertIsNotNone(old_params)
        self.assertEqual(old_params['title'], 'Shared panel')

        params = material.get_structure_params()
        self.assertEqual(params['title'], 'Replacement panel')
        self.assertEqual(str(params['thickness']), '3.50')

    def test_public_material_create_requires_dynamic_required_fields(self):
        response = self.client.post(
            reverse('materials:create'),
            self._post_data(**self.structure_field_data(self.structure_type, title='')),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Material.objects.filter(code='MAT-PUBLIC-001').exists())
        self.assertContains(response, 'Обязательное поле.')

    def test_public_material_create_persists_and_displays_zero_decimal_value(self):
        response = self.client.post(
            reverse('materials:create'),
            self._post_data(**self.structure_field_data(self.structure_type, thickness='0.00')),
        )

        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='MAT-PUBLIC-001')
        params = material.get_structure_params()
        self.assertEqual(str(params['thickness']), '0.00')

        detail_response = self.client.get(reverse('materials:detail', kwargs={'pk': material.pk}))
        self.assertContains(detail_response, '<td>0,00</td>', html=True)

    def test_public_material_update_missing_existing_dynamic_row_returns_form_error(self):
        row_id = self.insert_structure_row(title='Original panel', thickness='8.25')
        material = Material.objects.create(
            code='MAT-PUBLIC-005',
            name='Public material with missing dynamic row',
            struct_type=self.structure_type,
            struct_props_id=row_id,
        )
        delete_result = SQLExecutor.delete(self.structure_type, row_id)
        self.assertTrue(delete_result['success'], delete_result.get('error'))

        response = self.client.post(
            reverse('materials:edit', kwargs={'pk': material.pk}),
            self._post_data(
                code='MAT-PUBLIC-005',
                name='Public material with missing dynamic row',
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Запись параметров структуры не найдена.')
        material.refresh_from_db()
        self.assertEqual(material.struct_type, self.structure_type)
        self.assertEqual(str(material.struct_props_id), row_id)

    def test_public_material_form_without_structure_type_has_empty_state(self):
        form = PublicMaterialForm()

        self.assertFalse(form.structure_bound_fields)
        self.assertEqual(form.structure_empty_message, 'Выберите тип структуры, чтобы заполнить параметры.')

        response = self.client.get(reverse('materials:create'))

        self.assertContains(response, 'Выберите тип структуры, чтобы заполнить параметры.')


class SeedDataCommandTests(TestCase):
    def call_seed_data(self):
        output = StringIO()
        call_command('seed_data', stdout=output)
        return output.getvalue()

    def test_seed_data_creates_base_composite_properties(self):
        output = self.call_seed_data()

        group = PropertyGroup.objects.get(name='Composite material properties')
        properties = {
            prop.name: prop
            for prop in Property.objects.filter(
                name__in=['density', 'tensile_strength', 'elastic_modulus']
            )
        }

        self.assertEqual(len(properties), 3)
        self.assertEqual(properties['density'].display_name, 'Density')
        self.assertEqual(properties['density'].unit, 'g/cm3')
        self.assertEqual(properties['tensile_strength'].unit, 'MPa')
        self.assertEqual(properties['elastic_modulus'].unit, 'GPa')
        self.assertTrue(all(prop.group == group for prop in properties.values()))
        self.assertIn('properties:', output)

    def test_seed_data_creates_realistic_composite_materials_and_links(self):
        self.call_seed_data()

        materials = Material.objects.filter(code__startswith='CMP-')
        links = MaterialProperty.objects.filter(material__code__startswith='CMP-')

        self.assertEqual(materials.count(), 12)
        self.assertEqual(links.count(), 36)
        self.assertTrue(materials.filter(code='CMP-CFRP-T700-EP').exists())
        self.assertTrue(materials.filter(code='CMP-CFRP-M40J-EP').exists())
        self.assertTrue(materials.filter(code='CMP-CFRP-HS-EP').exists())
        self.assertTrue(materials.filter(code='CMP-GFRP-EGLASS-EP').exists())
        self.assertTrue(materials.filter(code='CMP-GFRP-SGLASS-EP').exists())
        self.assertTrue(materials.filter(code='CMP-AFRP-KEVLAR-EP').exists())
        self.assertTrue(materials.filter(code='CMP-BFRP-BASALT-EP').exists())

    def test_seed_data_uses_representative_values(self):
        self.call_seed_data()

        t700 = Material.objects.get(code='CMP-CFRP-T700-EP')
        m40j = Material.objects.get(code='CMP-CFRP-M40J-EP')
        e_glass = Material.objects.get(code='CMP-GFRP-EGLASS-EP')
        kevlar = Material.objects.get(code='CMP-AFRP-KEVLAR-EP')

        self.assertEqual(t700.properties.get(property__name='density').value, '1.55')
        self.assertEqual(t700.properties.get(property__name='tensile_strength').value, '2550')
        self.assertEqual(m40j.properties.get(property__name='elastic_modulus').value, '230')
        self.assertEqual(e_glass.properties.get(property__name='density').value, '1.95')
        self.assertEqual(kevlar.properties.get(property__name='tensile_strength').value, '1400')

    def test_seed_data_is_idempotent(self):
        first_output = self.call_seed_data()
        counts_after_first_run = (
            PropertyGroup.objects.count(),
            Property.objects.count(),
            Material.objects.count(),
            MaterialProperty.objects.count(),
        )

        second_output = self.call_seed_data()
        counts_after_second_run = (
            PropertyGroup.objects.count(),
            Property.objects.count(),
            Material.objects.count(),
            MaterialProperty.objects.count(),
        )

        self.assertEqual(counts_after_first_run, counts_after_second_run)
        self.assertIn('materials: created 12, updated 0', first_output)
        self.assertIn('materials: created 0, updated 12', second_output)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class MaterialAttachmentViewsTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile

        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.material = Material.objects.create(code='MAT-ATT-001', name='Attachment material')

    def tearDown(self):
        import shutil

        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_material_detail_shows_files_and_samples_tabs(self):
        response = self.client.get(reverse('materials:detail', kwargs={'pk': self.material.pk}))
        self.assertContains(response, 'Файлы')
        self.assertContains(response, 'Образцы')
        self.assertContains(response, reverse('material_attachments:list', kwargs={'material_pk': self.material.pk}))
        self.assertContains(response, reverse('material_samples:list', kwargs={'material_pk': self.material.pk}))

    def test_material_samples_tab_lists_samples(self):
        from apps.samples.models import Sample

        sample = Sample.objects.create(
            material=self.material,
            code='SMP-001',
            name='Test sample',
            object_type='plate',
        )
        samples_url = reverse('material_samples:list', kwargs={'material_pk': self.material.pk})
        response = self.client.get(samples_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sample.code)
        self.assertContains(response, reverse('samples:create'))

    def test_attach_file_on_material_attachments_tab(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.materials.models import MaterialAttachment

        attachments_url = reverse('material_attachments:list', kwargs={'material_pk': self.material.pk})
        get_response = self.client.get(attachments_url)
        self.assertContains(get_response, 'Прикрепить файл')

        post_response = self.client.post(
            attachments_url,
            {
                'attachment-title': 'Datasheet',
                'attachment-file': SimpleUploadedFile(
                    'datasheet.pdf',
                    b'%PDF-1.4 test',
                    content_type='application/pdf',
                ),
            },
        )
        self.assertRedirects(post_response, attachments_url)
        attachment = MaterialAttachment.objects.get(title='Datasheet')
        self.assertEqual(attachment.material, self.material)
        self.assertTrue(attachment.file.storage.exists(attachment.file.name))

    def test_material_delete_removes_attachment_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.materials.models import MaterialAttachment

        attachment = MaterialAttachment.objects.create(
            material=self.material,
            title='To delete',
            file=SimpleUploadedFile('doc.txt', b'content', content_type='text/plain'),
        )
        file_name = attachment.file.name
        self.material.delete()
        self.assertFalse(MaterialAttachment.objects.filter(title='To delete').exists())
        self.assertFalse(attachment.file.storage.exists(file_name))
