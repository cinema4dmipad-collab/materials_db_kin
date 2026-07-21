from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
)
from apps.structures.constants import DEFAULT_DECIMAL_PLACES
from apps.structures.decimal_range import decimal_storage_columns, pack_decimal_field_data
from apps.structures.models import StructureField


def empty_structure_sql_payload(structure_field: StructureField) -> dict:
    """Явный NULL для сопоставленного, но пустого поля импорта."""
    if structure_field.field_type == 'DecimalField':
        value_col, kind_col, b_col = decimal_storage_columns(structure_field.name)
        return {value_col: None, kind_col: None, b_col: None}
    return {structure_field.name: None}


def build_structure_sql_payload(structure_field: StructureField, parsed: dict | None) -> dict | None:
    """Преобразует разобранную ячейку в dict колонок SQL-таблицы структуры."""
    if parsed is None:
        return None

    field_type = structure_field.field_type
    if field_type == 'DecimalField':
        return _decimal_sql(structure_field, parsed)
    if field_type in {'CharField', 'TextField'}:
        text = str(parsed.get('value') or '').strip()
        if not text:
            return None
        if field_type == 'CharField':
            limit = structure_field.max_length or 255
            if len(text) > limit:
                raise ValidationError(
                    f'Значение длиннее {limit} символов ({len(text)}). Сократите текст в Excel.'
                )
        return {structure_field.name: text}
    if field_type == 'IntegerField':
        return _integer_sql(structure_field, parsed)
    if field_type == 'FloatField':
        return _float_sql(structure_field, parsed)
    if field_type == 'BooleanField':
        return _boolean_sql(structure_field, parsed)
    if field_type == 'MaterialLink':
        text = str(parsed.get('value') or '').strip()
        if not text:
            return None
        # Ожидается уже разрешённый UUID (или валидный UUID-текст).
        return {structure_field.name: text}
    if field_type in {'DateField', 'DateTimeField', 'ChoiceField'}:
        text = str(parsed.get('value') or '').strip()
        if not text:
            return None
        return {structure_field.name: text}
    text = str(parsed.get('value') or '').strip()
    if not text:
        return None
    return {structure_field.name: text}


def merge_structure_sql_payloads(payloads: list[dict]) -> dict:
    """
    Объединяет payload'ы полей структуры.
    При конфликте ключа побеждает последнее непустое значение —
    пустая ячейка не затирает уже найденное.
    """
    merged: dict = {}
    for payload in payloads:
        for key, value in payload.items():
            if key not in merged:
                merged[key] = value
                continue
            if _is_blank_sql_value(value) and not _is_blank_sql_value(merged[key]):
                continue
            merged[key] = value
    return merged


def _is_blank_sql_value(value) -> bool:
    return value is None or value == ''


def _decimal_sql(structure_field: StructureField, parsed: dict) -> dict | None:
    kind = parsed.get('value_kind') or VALUE_KIND_SCALAR
    places = structure_field.decimal_places or DEFAULT_DECIMAL_PLACES
    try:
        if kind == VALUE_KIND_RANGE:
            normalized = clean_number_property_fields(
                value_kind=kind,
                value='',
                value_min=parsed.get('value'),
                value_max=parsed.get('value_b'),
                decimal_places=places,
            )
        elif kind == VALUE_KIND_TOLERANCE:
            normalized = clean_number_property_fields(
                value_kind=kind,
                value=parsed.get('value'),
                value_min=None,
                value_max=None,
                value_tolerance=parsed.get('value_b'),
                decimal_places=places,
            )
        else:
            normalized = clean_number_property_fields(
                value_kind=VALUE_KIND_SCALAR,
                value=parsed.get('value'),
                value_min=None,
                value_max=None,
                decimal_places=places,
            )
    except ValidationError:
        return None
    if not str(normalized.get('value') or '').strip() and normalized.get('value_b') in (None, ''):
        return None
    return pack_decimal_field_data(
        structure_field.name,
        value_kind=normalized['value_kind'],
        value=normalized['value'],
        value_b=normalized.get('value_b'),
    )


def _integer_sql(structure_field: StructureField, parsed: dict) -> dict | None:
    value = _scalar_number(parsed)
    if value is None:
        return None
    try:
        return {structure_field.name: int(Decimal(str(value)))}
    except (InvalidOperation, ValueError, TypeError):
        return None


def _float_sql(structure_field: StructureField, parsed: dict) -> dict | None:
    value = _scalar_number(parsed)
    if value is None:
        return None
    try:
        return {structure_field.name: float(Decimal(str(value)))}
    except (InvalidOperation, ValueError, TypeError):
        return None


def _boolean_sql(structure_field: StructureField, parsed: dict) -> dict | None:
    text = str(parsed.get('value') or '').strip().casefold()
    if not text:
        return None
    if text in {'1', 'true', 'yes', 'да', 'y'}:
        return {structure_field.name: True}
    if text in {'0', 'false', 'no', 'нет', 'n'}:
        return {structure_field.name: False}
    return None


def _scalar_number(parsed: dict):
    kind = parsed.get('value_kind') or VALUE_KIND_SCALAR
    if kind == VALUE_KIND_RANGE:
        try:
            low = Decimal(str(parsed.get('value')))
            high = Decimal(str(parsed.get('value_b')))
            return (low + high) / 2
        except (InvalidOperation, ValueError, TypeError):
            return None
    if kind == VALUE_KIND_TOLERANCE:
        return parsed.get('value')
    return parsed.get('value')
