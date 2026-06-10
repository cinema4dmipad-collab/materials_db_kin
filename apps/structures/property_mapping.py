from __future__ import annotations

from apps.references.models import Property
from apps.structures.identifiers import normalize_identifier, validate_field_column_name
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE

PROPERTY_DATA_TYPE_TO_FIELD_TYPE = {
    'number': 'DecimalField',
    'string': 'CharField',
    'boolean': 'BooleanField',
    'date': 'DateField',
}


def structure_field_label_from_property(property_obj: Property) -> str:
    display_name = (property_obj.display_name or property_obj.name or '').strip()
    unit = (property_obj.unit or '').strip()
    if unit:
        return f'{display_name}, {unit}'
    return display_name


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
    return {
        'property_id': str(property_obj.id),
        'label': structure_field_label_from_property(property_obj),
        'name': structure_column_name_from_property(property_obj),
        'field_type': field_type,
        'data_type': property_obj.data_type,
        'unit': property_obj.unit or '',
        'group_name': property_obj.group.name if property_obj.group_id else '',
        'help_text': (property_obj.description or '')[:500],
    }


def reference_properties_for_picker() -> list[dict]:
    properties = Property.objects.select_related('group').order_by(
        'group__sort_order',
        'group__name',
        'display_name',
        'name',
    )
    return [property_to_structure_field_data(item) for item in properties]
