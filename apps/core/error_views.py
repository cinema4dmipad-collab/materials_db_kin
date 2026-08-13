"""Branded HTTP status pages (400/403/404/500)."""

from django.conf import settings
from django.http import HttpResponse
from django.template import loader

_STATUS_COPY = {
    400: (
        'Некорректный запрос',
        'Сервер не смог разобрать запрос. Проверьте адрес или вернитесь на главную и откройте нужный раздел ещё раз.',
    ),
    403: (
        'Доступ запрещён',
        'У вас нет прав на эту страницу в текущем рабочем пространстве. Если доступ должен быть — обратитесь к администратору.',
    ),
    404: (
        'Страница не найдена',
        'Такой страницы нет или запись удалили. Проверьте ссылку или вернитесь к списку материалов и образцов.',
    ),
    500: (
        'Ошибка сервера',
        'Что-то пошло не так на сервере. Попробуйте обновить страницу чуть позже. Если ошибка повторяется — сообщите администратору.',
    ),
}


def render_status_page(request, status_code: int) -> HttpResponse:
    title, message = _STATUS_COPY.get(
        status_code,
        ('Ошибка', 'Не удалось открыть страницу.'),
    )
    user = getattr(request, 'user', None)
    template = loader.get_template('errors/status.html')
    html = template.render(
        {
            'status_code': status_code,
            'error_title': title,
            'error_message': message,
            'app_version': getattr(settings, 'APP_VERSION', ''),
            'is_authenticated': bool(getattr(user, 'is_authenticated', False)),
        },
        request=None,
    )
    return HttpResponse(html, status=status_code)


def bad_request(request, exception):
    return render_status_page(request, 400)


def permission_denied(request, exception):
    return render_status_page(request, 403)


def page_not_found(request, exception):
    return render_status_page(request, 404)


def server_error(request):
    return render_status_page(request, 500)
