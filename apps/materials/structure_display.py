from __future__ import annotations

from apps.structures.display_format import format_structure_field_display
from apps.structures.forms import material_from_value
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE

STRUCTURE_SERVICE_COLUMNS = frozenset({'id', 'created_at', 'updated_at', 'created_by'})


def structure_field_display_value(field, value):
    if value is None or value == '':
        return '—'
    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        material = material_from_value(value)
        if material is not None:
            return f'{material.code} - {material.name}'
        return value
    return format_structure_field_display(field, value)


def build_structure_property_item(field, structure_params):
    value = structure_params.get(field.name)
    return {
        'label': field.label,
        'name': field.name,
        'field_type': field.field_type,
        'value': value,
        'display_value': structure_field_display_value(field, value),
    }


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
                'name': item['name'],
                'field_type': item['field_type'],
                'display_value': item['display_value'],
                'value': '' if item.get('value') in (None, '') else str(item['value']),
            }
            for item in structure_context.get('structure_properties') or []
        ],
    }
