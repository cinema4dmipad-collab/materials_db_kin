from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.core.backup import BackupError, create_scheduled_dump, should_run_scheduled
from apps.core.models import BackupRun


class Command(BaseCommand):
    help = 'Создаёт резервную копию PostgreSQL по расписанию, если её время наступило.'

    def handle(self, *args, **options):
        try:
            due = should_run_scheduled()
        except DatabaseError as exc:
            self.stderr.write(f'База ещё не готова к бэкапу: {exc}')
            return

        if not due:
            self.stdout.write('Резервное копирование по расписанию пока не требуется.')
            return

        try:
            run = create_scheduled_dump()
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        except DatabaseError as exc:
            self.stderr.write(f'База ещё не готова к бэкапу: {exc}')
            return

        if run is None:
            self.stdout.write('Успешная резервная копия на сегодня уже создана.')
            return

        if run.status == BackupRun.Status.FAILED:
            raise CommandError(f'Резервное копирование завершилось с ошибкой: {run.error_message}')

        self.stdout.write(
            self.style.SUCCESS(f'Резервная копия создана: {run.filename} ({run.size_bytes} байт).')
        )
