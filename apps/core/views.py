import re
from pathlib import Path

from django import get_version
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.core.version import format_git_commit_display, get_git_commit_hash
from apps.workspaces.mixins import workspace_login_required
from apps.workspaces.services import (
    materials_visible_in,
    samples_in_workspace,
    structure_types_visible_in,
)


SENSITIVE_VALUE_RE = re.compile(
    r'(?i)\b([A-Z0-9_.-]*(?:password|passwd|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key)[A-Z0-9_.-]*)'
    r'(\s*[:=]\s*)'
    r'([^\s,;]+)'
)
BEARER_TOKEN_RE = re.compile(r'(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]+)')
RECENT_LOG_LINES = 80
RECENT_LOG_BYTES = 64 * 1024


@workspace_login_required
def dashboard(request):
    active_workspace = getattr(request, 'active_workspace', None)
    materials_qs = materials_visible_in(active_workspace)
    samples_qs = samples_in_workspace(active_workspace)
    structures_qs = structure_types_visible_in(active_workspace)
    context = {
        'materials_count': materials_qs.count(),
        'samples_count': samples_qs.count(),
        'structures_count': structures_qs.count(),
        'recent_materials': materials_qs.order_by('-created_at')[:5],
    }
    return render(request, 'core/dashboard.html', context)


@workspace_login_required
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
    items = [
        {'label': 'App version', 'value': settings.APP_VERSION},
        {'label': 'Git commit', 'value': format_git_commit_display()},
        {'label': 'Django', 'value': get_version()},
        {'label': 'DEBUG', 'value': 'on' if settings.DEBUG else 'off'},
        {'label': 'Storage backend', 'value': storage_backend},
        {'label': 'S3 storage', 'value': 'enabled' if getattr(settings, 'USE_S3_STORAGE', False) else 'disabled'},
    ]
    if getattr(settings, 'USE_S3_STORAGE', False):
        items.append({
            'label': 'S3 bucket',
            'value': getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '') or '—',
        })
        items.append({
            'label': 'S3 endpoint',
            'value': getattr(settings, 'AWS_S3_ENDPOINT_URL', '') or '—',
        })
        items.append({
            'label': 'Debug S3 admin base',
            'value': getattr(settings, 'DEBUG_S3_ADMIN_BASE_URL', '') or '—',
        })
    return items


def _s3_admin_links() -> list[dict]:
    if not getattr(settings, 'USE_S3_STORAGE', False):
        return []

    base = getattr(settings, 'DEBUG_S3_ADMIN_BASE_URL', 'http://localhost').rstrip('/')
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '')
    filer_port = getattr(settings, 'SEAWEEDFS_FILER_PORT', '8888')
    master_port = getattr(settings, 'SEAWEEDFS_MASTER_PORT', '9333')
    admin_port = getattr(settings, 'SEAWEEDFS_ADMIN_PORT', '23646')

    links = [
        {
            'label': 'Filer',
            'url': f'{base}:{filer_port}/',
            'hint': 'Просмотр файлов и бакетов',
        },
        {
            'label': 'Master',
            'url': f'{base}:{master_port}/',
            'hint': 'Статус кластера SeaweedFS',
        },
        {
            'label': 'SeaweedFS Admin',
            'url': f'{base}:{admin_port}/',
            'hint': 'Административная панель',
        },
    ]
    if bucket:
        links.insert(0, {
            'label': f'Бакет «{bucket}»',
            'url': f'{base}:{filer_port}/buckets/{bucket}/',
            'hint': 'Файлы текущего бакета приложения',
        })
    return links


def _log_line_css_class(line: str) -> str:
    upper = line.upper()
    if ' ERROR ' in f' {upper} ' or upper.startswith('ERROR'):
        return 'debug-log-list__item--error'
    if ' WARNING ' in f' {upper} ' or upper.startswith('WARNING'):
        return 'debug-log-list__item--warning'
    if ' CRITICAL ' in f' {upper} ' or upper.startswith('CRITICAL'):
        return 'debug-log-list__item--critical'
    return ''


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

    recent_lines = lines[-max_lines:]
    return [
        {'text': line, 'css_class': _log_line_css_class(line)}
        for line in recent_lines
    ], ''


@never_cache
@staff_member_required
def debug_page(request):
    log_file = Path(getattr(settings, 'DEBUG_LOG_FILE', settings.BASE_DIR / 'logs' / 'debug.log'))
    log_lines, log_message = _read_recent_log_lines(log_file)
    context = {
        'database_status': _database_status(),
        'database_info': _database_info(),
        'runtime_info': _runtime_info(),
        's3_admin_links': _s3_admin_links(),
        'use_s3_storage': getattr(settings, 'USE_S3_STORAGE', False),
        'log_file_name': log_file.name,
        'log_lines': log_lines,
        'log_message': log_message,
    }
    return render(request, 'core/debug.html', context)
