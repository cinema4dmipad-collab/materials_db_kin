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



        self.material = Material.objects.create(code='MAT-SMP-UI', name='UI material')

        self.sample = Sample.objects.create(
            code='SMP-UI-001',
            name='UI sample',
            material=self.material,
            object_type='test',
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
            f'{prefix}-value': '1.55',
        }
        data.update(overrides)
        return data

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)



    def test_sample_crud_views(self):

        list_response = self.client.get(reverse('samples:list'))

        self.assertContains(list_response, 'SMP-UI-001')



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
        self.assertEqual(payload['properties'][0]['value'], '1.55')

    def test_sample_detail_shows_properties(self):
        density = Property.objects.create(
            name='detail_density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
        )
        SampleProperty.objects.create(
            sample=self.sample,
            property=density,
            value='2.10',
        )

        response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))

        self.assertContains(response, 'Свойства')
        self.assertContains(response, 'Density')
        self.assertContains(response, '2.10')

    def test_attach_scan_on_sample_scans_tab(self):

        scans_url = reverse('scans:list', kwargs={'sample_pk': self.sample.pk})

        post_response = self.client.post(

            scans_url,

            {

                'scan-title': 'Inline scan',

                'scan-description': 'Attached from scans tab',

                'scan-method': 'immersion',

                'scan-file': make_hdf5_upload('inline.h5'),

            },

        )

        self.assertRedirects(post_response, scans_url)

        scan = ScanRecord.objects.get(title='Inline scan')

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

        get_response = self.client.get(attachments_url)

        self.assertContains(get_response, 'Файлы')

        self.assertContains(get_response, 'Прикрепить файл')



        post_response = self.client.post(

            attachments_url,

            {

                'attachment-title': 'Photo',

                'attachment-file': SimpleUploadedFile('photo.jpg', b'jpeg', content_type='image/jpeg'),

            },

        )

        self.assertRedirects(post_response, attachments_url)

        self.assertTrue(SampleAttachment.objects.filter(title='Photo').exists())



    def test_sample_detail_shows_tabs(self):

        detail_response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))

        self.assertContains(detail_response, 'Сканы')

        self.assertContains(detail_response, 'Файлы')



    def test_global_scans_list(self):

        ScanRecord.objects.create(

            sample=self.sample,

            title='Global list scan',

            file=make_hdf5_upload('global.h5'),

        )

        response = self.client.get(reverse('scans_all'))

        self.assertContains(response, 'Global list scan')





@override_settings(**_STORAGE_OVERRIDE)

class ScanUiViewsTests(TestCase):

    def setUp(self):

        self.media_root = tempfile.mkdtemp()

        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)

        self.settings_override.enable()



        self.material = Material.objects.create(code='MAT-SCN-UI', name='Scan UI material')

        self.sample = Sample.objects.create(

            code='SMP-SCN-UI',

            name='Scan UI sample',

            material=self.material,

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


