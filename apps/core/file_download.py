from django.http import FileResponse, Http404


def build_file_download_response(file_field, *, filename=None, as_attachment=True):
    if not file_field or not file_field.name:
        raise Http404('Файл не найден')

    storage = file_field.storage
    if not storage.exists(file_field.name):
        raise Http404('Файл не найден')

    download_name = filename or file_field.name.rsplit('/', 1)[-1]
    file_handle = file_field.open('rb')
    response = FileResponse(
        file_handle,
        as_attachment=as_attachment,
        filename=download_name,
    )
    try:
        size = file_field.size
        if size is not None:
            response['Content-Length'] = size
    except Exception:
        pass
    return response
