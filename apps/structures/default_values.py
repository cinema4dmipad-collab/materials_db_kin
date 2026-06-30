from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.structures.constants import DEFAULT_DECIMAL_PLACES, DEFAULT_MAX_DIGITS
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE

_BOOLEAN_DEFAULTS = {
    '1', '0', 'true', 'false', 'yes', 'no', 'on', 'off', 'да', 'нет',
}


from apps.core.number_utils import normalize_decimal_input


def validate_structure_field_default(
    *,
    field_type: str,
    default_value: str,
    label: str,
    name: str,
    max_digits: int | None = None,
    decimal_places: int | None = None,
) -> None:
    raw = (default_value or '').strip()
    if not raw:
        return

    field_label = label or name or 'поле'
    text = normalize_decimal_input(raw)

    if field_type == 'IntegerField':
        if '.' in text or ',' in raw:
            raise ValueError(
                f'Поле «{field_label}» ({name}): для типа «Целое число» '
                f'значение по умолчанию «{raw}» должно быть целым, без дробной части.'
            )
        try:
            int(text)
        except ValueError as exc:
            raise ValueError(
                f'Поле «{field_label}» ({name}): некорректное целое значение '
                f'по умолчанию «{raw}».'
            ) from exc
        return

    if field_type == 'DecimalField':
        try:
            decimal_value = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(
                f'Поле «{field_label}» ({name}): некорректное десятичное значение '
                f'по умолчанию «{raw}».'
            ) from exc

        places = decimal_places if decimal_places is not None else DEFAULT_DECIMAL_PLACES
        digits = max_digits if max_digits is not None else DEFAULT_MAX_DIGITS
        sign, coefficient, exponent = decimal_value.as_tuple()
        scale = max(-exponent, 0)
        if scale > places:
            raise ValueError(
                f'Поле «{field_label}» ({name}): значение «{raw}» имеет больше '
                f'{places} знаков после запятой.'
            )
        total_digits = len(coefficient)
        if total_digits > digits:
            raise ValueError(
                f'Поле «{field_label}» ({name}): значение «{raw}» не помещается '
                f'в {digits} цифр (всего цифр и дробная часть).'
            )
        return

    if field_type == 'FloatField':
        try:
            float(text)
        except ValueError as exc:
            raise ValueError(
                f'Поле «{field_label}» ({name}): некорректное числовое значение '
                f'по умолчанию «{raw}».'
            ) from exc
        return

    if field_type == 'BooleanField':
        if text.lower() not in _BOOLEAN_DEFAULTS:
            raise ValueError(
                f'Поле «{field_label}» ({name}): для типа «Да/Нет» укажите '
                f'true/false, 1/0 или да/нет.'
            )
        return

    if field_type == 'DateField':
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f'Поле «{field_label}» ({name}): дата по умолчанию «{raw}» '
                f'должна быть в формате ГГГГ-ММ-ДД.'
            ) from exc
        return

    if field_type == 'DateTimeField':
        try:
            datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f'Поле «{field_label}» ({name}): дата и время по умолчанию «{raw}» '
                f'должны быть в формате ГГГГ-ММ-ДД или ГГГГ-ММ-ДДTЧЧ:ММ.'
            ) from exc
        return

    if field_type == MATERIAL_LINK_FIELD_TYPE:
        raise ValueError(
            f'Поле «{field_label}» ({name}): для ссылки на материал '
            f'значение по умолчанию не поддерживается.'
        )


def validate_structure_field_model(field) -> None:
    validate_structure_field_default(
        field_type=field.field_type,
        default_value=field.default_value,
        label=field.label,
        name=field.name,
        max_digits=field.max_digits,
        decimal_places=field.decimal_places,
    )
