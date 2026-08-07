import os

from django.core.exceptions import ValidationError

ALLOWED_SCAN_EXTENSIONS = {'.h5', '.hdf5'}
HDF5_SIGNATURE = b'\x89HDF\r\n\x1a\n'
MAX_SCAN_FILE_SIZE = 20 * 1024 * 1024 * 1024

ALLOWED_SCAN_PREVIEW_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_SCAN_PREVIEW_SIZE = 5 * 1024 * 1024


def format_max_scan_file_size():
    size_gb = MAX_SCAN_FILE_SIZE / (1024 ** 3)
    if size_gb == int(size_gb):
        return f'{int(size_gb)} ГБ'
    max_mb = MAX_SCAN_FILE_SIZE // (1024 * 1024)
    return f'{max_mb} МБ'


def format_max_scan_preview_size():
    max_mb = MAX_SCAN_PREVIEW_SIZE // (1024 * 1024)
    return f'{max_mb} МБ'


def validate_scan_file(uploaded_file):
    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension not in ALLOWED_SCAN_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_SCAN_EXTENSIONS))
        raise ValidationError(
            f'Скан должен быть в формате HDF5. Разрешены расширения: {allowed}.'
        )

    if uploaded_file.size > MAX_SCAN_FILE_SIZE:
        raise ValidationError(
            f'Размер файла не должен превышать {format_max_scan_file_size()}.'
        )

    uploaded_file.seek(0)
    signature = uploaded_file.read(len(HDF5_SIGNATURE))
    uploaded_file.seek(0)
    if signature != HDF5_SIGNATURE:
        raise ValidationError('Файл не является корректным HDF5 (неверная сигнатура).')


def _looks_like_preview_image(header: bytes) -> bool:
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    if header.startswith(b'\xff\xd8\xff'):
        return True
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    return False


def validate_scan_preview(uploaded_file):
    """Optional C-scan thumbnail: PNG / JPEG / WebP, small size."""
    if uploaded_file is None:
        return
    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension not in ALLOWED_SCAN_PREVIEW_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_SCAN_PREVIEW_EXTENSIONS))
        raise ValidationError(
            f'Превью должно быть изображением. Разрешены расширения: {allowed}.'
        )
    if uploaded_file.size > MAX_SCAN_PREVIEW_SIZE:
        raise ValidationError(
            f'Размер превью не должен превышать {format_max_scan_preview_size()}.'
        )
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not _looks_like_preview_image(header):
        raise ValidationError('Файл превью повреждён или имеет неверный формат изображения.')
