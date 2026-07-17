from __future__ import annotations

from apps.core.number_utils import parse_decimal
from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    form_state_from_value_slots,
    format_property_number_display,
)

DECIMAL_KIND_SUFFIX = '__kind'
DECIMAL_B_SUFFIX = '__b'

# Legacy suffixes (до схемы value + __b + __kind)
LEGACY_DECIMAL_A_SUFFIX = '__a'
LEGACY_DECIMAL_MIN_SUFFIX = '__min'
LEGACY_DECIMAL_MAX_SUFFIX = '__max'
LEGACY_DECIMAL_TOLERANCE_SUFFIX = '__tolerance'


def decimal_kind_column(name: str) -> str:
    return f'{name}{DECIMAL_KIND_SUFFIX}'


def decimal_b_column(name: str) -> str:
    return f'{name}{DECIMAL_B_SUFFIX}'


def decimal_companion_columns(name: str) -> tuple[str, str]:
    """Companion-колонки к базовой колонке name: __kind и __b."""
    return (
        decimal_kind_column(name),
        decimal_b_column(name),
    )


def decimal_storage_columns(name: str) -> tuple[str, str, str]:
    """Все три колонки хранения: value, __kind, __b."""
    return name, decimal_kind_column(name), decimal_b_column(name)


def is_decimal_companion_column(column_name: str) -> bool:
    return (
        column_name.endswith(DECIMAL_KIND_SUFFIX)
        or column_name.endswith(DECIMAL_B_SUFFIX)
        or column_name.endswith(LEGACY_DECIMAL_A_SUFFIX)
        or column_name.endswith(LEGACY_DECIMAL_MIN_SUFFIX)
        or column_name.endswith(LEGACY_DECIMAL_MAX_SUFFIX)
        or column_name.endswith(LEGACY_DECIMAL_TOLERANCE_SUFFIX)
    )


def decimal_base_column_name(column_name: str) -> str | None:
    for suffix in (
        DECIMAL_KIND_SUFFIX,
        DECIMAL_B_SUFFIX,
        LEGACY_DECIMAL_A_SUFFIX,
        LEGACY_DECIMAL_MIN_SUFFIX,
        LEGACY_DECIMAL_MAX_SUFFIX,
        LEGACY_DECIMAL_TOLERANCE_SUFFIX,
    ):
        if column_name.endswith(suffix):
            return column_name[: -len(suffix)]
    return None


def _read_value_slots(record: dict, column_name: str) -> tuple[str, object, object]:
    kind_col = decimal_kind_column(column_name)
    b_col = decimal_b_column(column_name)
    a_col = f'{column_name}{LEGACY_DECIMAL_A_SUFFIX}'

    kind = (record.get(kind_col) or VALUE_KIND_SCALAR).strip() or VALUE_KIND_SCALAR

    # Новая схема: base column = value, __b = extra
    if column_name in record and a_col not in record:
        return kind, record.get(column_name), record.get(b_col)

    # Промежуточная схема __a/__b
    if a_col in record:
        return kind, record.get(a_col), record.get(b_col)

    # Старая схема value/__min/__max/__tolerance
    raw_value = record.get(column_name)
    raw_min = record.get(f'{column_name}{LEGACY_DECIMAL_MIN_SUFFIX}')
    raw_max = record.get(f'{column_name}{LEGACY_DECIMAL_MAX_SUFFIX}')
    raw_tolerance = record.get(f'{column_name}{LEGACY_DECIMAL_TOLERANCE_SUFFIX}')

    if kind == VALUE_KIND_RANGE:
        return kind, raw_min, raw_max
    if kind == VALUE_KIND_TOLERANCE:
        nominal = raw_value if raw_value not in (None, '') else raw_min
        return kind, nominal, raw_tolerance
    scalar = raw_value
    if scalar in (None, '') and raw_min not in (None, '') and raw_max not in (None, ''):
        if raw_min == raw_max:
            scalar = raw_min
    return VALUE_KIND_SCALAR, scalar, None


def read_decimal_field_state(record: dict, column_name: str) -> dict:
    kind, value, value_b = _read_value_slots(record, column_name)
    form = form_state_from_value_slots(value_kind=kind, value=value, value_b=value_b)
    form['value'] = value
    form['value_b'] = value_b
    return form


def pack_decimal_field_data(
    column_name: str,
    *,
    value_kind,
    value,
    value_b,
) -> dict:
    kind = value_kind or VALUE_KIND_SCALAR
    return {
        column_name: value,
        decimal_kind_column(column_name): kind,
        decimal_b_column(column_name): value_b,
    }


def format_decimal_field_display(
    *,
    value_kind,
    value,
    value_b=None,
    decimal_places: int | None,
) -> str:
    text = format_property_number_display(
        value_kind=value_kind,
        value=value,
        value_b=value_b,
        decimal_places=decimal_places,
    )
    return text or '—'


def backfill_scalar_row(column_name: str, scalar_value) -> dict:
    decimal_value = parse_decimal(scalar_value)
    return pack_decimal_field_data(
        column_name,
        value_kind=VALUE_KIND_SCALAR,
        value=decimal_value if decimal_value is not None else scalar_value,
        value_b=None,
    )


def legacy_decimal_column_names(column_name: str) -> tuple[str, ...]:
    return (
        f'{column_name}{LEGACY_DECIMAL_A_SUFFIX}',
        f'{column_name}{LEGACY_DECIMAL_MIN_SUFFIX}',
        f'{column_name}{LEGACY_DECIMAL_MAX_SUFFIX}',
        f'{column_name}{LEGACY_DECIMAL_TOLERANCE_SUFFIX}',
    )
