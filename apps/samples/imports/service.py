from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import DataError, transaction

from apps.core.creator import assign_creator
from apps.core.property_number_value import VALUE_KIND_SCALAR
from apps.core.tag_utils import assign_tags, merge_import_tag_names
from apps.materials.imports.material_link import resolve_material_ref
from apps.materials.imports.report import ImportReport
from apps.materials.imports.staging import DraftMaterial
from apps.materials.imports.validate import HybridImportItem, validate_drafts
from apps.references.models import Property
from apps.samples.models import Sample, SampleProperty
from apps.structures.models import StructureType
from apps.structures.table_storage import get_row, insert_row, update_row
from apps.workspaces.models import Workspace

_SQL_SKIP_KEYS = frozenset({'id', 'created_by', 'created_at', 'updated_at'})


def normalize_sample_object_type(raw: str) -> str:
    text = (raw or '').strip()
    if not text:
        return 'unset'
    keys = {key for key, _label in Sample.OBJECT_TYPES}
    if text in keys:
        return text
    folded = text.casefold()
    for key, label in Sample.OBJECT_TYPES:
        if key.casefold() == folded or label.casefold() == folded:
            return key
    return 'unset'


class SampleImporter:
    def __init__(
        self,
        *,
        workspace: Workspace,
        material: Material,
        user=None,
        dry_run: bool = False,
        source_filename: str | None = None,
    ):
        self.workspace = workspace
        self.material = material
        self.user = user
        self.dry_run = dry_run
        self.source_filename = (source_filename or '').strip()

    def import_drafts(
        self,
        drafts: list[DraftMaterial],
        *,
        structure_type: StructureType | None,
    ) -> ImportReport:
        report = ImportReport(dry_run=self.dry_run, entity_noun='образцов')
        items = validate_drafts(
            drafts,
            structure_type=structure_type,
            workspace=self.workspace,
            report=report,
            create_missing_dictionaries=False,
            dry_run=self.dry_run,
        )
        if report.errors:
            return report
        if not items:
            report.add_error(
                'Нет строк для импорта. Проверьте сопоставление «Название» '
                'и что в файле есть строки данных с названием.'
            )
            return report

        if self.dry_run:
            self._count_hybrid_planned(items, report)
            return report

        try:
            with transaction.atomic():
                applied: list[tuple[Sample, HybridImportItem]] = []
                for item in items:
                    sample = self._apply_hybrid_item(item, structure_type, report)
                    applied.append((sample, item))
                for sample, item in applied:
                    self._apply_hybrid_links(sample, item, structure_type, report)
                if report.errors:
                    transaction.set_rollback(True)
        except DataError as exc:
            report.add_error(
                'Значение не умещается в поле БД (слишком длинный текст). '
                f'Сократите название (макс. {Sample._meta.get_field("name").max_length}), '
                f'код (50), тег (50) или строковое поле. Детали: {exc}'
            )
        except Exception as exc:  # noqa: BLE001 — показываем оператору вместо голого 500
            report.add_error(f'Ошибка записи импорта: {exc}')
        return report

    def _count_hybrid_planned(self, items: list[HybridImportItem], report: ImportReport) -> None:
        material_prop_ids = set()
        if self.material:
            material_prop_ids = set(self.material.properties.values_list('property_id', flat=True))
        for item in items:
            report.materials_created += 1
            if item.tag_names:
                report.tags_merged += 1
            report.properties_created += len(material_prop_ids)
            overlay_ids = {prop.property_ref.pk for prop in item.properties}
            for prop_id in overlay_ids:
                if prop_id in material_prop_ids:
                    report.properties_updated += 1
                    report.properties_created = max(0, report.properties_created - 1)
                else:
                    report.properties_created += 1

    def _material_structure_sql(self, structure_type: StructureType | None) -> dict:
        if (
            structure_type is None
            or not self.material
            or not self.material.struct_props_id
            or str(self.material.struct_type_id) != str(structure_type.pk)
        ):
            return {}
        row = get_row(structure_type, uuid.UUID(str(self.material.struct_props_id)))
        if not row:
            return {}
        return {key: value for key, value in row.items() if key not in _SQL_SKIP_KEYS}

    def _copy_material_properties(self, sample: Sample) -> dict[str, SampleProperty]:
        copied: dict[str, SampleProperty] = {}
        if not self.material:
            return copied
        for source in self.material.properties.select_related('property'):
            row = SampleProperty.objects.create(
                sample=sample,
                property=source.property,
                value_kind=source.value_kind,
                value=source.value,
                value_b=source.value_b,
            )
            copied[str(source.property_id)] = row
        return copied

    def _apply_hybrid_item(
        self,
        item: HybridImportItem,
        structure_type: StructureType | None,
        report: ImportReport,
    ) -> Sample:
        sample = Sample(
            workspace=self.workspace,
            material=self.material,
            code=item.code,
            name=item.name or item.code,
            description=item.description or '',
            object_type=normalize_sample_object_type(item.object_type),
            struct_type=structure_type,
        )
        assign_creator(sample, self.user)
        sample.save()
        report.materials_created += 1
        report.affected_material_ids.append(str(sample.pk))

        merged_tags = merge_import_tag_names([], item.tag_names)
        if merged_tags:
            assign_tags(sample, merged_tags, workspace=self.workspace)
            report.tags_merged += 1

        copied_props = self._copy_material_properties(sample)
        report.properties_created += len(copied_props)

        field_data = {**self._material_structure_sql(structure_type), **(item.structure_sql or {})}
        if structure_type is not None and structure_type.is_created:
            row_id = insert_row(
                structure_type,
                sample.code,
                field_data,
                allow_empty_null=True,
            )
            sample.struct_props_id = row_id
            sample.struct_type = structure_type
            sample.save(update_fields=['struct_props_id', 'struct_type'])

        for prop in item.properties:
            if prop.property_ref.data_type == Property.MATERIAL_LINK_DATA_TYPE:
                continue
            existed = str(prop.property_ref.pk) in copied_props
            _, prop_created = SampleProperty.objects.update_or_create(
                sample=sample,
                property=prop.property_ref,
                defaults={
                    'value_kind': prop.value_kind,
                    'value': prop.value,
                    'value_b': prop.value_b,
                    'notes': prop.notes,
                },
            )
            if prop_created:
                report.properties_created += 1
            else:
                report.properties_updated += 1
                if existed:
                    report.properties_created = max(0, report.properties_created - 1)
        return sample

    def _apply_hybrid_links(
        self,
        sample: Sample,
        item: HybridImportItem,
        structure_type: StructureType | None,
        report: ImportReport,
    ) -> None:
        if structure_type is None:
            return
        link_sql = {}
        for field_name, raw_ref in (item.structure_link_refs or {}).items():
            try:
                linked = resolve_material_ref(raw_ref, workspace=self.workspace)
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=item.row_number, column=field_name)
                continue
            link_sql[field_name] = str(linked.pk)

        if link_sql:
            if sample.struct_props_id and str(sample.struct_type_id) == str(structure_type.pk):
                update_row(
                    structure_type,
                    uuid.UUID(str(sample.struct_props_id)),
                    link_sql,
                    allow_empty_null=True,
                )
            else:
                row_id = insert_row(
                    structure_type,
                    sample.code,
                    {**(item.structure_sql or {}), **link_sql},
                    allow_empty_null=True,
                )
                sample.struct_props_id = row_id
                sample.struct_type = structure_type
                sample.save(update_fields=['struct_props_id', 'struct_type'])

        for prop in item.properties:
            if prop.property_ref.data_type != Property.MATERIAL_LINK_DATA_TYPE:
                continue
            try:
                linked = resolve_material_ref(prop.value, workspace=self.workspace)
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=item.row_number, column='value')
                continue
            _, prop_created = SampleProperty.objects.update_or_create(
                sample=sample,
                property=prop.property_ref,
                defaults={
                    'value_kind': VALUE_KIND_SCALAR,
                    'value': str(linked.pk),
                    'value_b': None,
                    'notes': prop.notes,
                },
            )
            if prop_created:
                report.properties_created += 1
            else:
                report.properties_updated += 1
                report.properties_created = max(0, report.properties_created - 1)
