import re
from pathlib import Path

from django import get_version
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.materials.models import Material
from apps.samples.models import Sample
from apps.structures.models import StructureType


SENSITIVE_VALUE_RE = re.compile(
    r'(?i)\b([A-Z0-9_.-]*(?:password|passwd|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key)[A-Z0-9_.-]*)'
    r'(\s*[:=]\s*)'
    r'([^\s,;]+)'
)
BEARER_TOKEN_RE = re.compile(r'(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]+)')
RECENT_LOG_LINES = 80
RECENT_LOG_BYTES = 64 * 1024


def dashboard(request):
    context = {
        'materials_count': Material.objects.count(),
        'samples_count': Sample.objects.count(),
        'structures_count': StructureType.objects.filter(is_active=True).count(),
        'recent_materials': Material.objects.order_by('-created_at')[:5],
    }
    return render(request, 'core/dashboard.html', context)


def help_page(request):
    return render(request, 'core/help.html')


def _redact_sensitive_text(value: str) -> str:
    value = SENSITIVE_VALUE_RE.sub(r'\1\2[redacted]', value)
    return BEARER_TOKEN_RE.sub(r'\1 [redacted]', value)


def _database_status() -> dict:
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover - exact DB errors vary by backend.
        return {
            'ok': False,
            'label': 'Ошибка подключения',
            'detail': _redact_sensitive_text(f'{exc.__class__.__name__}: {exc}'),
        }

    return {
        'ok': True,
        'label': 'Подключение активно',
        'detail': 'Тестовый запрос SELECT 1 выполнен успешно.',
    }


def _database_info() -> list[dict]:
    database = settings.DATABASES.get('default', {})
    return [
        {'label': 'DB engine', 'value': database.get('ENGINE', '—')},
        {'label': 'DB name', 'value': str(database.get('NAME', '—'))},
        {'label': 'DB host', 'value': database.get('HOST') or 'local'},
    ]


def _runtime_info() -> list[dict]:
    storage_backend = settings.STORAGES.get('default', {}).get('BACKEND', '—')
    return [
        {'label': 'App version', 'value': settings.APP_VERSION},
        {'label': 'Django', 'value': get_version()},
        {'label': 'DEBUG', 'value': 'on' if settings.DEBUG else 'off'},
        {'label': 'Storage backend', 'value': storage_backend},
        {'label': 'S3 storage', 'value': 'enabled' if getattr(settings, 'USE_S3_STORAGE', False) else 'disabled'},
    ]


def _read_recent_log_lines(log_file: Path, max_lines: int = RECENT_LOG_LINES) -> tuple[list[str], str]:
    if not log_file.exists() or not log_file.is_file():
        return [], 'Локальный файл логов пока не найден.'

    try:
        with log_file.open('rb') as file_obj:
            file_obj.seek(0, 2)
            file_size = file_obj.tell()
            start_offset = max(file_size - RECENT_LOG_BYTES, 0)
            file_obj.seek(start_offset)
            content = file_obj.read().decode('utf-8', errors='replace')
    except OSError as exc:
        return [], _redact_sensitive_text(f'Не удалось прочитать лог: {exc}')

    if start_offset > 0:
        # Avoid rendering a partial line that may contain a secret value without
        # the key needed by the redaction pattern.
        content = content.split('\n', 1)[1] if '\n' in content else ''

    lines = [_redact_sensitive_text(line) for line in content.splitlines() if line.strip()]
    if not lines:
        return [], 'Файл логов пуст.'

    return lines[-max_lines:], ''


@never_cache
@staff_member_required
def debug_page(request):
    log_file = Path(getattr(settings, 'DEBUG_LOG_FILE', settings.BASE_DIR / 'logs' / 'debug.log'))
    log_lines, log_message = _read_recent_log_lines(log_file)
    context = {
        'database_status': _database_status(),
        'database_info': _database_info(),
        'runtime_info': _runtime_info(),
        'log_file_name': log_file.name,
        'log_lines': log_lines,
        'log_message': log_message,
    }
    return render(request, 'core/debug.html', context)
