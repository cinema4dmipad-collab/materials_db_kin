from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction

from apps.materials.models import Material
from apps.structures.models import StructureType
from apps.structures.table_storage import delete_table_row
from apps.workspaces.models import Workspace

SESSION_LAST_IMPORT_DEBUG = 'material_import_last_debug_batch'


@dataclass
class ImportDebugUndoResult:
    ok: bool
    deleted_materials: int = 0
    deleted_structure_rows: int = 0
    message: str = ''


def get_last_import_debug_batch(session) -> dict | None:
    raw = session.get(SESSION_LAST_IMPORT_DEBUG)
    return raw if isinstance(raw, dict) else None


def store_last_import_debug_batch(
    session,
    *,
    workspace: Workspace,
    material_ids: list[str],
) -> None:
    unique_ids = list(dict.fromkeys(material_ids))
    materials = Material.objects.filter(
        pk__in=unique_ids,
        home_workspace=workspace,
    ).values('pk', 'code', 'name', 'struct_type_id', 'struct_props_id')
    session[SESSION_LAST_IMPORT_DEBUG] = {
        'workspace_slug': workspace.slug,
        'materials': [
            {
                'id': str(row['pk']),
                'code': row['code'],
                'name': row['name'],
                'struct_type_id': str(row['struct_type_id']) if row['struct_type_id'] else '',
                'struct_props_id': str(row['struct_props_id']) if row['struct_props_id'] else '',
            }
            for row in materials
        ],
    }
    session.modified = True


def clear_last_import_debug_batch(session) -> None:
    session.pop(SESSION_LAST_IMPORT_DEBUG, None)
    session.modified = True


def undo_last_import_debug_batch(session, *, workspace: Workspace) -> ImportDebugUndoResult:
    batch = get_last_import_debug_batch(session)
    if not batch:
        return ImportDebugUndoResult(ok=False, message='Нет сохранённого результата импорта для отката.')
    if batch.get('workspace_slug') != workspace.slug:
        return ImportDebugUndoResult(
            ok=False,
            message='Последний импорт относится к другому пространству.',
        )

    items = batch.get('materials') or []
    if not items:
        clear_last_import_debug_batch(session)
        return ImportDebugUndoResult(ok=False, message='Список материалов для отката пуст.')

    deleted_materials = 0
    deleted_structure_rows = 0
    struct_type_cache: dict[str, StructureType] = {}

    with transaction.atomic():
        for item in items:
            material = Material.objects.filter(
                pk=item.get('id'),
                home_workspace=workspace,
            ).first()
            if material is None:
                continue

            struct_type_id = material.struct_type_id
            struct_props_id = material.struct_props_id
            material.delete()
            deleted_materials += 1

            if not struct_type_id or not struct_props_id:
                continue
            if Material.objects.filter(
                struct_type_id=struct_type_id,
                struct_props_id=struct_props_id,
            ).exists():
                continue

            key = str(struct_type_id)
            struct_type = struct_type_cache.get(key)
            if struct_type is None:
                struct_type = StructureType.objects.filter(pk=struct_type_id, is_created=True).first()
                if struct_type is None:
                    continue
                struct_type_cache[key] = struct_type
            try:
                delete_table_row(struct_type, uuid.UUID(str(struct_props_id)))
            except ValueError:
                continue
            deleted_structure_rows += 1

    clear_last_import_debug_batch(session)
    return ImportDebugUndoResult(
        ok=True,
        deleted_materials=deleted_materials,
        deleted_structure_rows=deleted_structure_rows,
        message=(
            f'Удалено материалов: {deleted_materials}'
            + (f', строк структуры: {deleted_structure_rows}' if deleted_structure_rows else '')
        ),
    )
