from pathlib import Path

from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured

from apps.structures.models import StructureType

GENERATED_HEADER = '''# Автоматически генерируемые модели. Не редактировать вручную.
# Создаются командой: python manage.py generate_structure_model <id>

from django.db import models

from apps.structures.models import StructureInstance

'''


def structure_model_class_name(code: str) -> str:
    parts = code.replace('-', '_').split('_')
    return ''.join(part.capitalize() for part in parts if part) + 'Structure'


def generate_field_line(field) -> str:
    name = field.name
    if field.field_type == 'CharField':
        max_length = field.max_length or 200
        required = '' if field.is_required else ', blank=True'
        return f'    {name} = models.CharField(max_length={max_length}{required})'
    if field.field_type == 'TextField':
        if field.is_required:
            return f'    {name} = models.TextField()'
        return f'    {name} = models.TextField(blank=True)'
    if field.field_type == 'IntegerField':
        if field.is_required:
            return f'    {name} = models.IntegerField()'
        return f'    {name} = models.IntegerField(null=True, blank=True)'
    if field.field_type == 'DecimalField':
        max_digits = field.max_digits or 10
        decimal_places = field.decimal_places or 2
        if field.is_required:
            return f'    {name} = models.DecimalField(max_digits={max_digits}, decimal_places={decimal_places})'
        return (
            f'    {name} = models.DecimalField(max_digits={max_digits}, '
            f'decimal_places={decimal_places}, null=True, blank=True)'
        )
    if field.field_type == 'FloatField':
        if field.is_required:
            return f'    {name} = models.FloatField()'
        return f'    {name} = models.FloatField(null=True, blank=True)'
    if field.field_type == 'BooleanField':
        default = 'default=False'
        return f'    {name} = models.BooleanField({default})'
    if field.field_type == 'DateField':
        if field.is_required:
            return f'    {name} = models.DateField()'
        return f'    {name} = models.DateField(null=True, blank=True)'
    if field.field_type == 'DateTimeField':
        if field.is_required:
            return f'    {name} = models.DateTimeField()'
        return f'    {name} = models.DateTimeField(null=True, blank=True)'
    if field.field_type == 'ForeignKey':
        target = field.foreign_key_model or 'auth.User'
        if field.is_required:
            return f"    {name} = models.ForeignKey('{target}', on_delete=models.SET_NULL, null=True)"
        return (
            f"    {name} = models.ForeignKey('{target}', on_delete=models.SET_NULL, "
            f'null=True, blank=True)'
        )
    return f'    # unsupported field type: {field.field_type}'


def generate_model_code(structure_type: StructureType) -> str:
    raise ImproperlyConfigured(
        'Dynamic Django model generation is disabled. '
        'Use apps.structures.sql_executor.SQLExecutor for dynamic tables.'
    )


def generated_models_path() -> Path:
    return Path(__file__).resolve().parent / 'generated_models.py'


def model_already_generated(class_name: str) -> bool:
    path = generated_models_path()
    if not path.exists():
        return False
    return f'class {class_name}(' in path.read_text(encoding='utf-8')


def append_generated_model(structure_type: StructureType) -> str:
    raise ImproperlyConfigured(
        'Writing generated Django models is disabled. '
        'Dynamic structure tables are managed through SQLExecutor only.'
    )


def resolve_foreign_key_model(model_label: str):
    if not model_label:
        return None
    try:
        return django_apps.get_model(model_label)
    except (LookupError, ValueError):
        return None
