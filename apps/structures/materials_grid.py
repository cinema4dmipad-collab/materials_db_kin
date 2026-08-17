"""Materials × structure-fields matrix for the structure records list."""

from __future__ import annotations

from apps.core.unit_display import split_label_and_unit
from apps.materials.structure_display import (
    STRUCTURE_SERVICE_COLUMNS,
    structure_field_display_value,
)
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor


def structure_data_fields(structure_type: StructureType) -> list:
    return list(
        structure_type.fields.exclude(name__in=STRUCTURE_SERVICE_COLUMNS)
        .exclude(field_type='ForeignKey')
        .order_by('sort_order', 'name')
    )


def structure_field_headers(fields) -> list[dict]:
    seen: dict[str, int] = {}
    columns: list[dict] = []
    for field in fields:
        label = (field.label or field.name or 'Поле').strip()
        count = seen.get(label, 0) + 1
        seen[label] = count
        if count > 1:
            label = f'{label} ({field.name})'
        label_base, unit = split_label_and_unit(label)
        columns.append(
            {
                'name': field.name,
                'label': label,
                'label_base': label_base or label,
                'unit': unit,
            }
        )
    return columns


def structure_sql_rows_by_id(structure_type: StructureType) -> dict[str, dict]:
    result = SQLExecutor.get_all(structure_type, limit=None, offset=0)
    if not result.get('success'):
        return {}
    return {
        str(record['id']): record
        for record in (result.get('records') or [])
        if record.get('id') is not None
    }


def _rows_by_id(structure_type: StructureType) -> dict[str, dict]:
    return structure_sql_rows_by_id(structure_type)


def _cell_display(field, structure_params: dict | None) -> str:
    if not structure_params:
        return '—'
    try:
        return structure_field_display_value(
            field,
            structure_params.get(field.name),
            structure_params=structure_params,
        )
    except Exception:  # noqa: BLE001
        raw = structure_params.get(field.name)
        return '—' if raw is None or raw == '' else str(raw)


def build_structure_materials_grid(
    structure_type: StructureType,
    materials,
    rows_by_id: dict | None = None,
) -> dict:
    """
    Build a read-only grid: rows = materials of this structure type,
    columns = structure fields only (no reference properties).
    """
    fields = structure_data_fields(structure_type)
    columns = structure_field_headers(fields)
    if rows_by_id is None:
        rows_by_id = _rows_by_id(structure_type) if fields or materials else {}

    rows = []
    for material in materials:
        props_id = material.struct_props_id
        params = rows_by_id.get(str(props_id)) if props_id else None
        rows.append(
            {
                'material': material,
                'structure_record_id': props_id,
                'cells': [_cell_display(field, params) for field in fields],
            }
        )

    return {
        'columns': columns,
        'rows': rows,
        'fields': fields,
    }
