"""Bulk operations for materials list."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.materials.models import Material
from apps.structures.models import StructureType
from apps.structures.table_storage import delete_table_row
from apps.workspaces.permissions import can_delete_in_workspace


@dataclass
class BulkDeleteResult:
    deleted: list[str] = field(default_factory=list)
    skipped_forbidden: list[str] = field(default_factory=list)
    skipped_protected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)


def _cleanup_structure_row(struct_type_id, struct_props_id, cache: dict) -> None:
    if not struct_type_id or not struct_props_id:
        return
    if Material.objects.filter(
        struct_type_id=struct_type_id,
        struct_props_id=struct_props_id,
    ).exists():
        return
    key = str(struct_type_id)
    struct_type = cache.get(key)
    if struct_type is None:
        struct_type = StructureType.objects.filter(pk=struct_type_id, is_created=True).first()
        if struct_type is None:
            return
        cache[key] = struct_type
    try:
        delete_table_row(struct_type, uuid.UUID(str(struct_props_id)))
    except (ValueError, TypeError):
        return


def bulk_delete_materials(*, user, workspace, pks: list) -> BulkDeleteResult:
    """Delete materials the user may delete; skip protected/forbidden without aborting the batch."""
    result = BulkDeleteResult()
    if not pks:
        return result

    materials = list(
        Material.objects.filter(pk__in=pks)
        .select_related('struct_type', 'home_workspace')
        .prefetch_related('used_in_composite_layers')
    )
    by_pk = {str(m.pk): m for m in materials}
    struct_cache: dict = {}

    with transaction.atomic():
        for raw_pk in pks:
            key = str(raw_pk)
            material = by_pk.get(key)
            if material is None:
                continue
            label = f'{material.code} — {material.name}'
            if not can_delete_in_workspace(user, material, workspace):
                result.skipped_forbidden.append(label)
                continue
            if material.used_in_composite_layers.exists():
                result.skipped_protected.append(label)
                continue
            struct_type_id = material.struct_type_id
            struct_props_id = material.struct_props_id
            try:
                material.delete()
            except ProtectedError:
                result.skipped_protected.append(label)
                continue
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f'{label}: {exc}')
                continue
            result.deleted.append(label)
            _cleanup_structure_row(struct_type_id, struct_props_id, struct_cache)

    return result
