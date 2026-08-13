from decimal import Decimal, InvalidOperation
import uuid

from apps.core.number_utils import format_decimal_display, parse_decimal
from apps.structures.constants import resolve_structure_field_decimal_places
from apps.structures.choice_options import choice_label_for_value, resolved_choice_options
from apps.structures.models import CHOICE_FIELD_TYPE, MATERIAL_LINK_FIELD_TYPE


def _decimal_places(field) -> int:
    return max(resolve_structure_field_decimal_places(field), 0)


def _decimal_quantize(value, decimal_places: int) -> Decimal:
    if decimal_places == 0:
        exp = Decimal('1')
    else:
        exp = Decimal(f'1.{"0" * decimal_places}')
    return Decimal(str(value)).quantize(exp)


def normalize_structure_field_value(field, value):
    if value is None or value == '':
        return value
    if field.field_type == 'DecimalField':
        return _decimal_quantize(value, _decimal_places(field))
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        return str(uuid.UUID(str(value)))
    return value


def format_structure_field_display(field, value):
    if value is None or value == '':
        return '—'
    if field.field_type == 'DecimalField':
        normalized = _decimal_quantize(value, _decimal_places(field))
        return format_decimal_display(normalized, _decimal_places(field))
    if field.field_type == 'FloatField':
        return format_decimal_display(value)
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        from apps.structures.forms import material_link_display

        return material_link_display(value)
    options = resolved_choice_options(field)
    if field.field_type == CHOICE_FIELD_TYPE or options:
        return choice_label_for_value(options, value) or '—'
    return value
