import uuid
from decimal import Decimal

from apps.materials.models import Material
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE, StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class DisplayValue:
    """Обёртка для отображения значения в шаблонах."""

    def __init__(self, field: StructureField, value):
        self.field = field
        self._value = value

    def get_value(self):
        if self.field.field_type == MATERIAL_LINK_FIELD_TYPE and self._value not in (None, ''):
            try:
                material = Material.objects.get(pk=self._value)
            except (Material.DoesNotExist, ValueError, TypeError):
                return self._value
            return f'{material.code} - {material.name}'
        return self._value


def _coerce_for_db(field: StructureField, value):
    return SQLExecutor._coerce_for_db(field, value)


def _supported_fields(structure_type: StructureType):
    return structure_type.fields.exclude(field_type='ForeignKey')


def get_row(structure_type: StructureType, row_id: uuid.UUID) -> dict | None:
    if not structure_type.is_created:
        return None
    result = SQLExecutor.get_by_id(structure_type, row_id)
    if not result['success']:
        return None
    return result['record']


def get_display_values(structure_type: StructureType, row_id: uuid.UUID) -> list[DisplayValue]:
    row = get_row(structure_type, row_id)
    if not row:
        return []
    return [
        DisplayValue(field, row.get(field.name))
        for field in _supported_fields(structure_type)
    ]


def insert_row(
    structure_type: StructureType,
    code: str,
    field_data: dict,
    created_by: str = '',
) -> uuid.UUID:
    row_id = uuid.uuid4()
    data = {'id': str(row_id), 'created_by': created_by or ''}

    for field in _supported_fields(structure_type):
        if field.name in field_data:
            data[field.name] = field_data.get(field.name)

    result = SQLExecutor.insert(structure_type, data)
    if not result['success']:
        raise ValueError(result['error'])
    return row_id


def update_row(
    structure_type: StructureType,
    row_id: uuid.UUID,
    field_data: dict,
    code: str | None = None,
) -> None:
    data = {}

    for field in _supported_fields(structure_type):
        if field.name in field_data:
            data[field.name] = field_data[field.name]

    result = SQLExecutor.update(structure_type, row_id, data)
    if not result['success']:
        raise ValueError(result['error'])


def delete_table_row(structure_type: StructureType, row_id: uuid.UUID) -> None:
    result = SQLExecutor.delete(structure_type, row_id)
    if not result['success']:
        raise ValueError(result['error'])


def load_field_data(structure_type: StructureType, row_id: uuid.UUID) -> dict:
    row = get_row(structure_type, row_id)
    if not row:
        return {}
    result = {}
    for field in _supported_fields(structure_type):
        val = row.get(field.name)
        if isinstance(val, Decimal):
            result[field.name] = val
        else:
            result[field.name] = val
    return result


SERVICE_COLUMNS = {'id', 'created_at', 'updated_at', 'created_by'}


def structure_record_label(record: dict, structure_type: StructureType) -> str:
    for field in _supported_fields(structure_type):
        value = record.get(field.name)
        if value not in (None, ''):
            if field.field_type == MATERIAL_LINK_FIELD_TYPE:
                return str(DisplayValue(field, value).get_value())
            return str(value)
    record_id = str(record.get('id') or '')
    return record_id[:8] if record_id else '—'


def count_linked_materials(structure_type: StructureType, row_id) -> int:
    from apps.materials.models import Material

    return Material.objects.filter(
        struct_type=structure_type,
        struct_props_id=row_id,
    ).count()
