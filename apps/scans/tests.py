import shutil

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

from django.db import connection
from django.test import TestCase, override_settings

from django.urls import reverse

from apps.materials.models import Material

from apps.samples.models import Sample

from apps.scans.models import ScanRecord

from apps.scans.test_utils import make_hdf5_upload, make_preview_upload

from apps.scans.validators import (
    MAX_SCAN_FILE_SIZE,
    validate_scan_file,
    validate_scan_preview,
)
from apps.workspaces.services import ensure_legacy_workspace

class SampleModelTests(TestCase):

    def setUp(self):

        self.material = Material.objects.create(code='MAT-SMP-001', name='Test material')

        self.sample = Sample.objects.create(

            code='SMP-001',

            name='Test sample',

            material=self.material,

            created_by='tester',

        )

    def test_str(self):

        self.assertEqual(str(self.sample), 'SMP-001 - Test sample')

    def test_material_cascade_deletes_sample(self):

        sample_id = self.sample.id

        self.material.delete()

        self.assertFalse(Sample.objects.filter(pk=sample_id).exists())

class SampleDeleteRemovesScanFilesTests(TestCase):

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
            },
        )
        self.settings_override.enable()

        self.material = Material.objects.create(code='MAT-SMP-002', name='Cascade material')

        self.sample = Sample.objects.create(

            code='SMP-002',

            name='Cascade sample',

            material=self.material,

        )

        self.scan = ScanRecord.objects.create(

            sample=self.sample,

            title='Cascade scan',

            file=make_hdf5_upload('cascade.h5'),

        )

        self.file_name = self.scan.file.name

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_sample_delete_removes_scan_file(self):

        self.sample.delete()

        self.assertFalse(ScanRecord.objects.filter(title='Cascade scan').exists())

        self.assertFalse(self.scan.file.storage.exists(self.file_name))

class SampleViewsTests(TestCase):

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
            },
        )
        self.settings_override.enable()

        self.legacy_workspace = ensure_legacy_workspace()
        self.material = Material.objects.create(
            code='MAT-SMP-003',
            name='View material',
            home_workspace=self.legacy_workspace,
        )

        self.sample = Sample.objects.create(
            code='SMP-VIEW-001',
            name='View sample',
            material=self.material,
            workspace=self.legacy_workspace,
        )

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_sample_list_and_detail_views(self):

        list_response = self.client.get(reverse('samples:list'))

        self.assertContains(list_response, 'SMP-VIEW-001')

        detail_response = self.client.get(reverse('samples:detail', kwargs={'pk': self.sample.pk}))

        self.assertContains(detail_response, 'View sample')

        self.assertContains(detail_response, 'MAT-SMP-003')

class ScanFileValidationTests(TestCase):

    def test_rejects_unsupported_extension(self):

        uploaded = SimpleUploadedFile('scan.exe', b'bad', content_type='application/octet-stream')

        with self.assertRaisesMessage(Exception, 'HDF5'):

            validate_scan_file(uploaded)

    def test_rejects_invalid_signature(self):

        uploaded = SimpleUploadedFile('scan.h5', b'not-hdf5-content', content_type='application/x-hdf5')

        with self.assertRaisesMessage(Exception, 'сигнатур'):

            validate_scan_file(uploaded)

    def test_rejects_oversized_file(self):

        uploaded = SimpleUploadedFile(

            'scan.h5',

            b'\x89HDF\r\n\x1a\n',

            content_type='application/x-hdf5',

        )

        uploaded.size = MAX_SCAN_FILE_SIZE + 1

        with self.assertRaisesMessage(Exception, '20 ГБ'):

            validate_scan_file(uploaded)

    def test_accepts_valid_hdf5(self):

        validate_scan_file(make_hdf5_upload('scan.hdf5'))

    def test_preview_rejects_non_image(self):
        uploaded = SimpleUploadedFile('note.txt', b'hello', content_type='text/plain')
        with self.assertRaisesMessage(Exception, 'изображением'):
            validate_scan_preview(uploaded)

    def test_preview_accepts_png(self):
        validate_scan_preview(make_preview_upload())

class ScanRecordModelTests(TestCase):

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
            },
        )
        self.settings_override.enable()

        self.material = Material.objects.create(code='MAT-SCN-001', name='Scan material')

        self.sample = Sample.objects.create(

            code='SMP-SCN-001',

            name='Scan sample',

            material=self.material,

        )

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_create_scan_stores_file(self):

        scan = ScanRecord.objects.create(

            sample=self.sample,

            title='Echo scan',

            method='echo',

            file=make_hdf5_upload(),

            uploaded_by='tester',

        )

        self.assertTrue(scan.file.storage.exists(scan.file.name))

        self.assertTrue(scan.is_hdf5)

    def test_delete_scan_removes_file(self):

        scan = ScanRecord.objects.create(

            sample=self.sample,

            title='To delete',

            file=make_hdf5_upload(),

        )

        file_name = scan.file.name

        scan.delete()

        self.assertFalse(scan.file.storage.exists(file_name))

