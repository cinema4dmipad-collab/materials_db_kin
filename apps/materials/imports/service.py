from __future__ import annotations

import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import DataError, transaction

from apps.core.tag_utils import assign_tags, merge_import_tag_names
from apps.core.property_number_value import VALUE_KIND_SCALAR
from apps.materials.imports.material_link import resolve_material_ref
from apps.materials.imports.readers import read_import_file
from apps.materials.imports.report import ImportReport
from apps.materials.imports.source_note import with_import_source_note
from apps.materials.imports.staging import DraftMaterial
from apps.materials.imports.validate import HybridImportItem, validate_drafts, validate_rows
from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property
from apps.structures.models import StructureType
from apps.structures.table_storage import insert_row, update_row
from apps.workspaces.models import Workspace


class MaterialImporter:
    def __init__(
        self,
        *,
        workspace: Workspace,
        dry_run: bool = False,
        source_filename: str | None = None,
    ):
        self.workspace = workspace
        self.dry_run = dry_run
        self.source_filename = (source_filename or '').strip()

    def import_file(self, path: Path | str) -> ImportReport:
        file_path = Path(path)
        if not self.source_filename:
            self.source_filename = file_path.name
        rows = read_import_file(file_path)
        return self.import_rows(rows)

    def import_rows(self, rows: list[dict]) -> ImportReport:
        report = ImportReport(dry_run=self.dry_run)
        items = validate_rows(rows, workspace=self.workspace, report=report)
        if report.errors:
            return report
        if not items:
            report.add_error('Нет строк для импорта.')
            return report

        if self.dry_run:
            self._count_planned(items, report)
            return report

        try:
            with transaction.atomic():
                for item in items:
                    self._apply_legacy_item(item, report, resolve_links=False)
                for item in items:
                    self._apply_legacy_material_links(item, report)
                if report.errors:
                    transaction.set_rollback(True)
        except DataError as exc:
            report.add_error(
                'Значение не умещается в поле БД (слишком длинный текст). '
                f'Сократите название/код/тег или строковое поле. Детали: {exc}'
            )
        return report

    def import_drafts(
        self,
        drafts: list[DraftMaterial],
        *,
        structure_type: StructureType,
    ) -> ImportReport:
        report = ImportReport(dry_run=self.dry_run)
        items = validate_drafts(
            drafts,
            structure_type=structure_type,
            workspace=self.workspace,
            report=report,
        )
        if report.errors:
            return report
        if not items:
            report.add_error('Нет строк для импорта.')
            return report

        if self.dry_run:
            self._count_hybrid_planned(items, report)
            return report

        try:
            with transaction.atomic():
                applied: list[tuple[Material, HybridImportItem]] = []
                for item in items:
                    material = self._apply_hybrid_item(item, structure_type, report)
                    applied.append((material, item))
                for material, item in applied:
                    self._apply_hybrid_links(material, item, structure_type, report)
                if report.errors:
                    transaction.set_rollback(True)
        except DataError as exc:
            report.add_error(
                'Значение не умещается в поле БД (слишком длинный текст). '
                f'Сократите название (макс. {Material._meta.get_field("name").max_length}), '
                f'код (50), тег (50) или строковое поле. Детали: {exc}'
            )
        return report

    def _count_planned(self, items, report: ImportReport) -> None:
        codes = [item.code for item in items]
        existing = set(
            Material.objects.filter(
                home_workspace=self.workspace,
                code__in=codes,
            ).values_list('code', flat=True)
        )
        existing_properties = {
            (material_id, property_id)
            for material_id, property_id in MaterialProperty.objects.filter(
                material__home_workspace=self.workspace,
                material__code__in=codes,
            ).values_list('material_id', 'property_id')
        }
        material_ids_by_code = dict(
            Material.objects.filter(
                home_workspace=self.workspace,
                code__in=codes,
            ).values_list('code', 'id')
        )

        for item in items:
            if item.code in existing:
                report.materials_updated += 1
            else:
                report.materials_created += 1
            if item.tag_names:
                report.tags_merged += 1

            material_id = material_ids_by_code.get(item.code)
            for prop in item.properties:
                key = (material_id, prop.property_ref.pk) if material_id else None
                if key and key in existing_properties:
                    report.properties_updated += 1
                else:
                    report.properties_created += 1

    def _count_hybrid_planned(self, items: list[HybridImportItem], report: ImportReport) -> None:
        existing_codes = set(
            Material.objects.filter(
                home_workspace=self.workspace,
                code__in=[item.code for item in items],
            ).values_list('code', flat=True)
        )
        existing_properties = {
            (material_id, property_id)
            for material_id, property_id in MaterialProperty.objects.filter(
                material__home_workspace=self.workspace,
                material__code__in=[item.code for item in items],
            ).values_list('material_id', 'property_id')
        }
        material_ids_by_code = dict(
            Material.objects.filter(
                home_workspace=self.workspace,
                code__in=[item.code for item in items],
            ).values_list('code', 'id')
        )

        for item in items:
            if item.action == 'update' or item.code in existing_codes:
                report.materials_updated += 1
            else:
                report.materials_created += 1
            if item.tag_names:
                report.tags_merged += 1
            material_id = material_ids_by_code.get(item.code)
            for prop in item.properties:
                key = (material_id, prop.property_ref.pk) if material_id else None
                if key and key in existing_properties:
                    report.properties_updated += 1
                else:
                    report.properties_created += 1

    def _apply_legacy_item(self, item, report: ImportReport, *, resolve_links: bool = True) -> None:
        defaults = {
            'description': item.description,
        }
        if item.name:
            defaults['name'] = item.name
        if item.struct_type is not None:
            defaults['struct_type'] = item.struct_type

        material, created = Material.objects.update_or_create(
            home_workspace=self.workspace,
            code=item.code,
            defaults=defaults,
        )
        if created:
            report.materials_created += 1
            self._mark_created_from_import(material)
        else:
            report.materials_updated += 1
        report.affected_material_ids.append(str(material.pk))

        if item.tag_names:
            existing_names = list(material.tags.values_list('name', flat=True))
            merged = merge_import_tag_names(existing_names, item.tag_names)
            assign_tags(material, merged, workspace=self.workspace)
            report.tags_merged += 1

        for prop in item.properties:
            if (
                not resolve_links
                and prop.property_ref.data_type == Property.MATERIAL_LINK_DATA_TYPE
            ):
                continue
            value = prop.value
            if (
                resolve_links
                and prop.property_ref.data_type == Property.MATERIAL_LINK_DATA_TYPE
            ):
                linked = resolve_material_ref(prop.value, workspace=self.workspace)
                value = str(linked.pk)
            _, prop_created = MaterialProperty.objects.update_or_create(
                material=material,
                property=prop.property_ref,
                defaults={
                    'value_kind': prop.value_kind,
                    'value': value,
                    'value_b': prop.value_b,
                    'notes': prop.notes,
                },
            )
            if prop_created:
                report.properties_created += 1
            else:
                report.properties_updated += 1

    def _apply_legacy_material_links(self, item, report: ImportReport) -> None:
        material = Material.objects.get(home_workspace=self.workspace, code=item.code)
        for prop in item.properties:
            if prop.property_ref.data_type != Property.MATERIAL_LINK_DATA_TYPE:
                continue
            try:
                linked = resolve_material_ref(prop.value, workspace=self.workspace)
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=prop.row_number, column='value')
                continue
            _, prop_created = MaterialProperty.objects.update_or_create(
                material=material,
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

    def _mark_created_from_import(self, material: Material) -> None:
        if not self.source_filename:
            return
        description = with_import_source_note(material.description, self.source_filename)
        if description == (material.description or '').strip():
            return
        material.description = description
        material.save(update_fields=['description', 'updated_at'])

    def _apply_hybrid_item(
        self,
        item: HybridImportItem,
        structure_type: StructureType,
        report: ImportReport,
    ) -> Material:
        defaults = {
            'description': item.description,
            'struct_type': structure_type,
        }
        if item.name:
            defaults['name'] = item.name

        if item.existing_pk:
            material = Material.objects.get(pk=item.existing_pk, home_workspace=self.workspace)
            for key, value in defaults.items():
                setattr(material, key, value)
            material.save()
            created = False
        else:
            material, created = Material.objects.update_or_create(
                home_workspace=self.workspace,
                code=item.code,
                defaults=defaults,
            )

        if created:
            report.materials_created += 1
            self._mark_created_from_import(material)
        else:
            report.materials_updated += 1
        report.affected_material_ids.append(str(material.pk))

        if item.tag_names:
            existing_names = list(material.tags.values_list('name', flat=True))
            merged = merge_import_tag_names(existing_names, item.tag_names)
            assign_tags(material, merged, workspace=self.workspace)
            report.tags_merged += 1

        if item.structure_sql:
            if material.struct_props_id and str(material.struct_type_id) == str(structure_type.pk):
                update_row(
                    structure_type,
                    uuid.UUID(str(material.struct_props_id)),
                    item.structure_sql,
                    allow_empty_null=True,
                )
            else:
                row_id = insert_row(
                    structure_type,
                    material.code,
                    item.structure_sql,
                    allow_empty_null=True,
                )
                material.struct_props_id = row_id
                material.struct_type = structure_type
                material.save(update_fields=['struct_props_id', 'struct_type', 'updated_at'])

        for prop in item.properties:
            if prop.property_ref.data_type == Property.MATERIAL_LINK_DATA_TYPE:
                continue
            _, prop_created = MaterialProperty.objects.update_or_create(
                material=material,
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
        return material

    def _apply_hybrid_links(
        self,
        material: Material,
        item: HybridImportItem,
        structure_type: StructureType,
        report: ImportReport,
    ) -> None:
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
            if material.struct_props_id and str(material.struct_type_id) == str(structure_type.pk):
                update_row(
                    structure_type,
                    uuid.UUID(str(material.struct_props_id)),
                    link_sql,
                    allow_empty_null=True,
                )
            else:
                row_id = insert_row(
                    structure_type,
                    material.code,
                    {**(item.structure_sql or {}), **link_sql},
                    allow_empty_null=True,
                )
                material.struct_props_id = row_id
                material.struct_type = structure_type
                material.save(update_fields=['struct_props_id', 'struct_type', 'updated_at'])

        for prop in item.properties:
            if prop.property_ref.data_type != Property.MATERIAL_LINK_DATA_TYPE:
                continue
            try:
                linked = resolve_material_ref(prop.value, workspace=self.workspace)
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=item.row_number, column='value')
                continue
            _, prop_created = MaterialProperty.objects.update_or_create(
                material=material,
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
