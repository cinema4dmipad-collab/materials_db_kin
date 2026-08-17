import shutil

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import TestCase, override_settings

from django.urls import reverse

from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property
from apps.samples.forms import SamplePropertyFormSet
from apps.samples.models import Sample, SampleAttachment, SampleProperty

from apps.scans.models import ScanRecord

from apps.scans.test_utils import make_hdf5_upload
from apps.workspaces.services import ensure_legacy_workspace

_STORAGE_OVERRIDE = {

    'STORAGES': {

        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},

        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},

    },

}

@override_settings(**_STORAGE_OVERRIDE)

class SampleViewsTests(TestCase):

    def setUp(self):

        self.media_root = tempfile.mkdtemp()

        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)

        self.settings_override.enable()

        self.legacy_workspace = ensure_legacy_workspace()
        self.material = Material.objects.create(
            code='MAT-SMP-UI',
            name='UI material',
            home_workspace=self.legacy_workspace,
        )

        self.sample = Sample.objects.create(
            code='SMP-UI-001',
            name='UI sample',
            material=self.material,
            object_type='test',
            workspace=self.legacy_workspace,
        )

    def _property_formset_management_data(self, total='0', initial='0'):
        return {
            'properties-TOTAL_FORMS': total,
            'properties-INITIAL_FORMS': initial,
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
        }

    def _property_formset_data(self, property_obj, prefix='properties-0', **overrides):
        data = {
            f'{prefix}-property': str(property_obj.pk),
            f'{prefix}-value_kind': 'scalar',
            f'{prefix}-value': '1.55',
            f'{prefix}-value_min': '',
            f'{prefix}-value_max': '',
            f'{prefix}-value_tolerance': '',
        }
        data.update(overrides)
        return data

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_sample_crud_views(self):

        list_response = self.client.get(reverse('samples:list'))

        self.assertContains(list_response, 'SMP-UI-001')
        self.assertContains(list_response, 'type-pill-link')
        self.assertContains(list_response, 'Испытательный')

        create_response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-UI-002',
                'name': 'Second sample',
                'material': self.material.pk,
                'object_type': 'control',
                'created_by': 'tester',
                **self._property_formset_management_data(),
            },
        )

        self.assertEqual(create_response.status_code, 302)

        self.assertTrue(Sample.objects.filter(code='SMP-UI-002').exists())

    def test_sample_description_on_form_detail_and_search(self):
        form_page = self.client.get(reverse('samples:create'))
        self.assertContains(form_page, 'Описание')

        create_response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-UI-DESC',
                'name': 'Described sample',
                'description': 'Заготовка для УЗК',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_formset_management_data(),
            },
        )
        self.assertEqual(create_response.status_code, 302)
        sample = Sample.objects.get(code='SMP-UI-DESC')
        self.assertEqual(sample.description, 'Заготовка для УЗК')

        detail = self.client.get(reverse('samples:detail', kwargs={'pk': sample.pk}))
        self.assertContains(detail, 'Заготовка для УЗК')

        listed = self.client.get(
            reverse('samples:list'),
            {'q': 'УЗК', 'q_in': 'description'},
        )
        self.assertContains(listed, 'SMP-UI-DESC')
        missed = self.client.get(
            reverse('samples:list'),
            {'q': 'нет-такого-описания', 'q_in': 'description'},
        )
        self.assertNotContains(missed, 'SMP-UI-DESC')

    def test_sample_bulk_delete(self):
        other = Sample.objects.create(
            code='SMP-UI-BULK',
            name='Bulk sample',
            material=self.material,
            object_type='test',
            workspace=self.legacy_workspace,
        )
        list_page = self.client.get(reverse('samples:list'))
        self.assertContains(list_page, 'data-list-bulk-toggle')
        self.assertContains(list_page, reverse('samples:bulk_delete'))

        confirm = self.client.post(
            reverse('samples:bulk_delete'),
            {'ids': [str(self.sample.pk), str(other.pk)]},
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, 'UI sample')
        self.assertContains(confirm, 'Bulk sample')

        done = self.client.post(
            reverse('samples:bulk_delete'),
            {
                'ids': [str(self.sample.pk), str(other.pk)],
                'confirm': '1',
            },
        )
        self.assertRedirects(done, reverse('samples:list'))
        self.assertFalse(Sample.objects.filter(pk=self.sample.pk).exists())
        self.assertFalse(Sample.objects.filter(pk=other.pk).exists())

    def test_sample_list_filters_by_object_type_search(self):
        Sample.objects.create(
            code='SMP-UI-CTRL',
            name='Control sample',
            material=self.material,
            object_type='control',
            workspace=self.legacy_workspace,
        )

        response = self.client.get(
            reverse('samples:list'),
            {'q': 'Испытательный', 'q_in': 'object_type'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SMP-UI-001')
        self.assertNotContains(response, 'SMP-UI-CTRL')
        self.assertContains(response, 'type-pill-link')
        self.assertContains(response, 'Испытательный')

    def test_sample_list_sorts_by_name(self):
        Sample.objects.create(
            code='SMP-SORT-Z',
            name='Zulu sample',
            material=self.material,
            object_type='test',
            workspace=self.legacy_workspace,
        )
        Sample.objects.create(
            code='SMP-SORT-A',
            name='Alpha sample',
            material=self.material,
            object_type='test',
            workspace=self.legacy_workspace,
        )

        list_url = reverse('samples:list')
        by_name = self.client.get(list_url, {'sort': 'name', 'dir': 'asc'})
        html = by_name.content.decode()
        self.assertLess(html.find('Alpha sample'), html.find('UI sample'))
        self.assertLess(html.find('UI sample'), html.find('Zulu sample'))
        self.assertContains(by_name, 'table-sort')

    def test_sample_detail_has_inline_tags_form(self):
        response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIn('tags_form', response.context)
        self.assertContains(response, 'entity-detail-tags-form')

    def test_sample_tags_update_view(self):
        response = self.client.post(
            reverse('samples:tags', kwargs={'pk': self.sample.pk}),
            {'tag_names': 'лаб, тип::тест'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(self.sample.tags.values_list('name', flat=True)),
            {'лаб', 'тип::тест'},
        )

    def test_sample_property_formset_save_directly(self):
        density = Property.objects.create(
            name='direct_density',
            display_name='Density',
            data_type='number',
        )
        formset = SamplePropertyFormSet(
            {
                'properties-TOTAL_FORMS': '1',
                'properties-INITIAL_FORMS': '0',
                'properties-MIN_NUM_FORMS': '0',
                'properties-MAX_NUM_FORMS': '1000',
                'properties-0-property': str(density.pk),
                'properties-0-value': '1.62',
            },
            instance=self.sample,
            prefix='properties',
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(
            SampleProperty.objects.get(sample=self.sample, property=density).value,
            '1.62',
        )

    def test_sample_create_form_renders_property_picker(self):
        Property.objects.create(
            name='picker_density',
            display_name='Picker density',
            data_type='number',
        )
        response = self.client.get(reverse('samples:create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Свойства из материала')
        self.assertContains(response, 'Дополнительные свойства')
        self.assertContains(response, 'reference-properties-modal')
        self.assertContains(response, 'reference-properties-data')
        self.assertContains(response, 'reference_properties_picker.js')
        self.assertContains(response, 'id="add-extra-property-btn"')
        self.assertContains(response, 'data-sample-material-select')
        self.assertContains(response, 'material-property-forms-container')
        self.assertContains(response, 'extra-property-forms-container')
        self.assertContains(response, 'reference-materials-modal')
        self.assertContains(response, 'reference-materials-scope-tabs')

    def test_sample_create_view_saves_property_formset(self):
        density = Property.objects.create(
            name='sample_density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=density,
            value='1.60',
        )

        response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-UI-PROP',
                'name': 'Sample with properties',
                'material': self.material.pk,
                'object_type': 'test',
                'created_by': 'tester',
                **self._property_formset_management_data(total='1'),
                **self._property_formset_data(density, **{'properties-0-value': '1.62'}),
            },
        )

        self.assertEqual(response.status_code, 302)
        sample = Sample.objects.get(code='SMP-UI-PROP')
        link = SampleProperty.objects.get(sample=sample, property=density)
        self.assertEqual(link.value, '1.62')

    def test_sample_create_shows_warning_for_property_missing_on_material(self):
        density = Property.objects.create(
            name='material_density',
            display_name='Density',
            data_type='number',
        )
        custom = Property.objects.create(
            name='custom_prop',
            display_name='Custom property',
            data_type='number',
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=density,
            value='1.60',
        )

        response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-UI-EXTRA',
                'name': 'Sample with extra property',
                'material': self.material.pk,
                'object_type': 'test',
                'created_by': 'tester',
                **self._property_formset_management_data(total='2'),
                **self._property_formset_data(density, prefix='properties-0'),
                **self._property_formset_data(
                    custom,
                    prefix='properties-1',
                    **{'properties-1-value': '42'},
                ),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in response.context['messages']]
        self.assertTrue(
            any('Custom property' in message and 'отсутствуют у материала' in message for message in messages),
            messages,
        )

    def test_material_properties_json_view(self):
        density = Property.objects.create(
            name='json_density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=density,
            value='1.55',
        )

        response = self.client.get(
            reverse('materials:properties_json', kwargs={'pk': self.material.pk}),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['properties']), 1)
        self.assertEqual(payload['properties'][0]['property_id'], str(density.pk))
        self.assertEqual(payload['properties'][0]['value'], '1,55')

    def test_sample_detail_shows_properties(self):
        density = Property.objects.create(
            name='detail_density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        MaterialProperty.objects.create(
            material=self.material,
            property=density,
            value='1.60',
        )
        SampleProperty.objects.create(
            sample=self.sample,
            property=density,
            value='2.10',
        )

        response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))

        self.assertContains(response, 'Свойства')
        self.assertContains(response, 'Из свойств материала')
        self.assertContains(response, 'Density')
        self.assertContains(response, 'g/cm3')
        self.assertContains(response, '2,10')
        self.assertNotContains(response, 'client_filter_bar')

    def test_attach_scan_on_sample_scans_tab(self):

        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})

        post_response = self.client.post(

            create_url,

            {

                'title': 'Inline scan',

                'description': 'Attached from scans tab',

                'method': 'immersion',

                'file': make_hdf5_upload('inline.h5'),

            },

        )

        scan = ScanRecord.objects.get(title='Inline scan')

        self.assertRedirects(
            post_response,
            reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),
        )

        self.assertEqual(scan.sample, self.sample)

    def test_create_sample_does_not_attach_scan_on_create_form(self):

        create_response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-WITH-SCAN',
                'name': 'Sample with scan',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_formset_management_data(),
                'scan-title': 'Create scan',

                'scan-method': 'echo',

                'scan-file': make_hdf5_upload('create.h5'),

            },

        )

        self.assertEqual(create_response.status_code, 302)

        sample = Sample.objects.get(code='SMP-WITH-SCAN')

        self.assertFalse(ScanRecord.objects.filter(sample=sample).exists())

    def test_create_sample_does_not_attach_file_on_create_form(self):

        create_response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-WITH-FILE',
                'name': 'Sample with file',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_formset_management_data(),
                'attachment-title': 'Report',

                'attachment-file': SimpleUploadedFile(

                    'report.pdf',

                    b'%PDF-1.4 test',

                    content_type='application/pdf',

                ),

            },

        )

        self.assertEqual(create_response.status_code, 302)

        sample = Sample.objects.get(code='SMP-WITH-FILE')

        self.assertFalse(SampleAttachment.objects.filter(sample=sample).exists())

    def test_attachments_tab(self):

        attachments_url = reverse('attachments:list', kwargs={'sample_pk': self.sample.pk})
        create_url = reverse('attachments:create', kwargs={'sample_pk': self.sample.pk})

        get_response = self.client.get(attachments_url)

        self.assertContains(get_response, 'Файлы')

        self.assertContains(get_response, 'Добавить')
        self.assertContains(get_response, create_url)

        post_response = self.client.post(

            create_url,

            {

                'attachment-title': 'Photo',

                'attachment-file': SimpleUploadedFile('photo.jpg', b'jpeg', content_type='image/jpeg'),

            },

        )

        self.assertRedirects(post_response, attachments_url)

        self.assertTrue(SampleAttachment.objects.filter(title='Photo').exists())

    def test_attachments_tab_prefills_title_with_sample_name_and_sequence(self):
        create_url = reverse('attachments:create', kwargs={'sample_pk': self.sample.pk})

        response = self.client.get(create_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<input type="text" name="attachment-title" value="{self.sample.name} #0001"',
            html=False,
        )

    def test_attachment_title_increments_sequence(self):
        SampleAttachment.objects.create(
            sample=self.sample,
            title=f'{self.sample.name} #0001',
            file=SimpleUploadedFile('a.txt', b'a', content_type='text/plain'),
        )
        create_url = reverse('attachments:create', kwargs={'sample_pk': self.sample.pk})
        response = self.client.get(create_url)
        self.assertContains(
            response,
            f'value="{self.sample.name} #0002"',
            html=False,
        )

    def test_sample_detail_shows_tabs(self):

        detail_response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))

        self.assertContains(detail_response, 'Сканы')

        self.assertContains(detail_response, 'Файлы')

    def test_global_scans_list(self):

        ScanRecord.objects.create(
            sample=self.sample,
            title='Global list scan',
            file=make_hdf5_upload('global.h5'),
            workspace=self.legacy_workspace,
        )

        response = self.client.get(reverse('scans_all'))

        self.assertContains(response, 'Global list scan')

