"""Migrate materials from one StructureType to another with interactive field mapping."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from apps.materials.models import Material
from apps.structures.decimal_range import pack_decimal_field_data, read_decimal_field_state
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import delete_table_row, get_row, insert_row

SKIP = ''
SESSION_KEY = 'structure_migrate'


@dataclass(frozen=True)
class FieldMapRow:
    target: StructureField
    source_name: str  # empty = skip
    auto: bool
    compatible: bool
    warning: str = ''


def supported_fields(structure_type: StructureType):
    """All structure columns for mapping (including legacy ForeignKey → material link)."""
    return list(
        StructureField.objects.filter(structure_type=structure_type).order_by(
            'sort_order', 'name'
        )
    )


def _normalized_type(field_type: str) -> str:
    if field_type == 'ForeignKey':
        return 'MaterialLink'
    return field_type or ''


def fields_compatible(source: StructureField, target: StructureField) -> tuple[bool, str]:
    src_type = _normalized_type(source.field_type)
    tgt_type = _normalized_type(target.field_type)
    if src_type == tgt_type:
        return True, ''
    # Soft conversions into text
    if tgt_type in {'CharField', 'TextField'}:
        return True, 'Значение будет сохранено как строка.'
    if src_type == 'IntegerField' and tgt_type == 'DecimalField':
        return True, 'Целое будет записано как десятичное.'
    if src_type == 'FloatField' and tgt_type == 'DecimalField':
        return True, ''
    if src_type == 'DecimalField' and tgt_type in {'IntegerField', 'FloatField'}:
        return True, 'Дробная часть может быть потеряна.'
    if src_type == 'BooleanField' and tgt_type in {'CharField', 'TextField', 'IntegerField'}:
        return True, ''
    if src_type == 'MaterialLink' and tgt_type == 'MaterialLink':
        return True, ''
    return False, f'Типы несовместимы: {source.field_type} → {target.field_type}.'


def suggest_field_mapping(
    source: StructureType,
    target: StructureType,
) -> list[FieldMapRow]:
    """Auto-map only identical field names (case-insensitive); leave others empty."""
    source_fields = supported_fields(source)
    by_name = {f.name.lower(): f for f in source_fields}
    rows: list[FieldMapRow] = []
    for target_field in supported_fields(target):
        source_field = by_name.get(target_field.name.lower())
        if source_field is None:
            rows.append(
                FieldMapRow(
                    target=target_field,
                    source_name=SKIP,
                    auto=False,
                    compatible=True,
                )
            )
            continue
        ok, warning = fields_compatible(source_field, target_field)
        rows.append(
            FieldMapRow(
                target=target_field,
                source_name=source_field.name if ok else SKIP,
                auto=ok,
                compatible=ok,
                warning=warning if ok else warning,
            )
        )
    return rows


def parse_mapping_from_post(post, target: StructureType) -> dict[str, str]:
    """target_field.name → source_field.name or ''."""
    mapping: dict[str, str] = {}
    for field in supported_fields(target):
        key = f'map_{field.name}'
        # Constructor may post multiple keys; prefer non-empty.
        if hasattr(post, 'getlist'):
            values = [v.strip() for v in post.getlist(key) if (v or '').strip()]
            mapping[field.name] = values[0] if values else ''
        else:
            mapping[field.name] = (post.get(key) or '').strip()
    return mapping


def validate_mapping(
    source: StructureType,
    target: StructureType,
    mapping: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    source_names = {f.name for f in supported_fields(source)}
    source_by_name = {f.name: f for f in supported_fields(source)}
    claimed: dict[str, str] = {}
    for target_field in supported_fields(target):
        # Legacy ForeignKey has no SQL column — show in UI, but do not require/copy.
        if target_field.field_type == 'ForeignKey':
            continue
        src_name = (mapping.get(target_field.name) or '').strip()
        if not src_name:
            if target_field.is_required and not (target_field.default_value or '').strip():
                errors.append(
                    f'Обязательное поле «{target_field.label}» не сопоставлено '
                    'и не имеет значения по умолчанию.'
                )
            continue
        if src_name not in source_names:
            errors.append(f'Неизвестное исходное поле для «{target_field.label}»: {src_name}.')
            continue
        if src_name in claimed:
            errors.append(
                f'Исходное поле «{src_name}» сопоставлено дважды '
                f'(«{claimed[src_name]}» и «{target_field.label}»).'
            )
            continue
        claimed[src_name] = target_field.label
        ok, warning = fields_compatible(source_by_name[src_name], target_field)
        if not ok:
            errors.append(f'«{target_field.label}»: {warning}')
    return errors


def _copy_value_for_target(
    *,
    source_row: dict,
    source_field: StructureField,
    target_field: StructureField,
) -> dict:
    """Return payload fragment for insert into target."""
    if target_field.field_type == 'DecimalField':
        if source_field.field_type == 'DecimalField':
            state = read_decimal_field_state(source_row, source_field.name)
            return pack_decimal_field_data(
                target_field.name,
                value_kind=state['value_kind'],
                value=state['value'],
                value_b=state['value_b'],
            )
        raw = source_row.get(source_field.name)
        return pack_decimal_field_data(
            target_field.name,
            value_kind='scalar',
            value=raw,
            value_b=None,
        )

    if source_field.field_type == 'DecimalField' and target_field.field_type == 'IntegerField':
        state = read_decimal_field_state(source_row, source_field.name)
        value = state['value']
        try:
            return {target_field.name: int(value) if value not in (None, '') else None}
        except (TypeError, ValueError):
            return {target_field.name: value}

    if source_field.field_type == 'DecimalField':
        state = read_decimal_field_state(source_row, source_field.name)
        # CharField etc.: store display-ish scalar value
        return {target_field.name: state['value']}

    return {target_field.name: source_row.get(source_field.name)}


def build_target_payload(
    *,
    source_row: dict,
    source: StructureType,
    target: StructureType,
    mapping: dict[str, str],
) -> dict:
    source_by_name = {f.name: f for f in supported_fields(source)}
    payload: dict = {}
    for target_field in supported_fields(target):
        if target_field.field_type == 'ForeignKey':
            continue
        src_name = (mapping.get(target_field.name) or '').strip()
        if not src_name:
            continue
        source_field = source_by_name.get(src_name)
        if source_field is None or source_field.field_type == 'ForeignKey':
            continue
        payload.update(
            _copy_value_for_target(
                source_row=source_row,
                source_field=source_field,
                target_field=target_field,
            )
        )
    return payload


def materials_for_structure(source: StructureType):
    return Material.objects.filter(struct_type=source).select_related('home_workspace')


def migrate_materials(
    *,
    source: StructureType,
    target: StructureType,
    mapping: dict[str, str],
    delete_source: bool = False,
) -> dict:
    """
    Move all materials from source to target.

    Returns stats dict. Raises ValueError on mapping/precondition errors.
    """
    if source.pk == target.pk:
        raise ValueError('Исходный и целевой типы должны отличаться.')
    if not source.is_created or not SQLExecutor.table_exists(source):
        raise ValueError('Исходная SQL-таблица не создана.')
    if not target.is_created or not SQLExecutor.table_exists(target):
        raise ValueError('Целевая SQL-таблица не создана.')

    errors = validate_mapping(source, target, mapping)
    if errors:
        raise ValueError('; '.join(errors))

    materials = list(materials_for_structure(source))
    migrated = 0
    skipped_missing_row = 0
    deleted_source_rows = 0
    old_row_ids: set = set()

    with transaction.atomic():
        for material in materials:
            old_id = material.struct_props_id
            payload = {}
            if old_id:
                source_row = get_row(source, old_id)
                if source_row is None:
                    skipped_missing_row += 1
                else:
                    payload = build_target_payload(
                        source_row=source_row,
                        source=source,
                        target=target,
                        mapping=mapping,
                    )
                    old_row_ids.add(old_id)
            else:
                skipped_missing_row += 1

            new_id = insert_row(
                target,
                material.code,
                payload,
                created_by=material.created_by or '',
                allow_empty_null=True,
            )
            material.struct_type = target
            material.struct_props_id = new_id
            material.save(update_fields=['struct_type', 'struct_props_id', 'updated_at'])
            migrated += 1

        # Delete orphan source rows that are no longer referenced.
        for row_id in old_row_ids:
            still_linked = Material.objects.filter(
                struct_type=source,
                struct_props_id=row_id,
            ).exists()
            if still_linked:
                continue
            try:
                delete_table_row(source, row_id)
                deleted_source_rows += 1
            except ValueError:
                pass

        remaining = Material.objects.filter(struct_type=source).count()
        deleted_type = False
        if delete_source:
            if remaining:
                raise ValueError(
                    f'Нельзя удалить исходный тип: осталось материалов {remaining}.'
                )
            drop = SQLExecutor.drop_table(source)
            if not drop['success']:
                raise ValueError(drop.get('error') or 'Не удалось удалить SQL-таблицу.')
            source_name = source.name
            source.delete()
            deleted_type = True
        else:
            source_name = source.name

    return {
        'migrated': migrated,
        'skipped_missing_row': skipped_missing_row,
        'deleted_source_rows': deleted_source_rows,
        'deleted_source_type': deleted_type,
        'source_name': source_name,
        'target_name': target.name,
        'material_count': len(materials),
    }

