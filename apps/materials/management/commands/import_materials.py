from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.materials.imports.service import MaterialImporter
from apps.workspaces.models import Workspace


class Command(BaseCommand):
    help = 'Импорт материалов и свойств из CSV или XLSX в указанное пространство.'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='Путь к CSV или XLSX файлу')
        parser.add_argument(
            '--workspace',
            required=True,
            help='Slug домашнего пространства для импортируемых материалов',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Проверить файл и показать план без записи в БД',
        )

    def handle(self, *args, **options):
        file_path = Path(options['file'])
        workspace_slug = options['workspace'].strip()
        dry_run = options['dry_run']

        try:
            workspace = Workspace.objects.get(slug=workspace_slug, is_active=True)
        except Workspace.DoesNotExist as exc:
            raise CommandError(f'Пространство «{workspace_slug}» не найдено или неактивно.') from exc

        importer = MaterialImporter(workspace=workspace, dry_run=dry_run)
        try:
            report = importer.import_file(file_path)
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        for line in report.summary_lines():
            style = self.style.WARNING if dry_run else self.style.SUCCESS
            self.stdout.write(style(line))

        for error in report.errors:
            location = ''
            if error.row is not None:
                location = f'строка {error.row}'
                if error.column:
                    location += f', {error.column}'
                location += ': '
            self.stdout.write(self.style.ERROR(f'{location}{error.message}'))

        if not report.ok:
            raise CommandError('Импорт не выполнен из-за ошибок валидации.')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run: изменения не сохранены.'))
