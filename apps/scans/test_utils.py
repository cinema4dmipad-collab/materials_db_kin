HDF5_SIGNATURE = b'\x89HDF\r\n\x1a\n'


def make_hdf5_upload(name='scan.h5', extra=b''):
    from django.core.files.uploadedfile import SimpleUploadedFile

    content = HDF5_SIGNATURE + extra
    return SimpleUploadedFile(name, content, content_type='application/x-hdf5')
