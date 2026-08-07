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
# Короткий TTL: после restore из чужого дампа часто остаётся RUNNING без процесса.
STALE_RUNNING_AFTER = timedelta(minutes=10)


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


def list_server_dumps() -> list[tuple[str, str]]:
    """Список .dump в BACKUP_DIR для выбора в UI: (filename, label)."""
    backup_dir = get_backup_dir()
    items: list[tuple[str, str, float]] = []
    for path in backup_dir.glob('*.dump'):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        size_kb = max(stat.st_size / 1024, 0.1)
        label = f'{path.name} ({size_kb:.1f} КБ)'
        items.append((path.name, label, stat.st_mtime))
    items.sort(key=lambda row: row[2], reverse=True)
    return [(name, label) for name, label, _mtime in items]


def resolve_server_dump(filename: str) -> Path:
    """Безопасно резолвит имя файла внутри BACKUP_DIR."""
    name = Path(filename).name
    if not name or name != filename or not name.endswith('.dump'):
        raise BackupError('Некорректное имя файла дампа.')
    backup_dir = get_backup_dir().resolve()
    path = (backup_dir / name).resolve()
    if path.parent != backup_dir or not path.is_file():
        raise BackupError('Файл дампа на сервере не найден.')
    return path


def delete_server_dump(filename: str) -> str:
    """Удаляет .dump с тома и отвязывает его от записей BackupRun."""
    path = resolve_server_dump(filename)
    name = path.name
    path.unlink()
    BackupRun.objects.filter(filename=name).update(filename='')
    return name


def assert_pg_custom_dump(path: Path) -> None:
    """Проверяет сигнатуру custom-format pg_dump (PGDMP)."""
    try:
        with path.open('rb') as handle:
            magic = handle.read(5)
    except OSError as exc:
        raise BackupError(f'Не удалось прочитать файл дампа: {exc}') from exc
    if magic != b'PGDMP':
        raise BackupError(
            'Файл не похож на целый дамп pg_dump (-Fc). '
            'Возможно, скачивание оборвалось — скачайте снова через «Скачать» в таблице '
            'или скопируйте файл на рабочий стол и загрузите копию.'
        )


def _clear_stale_backup_state() -> None:
    """Снимает зависшие RUNNING и устаревший lock-файл после краша / restore."""
    now = timezone.now()
    cutoff = now - STALE_RUNNING_AFTER
    BackupRun.objects.filter(status=BackupRun.Status.RUNNING, started_at__lt=cutoff).update(
        status=BackupRun.Status.FAILED,
        finished_at=now,
        error_message='Прервано: процесс резервного копирования не завершился.',
    )

    lock_path = get_backup_dir() / '.backup.lock'
    if lock_path.exists():
        if BackupRun.objects.filter(status=BackupRun.Status.RUNNING).exists():
            return
        try:
            age = now.timestamp() - lock_path.stat().st_mtime
        except OSError:
            return
        if age > STALE_RUNNING_AFTER.total_seconds():
            lock_path.unlink(missing_ok=True)
        return

    # Нет lock-файла, но в БД есть RUNNING — сирота (краш воркера или restore дампа).
    BackupRun.objects.filter(status=BackupRun.Status.RUNNING).update(
        status=BackupRun.Status.FAILED,
        finished_at=now,
        error_message=(
            'Прервано: запуск остался в статусе «выполняется» без активного процесса '
            '(часто после восстановления дампа).'
        ),
    )


def cancel_running_backups(*, reason: str = 'Отменено администратором.') -> int:
    """Принудительно завершает все RUNNING и снимает lock."""
    now = timezone.now()
    updated = BackupRun.objects.filter(status=BackupRun.Status.RUNNING).update(
        status=BackupRun.Status.FAILED,
        finished_at=now,
        error_message=reason,
    )
    lock_path = get_backup_dir() / '.backup.lock'
    lock_path.unlink(missing_ok=True)
    return updated


def get_running_backup() -> BackupRun | None:
    _clear_stale_backup_state()
    return BackupRun.objects.filter(status=BackupRun.Status.RUNNING).order_by('-started_at').first()


