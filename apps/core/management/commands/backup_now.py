from django.core.management.base import BaseCommand, CommandError

from apps.core.backup import BackupError, create_manual_volume_dump
from apps.core.models import BackupRun


class Command(BaseCommand):
    help = 'Немедленно создаёт резервную копию PostgreSQL в BACKUP_DIR.'

    def handle(self, *args, **options):
        try:
            run = create_manual_volume_dump()
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        if run.status == BackupRun.Status.FAILED:
            raise CommandError(f'Резервное копирование завершилось с ошибкой: {run.error_message}')

        self.stdout.write(
            self.style.SUCCESS(f'Резервная копия создана: {run.filename} ({run.size_bytes} байт).')
        )
