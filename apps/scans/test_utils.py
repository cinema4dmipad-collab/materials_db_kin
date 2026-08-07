HDF5_SIGNATURE = b'\x89HDF\r\n\x1a\n'
PNG_1X1 = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)


def make_hdf5_upload(name='scan.h5', extra=b''):
    from django.core.files.uploadedfile import SimpleUploadedFile

    content = HDF5_SIGNATURE + extra
    return SimpleUploadedFile(name, content, content_type='application/x-hdf5')


def make_preview_upload(name='preview.png', content=None):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name,
        content if content is not None else PNG_1X1,
        content_type='image/png',
    )