@override_settings(**_STORAGE_OVERRIDE)

class ScanUiViewsTests(TestCase):

    def setUp(self):

        self.media_root = tempfile.mkdtemp()

        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)

        self.settings_override.enable()

        self.legacy_workspace = ensure_legacy_workspace()
        self.material = Material.objects.create(
            code='MAT-SCN-UI',
            name='Scan UI material',
            home_workspace=self.legacy_workspace,
        )

        self.sample = Sample.objects.create(
            code='SMP-SCN-UI',
            name='Scan UI sample',
            material=self.material,
            workspace=self.legacy_workspace,
        )

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_scan_detail_and_edit_views(self):

        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})

        response = self.client.post(

            create_url,

            {

                'title': 'Echo scan',

                'description': 'Test',

                'method': 'echo',

                'file': make_hdf5_upload('echo.h5'),

            },

        )

        self.assertEqual(response.status_code, 302)

        scan = ScanRecord.objects.get(title='Echo scan')

        detail_response = self.client.get(

            reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),

        )

        self.assertContains(detail_response, 'Echo scan')

        self.assertContains(detail_response, 'HDF5')

        edit_response = self.client.post(

            reverse('scans:edit', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),

            {

                'title': 'Echo scan updated',

                'description': 'Updated',

                'method': 'shadow',

            },

        )

        self.assertEqual(edit_response.status_code, 302)

        scan.refresh_from_db()

        self.assertEqual(scan.title, 'Echo scan updated')

