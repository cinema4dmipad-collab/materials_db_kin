from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db.models import FileField
from django.db.models.fields.files import FieldFile
from django.http import Http404
from django.test import TestCase, override_settings

from apps.core.file_download import build_file_download_response


class FileDownloadTests(TestCase):
    def test_build_file_download_response_streams_existing_file(self):
        with TemporaryDirectory() as temp_dir:
            storage = FileSystemStorage(location=temp_dir, base_url='/media/')
            storage.save('docs/readme.txt', ContentFile(b'hello'))

            class Dummy:
                name = 'docs/readme.txt'
                storage = storage

                @property
                def size(self):
                    return storage.size(self.name)

                def open(self, mode='rb'):
                    return storage.open(self.name, mode)

            response = build_file_download_response(
                Dummy(),
                filename='readme.txt',
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment; filename="readme.txt"', response['Content-Disposition'])
            self.assertEqual(b''.join(response.streaming_content), b'hello')

    def test_build_file_download_response_raises_for_missing_file(self):
        with TemporaryDirectory() as temp_dir:
            storage = FileSystemStorage(location=temp_dir, base_url='/media/')

            class Dummy:
                name = 'missing.txt'
                storage = storage

            with self.assertRaises(Http404):
                build_file_download_response(FieldFile(None, FileField(), Dummy()))
