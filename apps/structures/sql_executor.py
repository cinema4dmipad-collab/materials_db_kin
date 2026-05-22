import re
import uuid
from datetime import date, datetime
from decimal import Decimal

from django.db import connection
from django.utils import timezone

from apps.structures.models import StructureField, StructureType

IDENTIFIER_RE = re.compile(r'^[a-z][a-z0-9_]*$')


class SQLExecutor:
    """SQL-only access layer for dynamic structure tables."""

    @classmethod
    def create_table(cls, structure_type: StructureType) -> dict:
        try:
            original_structure_type = structure_type
            structure_type = StructureType.objects.prefetch_related('fields').get(pk=structure_type.pk)
            if structure_type.is_created:
                raise ValueError(f'Таблица «{structure_type.table_name}» уже создана.')

            fields = list(structure_type.fields.all())
            if not fields:
                raise ValueError(f'У типа «{structure_type.name}» нет полей.')
            if cls.table_exists(structure_type):
                raise ValueError(f'Таблица «{structure_type.table_name}» уже существует.')

            table_name = cls.quote_identifier(structure_type.table_name)
            columns = [cls._id_column_sql()]
            columns.extend(cls._column_definition(field) for field in cls._sql_fields(fields))
            columns.extend(
                [
                    cls._timestamp_column_sql('created_at'),
                    cls._timestamp_column_sql('updated_at'),
                    f'{cls.quote_identifier("created_by")} {cls._text_type(100)} NULL',
                ]
            )

            with connection.cursor() as cursor:
                cursor.execute(f'CREATE TABLE {table_name} ({", ".join(columns)})')

            structure_type.is_created = True
            structure_type.save(update_fields=['is_created'])
            original_structure_type.is_created = True
            return {'success': True, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def drop_table(cls, structure_type: StructureType) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            with connection.cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS {table_name}')

            structure_type.is_created = False
            structure_type.save(update_fields=['is_created'])
            return {'success': True, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def table_exists(cls, structure_type: StructureType | str) -> bool:
        table_name = (
            structure_type.table_name
            if isinstance(structure_type, StructureType)
            else str(structure_type)
        )
        cls.validate_identifier(table_name)
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = %s
                    """,
                    [table_name],
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = %s",
                    [table_name],
                )
            return cursor.fetchone() is not None

    @classmethod
    def insert(cls, structure_type: StructureType, data: dict) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            row_id = str(data.get('id') or uuid.uuid4())
            now = timezone.now()

            columns = ['id', 'created_at', 'updated_at', 'created_by']
            values = [row_id, now, now, data.get('created_by', '')]

            for field in cls._sql_fields(structure_type.fields.all()):
                value = data.get(field.name)
                if field.name in data and not cls._is_empty_value(value):
                    cls.validate_identifier(field.name)
                    columns.append(field.name)
                    values.append(cls._coerce_for_db(field, value))
                elif cls._has_default(field):
                    cls.validate_identifier(field.name)
                    columns.append(field.name)
                    values.append(cls._default_for_db(field))
                elif field.is_required:
                    raise ValueError(f'Field {field.name!r} is required.')

            quoted_columns = ', '.join(cls.quote_identifier(column) for column in columns)
            placeholders = ', '.join(['%s'] * len(values))
            sql = f'INSERT INTO {table_name} ({quoted_columns}) VALUES ({placeholders})'

            with connection.cursor() as cursor:
                cursor.execute(sql, values)

            return {'success': True, 'id': row_id, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def get_all(cls, structure_type: StructureType, limit: int = 100, offset: int = 0) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT * FROM {table_name} ORDER BY {cls.quote_identifier("created_at")} DESC '
                    'LIMIT %s OFFSET %s',
                    [limit, offset],
                )
                columns = [column[0] for column in cursor.description]
                records = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                total = cursor.fetchone()[0]

            return {'success': True, 'records': records, 'total': total, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def get_by_id(cls, structure_type: StructureType, record_id: str | uuid.UUID) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT * FROM {table_name} WHERE {cls.quote_identifier("id")} = %s',
                    [str(record_id)],
                )
                columns = [column[0] for column in cursor.description]
                row = cursor.fetchone()

            if row is None:
                return {'success': False, 'record': None, 'error': 'Record not found'}
            return {
                'success': True,
                'record': dict(zip(columns, row, strict=True)),
                'error': None,
            }
        except Exception as exc:
            return {'success': False, 'record': None, 'error': str(exc)}

    @classmethod
    def update(cls, structure_type: StructureType, record_id: str | uuid.UUID, data: dict) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            fields_by_name = {
                field.name: field for field in cls._sql_fields(structure_type.fields.all())
            }
            assignments = [f'{cls.quote_identifier("updated_at")} = %s']
            values = [timezone.now()]

            for name, value in data.items():
                if name in {'id', 'created_at', 'updated_at', 'created_by'}:
                    continue
                field = fields_by_name.get(name)
                if field is None:
                    continue
                if field.is_required and cls._is_empty_value(value):
                    raise ValueError(f'Field {field.name!r} is required.')
                assignments.append(f'{cls.quote_identifier(name)} = %s')
                values.append(cls._coerce_for_db(field, value))

            values.append(str(record_id))
            with connection.cursor() as cursor:
                cursor.execute(
                    f'UPDATE {table_name} SET {", ".join(assignments)} '
                    f'WHERE {cls.quote_identifier("id")} = %s',
                    values,
                )

            return {'success': True, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def delete(cls, structure_type: StructureType, record_id: str | uuid.UUID) -> dict:
        try:
            table_name = cls.quote_identifier(structure_type.table_name)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'DELETE FROM {table_name} WHERE {cls.quote_identifier("id")} = %s',
                    [str(record_id)],
                )
            return {'success': True, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @classmethod
    def add_column(cls, structure_type: StructureType, field: StructureField) -> dict:
        try:
            if not cls._is_sql_backed_field(field):
                return {'success': True, 'error': None}

            table_name = cls.quote_identifier(structure_type.table_name)
            column_name = cls.quote_identifier(field.name)
            has_default = cls._has_default(field)
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                row_count = cursor.fetchone()[0]
                if row_count and field.is_required and not has_default:
                    raise ValueError(
                        f'Cannot add required column {field.name!r} to non-empty table '
                        'without StructureField.default_value.'
                    )

                # Portable engines cannot all enforce NOT NULL after adding a column without
                # rebuilding the table. For populated tables, add it nullable, backfill it,
                # and let inserts/defaults preserve the required-field invariant.
                force_nullable = bool(row_count and field.is_required and has_default)
                cursor.execute(
                    f'ALTER TABLE {table_name} ADD COLUMN '
                    f'{cls._column_definition(field, force_nullable=force_nullable)}'
                )
                if row_count and has_default:
                    cursor.execute(
                        f'UPDATE {table_name} SET {column_name} = %s '
                        f'WHERE {column_name} IS NULL',
                        [cls._default_for_db(field)],
                    )
            return {'success': True, 'error': None}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    @staticmethod
    def validate_identifier(identifier: str) -> None:
        if not IDENTIFIER_RE.fullmatch(identifier or ''):
            raise ValueError(
                f'Недопустимый SQL идентификатор: {identifier}. '
                'Используйте snake_case латиницей.'
            )

    @classmethod
    def quote_identifier(cls, identifier: str) -> str:
        cls.validate_identifier(identifier)
        return connection.ops.quote_name(identifier)

    @staticmethod
    def _is_sql_backed_field(field: StructureField) -> bool:
        return field.field_type != 'ForeignKey'

    @classmethod
    def _sql_fields(cls, fields) -> list[StructureField]:
        return [field for field in fields if cls._is_sql_backed_field(field)]

    @staticmethod
    def _is_empty_value(value) -> bool:
        return value is None or value == ''

    @classmethod
    def _column_definition(
        cls,
        field: StructureField,
        *,
        force_nullable: bool = False,
        include_default: bool = True,
    ) -> str:
        null_constraint = 'NULL' if force_nullable else 'NOT NULL' if field.is_required else 'NULL'
        default_clause = ''
        if include_default and cls._has_default(field):
            default_clause = f' DEFAULT {cls._sql_literal(cls._default_for_db(field))}'
        return (
            f'{cls.quote_identifier(field.name)} {cls._field_sql_type(field)} '
            f'{null_constraint}{default_clause}'
        )

    @classmethod
    def _id_column_sql(cls) -> str:
        if connection.vendor == 'postgresql':
            return f'{cls.quote_identifier("id")} UUID PRIMARY KEY DEFAULT gen_random_uuid()'
        return f'{cls.quote_identifier("id")} TEXT PRIMARY KEY'

    @classmethod
    def _timestamp_column_sql(cls, name: str) -> str:
        sql_type = 'TIMESTAMP' if connection.vendor == 'postgresql' else 'DATETIME'
        default = 'NOW()' if connection.vendor == 'postgresql' else 'CURRENT_TIMESTAMP'
        return f'{cls.quote_identifier(name)} {sql_type} DEFAULT {default}'

    @staticmethod
    def _text_type(max_length: int | None = None) -> str:
        if connection.vendor == 'postgresql' and max_length:
            return f'VARCHAR({max_length})'
        return 'TEXT'

    @classmethod
    def _field_sql_type(cls, field: StructureField) -> str:
        if field.field_type == 'CharField':
            return cls._text_type(field.max_length or 255)
        if field.field_type == 'TextField':
            return 'TEXT'
        if field.field_type == 'IntegerField':
            return 'INTEGER'
        if field.field_type == 'FloatField':
            return 'DOUBLE PRECISION' if connection.vendor == 'postgresql' else 'REAL'
        if field.field_type == 'DecimalField':
            return f'DECIMAL({field.max_digits or 10}, {field.decimal_places or 2})'
        if field.field_type == 'BooleanField':
            return 'BOOLEAN' if connection.vendor == 'postgresql' else 'INTEGER'
        if field.field_type == 'DateField':
            return 'DATE'
        if field.field_type == 'DateTimeField':
            return 'TIMESTAMP' if connection.vendor == 'postgresql' else 'DATETIME'
        if field.field_type == 'ForeignKey':
            return 'TEXT'
        return 'TEXT'

    @staticmethod
    def _coerce_for_db(field: StructureField, value):
        if value is None or value == '':
            return None
        if field.field_type == 'BooleanField':
            if isinstance(value, str):
                value = value.strip().lower() in {'1', 'true', 'yes', 'on'}
            if connection.vendor == 'sqlite':
                return 1 if value else 0
            return bool(value)
        if field.field_type == 'IntegerField':
            return int(value)
        if field.field_type == 'DecimalField':
            return Decimal(str(value))
        if field.field_type == 'FloatField':
            return float(value)
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

    @staticmethod
    def _has_default(field: StructureField) -> bool:
        return field.default_value != ''

    @classmethod
    def _default_for_db(cls, field: StructureField):
        return cls._coerce_for_db(field, field.default_value)

    @staticmethod
    def _sql_literal(value) -> str:
        if value is None:
            return 'NULL'
        if isinstance(value, bool):
            if connection.vendor == 'sqlite':
                return '1' if value else '0'
            return 'TRUE' if value else 'FALSE'
        if isinstance(value, int | float | Decimal):
            return str(value)
        if isinstance(value, datetime):
            value = value.isoformat(sep=' ')
        elif isinstance(value, date):
            value = value.isoformat()
        return "'" + str(value).replace("'", "''") + "'"
