from __future__ import annotations

from apps.structures.models import StructureType


def structure_types_for_picker() -> list[dict]:
    structure_types = (
        StructureType.objects.filter(is_active=True)
        .prefetch_related('fields')
        .order_by('name')
    )
    return [
        {
            'structure_type_id': str(item.pk),
            'code': item.code,
            'name': item.name,
            'label': item.name,
            'description': (item.description or '')[:200],
            'field_count': item.fields.count(),
            'is_created': item.is_created,
            'display_color': item.display_color,
        }
        for item in structure_types
    ]
