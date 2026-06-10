MAX_ATTACHMENT_FILE_SIZE = 100 * 1024 * 1024


def validate_attachment_file(uploaded_file):
    from django.core.exceptions import ValidationError

    if uploaded_file.size > MAX_ATTACHMENT_FILE_SIZE:
        max_mb = MAX_ATTACHMENT_FILE_SIZE // (1024 * 1024)
        raise ValidationError(f'Размер файла не должен превышать {max_mb} МБ.')
