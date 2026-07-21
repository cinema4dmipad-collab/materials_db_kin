from __future__ import annotations

import re

from apps.materials.imports.value_parse import PARSE_AUTO
from apps.materials.imports.wide import WideColumn
from apps.references.models import Property
from apps.structures.models import StructureField

TARGET_SKIP = 'skip'
TARGET_CODE = 'material.code'
TARGET_NAME = 'material.name'
TARGET_DESCRIPTION = 'material.description'
TARGET_TAGS = 'material.tags'
TARGET_PROPERTY_PREFIX = 'property:'
TARGET_STRUCTURE_PREFIX = 'structure:'

MATERIAL_TARGETS = (
    (TARGET_SKIP, '— пропустить —'),
    (TARGET_CODE, 'Код материала'),
    (TARGET_NAME, 'Название'),
    (TARGET_DESCRIPTION, 'Описание'),
    (TARGET_TAGS, 'Теги (для «Марка» → марка::значение)'),
)

# Несколько колонок в эти цели допустимы (склеиваются / накапливаются).
MULTI_VALUE_TARGETS = frozenset({TARGET_DESCRIPTION, TARGET_TAGS})

# Политики уникальности из staging (строки, чтобы не плодить циклы импорта).
_MATCH_BY_CODE = 'code'


def normalize_mapping_entry(value) -> tuple[str, str]:
    """Возвращает (target, parse_mode)."""
    if isinstance(value, dict):
        return value.get('target') or TARGET_SKIP, value.get('parse') or PARSE_AUTO
    return (value or TARGET_SKIP), PARSE_AUTO


def required_import_targets(match_policy: str | None = None) -> list[tuple[str, str]]:
    """
    Цели маппинга, без которых импорт не создаст материал.
    Тип структуры задаётся на шаге configure (не колонка файла).
    """
    required = [(TARGET_NAME, 'Название')]
    if (match_policy or '') == _MATCH_BY_CODE:
        required.insert(0, (TARGET_CODE, 'Код материала'))
    return required


def missing_required_targets(
    mapping_rows: list[dict],
    *,
    match_policy: str | None = None,
) -> list[tuple[str, str]]:
    mapped = {
        (row.get('target') or TARGET_SKIP)
        for row in mapping_rows
        if (row.get('target') or TARGET_SKIP) != TARGET_SKIP
    }
    return [(target, label) for target, label in required_import_targets(match_policy) if target not in mapped]


def target_allows_multiple_columns(target: str) -> bool:
    return target in MULTI_VALUE_TARGETS or target == TARGET_SKIP


def find_duplicate_mapping_targets(mapping_rows: list[dict]) -> list[dict]:
    """
    Колонки, сопоставленные с одной и той же целью (кроме описания/тегов).
    [{target, columns: [label, ...]}, ...]
    """
    by_target: dict[str, list[str]] = {}
    for row in mapping_rows:
        target = row.get('target') or TARGET_SKIP
        if target_allows_multiple_columns(target):
            continue
        column = row.get('column')
        if column is not None:
            label = getattr(column, 'display', None) or str(getattr(column, 'label', '') or column)
        else:
            label = str(row.get('column_label') or row.get('sample') or '?')
        by_target.setdefault(target, []).append(label)
    return [
        {'target': target, 'columns': columns}
        for target, columns in by_target.items()
        if len(columns) > 1
    ]


def mapping_choices(
    properties=None,
    structure_fields=None,
    *,
    match_policy: str | None = None,
) -> list[tuple[str, str]]:
    required_keys = {target for target, _label in required_import_targets(match_policy)}
    choices = []
    for value, label in MATERIAL_TARGETS:
        if value in required_keys:
            choices.append((value, f'{label} ★ обязательно'))
        else:
            choices.append((value, label))
    if structure_fields:
        for field in structure_fields:
            label = field.label or field.name
            prefix = 'Поле структуры'
            if field.is_required:
                choices.append(
                    (f'{TARGET_STRUCTURE_PREFIX}{field.name}', f'{prefix}: {label} ★ обязательно')
                )
            else:
                choices.append((f'{TARGET_STRUCTURE_PREFIX}{field.name}', f'{prefix}: {label}'))
    qs = properties if properties is not None else Property.objects.order_by('display_name', 'name')
    for prop in qs:
        label = prop.display_name or prop.name
        if prop.unit:
            label = f'{label} ({prop.unit})'
        choices.append((f'{TARGET_PROPERTY_PREFIX}{prop.pk}', f'Свойство: {label}'))
    return choices


