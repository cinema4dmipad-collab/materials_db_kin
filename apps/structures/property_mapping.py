from __future__ import annotations

from apps.references.models import Property
from apps.structures.identifiers import normalize_identifier, validate_field_column_name
from apps.structures.constants import DEFAULT_DECIMAL_PLACES, DEFAULT_MAX_DIGITS

PROPERTY_DATA_TYPE_TO_FIELD_TYPE = {
    'number': 'DecimalField',
    'string': 'CharField',
    'boolean': 'BooleanField',
    'date': 'DateField',
    'material_link': 'MaterialLink',
    'choice': 'CharField',
}


def structure_field_label_from_property(property_obj: Property) -> str:
    return property_obj.label_with_unit()


def structure_column_name_from_property(property_obj: Property) -> str:
    raw_name = (property_obj.name or '').strip()
    if not raw_name:
        raw_name = normalize_identifier(property_obj.display_name, max_length=63)
    base = normalize_identifier(raw_name, max_length=63)
    if not base:
        base = 'property'

    candidates = [base, f'{base}_value', f'{base}_prop']
    for candidate in candidates:
        try:
            return validate_field_column_name(candidate[:63].rstrip('_'))
        except ValueError:
            continue
    return validate_field_column_name(f'prop_{base[:58]}')


def property_to_structure_field_data(property_obj: Property) -> dict:
    field_type = PROPERTY_DATA_TYPE_TO_FIELD_TYPE.get(
        property_obj.data_type,
        'DecimalField',
    )
    result = {
        'property_id': str(property_obj.id),
        'label': structure_field_label_from_property(property_obj),
        'name': structure_column_name_from_property(property_obj),
        'field_type': field_type,
        'data_type': property_obj.data_type,
        'unit': property_obj.effective_unit(),
        'group_name': property_obj.group.name if property_obj.group_id else '',
        'help_text': (property_obj.description or '')[:500],
    }
    if field_type == 'DecimalField':
        result['max_digits'] = DEFAULT_MAX_DIGITS
        result['decimal_places'] = DEFAULT_DECIMAL_PLACES
    if property_obj.data_type == Property.CHOICE_DATA_TYPE:
        result['choices'] = [
            {'value': item.value, 'label': item.label}
            for item in property_obj.choice_options()
        ]
    return result


def reference_properties_for_picker(
    *,
    exclude_data_types: set[str] | frozenset[str] | None = None,
) -> list[dict]:
    properties = (
        Property.objects.select_related('group')
        .prefetch_related('choices')
        .order_by(
            'group__sort_order',
            'group__name',
            'display_name',
            'name',
        )
    )
    excluded = exclude_data_types or frozenset()
    return [
        property_to_structure_field_data(item)
        for item in properties
        if item.data_type not in excluded
    ]
