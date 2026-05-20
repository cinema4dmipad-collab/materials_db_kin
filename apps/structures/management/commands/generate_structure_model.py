import importlib

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.structures.models import StructureType
from apps.structures.services import append_generated_model, structure_model_class_name


class Command(BaseCommand):
    help = 'Генерирует Django-модель для существующего типа структуры'

    def add_arguments(self, parser):
        parser.add_argument('structure_type_id', type=int)

    def handle(self, *args, **options):
        try:
            structure_type = StructureType.objects.prefetch_related('fields').get(
                pk=options['structure_type_id']
            )
        except StructureType.DoesNotExist as exc:
            raise CommandError(f'Тип структуры id={options["structure_type_id"]} не найден') from exc

        if not structure_type.fields.exists():
            raise CommandError(
                f'У типа «{structure_type.name}» нет полей. Добавьте поля в админке.'
            )

        try:
            class_name = append_generated_model(structure_type)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        import apps.structures.generated_models as generated_models

        importlib.reload(generated_models)

        call_command('makemigrations', 'structures', verbosity=1)
        call_command('migrate', 'structures', verbosity=1)

        self.stdout.write(
            self.style.SUCCESS(
                f'Модель {class_name} ({structure_model_class_name(structure_type.code)}) создана'
            )
        )
