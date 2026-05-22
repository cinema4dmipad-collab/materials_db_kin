from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class TableGenerator:
    """Compatibility wrapper for SQL-only dynamic table management."""

    @staticmethod
    def validate_table_name(table_name: str) -> None:
        SQLExecutor.validate_identifier(table_name)

    @staticmethod
    def create_table(structure_type: StructureType):
        result = SQLExecutor.create_table(structure_type)
        if not result['success']:
            raise ValueError(result['error'])
        return result

    @staticmethod
    def register_model(structure_type: StructureType):
        return None

    @staticmethod
    def table_exists(table_name: str) -> bool:
        return SQLExecutor.table_exists(table_name)

    @staticmethod
    def drop_table(structure_type: StructureType):
        result = SQLExecutor.drop_table(structure_type)
        if not result['success']:
            raise ValueError(result['error'])
        return result

    @staticmethod
    def add_column(structure_type: StructureType, field: StructureField):
        result = SQLExecutor.add_column(structure_type, field)
        if not result['success']:
            raise ValueError(result['error'])
        return result

    @staticmethod
    def _model_name(structure_type: StructureType) -> str:
        return f'dynamic_{structure_type.code.replace("-", "_")}'
