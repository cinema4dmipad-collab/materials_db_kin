from django.core.management.base import BaseCommand

from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor


class Command(BaseCommand):
    help = 'Создаёт таблицы для всех типов структур с is_created=False'

    def handle(self, *args, **options):
        to_create = StructureType.objects.filter(is_created=False).prefetch_related('fields')
        created = 0

        for structure_type in to_create:
            self.stdout.write(f'Создаю таблицу для {structure_type.name}...')
            result = SQLExecutor.create_table(structure_type)
            if result['success']:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  OK: {structure_type.table_name}'))
            else:
                self.stdout.write(self.style.ERROR(f'  Ошибка: {result["error"]}'))

        self.stdout.write(self.style.SUCCESS(f'Готово. Создано таблиц: {created}'))
