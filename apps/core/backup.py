import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from django.conf import settings
from django.utils import timezone

from apps.core.models import BackupRun, BackupSettings

SCHEDULED_DUMP_NAME_RE = re.compile(r'^materials_db_\d{8}_\d{6}\.dump$')
STALE_RUNNING_AFTER = timedelta(hours=6)


class BackupError(Exception):
    """Ошибка создания резервной копии PostgreSQL."""


def is_postgresql() -> bool:
    return settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'


def ensure_pg_dump() -> str:
    pg_dump_path = shutil.which('pg_dump')
    if not pg_dump_path:
        raise BackupError('Утилита pg_dump не найдена в PATH.')
    return pg_dump_path


def get_backup_dir() -> Path:
    backup_dir = Path(settings.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_temp_dir() -> Path:
    temp_dir = get_backup_dir() / 'tmp'
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _clear_stale_backup_state() -> None:
    """Снимает зависшие RUNNING и устаревший lock-файл после краша процесса."""
    cutoff = timezone.now() - STALE_RUNNING_AFTER
    BackupRun.objects.filter(status=BackupRun.Status.RUNNING, started_at__lt=cutoff).update(
        status=BackupRun.Status.FAILED,
        finished_at=timezone.now(),
        error_message='Прервано: процесс резервного копирования не завершился.',
    )

    lock_path = get_backup_dir() / '.backup.lock'
    if not lock_path.exists():
        return
    if BackupRun.objects.filter(status=BackupRun.Status.RUNNING).exists():
        return
    try:
        age = timezone.now().timestamp() - lock_path.stat().st_mtime
    except OSError:
        return
    if age > STALE_RUNNING_AFTER.total_seconds():
        lock_path.unlink(missing_ok=True)


@contextmanager
def backup_lock() -> Iterator[None]:
    """Запрещает параллельные процессы резервного копирования."""
    _clear_stale_backup_state()

    if BackupRun.objects.filter(status=BackupRun.Status.RUNNING).exists():
        raise BackupError('Резервное копирование уже выполняется.')

    lock_path = get_backup_dir() / '.backup.lock'
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BackupError('Резервное копирование уже выполняется.') from exc

    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as lock_file:
            lock_file.write(str(os.getpid()))
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def run_pg_dump(output_path: Path) -> None:
    if not is_postgresql():
        raise BackupError('Резервное копирование доступно только для PostgreSQL.')

    database = settings.DATABASES['default']
    command = [
        ensure_pg_dump(),
        '-Fc',
        '-f',
        str(output_path),
        '-h',
        database['HOST'],
        '-p',
        str(database['PORT']),
        '-U',
        database['USER'],
        database['NAME'],
    ]
    environment = os.environ.copy()
    if password := database.get('PASSWORD'):
        environment['PGPASSWORD'] = password

    try:
        subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise BackupError(f'pg_dump завершился с ошибкой: {message}') from exc
    except OSError as exc:
        raise BackupError(f'Не удалось запустить pg_dump: {exc}') from exc


def apply_retention(retention_count: int) -> None:
    """Удаляет только именованные scheduled-дампы, не трогая tmp/."""
    keep = max(int(retention_count), 1)
    backups = sorted(
        (
            path
            for path in get_backup_dir().glob('*.dump')
            if SCHEDULED_DUMP_NAME_RE.match(path.name)
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for backup_path in backups[keep:]:
        backup_path.unlink(missing_ok=True)


def _complete_run(run: BackupRun, output_path: Path) -> BackupRun:
    run.status = BackupRun.Status.SUCCESS
    run.finished_at = timezone.now()
    run.filename = output_path.name
    run.size_bytes = output_path.stat().st_size
    run.error_message = ''
    run.save(
        update_fields=[
            'status',
            'finished_at',
            'filename',
            'size_bytes',
            'error_message',
        ]
    )
    return run


def _fail_run(run: BackupRun, error: Exception, output_path: Path) -> BackupRun:
    output_path.unlink(missing_ok=True)
    run.status = BackupRun.Status.FAILED
    run.finished_at = timezone.now()
    run.error_message = str(error)
    run.save(update_fields=['status', 'finished_at', 'error_message'])
    return run


def _has_successful_scheduled_today(local_now: datetime) -> bool:
    return BackupRun.objects.filter(
        trigger=BackupRun.Trigger.SCHEDULED,
        status=BackupRun.Status.SUCCESS,
        started_at__date=local_now.date(),
    ).exists()


SCHEDULE_GRACE = timedelta(minutes=15)


def should_run_scheduled(now: datetime | None = None) -> bool:
    backup_settings = BackupSettings.get_solo()
    if not backup_settings.enabled:
        return False

    local_now = timezone.localtime(now or timezone.now())
    if _has_successful_scheduled_today(local_now):
        return False

    scheduled = local_now.replace(
        hour=backup_settings.schedule_hour,
        minute=backup_settings.schedule_minute,
        second=0,
        microsecond=0,
    )
    return scheduled <= local_now < scheduled + SCHEDULE_GRACE


def create_volume_dump(*, trigger: str, user=None, enforce_daily_once: bool = False) -> BackupRun | None:
    """Создаёт дамп в BACKUP_DIR и применяет retention.

    При enforce_daily_once=True и уже существующем успешном scheduled-дампе за сегодня
    возвращает None (без ошибки) — удобно для cron при гонке двух вызовов.
    """
    with backup_lock():
        local_now = timezone.localtime()
        if enforce_daily_once and _has_successful_scheduled_today(local_now):
            return None

        timestamp = local_now.strftime('%Y%m%d_%H%M%S')
        output_path = get_backup_dir() / f'materials_db_{timestamp}.dump'
        run = BackupRun.objects.create(
            trigger=trigger,
            status=BackupRun.Status.RUNNING,
            filename=output_path.name,
            created_by=user,
        )
        try:
            run_pg_dump(output_path)
        except Exception as exc:
            return _fail_run(run, exc, output_path)

        _complete_run(run, output_path)
        apply_retention(BackupSettings.get_solo().retention_count)
        return run


def create_scheduled_dump(user=None) -> BackupRun | None:
    return create_volume_dump(
        trigger=BackupRun.Trigger.SCHEDULED,
        user=user,
        enforce_daily_once=True,
    )


def create_manual_volume_dump(user=None) -> BackupRun:
    return create_volume_dump(trigger=BackupRun.Trigger.MANUAL, user=user)


def create_manual_temp_dump(user=None) -> tuple[BackupRun, Path]:
    with backup_lock():
        with tempfile.NamedTemporaryFile(
            suffix='.dump',
            prefix='materials_db_',
            dir=get_temp_dir(),
            delete=False,
        ) as temporary_file:
            output_path = Path(temporary_file.name)

        run = BackupRun.objects.create(
            trigger=BackupRun.Trigger.MANUAL,
            status=BackupRun.Status.RUNNING,
            filename=output_path.name,
            created_by=user,
        )
        try:
            run_pg_dump(output_path)
            return _complete_run(run, output_path), output_path
        except Exception as exc:
            _fail_run(run, exc, output_path)
            return run, output_path
