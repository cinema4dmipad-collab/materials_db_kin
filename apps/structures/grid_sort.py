"""Sort structure-grid rows by material fields or SQL property values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.core.number_utils import parse_decimal
from apps.core.table_sort import DIR_DESC
from apps.materials.structure_display import structure_field_display_value
from apps.structures.decimal_range import read_decimal_field_state


def _is_empty(value) -> bool:
    return value is None or value == ''


def _as_decimal(raw):
    try:
        return parse_decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return None


def sortable_field_value(field, record):
    if not record:
        return None
    if field.field_type == 'DecimalField':
        state = read_decimal_field_state(record, field.name)
        return _as_decimal(state.get('value'))
    raw = record.get(field.name)
    if _is_empty(raw):
        return None
    if field.field_type in ('IntegerField', 'FloatField'):
        number = _as_decimal(raw)
        if number is not None:
            return number
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            return None
    if field.field_type == 'BooleanField':
        if isinstance(raw, bool):
            return int(raw)
        text = str(raw).strip().lower()
        if text in {'1', 'true', 'yes', 'да'}:
            return 1
        if text in {'0', 'false', 'no', 'нет'}:
            return 0
        return 0
    if field.field_type in ('DateField', 'DateTimeField'):
        if isinstance(raw, (date, datetime)):
            return raw
        return str(raw)
    display = structure_field_display_value(field, raw, structure_params=record)
    if display in (None, '', '—'):
        return None
    return str(display).casefold()


def sort_structure_materials(
    materials,
    *,
    sort_key: str,
    direction: str,
    fields,
    rows_by_id: dict,
):
    items = list(materials)
    reverse = direction == DIR_DESC
    if sort_key == 'name':
        return sorted(items, key=lambda material: (material.name or '').casefold(), reverse=reverse)
    if sort_key == 'code':
        return sorted(items, key=lambda material: (material.code or '').casefold(), reverse=reverse)

    field = next((item for item in fields if item.name == sort_key), None)
    if field is None:
        return items

    keyed = []
    missing = []
    for material in items:
        props_id = material.struct_props_id
        record = rows_by_id.get(str(props_id)) if props_id else None
        value = sortable_field_value(field, record)
        if value is None:
            missing.append(material)
        else:
            keyed.append((value, str(material.pk), material))
    keyed.sort(key=lambda item: (item[0], item[1]), reverse=reverse)
    return [item[2] for item in keyed] + missing
