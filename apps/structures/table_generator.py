import re
import uuid

from django.apps import apps
from django.db import connection, models

from apps.structures.dynamic_models import REGISTERED_MODELS
from apps.structures.models import StructureField, StructureType

TABLE_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


class TableGenerator:
    """Динамическое создание таблиц и Django-моделей."""

    @staticmethod
    def validate_table_name(table_name: str) -> None:
        if not TABLE_NAME_RE.match(table_name):
            raise ValueError(
                f'Недопустимое имя таблицы: {table_name}. '
                'Используйте snake_case латиницей.'
            )

    @staticmethod
    def create_table(structure_type: StructureType):
        TableGenerator.validate_table_name(structure_type.table_name)
        if not structure_type.fields.exists():
            raise ValueError(f'У типа «{structure_type.name}» нет полей.')

        if structure_type.is_created and TableGenerator.table_exists(structure_type.table_name):
            return TableGenerator.register_model(structure_type)

        sql = TableGenerator._generate_create_sql(structure_type)
        with connection.cursor() as cursor:
            cursor.execute(sql)

        model = TableGenerator._create_django_model(structure_type)
        model_name = TableGenerator._model_name(structure_type)
        TableGenerator._register_model_class(model_name, model)

        structure_type.is_created = True
        structure_type.save(update_fields=['is_created'])
        return model

    @staticmethod
    def register_model(structure_type: StructureType):
        if not structure_type.is_created:
            return None
        model = TableGenerator._create_django_model(structure_type)
        model_name = TableGenerator._model_name(structure_type)
        TableGenerator._register_model_class(model_name, model)
        return model

    @staticmethod
    def _register_model_class(model_name: str, model):
        REGISTERED_MODELS[model_name] = model
        try:
            apps.get_model('structures', model_name)
        except LookupError:
            apps.register_model('structures', model)

    @staticmethod
    def table_exists(table_name: str) -> bool:
        table_name = table_name.lower()
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute(
                    'SELECT 1 FROM information_schema.tables WHERE table_name = %s',
                    [table_name],
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=%s",
                    [table_name],
                )
            return cursor.fetchone() is not None

    @staticmethod
    def drop_table(structure_type: StructureType):
        TableGenerator.validate_table_name(structure_type.table_name)
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS {structure_type.table_name}')
        model_name = TableGenerator._model_name(structure_type)
        REGISTERED_MODELS.pop(model_name, None)
        structure_type.is_created = False
        structure_type.save(update_fields=['is_created'])

    @staticmethod
    def add_column(structure_type: StructureType, field: StructureField):
        if not structure_type.is_created:
            raise ValueError('Таблица ещё не создана.')
        column_sql = TableGenerator._field_to_sql(field)
        sql = f'ALTER TABLE {structure_type.table_name} ADD COLUMN {column_sql}'
        with connection.cursor() as cursor:
            cursor.execute(sql)

    @staticmethod
    def _model_name(structure_type: StructureType) -> str:
        return f'dynamic_{structure_type.code.replace("-", "_")}'

    @staticmethod
    def _generate_create_sql(structure_type: StructureType) -> str:
        fields_sql = [TableGenerator._id_column_sql()]
        for field in structure_type.fields.all():
            fields_sql.append(TableGenerator._field_to_sql(field))
        fields_sql.append(TableGenerator._timestamp_column_sql('created_at'))
        fields_sql.append(TableGenerator._timestamp_column_sql('updated_at'))
        fields_sql.append('created_by VARCHAR(100) NULL' if connection.vendor == 'postgresql' else 'created_by TEXT')
        columns = ',\n                '.join(fields_sql)
        return f'''
            CREATE TABLE IF NOT EXISTS {structure_type.table_name} (
                {columns}
            )
        '''

    @staticmethod
    def _id_column_sql() -> str:
        if connection.vendor == 'postgresql':
            return 'id UUID PRIMARY KEY DEFAULT gen_random_uuid()'
        return 'id TEXT PRIMARY KEY'

    @staticmethod
    def _timestamp_column_sql(name: str) -> str:
        if connection.vendor == 'postgresql':
            return f'{name} TIMESTAMP DEFAULT NOW()'
        return f'{name} DATETIME DEFAULT CURRENT_TIMESTAMP'

    @staticmethod
    def _field_to_sql(field: StructureField) -> str:
        null_constraint = 'NOT NULL' if field.is_required else 'NULL'
        type_mapping = {
            'CharField': f'VARCHAR({field.max_length or 255})',
            'TextField': 'TEXT',
            'IntegerField': 'INTEGER',
            'FloatField': 'REAL' if connection.vendor == 'sqlite' else 'FLOAT',
            'DecimalField': f'DECIMAL({field.max_digits or 10}, {field.decimal_places or 2})',
            'BooleanField': 'BOOLEAN' if connection.vendor == 'postgresql' else 'INTEGER',
            'DateField': 'DATE',
            'DateTimeField': 'TIMESTAMP' if connection.vendor == 'postgresql' else 'DATETIME',
            'ForeignKey': 'TEXT',
        }
        sql_type = type_mapping.get(field.field_type, 'TEXT')
        return f'{field.name} {sql_type} {null_constraint}'

    @staticmethod
    def _create_django_model(structure_type: StructureType):
        model_name = TableGenerator._model_name(structure_type)

        meta = type(
            'Meta',
            (),
            {
                'db_table': structure_type.table_name,
                'managed': False,
                'app_label': 'structures',
            },
        )

        attrs = {
            '__module__': 'apps.structures.dynamic_models',
            'Meta': meta,
            'id': models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False),
            'created_at': models.DateTimeField(auto_now_add=True),
            'updated_at': models.DateTimeField(auto_now=True),
            'created_by': models.CharField(max_length=100, blank=True),
        }

        for field in structure_type.fields.all():
            if field.field_type == 'ForeignKey':
                continue
            field_class = getattr(models, field.field_type)
            field_kwargs = {'verbose_name': field.label}
            if not field.is_required:
                field_kwargs['blank'] = True
                field_kwargs['null'] = True
            if field.field_type == 'CharField':
                field_kwargs['max_length'] = field.max_length or 255
            if field.field_type == 'DecimalField':
                field_kwargs['max_digits'] = field.max_digits or 10
                field_kwargs['decimal_places'] = field.decimal_places or 2
            if field.field_type == 'BooleanField' and field.is_required:
                field_kwargs['default'] = False
            attrs[field.name] = field_class(**field_kwargs)

        return type(model_name, (models.Model,), attrs)
