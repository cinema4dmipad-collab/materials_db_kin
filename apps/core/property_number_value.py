from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.core.number_utils import format_decimal_display, normalize_decimal_input, parse_decimal

VALUE_KIND_SCALAR = 'scalar'
VALUE_KIND_RANGE = 'range'
VALUE_KIND_TOLERANCE = 'tolerance'

VALUE_KIND_CHOICES = (
    (VALUE_KIND_SCALAR, 'Точное'),
    (VALUE_KIND_RANGE, 'Диапазон'),
    (VALUE_KIND_TOLERANCE, '± погрешность'),
)

_VALID_VALUE_KINDS = {VALUE_KIND_SCALAR, VALUE_KIND_RANGE, VALUE_KIND_TOLERANCE}


def effective_bounds(
    value_kind: str,
    value,
    value_b,
) -> tuple[Decimal | None, Decimal | None]:
    """value — основное число (scalar / min / номинал), value_b — второе (max / ±)."""
    kind = (value_kind or VALUE_KIND_SCALAR).strip() or VALUE_KIND_SCALAR
    a = _coerce_decimal(value)
    b = _coerce_decimal(value_b)
    if a is None:
        return None, None
    if kind == VALUE_KIND_RANGE:
        return a, b
    if kind == VALUE_KIND_TOLERANCE:
        if b is None:
            return None, None
        return a - b, a + b
    return a, a


def _coerce_decimal(raw) -> Decimal | None:
    if raw in (None, ''):
        return None
    if isinstance(raw, Decimal):
        return raw
    return parse_decimal(raw)


def format_property_number_display(
    *,
    value_kind: str,
    value,
    value_b=None,
    decimal_places: int | None,
) -> str:
    kind = (value_kind or VALUE_KIND_SCALAR).strip() or VALUE_KIND_SCALAR
    if kind == VALUE_KIND_TOLERANCE:
        if value in (None, '') or value_b in (None, ''):
            return ''
        nominal = format_decimal_display(value, decimal_places)
        tolerance = format_decimal_display(value_b, decimal_places)
        return f'{nominal}±{tolerance}'
    if kind == VALUE_KIND_RANGE:
        if value in (None, '') or value_b in (None, ''):
            return ''
        left = format_decimal_display(value, decimal_places)
        right = format_decimal_display(value_b, decimal_places)
        return f'{left}–{right}'
    if value in (None, ''):
        return ''
    return format_decimal_display(value, decimal_places)


def _parse_component(raw, *, decimal_places: int | None) -> Decimal:
    normalized = normalize_decimal_input(raw)
    if not normalized:
        raise ValidationError('Введите корректное число.')
    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValidationError('Введите корректное число.') from exc
    if decimal_places is not None:
        exponent = decimal_value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < 0 and abs(exponent) > decimal_places:
            raise ValidationError(f'Не более {decimal_places} знаков после запятой.')
    return decimal_value


def _normalize_scalar_string(decimal_value: Decimal) -> str:
    text = format(decimal_value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def _empty_number_payload(value_kind: str) -> dict:
    return {
        'value_kind': value_kind,
        'value': '',
        'value_b': None,
    }


def clean_number_property_fields(
    *,
    value_kind: str,
    value,
    value_min,
    value_max,
    value_tolerance=None,
    decimal_places: int | None,
) -> dict:
    """Принимает поля формы, возвращает value_kind + value + value_b."""
    kind = (value_kind or VALUE_KIND_SCALAR).strip() or VALUE_KIND_SCALAR
    if kind not in _VALID_VALUE_KINDS:
        raise ValidationError('Некорректный режим числового значения.')

    if kind == VALUE_KIND_RANGE:
        min_raw = (value_min or '').strip() if isinstance(value_min, str) else value_min
        max_raw = (value_max or '').strip() if isinstance(value_max, str) else value_max
        if min_raw in (None, '') and max_raw in (None, ''):
            return _empty_number_payload(VALUE_KIND_RANGE)
        if min_raw in (None, '') or max_raw in (None, ''):
            raise ValidationError('Укажите оба конца диапазона.')
        min_value = _parse_component(min_raw, decimal_places=decimal_places)
        max_value = _parse_component(max_raw, decimal_places=decimal_places)
        if min_value > max_value:
            raise ValidationError('Начало диапазона не может быть больше конца.')
        return {
            'value_kind': VALUE_KIND_RANGE,
            'value': _normalize_scalar_string(min_value),
            'value_b': max_value,
        }

    if kind == VALUE_KIND_TOLERANCE:
        nominal_raw = (value or '').strip() if isinstance(value, str) else value
        tolerance_raw = (
            (value_tolerance or '').strip()
            if isinstance(value_tolerance, str)
            else value_tolerance
        )
        if nominal_raw in (None, '') and tolerance_raw in (None, ''):
            return _empty_number_payload(VALUE_KIND_TOLERANCE)
        if nominal_raw in (None, '') or tolerance_raw in (None, ''):
            raise ValidationError('Укажите номинал и погрешность.')
        nominal_value = _parse_component(nominal_raw, decimal_places=decimal_places)
        tolerance_value = _parse_component(tolerance_raw, decimal_places=decimal_places)
        if tolerance_value < 0:
            raise ValidationError('Погрешность не может быть отрицательной.')
        return {
            'value_kind': VALUE_KIND_TOLERANCE,
            'value': _normalize_scalar_string(nominal_value),
            'value_b': tolerance_value,
        }

    scalar_raw = (value or '').strip() if isinstance(value, str) else value
    if scalar_raw in (None, ''):
        return _empty_number_payload(VALUE_KIND_SCALAR)
    scalar_value = _parse_component(scalar_raw, decimal_places=decimal_places)
    return {
        'value_kind': VALUE_KIND_SCALAR,
        'value': _normalize_scalar_string(scalar_value),
        'value_b': None,
    }


def sync_number_property_instance(instance) -> None:
    """Для числовых свойств value уже нормализован в clean; value_b — доп. слот."""
    kind = getattr(instance, 'value_kind', VALUE_KIND_SCALAR)
    if kind == VALUE_KIND_SCALAR:
        instance.value_b = None


def form_state_from_value_slots(*, value_kind, value, value_b) -> dict:
    """Маппинг value/value_b → поля формы (value, min, max, tolerance)."""
    kind = (value_kind or VALUE_KIND_SCALAR).strip() or VALUE_KIND_SCALAR
    if kind == VALUE_KIND_RANGE:
        return {
            'value_kind': kind,
            'value': '',
            'value_min': value,
            'value_max': value_b,
            'value_tolerance': None,
        }
    if kind == VALUE_KIND_TOLERANCE:
        return {
            'value_kind': kind,
            'value': value,
            'value_min': None,
            'value_max': None,
            'value_tolerance': value_b,
        }
    return {
        'value_kind': VALUE_KIND_SCALAR,
        'value': value,
        'value_min': None,
        'value_max': None,
        'value_tolerance': None,
    }


# Обратная совместимость для импортов во время рефакторинга
form_state_from_value_ab = form_state_from_value_slots