@contextmanager
def backup_lock() -> Iterator[None]:
    """Запрещает параллельные процессы резервного копирования."""
    _clear_stale_backup_state()

    if BackupRun.objects.filter(status=BackupRun.Status.RUNNING).exists():
        raise BackupError(
            'Резервное копирование уже выполняется или остался зависший запуск. '
            'Нажмите «Сбросить зависший запуск» на странице бэкапов и повторите.'
        )

    lock_path = get_backup_dir() / '.backup.lock'
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BackupError(
            'Резервное копирование уже выполняется или остался зависший запуск. '
            'Нажмите «Сбросить зависший запуск» на странице бэкапов и повторите.'
        ) from exc

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
    timeout = int(getattr(settings, 'BACKUP_SUBPROCESS_TIMEOUT', 1800))
    command = [
        ensure_pg_dump(),
        '-Fc',
        # Не ждать блокировки бесконечно (иначе кнопка «висит» в браузере).
        '--lock-wait-timeout=60000',
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
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupError(
            f'pg_dump превысил лимит времени ({timeout} с). Повторите позже или увеличьте BACKUP_SUBPROCESS_TIMEOUT.'
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise BackupError(f'pg_dump завершился с ошибкой: {message}') from exc
    except OSError as exc:
        raise BackupError(f'Не удалось запустить pg_dump: {exc}') from exc


def ensure_pg_restore() -> str:
    pg_restore_path = shutil.which('pg_restore')
    if not pg_restore_path:
        raise BackupError('Утилита pg_restore не найдена в PATH.')
    return pg_restore_path


def run_pg_restore(dump_path: Path) -> None:
    """Восстанавливает custom-format dump (-Fc) в текущую БД."""
    if not is_postgresql():
        raise BackupError('Восстановление доступно только для PostgreSQL.')
    if not dump_path.is_file():
        raise BackupError('Файл дампа не найден.')
    assert_pg_custom_dump(dump_path)

    database = settings.DATABASES['default']
    command = [
        ensure_pg_restore(),
        '--clean',
        '--if-exists',
        '--no-owner',
        '--no-acl',
        '-h',
        database['HOST'],
        '-p',
        str(database['PORT']),
        '-U',
        database['USER'],
        '-d',
        database['NAME'],
        str(dump_path),
    ]
    environment = os.environ.copy()
    if password := database.get('PASSWORD'):
        environment['PGPASSWORD'] = password

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=environment,
            timeout=int(getattr(settings, 'BACKUP_SUBPROCESS_TIMEOUT', 1800)),
        )
    except subprocess.TimeoutExpired as exc:
        timeout = int(getattr(settings, 'BACKUP_SUBPROCESS_TIMEOUT', 1800))
        raise BackupError(
            f'pg_restore превысил лимит времени ({timeout} с). Повторите позже или увеличьте BACKUP_SUBPROCESS_TIMEOUT.'
        ) from exc
    except OSError as exc:
        raise BackupError(f'Не удалось запустить pg_restore: {exc}') from exc

    if completed.returncode == 0:
        return

    combined = '\n'.join(
        part for part in ((completed.stderr or '').strip(), (completed.stdout or '').strip()) if part
    )
    # pg_restore often returns 1 for non-fatal warnings; fail on real errors.
    if completed.returncode > 1 or 'error:' in combined.lower():
        raise BackupError(f'pg_restore завершился с ошибкой: {combined or completed.returncode}')


def restore_from_dump(*, dump_path: Path, original_name: str = '', user=None) -> BackupRun:
    """Применяет дамп к БД. BackupRun пишется после restore (старая история затирается дампом)."""
    size_bytes = dump_path.stat().st_size if dump_path.is_file() else None
    display_name = (original_name or dump_path.name)[:255]

    with backup_lock():
        try:
            run_pg_restore(dump_path)
        except BackupError:
            raise

        # Дамп мог вернуть старые RUNNING-записи — сбрасываем, не трогая текущий lock.
        BackupRun.objects.filter(status=BackupRun.Status.RUNNING).update(
            status=BackupRun.Status.FAILED,
            finished_at=timezone.now(),
            error_message='Сброшено после восстановления дампа.',
        )

        from django.db import IntegrityError

        try:
            return BackupRun.objects.create(
                trigger=BackupRun.Trigger.RESTORE,
                status=BackupRun.Status.SUCCESS,
                finished_at=timezone.now(),
                filename=display_name,
                size_bytes=size_bytes,
                created_by=user,
            )
        except IntegrityError:
            # Дамп с другого стенда может не содержать текущего пользователя.
            return BackupRun.objects.create(
                trigger=BackupRun.Trigger.RESTORE,
                status=BackupRun.Status.SUCCESS,
                finished_at=timezone.now(),
                filename=display_name,
                size_bytes=size_bytes,
                created_by=None,
            )


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


def _last_successful_scheduled() -> BackupRun | None:
    return (
        BackupRun.objects.filter(
            trigger=BackupRun.Trigger.SCHEDULED,
            status=BackupRun.Status.SUCCESS,
        )
        .order_by('-started_at')
        .first()
    )


def _schedule_interval_elapsed(local_now: datetime, interval_days: int) -> bool:
    """True, если с последнего успешного scheduled-дампа прошло >= interval_days."""
    last = _last_successful_scheduled()
    if last is None:
        return True
    last_local = timezone.localtime(last.started_at)
    days_since = (local_now.date() - last_local.date()).days
    return days_since >= max(int(interval_days), 1)


SCHEDULE_GRACE = timedelta(minutes=15)


def should_run_scheduled(now: datetime | None = None) -> bool:
    backup_settings = BackupSettings.get_solo()
    if not backup_settings.enabled:
        return False

    local_now = timezone.localtime(now or timezone.now())
    scheduled = local_now.replace(
        hour=backup_settings.schedule_hour,
        minute=backup_settings.schedule_minute,
        second=0,
        microsecond=0,
    )
    if not (scheduled <= local_now < scheduled + SCHEDULE_GRACE):
        return False

    return _schedule_interval_elapsed(local_now, backup_settings.interval_days)


def create_volume_dump(*, trigger: str, user=None, enforce_daily_once: bool = False) -> BackupRun | None:
    """Создаёт дамп в BACKUP_DIR и применяет retention.

    При enforce_daily_once=True повторный scheduled-дамп в пределах interval_days
    возвращает None (без ошибки) — удобно для cron при гонке двух вызовов.
    """
    with backup_lock():
        local_now = timezone.localtime()
        if enforce_daily_once:
            interval_days = BackupSettings.get_solo().interval_days
            if not _schedule_interval_elapsed(local_now, interval_days):
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
