from django.core.management.base import BaseCommand

from apps.structures.models import StructureType
from apps.structures.table_generator import TableGenerator


class Command(BaseCommand):
    help = 'Создаёт таблицы для всех типов структур с is_created=False'

    def handle(self, *args, **options):
        to_create = StructureType.objects.filter(is_created=False).prefetch_related('fields')
        created = 0

        for structure_type in to_create:
            if not structure_type.fields.exists():
                self.stdout.write(
                    self.style.WARNING(f'  Пропуск {structure_type.name}: нет полей')
                )
                continue
            self.stdout.write(f'Создаю таблицу для {structure_type.name}...')
            try:
                TableGenerator.create_table(structure_type)
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  OK: {structure_type.table_name}'))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'  Ошибка: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'Готово. Создано таблиц: {created}'))
