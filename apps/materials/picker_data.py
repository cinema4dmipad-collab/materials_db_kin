from __future__ import annotations

from apps.materials.layer_thickness import layer_thickness_mm_by_material_id
from apps.materials.models import Material
from apps.workspaces.services import materials_in_workspace_tab, materials_shared_in, materials_visible_in

MATERIAL_PICKER_SCOPE_WORKSPACE = 'workspace'
MATERIAL_PICKER_SCOPE_SHARED = 'shared'


def _material_picker_item(material: Material, scopes: list[str], thickness_mm=None) -> dict:
    return {
        'material_id': str(material.pk),
        'code': material.code,
        'name': material.name,
        'label': f'{material.code} - {material.name}',
        'struct_type_name': material.struct_type.name if material.struct_type_id else 'Без типа',
        'scopes': scopes,
        'thickness_mm': thickness_mm,
    }


def materials_for_picker(workspace=None) -> list[dict]:
    if workspace is None:
        materials = list(
            Material.objects.select_related('struct_type').order_by('code', 'name')
        )
        thicknesses = layer_thickness_mm_by_material_id(materials)
        return [
            _material_picker_item(
                item,
                [MATERIAL_PICKER_SCOPE_WORKSPACE, MATERIAL_PICKER_SCOPE_SHARED],
                thickness_mm=thicknesses.get(item.pk),
            )
            for item in materials
        ]

    by_pk: dict = {}
    workspace_qs = materials_in_workspace_tab(workspace).select_related('struct_type')
    shared_qs = materials_shared_in(workspace).select_related('struct_type')

    for item in workspace_qs:
        by_pk[item.pk] = (item, [MATERIAL_PICKER_SCOPE_WORKSPACE])

    for item in shared_qs:
        if item.pk in by_pk:
            by_pk[item.pk][1].append(MATERIAL_PICKER_SCOPE_SHARED)
        else:
            by_pk[item.pk] = (item, [MATERIAL_PICKER_SCOPE_SHARED])

    materials = [material for material, _scopes in by_pk.values()]
    thicknesses = layer_thickness_mm_by_material_id(materials)
    items = [
        _material_picker_item(material, scopes, thickness_mm=thicknesses.get(material.pk))
        for material, scopes in by_pk.values()
    ]
    items.sort(key=lambda row: (row['code'], row['name']))
    return items


def materials_for_picker_queryset(workspace=None):
    if workspace is not None:
        return materials_visible_in(workspace).select_related('struct_type').order_by('code', 'name')
    return Material.objects.select_related('struct_type').order_by('code', 'name')
