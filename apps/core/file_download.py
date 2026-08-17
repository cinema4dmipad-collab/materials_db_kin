from django.http import FileResponse, Http404


class StorageUnavailable(OSError):
    """Raised when object storage is unreachable (timeout / connection error)."""


def build_file_download_response(
    file_field,
    *,
    filename=None,
    as_attachment=True,
    cache_control=None,
):
    if not file_field or not file_field.name:
        raise Http404('Файл не найден')

    storage = file_field.storage
    try:
        if not storage.exists(file_field.name):
            raise Http404('Файл не найден')
        file_handle = file_field.open('rb')
    except Http404:
        raise
    except Exception as exc:
        # S3/SeaweedFS: EndpointConnectionError, ConnectTimeoutError, etc.
        name = type(exc).__name__
        if any(
            token in name
            for token in (
                'Timeout',
                'Connection',
                'Endpoint',
                'Connect',
                'ReadTimeout',
            )
        ) or isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            raise StorageUnavailable('Файловое хранилище недоступно') from exc
        raise

    download_name = filename or file_field.name.rsplit('/', 1)[-1]
    response = FileResponse(
        file_handle,
        as_attachment=as_attachment,
        filename=download_name,
    )
    if cache_control:
        response['Cache-Control'] = cache_control
    try:
        size = file_field.size
        if size is not None:
            response['Content-Length'] = size
    except Exception:
        pass
    return response