from django.test import TransactionTestCase

from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class SampleStructureParamsTests(TransactionTestCase):
    def setUp(self):
        self.legacy_workspace = ensure_legacy_workspace()
        self.structure_type = StructureType.objects.create(
            name='Sample Panel Struct',
            code='sample_panel_struct',
            table_name='structures_sample_panel_struct',
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

        insert = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Material panel', 'thickness': '10.00'},
        )
        self.assertTrue(insert['success'], insert.get('error'))
        self.material = Material.objects.create(
            code='MAT-SMP-STRUCT',
            name='Material with structure',
            home_workspace=self.legacy_workspace,
            struct_type=self.structure_type,
            struct_props_id=insert['id'],
        )
        self.other_material = Material.objects.create(
            code='MAT-SMP-STRUCT-2',
            name='Other structured material',
            home_workspace=self.legacy_workspace,
        )
        other_insert = SQLExecutor.insert(
            self.structure_type,
            {'title': 'Other panel', 'thickness': '20.00'},
        )
        self.assertTrue(other_insert['success'], other_insert.get('error'))
        self.other_material.struct_type = self.structure_type
        self.other_material.struct_props_id = other_insert['id']
        self.other_material.save(update_fields=['struct_type', 'struct_props_id'])

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def _structure_field_data(self, **overrides):
        data = {'title': 'Sample panel', 'thickness': '12.50'}
        data.update(overrides)
        payload = {}
        for field in self.structure_type.fields.exclude(field_type='ForeignKey'):
            base = f'structure_field_{field.pk}'
            if field.field_type == 'DecimalField':
                payload[base] = data[field.name]
                payload[f'{base}__b'] = ''
                payload[f'{base}__kind'] = 'scalar'
            else:
                payload[base] = data[field.name]
        return payload

    def _property_mgmt(self):
        return {
            'properties-TOTAL_FORMS': '0',
            'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
        }

    def test_create_copies_structure_params_to_sample_row(self):
        response = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-STRUCT-1',
                'name': 'Structured sample',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='Copied panel', thickness='11.00'),
            },
        )
        self.assertEqual(response.status_code, 302)
        sample = Sample.objects.get(code='SMP-STRUCT-1')
        self.assertEqual(sample.struct_type_id, self.structure_type.pk)
        self.assertIsNotNone(sample.struct_props_id)
        self.assertNotEqual(str(sample.struct_props_id), str(self.material.struct_props_id))

        sample_params = sample.get_structure_params()
        self.assertEqual(sample_params['title'], 'Copied panel')
        self.assertEqual(str(sample_params['thickness']), '11.00')

        material_params = self.material.get_structure_params()
        self.assertEqual(material_params['title'], 'Material panel')
        self.assertEqual(str(material_params['thickness']), '10.00')

    def test_edit_updates_sample_row_not_material(self):
        create = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-STRUCT-2',
                'name': 'Edit me',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='Before', thickness='9.00'),
            },
        )
        self.assertEqual(create.status_code, 302)
        sample = Sample.objects.get(code='SMP-STRUCT-2')
        sample_row_id = sample.struct_props_id

        edit = self.client.post(
            reverse('samples:edit', kwargs={'pk': sample.pk}),
            {
                'code': sample.code,
                'name': sample.name,
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='After', thickness='9.50'),
            },
        )
        self.assertEqual(edit.status_code, 302)
        sample.refresh_from_db()
        self.assertEqual(sample.struct_props_id, sample_row_id)
        self.assertEqual(sample.get_structure_params()['title'], 'After')
        self.assertEqual(self.material.get_structure_params()['title'], 'Material panel')

    def test_material_change_resets_structure_from_new_material(self):
        create = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-STRUCT-3',
                'name': 'Switch material',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='Old copy', thickness='8.00'),
            },
        )
        self.assertEqual(create.status_code, 302)
        sample = Sample.objects.get(code='SMP-STRUCT-3')
        old_row = sample.struct_props_id

        edit = self.client.post(
            reverse('samples:edit', kwargs={'pk': sample.pk}),
            {
                'code': sample.code,
                'name': sample.name,
                'material': self.other_material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='From other', thickness='21.00'),
            },
        )
        self.assertEqual(edit.status_code, 302)
        sample.refresh_from_db()
        self.assertNotEqual(sample.struct_props_id, old_row)
        self.assertEqual(sample.material_id, self.other_material.pk)
        self.assertEqual(sample.get_structure_params()['title'], 'From other')
        self.assertIsNone(
            SQLExecutor.get_structure_instance(self.structure_type, old_row),
        )

    def test_detail_shows_sample_structure_overrides(self):
        create = self.client.post(
            reverse('samples:create'),
            {
                'code': 'SMP-STRUCT-4',
                'name': 'Detail sample',
                'material': self.material.pk,
                'object_type': 'test',
                **self._property_mgmt(),
                **self._structure_field_data(title='Sample-only title', thickness='13.00'),
            },
        )
        self.assertEqual(create.status_code, 302)
        sample = Sample.objects.get(code='SMP-STRUCT-4')
        response = self.client.get(reverse('samples:detail', kwargs={'pk': sample.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sample-only title')
        self.assertContains(response, 'Из параметров структуры')
        self.assertNotContains(response, 'Material panel')

    def test_create_form_renders_editable_structure_fields(self):
        response = self.client.get(
            reverse('samples:create'),
            {'material': str(self.material.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Параметры структуры')
        title_field = self.structure_type.fields.get(name='title')
        self.assertContains(response, f'structure_field_{title_field.pk}')
