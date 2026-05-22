import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.materials.admin import MaterialAdmin, MaterialForm
from apps.materials.forms import MaterialForm as PublicMaterialForm
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
        create_result = SQLExecutor.create_table(self.structure_type)
        self.assertTrue(create_result['success'], create_result.get('error'))

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def insert_structure_row(self, **overrides):
        data = {'title': 'Panel A', 'thickness': '12.50'}
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


class MaterialAdminStructureLinkTests(MaterialStructureLinkTests):
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
    def test_public_material_form_includes_structure_fields_and_choices(self):
        row_id = self.insert_structure_row(title='Public row')

        form = PublicMaterialForm(data={'struct_type': str(self.structure_type.pk)})
        props_field = form.fields['struct_props_id']

        self.assertIn('struct_type', form.fields)
        self.assertIn('struct_props_id', form.fields)
        self.assertIn((str(row_id), 'Public row'), list(props_field.widget.choices))
        self.assertNotIn('data-load-url', props_field.widget.attrs)

    @override_settings(ROOT_URLCONF='apps.materials.tests')
    def test_public_material_form_renders_without_admin_url_namespace(self):
        form = PublicMaterialForm()

        rendered = form.as_p()

        self.assertIn('name="struct_props_id"', rendered)
        self.assertNotIn('data-load-url', rendered)

    def test_public_material_form_uses_provided_structure_load_url(self):
        form = PublicMaterialForm(structure_load_url='/structures/load/')

        self.assertEqual(
            form.fields['struct_props_id'].widget.attrs['data-load-url'],
            '/structures/load/',
        )

    def test_public_material_form_existing_instance_includes_selected_row(self):
        selected_row_id = self.insert_structure_row(title='Selected public row')
        for index in range(105):
            self.insert_structure_row(title=f'Public row {index:03d}')
        material = Material.objects.create(
            code='MAT-008',
            name='Public material with selected structure',
            struct_type=self.structure_type,
            struct_props_id=selected_row_id,
        )

        form = PublicMaterialForm(instance=material)

        choices = list(form.fields['struct_props_id'].widget.choices)
        self.assertIn((str(selected_row_id), 'Selected public row'), choices)

    def test_public_material_form_validates_selected_dynamic_row(self):
        row_id = self.insert_structure_row(title='Valid public row')
        valid_form = PublicMaterialForm(
            data={
                'code': 'MAT-009',
                'name': 'Valid public material',
                'struct_type': str(self.structure_type.pk),
                'struct_props_id': str(row_id),
            }
        )
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

        invalid_form = PublicMaterialForm(
            data={
                'code': 'MAT-010',
                'name': 'Invalid public material',
                'struct_type': str(self.structure_type.pk),
                'struct_props_id': str(uuid.uuid4()),
            }
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn('struct_props_id', invalid_form.errors)


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
