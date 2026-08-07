from django.core.management.base import BaseCommand

from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor


class Command(BaseCommand):
    help = (
        'Добавляет колонки value/__kind/__b для DecimalField '
        'в уже созданных SQL-таблицах структур, выполняет backfill и удаляет legacy-колонки.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--structure-type',
            dest='structure_type_code',
            help='Код типа структуры (если не указан — все созданные типы).',
        )

    def handle(self, *args, **options):
        queryset = StructureType.objects.filter(is_created=True).prefetch_related('fields')
        code = options.get('structure_type_code')
        if code:
            queryset = queryset.filter(code=code)

        migrated = 0
        for structure_type in queryset:
            self.stdout.write(f'Обработка {structure_type.name} ({structure_type.table_name})...')
            add_result = SQLExecutor.add_companion_columns_for_decimal_fields(structure_type)
            if not add_result['success']:
                self.stdout.write(self.style.ERROR(f'  Ошибка ADD COLUMN: {add_result["error"]}'))
                continue
            if add_result['added']:
                self.stdout.write(
                    self.style.SUCCESS(f'  Добавлены колонки: {", ".join(add_result["added"])}')
                )
            backfill_result = SQLExecutor.backfill_decimal_companion_columns(structure_type)
            if not backfill_result['success']:
                self.stdout.write(self.style.ERROR(f'  Ошибка backfill: {backfill_result["error"]}'))
                continue
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Backfill: обновлено строк {backfill_result["updated"]}'
                )
            )
            migrate_result = SQLExecutor.migrate_legacy_decimal_columns(structure_type)
            if not migrate_result['success']:
                self.stdout.write(
                    self.style.ERROR(f'  Ошибка миграции legacy: {migrate_result["error"]}')
                )
                continue
            if migrate_result['dropped']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Удалены legacy-колонки: {", ".join(migrate_result["dropped"])}'
                    )
                )
            migrated += 1

        self.stdout.write(self.style.SUCCESS(f'Готово. Обработано типов: {migrated}'))
