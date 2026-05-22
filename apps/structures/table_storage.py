import uuid
from decimal import Decimal

from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class DisplayValue:
    """Обёртка для отображения значения в шаблонах."""

    def __init__(self, field: StructureField, value):
        self.field = field
        self._value = value

    def get_value(self):
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
