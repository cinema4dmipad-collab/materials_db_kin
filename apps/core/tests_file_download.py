from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import Http404
from django.test import TestCase

from apps.core.file_download import build_file_download_response


def _file_field_stub(fs, name):
    class Stub:
        pass

    stub = Stub()
    stub.name = name
    stub.storage = fs
    stub.size = fs.size(name) if fs.exists(name) else None
    stub.open = lambda mode='rb': fs.open(name, mode)
    return stub


class FileDownloadTests(TestCase):
    def test_build_file_download_response_streams_existing_file(self):
        with TemporaryDirectory() as temp_dir:
            fs = FileSystemStorage(location=temp_dir, base_url='/media/')
            fs.save('docs/readme.txt', ContentFile(b'hello'))

            response = build_file_download_response(
                _file_field_stub(fs, 'docs/readme.txt'),
                filename='readme.txt',
            )

            try:
                self.assertEqual(response.status_code, 200)
                self.assertIn('attachment; filename="readme.txt"', response['Content-Disposition'])
                self.assertEqual(b''.join(response.streaming_content), b'hello')
            finally:
                response.close()

    def test_build_file_download_response_raises_for_missing_file(self):
        with TemporaryDirectory() as temp_dir:
            fs = FileSystemStorage(location=temp_dir, base_url='/media/')

            with self.assertRaises(Http404):
                build_file_download_response(_file_field_stub(fs, 'missing.txt'))