class ScanViewsTests(TestCase):

    def setUp(self):
        connection.ensure_connection()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
            },
        )
        self.settings_override.enable()

        self.legacy_workspace = ensure_legacy_workspace()
        self.material = Material.objects.create(
            code='MAT-SCN-002',
            name='Upload material',
            home_workspace=self.legacy_workspace,
        )

        self.sample = Sample.objects.create(
            code='SMP-SCN-002',
            name='Upload sample',
            material=self.material,
            workspace=self.legacy_workspace,
        )

    def tearDown(self):

        self.settings_override.disable()

        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_scan_detail_has_inline_tags_form(self):
        scan = ScanRecord.objects.create(
            sample=self.sample,
            workspace=self.legacy_workspace,
            title='Tagged scan',
            method='ut',
            file=make_hdf5_upload('tagged.h5'),
        )
        response = self.client.get(
            reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('tags_form', response.context)
        self.assertContains(response, 'entity-detail-tags-form')

    def test_scan_detail_has_keenetix_open_button(self):
        scan = ScanRecord.objects.create(
            sample=self.sample,
            workspace=self.legacy_workspace,
            title='KeenetiX link scan',
            method='ut',
            file=make_hdf5_upload('keenetix-link.h5'),
        )
        response = self.client.get(
            reverse('scans:detail', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Открыть в KeenetiX')
        self.assertContains(response, 'data-keenetix-open-scan')
        self.assertContains(response, f'data-scan-id="{scan.pk}"')
        self.assertNotContains(response, 'keenetix://')

    def test_scan_tags_update_view(self):
        scan = ScanRecord.objects.create(
            sample=self.sample,
            workspace=self.legacy_workspace,
            title='Tag update scan',
            method='ut',
            file=make_hdf5_upload('tag-update.h5'),
        )
        response = self.client.post(
            reverse('scans:tags', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),
            {'tag_names': 'hdf5, метод::ут'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(scan.tags.values_list('name', flat=True)),
            {'hdf5', 'метод::ут'},
        )

    def test_create_scan_assigns_tags_to_sample_workspace(self):
        """Tags must follow sample.workspace even when active workspace differs."""
        from apps.core.models import Tag
        from apps.workspaces.models import Workspace

        home = Workspace.objects.create(slug='ws-scan-home', name='Scan home')
        self.assertNotEqual(home.pk, self.legacy_workspace.pk)
        material = Material.objects.create(
            code='MAT-SCN-SHARED',
            name='Shared scan material',
            home_workspace=home,
            visibility_mode='all_workspaces',
        )
        sample = Sample.objects.create(
            code='SMP-SCN-SHARED',
            name='Shared sample',
            material=material,
            workspace=home,
        )

        response = self.client.post(
            reverse('scans:create', kwargs={'sample_pk': sample.pk}),
            {
                'title': 'Cross-ws scan',
                'description': '',
                'method': 'echo',
                'file': make_hdf5_upload('cross-ws.h5'),
                'tag_names': 'кросс-тег',
            },
        )
        self.assertEqual(response.status_code, 302)
        scan = ScanRecord.objects.get(title='Cross-ws scan')
        self.assertEqual(scan.workspace_id, home.pk)
        tag = scan.tags.get(name='кросс-тег')
        self.assertEqual(tag.workspace_id, home.pk)
        self.assertFalse(
            Tag.objects.filter(name='кросс-тег', workspace=self.legacy_workspace).exists()
        )

    def test_upload_list_and_delete_scan(self):

        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})

        response = self.client.post(

            create_url,

            {

                'title': 'Surface scan',

                'description': 'Top view',

                'method': 'shadow',

                'file': make_hdf5_upload('surface.h5'),

                'preview': make_preview_upload('surface.png'),

            },

        )

        self.assertEqual(response.status_code, 302)

        scan = ScanRecord.objects.get(title='Surface scan')

        self.assertTrue(scan.file.storage.exists(scan.file.name))
        self.assertTrue(scan.preview)
        self.assertTrue(scan.preview.storage.exists(scan.preview.name))

        list_response = self.client.get(reverse('scans:list', kwargs={'sample_pk': self.sample.pk}))

        self.assertContains(list_response, 'Surface scan')
        self.assertContains(list_response, 'file-tile')
        self.assertContains(list_response, 'file-tile__preview-img')
        preview_url = reverse('scans:preview', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk})
        self.assertContains(list_response, preview_url)
        preview_response = self.client.get(preview_url)
        self.assertEqual(preview_response.status_code, 200)
        self.assertTrue(b''.join(preview_response.streaming_content).startswith(b'\x89PNG'))

        file_name = scan.file.name
        preview_name = scan.preview.name

        delete_response = self.client.post(

            reverse('scans:delete', kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk}),

        )

        self.assertEqual(delete_response.status_code, 302)

        self.assertFalse(ScanRecord.objects.filter(pk=scan.pk).exists())

        self.assertFalse(scan.file.storage.exists(file_name))
        self.assertFalse(scan.file.storage.exists(preview_name))

    def test_download_view_streams_file_through_app(self):
        scan = ScanRecord.objects.create(
            sample=self.sample,
            title='Download scan',
            method='echo',
            file=make_hdf5_upload('download.h5'),
            workspace=self.legacy_workspace,
        )
        download_url = reverse(
            'scans:download',
            kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk},
        )

        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertNotIn('seaweedfs', download_url)
        self.assertTrue(b''.join(response.streaming_content))

    def test_list_page_uses_app_download_url(self):
        scan = ScanRecord.objects.create(
            sample=self.sample,
            title='Listed scan',
            method='echo',
            file=make_hdf5_upload('listed.h5'),
            workspace=self.legacy_workspace,
        )
        list_url = reverse('scans:list', kwargs={'sample_pk': self.sample.pk})
        download_url = reverse(
            'scans:download',
            kwargs={'sample_pk': self.sample.pk, 'pk': scan.pk},
        )

        response = self.client.get(list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, download_url)
        self.assertNotContains(response, 'seaweedfs:8333')

    def test_all_scans_list_filters_by_method_search(self):
        ScanRecord.objects.create(
            sample=self.sample,
            title='Echo scan',
            method='echo',
            file=make_hdf5_upload('echo.h5'),
            workspace=self.legacy_workspace,
        )
        ScanRecord.objects.create(
            sample=self.sample,
            title='Shadow scan',
            method='shadow',
            file=make_hdf5_upload('shadow.h5'),
            workspace=self.legacy_workspace,
        )

        response = self.client.get(
            reverse('scans_all'),
            {'q': 'Эхо', 'q_in': 'method'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Echo scan')
        self.assertNotContains(response, 'Shadow scan')
        self.assertContains(response, 'file-tile')

    def test_sample_scans_list_filters_by_method_search(self):
        ScanRecord.objects.create(
            sample=self.sample,
            title='Echo scan',
            method='echo',
            file=make_hdf5_upload('echo-list.h5'),
            workspace=self.legacy_workspace,
        )
        ScanRecord.objects.create(
            sample=self.sample,
            title='Shadow scan',
            method='shadow',
            file=make_hdf5_upload('shadow-list.h5'),
            workspace=self.legacy_workspace,
        )

        response = self.client.get(
            reverse('scans:list', kwargs={'sample_pk': self.sample.pk}),
            {'q': 'Эхо', 'q_in': 'method'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Echo scan')
        self.assertNotContains(response, 'Shadow scan')

    def test_upload_rejects_invalid_extension(self):

        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})

        response = self.client.post(

            create_url,

            {

                'title': 'Bad file',

                'method': 'echo',

                'file': SimpleUploadedFile('bad.exe', b'bad', content_type='application/octet-stream'),

            },

        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(ScanRecord.objects.filter(title='Bad file').exists())

    def test_create_form_prefills_title_with_sample_name_and_sequence(self):
        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})

        response = self.client.get(create_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<input type="text" name="title" value="{self.sample.name} #0001"',
            html=False,
        )

    def test_scans_tab_attach_form_prefills_title_with_sample_name_and_sequence(self):
        scans_url = reverse('scans:list', kwargs={'sample_pk': self.sample.pk})

        response = self.client.get(scans_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<input type="text" name="scan-title" value="{self.sample.name} #0001"',
            html=False,
        )

    def test_default_scan_title_increments_sequence(self):
        ScanRecord.objects.create(
            sample=self.sample,
            title=f'{self.sample.name} #0001',
            method='echo',
            workspace=self.legacy_workspace,
        )
        create_url = reverse('scans:create', kwargs={'sample_pk': self.sample.pk})
        response = self.client.get(create_url)
        self.assertContains(
            response,
            f'value="{self.sample.name} #0002"',
            html=False,
        )