def suggest_target(
    column: WideColumn,
    properties: list[Property],
    structure_fields: list[StructureField] | None = None,
    *,
    claimed_targets: set[str] | None = None,
) -> str:
    claimed = claimed_targets or set()
    hay = f'{column.group} {column.label}'.casefold()

    def _free(target: str) -> bool:
        return target_allows_multiple_columns(target) or target not in claimed

    if any(token in hay for token in ('наименование', 'название', 'name')) and _free(TARGET_NAME):
        return TARGET_NAME
    if 'марка' in hay:
        return TARGET_TAGS
    if any(token in hay for token in ('код', 'code', 'артикул', 'sku')) and _free(TARGET_CODE):
        return TARGET_CODE
    if 'производител' in hay:
        return TARGET_DESCRIPTION
    if 'описан' in hay:
        return TARGET_DESCRIPTION
    if 'тег' in hay or 'tag' in hay:
        return TARGET_TAGS

    best = TARGET_SKIP
    best_score = 0.0
    if structure_fields:
        for field in structure_fields:
            target = f'{TARGET_STRUCTURE_PREFIX}{field.name}'
            if not _free(target):
                continue
            for candidate in (field.label, field.name):
                if not candidate:
                    continue
                score = _similarity(hay, candidate.casefold())
                if score > best_score and score >= 0.45:
                    best_score = score
                    best = target
    if best != TARGET_SKIP:
        return best

    for prop in properties:
        target = f'{TARGET_PROPERTY_PREFIX}{prop.pk}'
        if not _free(target):
            continue
        for candidate in (prop.name, prop.display_name):
            if not candidate:
                continue
            score = _similarity(hay, candidate.casefold())
            if score > best_score and score >= 0.45:
                best_score = score
                best = target
    return best


def suggest_parse_mode(
    column: WideColumn,
    target: str,
    *,
    structure_fields=None,
    properties=None,
) -> str:
    if target.startswith(TARGET_STRUCTURE_PREFIX):
        field_name = target.split(':', 1)[1]
        for structure_field in structure_fields or []:
            if structure_field.name == field_name and structure_field.field_type == 'MaterialLink':
                return 'text'
    if target.startswith(TARGET_PROPERTY_PREFIX):
        prop_id = target.split(':', 1)[1]
        for prop in properties or []:
            if str(prop.pk) == prop_id and prop.data_type == Property.MATERIAL_LINK_DATA_TYPE:
                return 'text'
    if target.startswith(TARGET_STRUCTURE_PREFIX) or target.startswith(TARGET_PROPERTY_PREFIX):
        hay = f'{column.group} {column.label}'.casefold()
        if any(token in hay for token in ('замасливатель', 'плетения', 'производител', 'основа')):
            return 'text'
    return PARSE_AUTO


def mapping_for_session(mapping_rows: list[dict]) -> dict:
    """mapping_rows: {column, target, parse} → session dict by index."""
    result = {}
    for item in mapping_rows:
        result[str(item['column'].index)] = {
            'target': item['target'],
            'parse': item.get('parse') or PARSE_AUTO,
            'label': item['column'].display,
        }
    return result


def profile_payload_from_mapping(
    mapping: dict,
    *,
    sheet,
    header_row,
    group_row,
    match_policy,
    structure_type_id=None,
) -> dict:
    return {
        'sheet': sheet,
        'header_row': header_row,
        'group_row': group_row,
        'match_policy': match_policy,
        'structure_type_id': structure_type_id or '',
        'columns': [
            {
                'label': (entry.get('label') if isinstance(entry, dict) else ''),
                'target': normalize_mapping_entry(entry)[0],
                'parse': normalize_mapping_entry(entry)[1],
            }
            for entry in mapping.values()
        ],
    }


def apply_profile_to_columns(columns: list[WideColumn], profile_columns: list[dict]) -> dict:
    """Сопоставляет сохранённый профиль к колонкам текущего файла по label."""
    by_label = {
        (item.get('label') or '').casefold(): item
        for item in profile_columns
        if item.get('label')
    }
    mapping = {}
    for col in columns:
        key = col.display.casefold()
        item = by_label.get(key) or by_label.get(col.label.casefold())
        if item:
            mapping[str(col.index)] = {
                'target': item.get('target') or TARGET_SKIP,
                'parse': item.get('parse') or PARSE_AUTO,
                'label': col.display,
            }
    return mapping


def _similarity(a: str, b: str) -> float:
    a_tokens = set(re.findall(r'[\wа-яё]+', a, flags=re.IGNORECASE))
    b_tokens = set(re.findall(r'[\wа-яё]+', b, flags=re.IGNORECASE))
    if not a_tokens or not b_tokens:
        return 1.0 if a.strip() == b.strip() else 0.0
    inter = len(a_tokens & b_tokens)
    return inter / max(len(a_tokens), len(b_tokens))
