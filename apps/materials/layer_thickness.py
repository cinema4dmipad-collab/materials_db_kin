"""Ply thickness from a material's structure field or reference property «Толщина»."""

from __future__ import annotations

from collections import defaultdict
from decimal import InvalidOperation

from apps.core.number_utils import parse_decimal
from apps.core.unit_display import split_label_and_unit
from apps.structures.decimal_range import read_decimal_field_state

THICKNESS_FIELD_NAMES = frozenset({'thickness', 'thickness_mm', 'tolshchina'})
THICKNESS_CAPTION = 'толщина'
NUMERIC_STRUCTURE_TYPES = frozenset({'DecimalField', 'IntegerField', 'FloatField'})


def _as_number(raw):
    try:
        number = parse_decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if number is None:
        return None
    value = float(number)
    if value <= 0:
        return None
    return value


def is_thickness_caption(text: str) -> bool:
    base, _unit = split_label_and_unit((text or '').strip())
    return base.casefold() == THICKNESS_CAPTION


def is_thickness_field(field) -> bool:
    name = (getattr(field, 'name', None) or '').strip().casefold()
    if name in THICKNESS_FIELD_NAMES:
        return True
    return is_thickness_caption(getattr(field, 'label', None) or '')


def is_thickness_property(prop) -> bool:
    name = (getattr(prop, 'name', None) or '').strip().casefold()
    if name in THICKNESS_FIELD_NAMES:
        return True
    base_name = getattr(prop, 'base_display_name', None)
    caption = base_name() if callable(base_name) else (getattr(prop, 'display_name', None) or '')
    return is_thickness_caption(caption)


def _preferred_structure_field(fields):
    ranked = [
        field
        for field in fields
        if is_thickness_field(field) and field.field_type in NUMERIC_STRUCTURE_TYPES
    ]
    if not ranked:
        return None
    ranked.sort(
        key=lambda field: (
            0 if (field.name or '').casefold() in THICKNESS_FIELD_NAMES else 1,
            field.sort_order,
            field.name,
        )
    )
    return ranked[0]


def _number_from_structure_field(field, record):
    if not record:
        return None
    if field.field_type == 'DecimalField':
        state = read_decimal_field_state(record, field.name)
        return _as_number(state.get('value'))
    return _as_number(record.get(field.name))


def layer_thickness_mm_by_material_id(materials) -> dict:
    """Map ``material.pk → thickness mm`` for materials that have a Толщина value."""
    items = list(materials)
    result = {}
    by_type = defaultdict(list)
    types = {}
    for material in items:
        if material.struct_type_id and material.struct_props_id:
            by_type[material.struct_type_id].append(material)
            types[material.struct_type_id] = material.struct_type

    if by_type:
        from apps.structures.materials_grid import structure_data_fields, structure_sql_rows_by_id

        for type_id, group in by_type.items():
            structure_type = types[type_id]
            if not getattr(structure_type, 'is_created', False):
                continue
            field = _preferred_structure_field(structure_data_fields(structure_type))
            if field is None:
                continue
            rows = structure_sql_rows_by_id(structure_type)
            for material in group:
                value = _number_from_structure_field(
                    field,
                    rows.get(str(material.struct_props_id)),
                )
                if value is not None:
                    result[material.pk] = value

    missing = [material for material in items if material.pk not in result]
    if missing:
        from apps.materials.models import MaterialProperty

        properties = (
            MaterialProperty.objects.filter(
                material_id__in=[material.pk for material in missing],
                property__data_type='number',
            )
            .select_related('property')
            .order_by('property__name')
        )
        by_material: dict = defaultdict(list)
        for row in properties:
            if is_thickness_property(row.property):
                by_material[row.material_id].append(row)
        for material_id, rows in by_material.items():
            rows.sort(
                key=lambda row: (
                    0 if (row.property.name or '').casefold() in THICKNESS_FIELD_NAMES else 1,
                    row.property.name,
                )
            )
            value = _as_number(rows[0].value)
            if value is not None:
                result[material_id] = value
    return result
