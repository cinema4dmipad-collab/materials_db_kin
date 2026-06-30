from __future__ import annotations

from apps.materials.models import Material
from apps.workspaces.services import materials_visible_in


def materials_for_picker(workspace=None) -> list[dict]:
    if workspace is not None:
        materials = materials_visible_in(workspace)
    else:
        materials = Material.objects.all()
    materials = materials.select_related('struct_type').order_by('code', 'name')
    return [
        {
            'material_id': str(item.pk),
            'code': item.code,
            'name': item.name,
            'label': f'{item.code} - {item.name}',
            'struct_type_name': item.struct_type.name if item.struct_type_id else 'Без типа',
        }
        for item in materials
    ]
