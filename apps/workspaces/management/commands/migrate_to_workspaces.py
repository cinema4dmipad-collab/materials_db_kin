from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.workspaces.models import WorkspaceMembership, WorkspaceRole
from apps.workspaces.services import ensure_legacy_workspace

User = get_user_model()


def _model_has_field(model, field_name: str) -> bool:
    return any(field.name == field_name for field in model._meta.get_fields())


class Command(BaseCommand):
    help = 'Создаёт Legacy workspace и привязывает существующие данные и пользователей.'

    def handle(self, *args, **options):
        with transaction.atomic():
            legacy = ensure_legacy_workspace()
            self.stdout.write(self.style.SUCCESS(f'Workspace: {legacy.name} ({legacy.slug})'))

            self._assign_materials(legacy)
            self._assign_structure_types(legacy)
            self._assign_samples(legacy)
            self._assign_scans(legacy)
            self._assign_attachments(legacy)
            self._assign_tags(legacy)
            self._assign_memberships(legacy)

        self.stdout.write(self.style.SUCCESS('Миграция на workspaces завершена.'))

    def _assign_materials(self, legacy):
        try:
            from apps.materials.models import Material
        except ImportError:
            return
        if not _model_has_field(Material, 'home_workspace'):
            self.stdout.write('Material.home_workspace отсутствует — пропуск.')
            return
        updated = Material.objects.filter(home_workspace__isnull=True).update(
            home_workspace=legacy,
        )
        if _model_has_field(Material, 'visibility_mode'):
            Material.objects.filter(home_workspace=legacy).update(visibility_mode='all_workspaces')
        self.stdout.write(f'Material: обновлено {updated} записей.')

    def _assign_structure_types(self, legacy):
        try:
            from apps.structures.models import StructureType
        except ImportError:
            return
        if not _model_has_field(StructureType, 'home_workspace'):
            self.stdout.write('StructureType.home_workspace отсутствует — пропуск.')
            return
        updated = StructureType.objects.filter(home_workspace__isnull=True).update(
            home_workspace=legacy,
        )
        if _model_has_field(StructureType, 'visibility_mode'):
            StructureType.objects.filter(home_workspace=legacy).update(
                visibility_mode='all_workspaces'
            )
        self.stdout.write(f'StructureType: обновлено {updated} записей.')

    def _assign_samples(self, legacy):
        try:
            from apps.samples.models import Sample
        except ImportError:
            return
        if not _model_has_field(Sample, 'workspace'):
            self.stdout.write('Sample.workspace отсутствует — пропуск.')
            return
        updated = Sample.objects.filter(workspace__isnull=True).update(workspace=legacy)
        self.stdout.write(f'Sample: обновлено {updated} записей.')

    def _assign_scans(self, legacy):
        try:
            from apps.scans.models import ScanRecord
        except ImportError:
            return
        if _model_has_field(ScanRecord, 'workspace'):
            updated = ScanRecord.objects.filter(workspace__isnull=True).update(workspace=legacy)
            self.stdout.write(f'ScanRecord: обновлено {updated} записей.')
            return
        if _model_has_field(ScanRecord, 'sample'):
            from apps.samples.models import Sample

            if _model_has_field(Sample, 'workspace'):
                self.stdout.write('ScanRecord.workspace отсутствует — сканы через Sample.workspace.')
            return
        self.stdout.write('ScanRecord.workspace отсутствует — пропуск.')

    def _assign_attachments(self, legacy):
        for import_path, label in (
            ('apps.samples.models', 'SampleAttachment'),
            ('apps.materials.models', 'MaterialAttachment'),
        ):
            try:
                module = __import__(import_path, fromlist=[label])
                model = getattr(module, label)
            except (ImportError, AttributeError):
                continue
            if not _model_has_field(model, 'workspace'):
                self.stdout.write(f'{label}.workspace отсутствует — пропуск.')
                continue
            updated = model.objects.filter(workspace__isnull=True).update(workspace=legacy)
            self.stdout.write(f'{label}: обновлено {updated} записей.')

    def _assign_memberships(self, legacy):
        created = 0
        for user in User.objects.all():
            _, was_created = WorkspaceMembership.objects.get_or_create(
                workspace=legacy,
                user=user,
                defaults={'role': WorkspaceRole.MANAGER},
            )
            if was_created:
                created += 1
        self.stdout.write(f'WorkspaceMembership: создано {created} записей.')

    def _assign_tags(self, legacy):
        try:
            from apps.core.models import Tag
        except ImportError:
            return
        if not _model_has_field(Tag, 'workspace'):
            self.stdout.write('Tag.workspace отсутствует — пропуск.')
            return
        updated = Tag.objects.filter(workspace__isnull=True).update(workspace=legacy)
        self.stdout.write(f'Tag: обновлено {updated} записей.')
