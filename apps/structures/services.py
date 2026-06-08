from django.core.exceptions import ImproperlyConfigured

from apps.structures.models import StructureType

_DISABLED_MSG = (
    'Dynamic Django model generation is disabled. '
    'Use apps.structures.sql_executor.SQLExecutor for dynamic tables.'
)


def generate_model_code(structure_type: StructureType) -> str:
    raise ImproperlyConfigured(_DISABLED_MSG)


def append_generated_model(structure_type: StructureType) -> str:
    raise ImproperlyConfigured(_DISABLED_MSG)
