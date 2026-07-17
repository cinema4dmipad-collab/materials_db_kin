from __future__ import annotations

from apps.core.unit_display import split_label_and_unit
from apps.structures.display_format import format_structure_field_display
from apps.structures.constants import DEFAULT_DECIMAL_PLACES
from apps.structures.decimal_range import format_decimal_field_display, read_decimal_field_state
from apps.structures.forms import material_from_value
from apps.structures.choice_options import choice_label_for_value, resolved_choice_options
from apps.structures.models import CHOICE_FIELD_TYPE, MATERIAL_LINK_FIELD_TYPE

STRUCTURE_SERVICE_COLUMNS = frozenset({'id', 'created_at', 'updated_at', 'created_by'})


def structure_field_display_value(field, value, structure_params=None):
    if field.field_type == 'DecimalField':
        record = structure_params if structure_params is not None else {field.name: value}
        state = read_decimal_field_state(record, field.name)
        return format_decimal_field_display(
            value_kind=state['value_kind'],
            value=state['value'],
            value_b=state['value_b'],
            decimal_places=field.decimal_places or DEFAULT_DECIMAL_PLACES,
        )
    if value is None or value == '':
        return '—'
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        material = material_from_value(value)
        if material is not None:
            return f'{material.code} - {material.name}'
        return value
    options = resolved_choice_options(field)
    if field.field_type == CHOICE_FIELD_TYPE or options:
        return choice_label_for_value(options, value) or '—'
    return format_structure_field_display(field, value)


def build_structure_property_item(field, structure_params):
    value = structure_params.get(field.name)
    label = field.label or field.name
    base_label, unit = split_label_and_unit(label)
    state = (
        read_decimal_field_state(structure_params, field.name)
        if field.field_type == 'DecimalField'
        else None
    )
    item = {
        'label': base_label or label,
        'unit': unit,
        'name': field.name,
        'field_type': field.field_type,
        'value': value,
        'display_value': structure_field_display_value(
            field,
            value,
            structure_params=structure_params,
        ),
    }
    if state is not None:
        item.update(
            {
                'value_kind': state['value_kind'],
                'value_b': state['value_b'],
            }
        )
    return item


def get_material_structure_context(material):
    structure_context = {
        'structure_type': material.struct_type if getattr(material, 'struct_type_id', None) else None,
        'structure_properties': [],
        'structure_message': '',
    }

    if material is None or not material.struct_type_id:
        structure_context['structure_message'] = 'Структура не выбрана.'
        return structure_context

    if not material.struct_props_id:
        structure_context['structure_message'] = 'Запись параметров структуры не выбрана.'
        return structure_context

    structure_params = material.get_structure_params()
    if structure_params is None:
        structure_context['structure_message'] = 'Запись параметров структуры не найдена.'
        return structure_context

    fields = (
        material.struct_type.fields.exclude(name__in=STRUCTURE_SERVICE_COLUMNS)
        .exclude(field_type='ForeignKey')
        .order_by('sort_order', 'name')
    )
    structure_context['structure_properties'] = [
        build_structure_property_item(field, structure_params)
        for field in fields
    ]

    if not structure_context['structure_properties']:
        structure_context['structure_message'] = 'Параметры структуры не заданы.'
    return structure_context


def serialize_structure_context(structure_context):
    structure_type = structure_context.get('structure_type')
    return {
        'structure_type': (
            {
                'id': str(structure_type.pk),
                'name': structure_type.name,
            }
            if structure_type is not None
            else None
        ),
        'structure_message': structure_context.get('structure_message') or '',
        'structure_properties': [
            {
                'label': item['label'],
                'unit': item.get('unit') or '',
                'name': item['name'],
                'field_type': item['field_type'],
                'display_value': item['display_value'],
                'value': '' if item.get('value') in (None, '') else str(item['value']),
                'value_kind': item.get('value_kind'),
                'value_b': (
                    '' if item.get('value_b') in (None, '') else str(item['value_b'])
                ),
            }
            for item in structure_context.get('structure_properties') or []
        ],
    }
