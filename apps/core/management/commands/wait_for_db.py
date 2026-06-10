import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'Ожидает доступности базы данных перед migrate/запуском'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=60,
            help='Максимальное время ожидания в секундах',
        )

    def handle(self, *args, **options):
        timeout = options['timeout']
        for second in range(timeout):
            try:
                connection.ensure_connection()
                self.stdout.write(self.style.SUCCESS('База данных доступна.'))
                return
            except OperationalError:
                if second == 0:
                    self.stdout.write('Ожидание базы данных...')
                time.sleep(1)
        raise OperationalError(f'База данных недоступна после {timeout} с.')
