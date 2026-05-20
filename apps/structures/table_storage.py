import uuid
from datetime import date, datetime
from decimal import Decimal

from django.db import connection
from django.utils import timezone

# connection used in _coerce_for_db for sqlite boolean

from apps.structures.models import StructureField, StructureType


class DisplayValue:
    """Обёртка для отображения значения в шаблонах."""

    def __init__(self, field: StructureField, value):
        self.field = field
        self._value = value

    def get_value(self):
        return self._value


def _coerce_for_db(field: StructureField, value):
    if value is None or value == '':
        return None
    if field.field_type == 'BooleanField':
        return 1 if value else 0 if connection.vendor == 'sqlite' else bool(value)
    if field.field_type == 'IntegerField':
        return int(value)
    if field.field_type in ('DecimalField', 'FloatField'):
        return Decimal(str(value))
    if field.field_type == 'DateField' and isinstance(value, str):
        return date.fromisoformat(value)
    if field.field_type == 'DateTimeField':
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
    if hasattr(value, 'pk'):
        return str(value.pk)
    return value


def get_row(structure_type: StructureType, row_id: uuid.UUID) -> dict | None:
    if not structure_type.is_created:
        return None
    field_names = list(
        structure_type.fields.exclude(field_type='ForeignKey').values_list('name', flat=True)
    )
    columns = ['id', 'created_at', 'updated_at', 'created_by'] + field_names
    col_list = ', '.join(columns)
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT {col_list} FROM {structure_type.table_name} WHERE id = %s',
            [str(row_id)],
        )
        row = cursor.fetchone()
    if not row:
        return None
    return dict(zip(columns, row, strict=True))


def get_display_values(structure_type: StructureType, row_id: uuid.UUID) -> list[DisplayValue]:
    row = get_row(structure_type, row_id)
    if not row:
        return []
    return [
        DisplayValue(field, row.get(field.name))
        for field in structure_type.fields.all()
    ]


def insert_row(
    structure_type: StructureType,
    code: str,
    field_data: dict,
    created_by: str = '',
) -> uuid.UUID:
    row_id = uuid.uuid4()
    now = timezone.now()
    columns = ['id', 'created_at', 'updated_at', 'created_by']
    values = [str(row_id), now, now, created_by or '']

    for field in structure_type.fields.exclude(field_type='ForeignKey'):
        columns.append(field.name)
        values.append(_coerce_for_db(field, field_data.get(field.name)))

    placeholders = ', '.join(['%s'] * len(values))
    col_names = ', '.join(columns)
    with connection.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO {structure_type.table_name} ({col_names}) VALUES ({placeholders})',
            values,
        )
    return row_id


def update_row(
    structure_type: StructureType,
    row_id: uuid.UUID,
    field_data: dict,
    code: str | None = None,
) -> None:
    sets = ['updated_at = %s']
    params = [timezone.now()]

    for field in structure_type.fields.exclude(field_type='ForeignKey'):
        sets.append(f'{field.name} = %s')
        params.append(_coerce_for_db(field, field_data.get(field.name)))

    params.append(str(row_id))
    with connection.cursor() as cursor:
        cursor.execute(
            f'UPDATE {structure_type.table_name} SET {", ".join(sets)} WHERE id = %s',
            params,
        )


def delete_table_row(structure_type: StructureType, row_id: uuid.UUID) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM {structure_type.table_name} WHERE id = %s',
            [str(row_id)],
        )


def load_field_data(structure_type: StructureType, row_id: uuid.UUID) -> dict:
    row = get_row(structure_type, row_id)
    if not row:
        return {}
    result = {}
    for field in structure_type.fields.exclude(field_type='ForeignKey'):
        val = row.get(field.name)
        if isinstance(val, Decimal):
            result[field.name] = val
        else:
            result[field.name] = val
    return result
