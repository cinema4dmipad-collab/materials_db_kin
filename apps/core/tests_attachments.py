import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.attachments.kinds import (
    KIND_EXCEL,
    KIND_PDF,
    KIND_PRESENTATION,
    KIND_WORD,
    detect_attachment_kind,
)
from apps.core.attachments.processing import process_attachment_preview
from apps.core.attachments.statuses import PREVIEW_FAILED, PREVIEW_READY, PREVIEW_SKIPPED
from apps.samples.models import SampleAttachment
from apps.scans.models import ScanAttachment
from apps.workspaces.models import BUILTIN_GROUP_OPERATOR, Workspace
from apps.workspaces.services import assign_user_to_groups, ensure_default_groups
from apps.workspaces.test_utils import (
    DEFAULT_TEST_PASSWORD,
    create_test_material,
    create_test_sample,
    create_test_scan,
)

User = get_user_model()

# Minimal one-page PDF accepted by pypdfium2.
MINIMAL_PDF = (
    b'%PDF-1.4\n'
    b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
    b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
    b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n'
    b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n'
    b'0000000058 00000 n \n0000000115 00000 n \n'
    b'trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF'
)


class AttachmentKindTests(TestCase):
    def test_detect_kinds(self):
        self.assertEqual(detect_attachment_kind('a.PDF'), KIND_PDF)
        self.assertEqual(detect_attachment_kind('report.docx'), KIND_WORD)
        self.assertEqual(detect_attachment_kind('deck.pptx'), KIND_PRESENTATION)
        self.assertEqual(detect_attachment_kind('slides.odp'), KIND_PRESENTATION)
        self.assertEqual(detect_attachment_kind('table.xlsx'), KIND_EXCEL)
        self.assertEqual(detect_attachment_kind('photo.png'), 'other')


class AttachmentPreviewProcessingTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
                },
            },
        )
        self.settings_override.enable()
        self.workspace = Workspace.objects.create(slug='att-ws', name='Att WS')
        ensure_default_groups(self.workspace)
        self.user = User.objects.create_user('att-user', password=DEFAULT_TEST_PASSWORD)
        assign_user_to_groups(self.user, self.workspace, [BUILTIN_GROUP_OPERATOR])
        self.material = create_test_material(home_workspace=self.workspace)
        self.sample = create_test_sample(material=self.material, workspace=self.workspace)

    def tearDown(self):
        self.settings_override.disable()

    def test_pdf_renders_preview_image(self):
        attachment = SampleAttachment.objects.create(
            sample=self.sample,
            title='PDF doc',
            file=SimpleUploadedFile('note.pdf', MINIMAL_PDF, content_type='application/pdf'),
        )
        process_attachment_preview(attachment)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_READY)
        self.assertTrue(attachment.preview_image)
        self.assertTrue(attachment.preview_image.name.lower().endswith('.png'))
        self.assertTrue(attachment.preview_image.storage.exists(attachment.preview_image.name))
        with attachment.preview_image.open('rb') as handle:
            self.assertEqual(handle.read(8), b'\x89PNG\r\n\x1a\n')

    def test_excel_skipped(self):
        attachment = SampleAttachment.objects.create(
            sample=self.sample,
            title='Sheet',
            file=SimpleUploadedFile(
                'data.xlsx',
                b'PK\x03\x04fake',
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            ),
        )
        process_attachment_preview(attachment)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_SKIPPED)
        self.assertFalse(attachment.preview_image)

    @patch('apps.core.attachments.processing.convert_office_to_pdf')
    def test_word_uses_libreoffice(self, convert_mock):
        pdf_dir = Path(tempfile.mkdtemp())
        pdf_path = pdf_dir / 'out.pdf'
        pdf_path.write_bytes(MINIMAL_PDF)
        convert_mock.return_value = pdf_path

        attachment = SampleAttachment.objects.create(
            sample=self.sample,
            title='Word',
            file=SimpleUploadedFile(
                'letter.docx',
                b'PK\x03\x04word',
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            ),
        )
        process_attachment_preview(attachment)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_READY)
        self.assertTrue(attachment.preview_image)
        self.assertTrue(attachment.preview_image.name.lower().endswith('.png'))
        convert_mock.assert_called_once()

    @patch('apps.core.attachments.processing.convert_office_to_pdf')
    def test_pptx_uses_libreoffice(self, convert_mock):
        pdf_dir = Path(tempfile.mkdtemp())
        pdf_path = pdf_dir / 'out.pdf'
        pdf_path.write_bytes(MINIMAL_PDF)
        convert_mock.return_value = pdf_path

        attachment = SampleAttachment.objects.create(
            sample=self.sample,
            title='Deck',
            file=SimpleUploadedFile(
                'slides.pptx',
                b'PK\x03\x04pptx',
                content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            ),
        )
        process_attachment_preview(attachment)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_READY)
        self.assertTrue(attachment.preview_image)
        convert_mock.assert_called_once()

    def test_word_failure_marks_failed(self):
        from apps.core.attachments.convert import LibreOfficeConvertError

        with patch(
            'apps.core.attachments.processing.convert_office_to_pdf',
            side_effect=LibreOfficeConvertError('nope'),
        ):
            attachment = SampleAttachment.objects.create(
                sample=self.sample,
                title='Word fail',
                file=SimpleUploadedFile('bad.docx', b'PK\x03\x04', content_type='application/octet-stream'),
            )
            process_attachment_preview(attachment)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_FAILED)


class ScanAttachmentViewsTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
                },
            },
        )
        self.settings_override.enable()
        self.workspace = Workspace.objects.create(slug='scan-att-ws', name='Scan Att')
        ensure_default_groups(self.workspace)
        self.user = User.objects.create_user('scan-att', password=DEFAULT_TEST_PASSWORD)
        assign_user_to_groups(self.user, self.workspace, [BUILTIN_GROUP_OPERATOR])
        self.client.login(username='scan-att', password=DEFAULT_TEST_PASSWORD)
        session = self.client.session
        session['active_workspace_id'] = str(self.workspace.pk)
        session.save()
        self.material = create_test_material(home_workspace=self.workspace)
        self.sample = create_test_sample(material=self.material, workspace=self.workspace)
        self.scan = create_test_scan(sample=self.sample, workspace=self.workspace)

    def tearDown(self):
        self.settings_override.disable()

    def test_attach_pdf_to_scan(self):
        list_url = reverse(
            'scans:attachment_list',
            kwargs={'sample_pk': self.sample.pk, 'scan_pk': self.scan.pk},
        )
        self.assertContains(self.client.get(list_url), 'Добавить')
        url = reverse(
            'scans:attachment_create',
            kwargs={'sample_pk': self.sample.pk, 'scan_pk': self.scan.pk},
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    'attachment-title': 'Protocol',
                    'attachment-description': '',
                    'attachment-file': SimpleUploadedFile(
                        'protocol.pdf',
                        MINIMAL_PDF,
                        content_type='application/pdf',
                    ),
                },
            )
        self.assertEqual(response.status_code, 302)
        attachment = ScanAttachment.objects.get(title='Protocol')
        self.assertEqual(attachment.scan_id, self.scan.pk)
        attachment.refresh_from_db()
        self.assertEqual(attachment.preview_status, PREVIEW_READY)
        preview = self.client.get(
            reverse(
                'scans:attachment_preview',
                kwargs={
                    'sample_pk': self.sample.pk,
                    'scan_pk': self.scan.pk,
                    'pk': attachment.pk,
                },
            )
        )
        self.assertEqual(preview.status_code, 200)
        content_type = preview.get('Content-Type', '')
        self.assertIn('image/png', content_type)
        body = b''.join(preview.streaming_content)
        self.assertTrue(body.startswith(b'\x89PNG'))
