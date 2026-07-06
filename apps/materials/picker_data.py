from __future__ import annotations

from apps.materials.models import Material
from apps.workspaces.services import materials_owned_by, materials_shared_in, materials_visible_in

MATERIAL_PICKER_SCOPE_WORKSPACE = 'workspace'
MATERIAL_PICKER_SCOPE_SHARED = 'shared'


def _material_picker_item(material: Material, scopes: list[str]) -> dict:
    return {
        'material_id': str(material.pk),
        'code': material.code,
        'name': material.name,
        'label': f'{material.code} - {material.name}',
        'struct_type_name': material.struct_type.name if material.struct_type_id else 'Без типа',
        'scopes': scopes,
    }


def materials_for_picker(workspace=None) -> list[dict]:
    if workspace is None:
        materials = Material.objects.select_related('struct_type').order_by('code', 'name')
        return [
            _material_picker_item(
                item,
                [MATERIAL_PICKER_SCOPE_WORKSPACE, MATERIAL_PICKER_SCOPE_SHARED],
            )
            for item in materials
        ]

    by_pk: dict = {}
    owned_qs = materials_owned_by(workspace).select_related('struct_type')
    shared_qs = materials_shared_in(workspace).select_related('struct_type')

    for item in owned_qs:
        by_pk[item.pk] = (item, [MATERIAL_PICKER_SCOPE_WORKSPACE])

    for item in shared_qs:
        if item.pk in by_pk:
            by_pk[item.pk][1].append(MATERIAL_PICKER_SCOPE_SHARED)
        else:
            by_pk[item.pk] = (item, [MATERIAL_PICKER_SCOPE_SHARED])

    items = [
        _material_picker_item(material, scopes)
        for material, scopes in by_pk.values()
    ]
    items.sort(key=lambda row: (row['code'], row['name']))
    return items


def materials_for_picker_queryset(workspace=None):
    if workspace is not None:
        return materials_visible_in(workspace).select_related('struct_type').order_by('code', 'name')
    return Material.objects.select_related('struct_type').order_by('code', 'name')
