import uuid
from decimal import Decimal

from apps.materials.models import Material
from apps.structures.constants import resolve_structure_field_decimal_places
from apps.structures.decimal_range import format_decimal_field_display, read_decimal_field_state
from apps.structures.choice_options import choice_label_for_value, resolved_choice_options
from apps.structures.models import CHOICE_FIELD_TYPE, MATERIAL_LINK_FIELD_TYPE, StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor


class DisplayValue:
    """Обёртка для отображения значения в шаблонах."""

    def __init__(self, field: StructureField, value, row: dict | None = None):
        self.field = field
        self._value = value
        self._row = row or {}

    def get_value(self):
        if self.field.field_type == MATERIAL_LINK_FIELD_TYPE and self._value not in (None, ''):
            from apps.structures.forms import material_link_display

            return material_link_display(self._value)
        if self.field.field_type == 'DecimalField':
            state = read_decimal_field_state(self._row, self.field.name)
            return format_decimal_field_display(
                value_kind=state['value_kind'],
                value=state['value'],
                value_b=state['value_b'],
                decimal_places=resolve_structure_field_decimal_places(self.field),
            )
        return self._value

    @property
    def material_pk(self):
        if self.field.field_type != MATERIAL_LINK_FIELD_TYPE:
            return None
        if self._value in (None, ''):
            return None
        from apps.structures.forms import material_from_value

        material = material_from_value(self._value)
        return str(material.pk) if material is not None else None


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
        DisplayValue(field, row.get(field.name), row=row)
        for field in _supported_fields(structure_type)
    ]


def insert_row(
    structure_type: StructureType,
    code: str,
    field_data: dict,
    created_by: str = '',
    *,
    allow_empty_null: bool = False,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    data = {'id': str(row_id), 'created_by': created_by or ''}
    data.update(field_data or {})

    result = SQLExecutor.insert(structure_type, data, allow_empty_null=allow_empty_null)
    if not result['success']:
        raise ValueError(result['error'])
    return row_id


def update_row(
    structure_type: StructureType,
    row_id: uuid.UUID,
    field_data: dict,
    code: str | None = None,
    *,
    allow_empty_null: bool = False,
) -> None:
    result = SQLExecutor.update(
        structure_type,
        row_id,
        field_data or {},
        allow_empty_null=allow_empty_null,
    )
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


def _structure_field_label_fragment(field: StructureField, record: dict) -> str | None:
    if field.field_type == 'DecimalField':
        state = read_decimal_field_state(record, field.name)
        text = format_decimal_field_display(
            value_kind=state['value_kind'],
            value=state['value'],
            value_b=state['value_b'],
            decimal_places=resolve_structure_field_decimal_places(field),
        )
        return text if text != '—' else None

    value = record.get(field.name)
    if value in (None, ''):
        return None

    if field.field_type == MATERIAL_LINK_FIELD_TYPE:
        from apps.structures.forms import MATERIAL_LINK_MISSING_LABEL, material_link_display

        text = material_link_display(value)
        return None if text == MATERIAL_LINK_MISSING_LABEL else text

    options = resolved_choice_options(field)
    if field.field_type == CHOICE_FIELD_TYPE or options:
        return choice_label_for_value(options, value) or str(value)

    return str(value)


def structure_record_label(record: dict, structure_type: StructureType) -> str:
    for field in _supported_fields(structure_type):
        fragment = _structure_field_label_fragment(field, record)
        if fragment:
            return fragment
    record_id = str(record.get('id') or '')
    if record_id:
        return f'Запись {record_id[:8]}…'
    return '—'


def linked_materials_display_label(linked_materials) -> str:
    if not linked_materials:
        return ''
    if len(linked_materials) == 1:
        return linked_materials[0]['name']
    return ', '.join(material['name'] for material in linked_materials)


def structure_record_display_label(
    record: dict,
    structure_type: StructureType,
    linked_materials=None,
    *,
    workspace=None,
) -> str:
    if linked_materials is None:
        linked_materials = linked_materials_for_record(
            structure_type,
            record['id'],
            workspace=workspace,
        )
    material_label = linked_materials_display_label(linked_materials)
    if material_label:
        return material_label
    return structure_record_label(record, structure_type)


def count_linked_materials(structure_type: StructureType, row_id) -> int:
    from apps.materials.models import Material

    return Material.objects.filter(
        struct_type=structure_type,
        struct_props_id=row_id,
    ).count()


def linked_materials_for_record(structure_type: StructureType, row_id, workspace=None):
    from apps.materials.models import Material

    queryset = Material.objects.filter(
        struct_type=structure_type,
        struct_props_id=row_id,
    ).order_by('code', 'name')
    if workspace is not None:
        from apps.workspaces.services import materials_visible_in

        queryset = queryset.filter(pk__in=materials_visible_in(workspace).values('pk'))
    return list(queryset.values('pk', 'code', 'name'))
