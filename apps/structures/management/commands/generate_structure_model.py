from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Сообщает, что генерация Django-моделей для структур отключена'

    def add_arguments(self, parser):
        parser.add_argument('structure_type_id', type=int)

    def handle(self, *args, **options):
        raise CommandError(
            'Dynamic Django model generation is disabled. '
            'Use sync_structure_tables or the admin create-table action to create SQL-only '
            'dynamic structure tables.'
        )
