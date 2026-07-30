from __future__ import annotations

import re

from apps.materials.imports.value_parse import PARSE_AUTO, PARSE_BOOLEAN, PARSE_DATE, PARSE_TEXT
from apps.materials.imports.wide import WideColumn
from apps.references.models import Property
from apps.structures.models import StructureField

TARGET_SKIP = 'skip'
TARGET_CODE = 'material.code'
TARGET_NAME = 'material.name'
TARGET_DESCRIPTION = 'material.description'
TARGET_TAGS = 'material.tags'
TARGET_MANUFACTURER = 'material.manufacturer'
TARGET_AVAILABILITY = 'material.availability'
TARGET_TECHNOLOGY = 'material.technology'
TARGET_PROPERTY_PREFIX = 'property:'
TARGET_STRUCTURE_PREFIX = 'structure:'

MATERIAL_TARGETS = (
    (TARGET_SKIP, '— пропустить —'),
    (TARGET_CODE, 'Код материала'),
    (TARGET_NAME, 'Название'),
    (TARGET_DESCRIPTION, 'Описание'),
    (TARGET_MANUFACTURER, 'Производитель'),
    (TARGET_AVAILABILITY, 'Доступность'),
    (TARGET_TECHNOLOGY, 'Технология'),
    (TARGET_TAGS, 'Теги (для «Марка» → марка::значение)'),
)

# Несколько колонок в эти цели допустимы (склеиваются / накапливаются).
MULTI_VALUE_TARGETS = frozenset({TARGET_DESCRIPTION, TARGET_TAGS})

# Опциональные поля материала — добавляются оператором через «Поле материала».
OPTIONAL_MATERIAL_TARGETS = (
    (TARGET_DESCRIPTION, 'Описание'),
    (TARGET_MANUFACTURER, 'Производитель'),
    (TARGET_AVAILABILITY, 'Доступность'),
    (TARGET_TECHNOLOGY, 'Технология'),
)
OPTIONAL_MATERIAL_TARGET_KEYS = frozenset(target for target, _label in OPTIONAL_MATERIAL_TARGETS)

TARGET_TAG_ROW_PREFIX = 'tag:'


def field_mapping_section(target: str, *, is_primary: bool) -> str:
    """Секция конструктора: primary | material | property | tag."""
    if is_primary:
        return 'primary'
    if (target or '').startswith(TARGET_TAG_ROW_PREFIX) or target == TARGET_TAGS:
        return 'tag'
    if (target or '').startswith(TARGET_PROPERTY_PREFIX):
        return 'property'
    return 'material'

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


def primary_import_targets(
    structure_fields=None,
    *,
    match_policy: str | None = None,
) -> list[tuple[str, str]]:
    """
    Строки конструктора по умолчанию: обязательные поля материала + поля структуры.
    Доп. свойства и метаданные материала добавляются через «+».
    """
    targets = list(required_import_targets(match_policy))
    seen = {target for target, _label in targets}
    for field in structure_fields or []:
        target = f'{TARGET_STRUCTURE_PREFIX}{field.name}'
        if target in seen:
            continue
        label = field.label or field.name
        if field.is_required:
            label = f'{label} ★'
        targets.append((target, label))
        seen.add(target)
    return targets


def missing_required_targets(
    mapping_rows: list[dict],
    *,
    match_policy: str | None = None,
) -> list[tuple[str, str]]:
    mapped = set()
    for row in mapping_rows:
        target = row.get('target') or TARGET_SKIP
        if target == TARGET_SKIP:
            continue
        # Field-primary: цель «назначена», только если выбрана колонка.
        if row.get('is_field_row'):
            if row.get('column') is not None or row.get('column_index') is not None:
                mapped.add(target)
            continue
        mapped.add(target)
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


def mapping_catalog_groups(choices: list[tuple[str, str]]) -> list[dict]:
    """Группы целей для панели «реквизиты» / меню «+»."""
    material: list[dict] = []
    structure: list[dict] = []
    properties: list[dict] = []
    skip: list[dict] = []
    for value, label in choices:
        item = {'target': value, 'label': label}
        if value == TARGET_SKIP:
            skip.append(item)
        elif value.startswith(TARGET_STRUCTURE_PREFIX):
            structure.append(item)
        elif value.startswith(TARGET_PROPERTY_PREFIX):
            properties.append(item)
        else:
            material.append(item)
    groups: list[dict] = []
    if material:
        groups.append({'id': 'material', 'label': 'Материал', 'items': material})
    if structure:
        groups.append({'id': 'structure', 'label': 'Параметры структуры', 'items': structure})
    if properties:
        groups.append({'id': 'property', 'label': 'Доп. свойства', 'items': properties})
    if skip:
        groups.append({'id': 'skip', 'label': 'Пропустить', 'items': skip})
    return groups


def addon_catalog_groups(
    properties=None,
    *,
    exclude_targets: set[str] | None = None,
) -> list[dict]:
    """Каталог для «Поле материала»: опциональные поля / справочники материала."""
    excluded = exclude_targets or set()
    choices: list[tuple[str, str]] = []
    for value, label in OPTIONAL_MATERIAL_TARGETS:
        if value not in excluded:
            choices.append((value, label))
    # properties=[] — доп. свойства добавляются модалкой «Добавить свойство».
    qs = properties if properties is not None else []
    for prop in qs:
        target = f'{TARGET_PROPERTY_PREFIX}{prop.pk}'
        if target in excluded:
            continue
        label = prop.display_name or prop.name
        if prop.unit:
            label = f'{label} ({prop.unit})'
        choices.append((target, label))
    return mapping_catalog_groups(choices)


def suggest_target(
    column: WideColumn,
    properties: list[Property],
    structure_fields: list[StructureField] | None = None,
    *,
    claimed_targets: set[str] | None = None,
) -> str:
    """
    Автоподстановка только для primary-целей: название / код / поля структуры.
    Доп. свойства и метаданные материала оператор добавляет вручную.
    """
    claimed = claimed_targets or set()
    hay = f'{column.group} {column.label}'.casefold()

    def _free(target: str) -> bool:
        return target_allows_multiple_columns(target) or target not in claimed

    if any(token in hay for token in ('наименование', 'название', 'name')) and _free(TARGET_NAME):
        return TARGET_NAME
    if any(token in hay for token in ('код', 'code', 'артикул', 'sku')) and _free(TARGET_CODE):
        return TARGET_CODE

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
    return best


def _sample_text(sample_value, *, max_len: int = 80) -> str:
    if sample_value is None:
        return '—'
    sample_text = str(sample_value).replace('\n', ' ').strip()
    if len(sample_text) > max_len:
        return sample_text[: max_len - 3] + '…'
    return sample_text or '—'


def _field_ui_label(raw: str) -> str:
    """Подпись для строки поля без служебных суффиксов mapping_choices."""
    text = (raw or '').strip()
    for prefix in ('Свойство: ', 'Поле структуры: '):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    for suffix in (' ★ обязательно', ' ★'):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
    return text or raw


def resolve_tag_column_indices(
    columns: list[WideColumn],
    mapping: dict,
    tag_columns: list[str] | None = None,
) -> list[int]:
    """Индексы колонок, из которых формируются scoped-теги (порядок как в файле)."""
    indices: set[int] = set()
    for raw in tag_columns or []:
        try:
            indices.add(int(raw))
        except (TypeError, ValueError):
            continue
    for key, entry in (mapping or {}).items():
        target, _parse = normalize_mapping_entry(entry)
        if target == TARGET_TAGS:
            try:
                indices.add(int(key))
            except (TypeError, ValueError):
                continue
    order = [column.index for column in columns]
    return [index for index in order if index in indices]


def build_field_mapping_rows(
    *,
    columns: list[WideColumn],
    mapping: dict,
    structure_fields=None,
    match_policy: str | None = None,
    target_labels: dict[str, str] | None = None,
    sample_row: dict | None = None,
    tag_columns: list[str] | None = None,
) -> list[dict]:
    """
    Проекция column→target на строки «поле → колонка» для UI.
    Primary + уже замапленные addon-цели из session.
    """
    labels = dict(target_labels or {})
    primary = primary_import_targets(structure_fields, match_policy=match_policy)
    primary_keys = [target for target, _label in primary]
    primary_set = set(primary_keys)
    required_keys = {target for target, _label in required_import_targets(match_policy)}

    # target → first column index (v1: одна колонка на цель)
    by_target: dict[str, tuple[WideColumn, str]] = {}
    for column in columns:
        key = str(column.index)
        if key not in mapping:
            continue
        target, parse = normalize_mapping_entry(mapping[key])
        if target == TARGET_SKIP:
            continue
        if target not in by_target:
            by_target[target] = (column, parse)

    ordered_targets: list[tuple[str, str, bool]] = []
    for target, label in primary:
        # primary уже с чистыми подписями; mapping_choices добавляет «★ обязательно».
        ordered_targets.append((target, label, True))
    for target, (column, parse) in by_target.items():
        if target in primary_set:
            continue
        if target == TARGET_TAGS:
            continue
        ordered_targets.append((target, _field_ui_label(labels.get(target, target)), False))

    sample = sample_row or {}
    rows: list[dict] = []
    for target, label, is_primary in ordered_targets:
        column = None
        parse = PARSE_AUTO
        if target in by_target:
            column, parse = by_target[target]
        sample_text = _sample_text(sample.get(column.index)) if column is not None else '—'
        section = field_mapping_section(target, is_primary=is_primary)
        rows.append({
            'is_field_row': True,
            'is_primary': section == 'primary',
            'is_material': section == 'material',
            'is_property': section == 'property',
            'is_tag': section == 'tag',
            'is_addon': section != 'primary',
            'section': section,
            'target': target,
            'mapping_target': target,
            'target_label': label,
            'is_required_target': target in required_keys,
            'column': column,
            'column_index': column.index if column is not None else None,
            'parse': parse,
            'sample': sample_text,
            'tag_preview': '',
        })

    column_by_index = {column.index: column for column in columns}
    for col_index in resolve_tag_column_indices(columns, mapping, tag_columns):
        column = column_by_index.get(col_index)
        if column is None:
            continue
        key = str(column.index)
        if key in mapping:
            _target, parse = normalize_mapping_entry(mapping[key])
        else:
            parse = PARSE_AUTO
        sample_text = _sample_text(sample.get(column.index))
        tag_preview = _preview_tag_from_column(column, sample_text)
        rows.append({
            'is_field_row': True,
            'is_primary': False,
            'is_material': False,
            'is_property': False,
            'is_tag': True,
            'is_addon': True,
            'section': 'tag',
            'target': f'{TARGET_TAG_ROW_PREFIX}{column.index}',
            'mapping_target': TARGET_TAGS,
            'target_label': column.display or column.label or f'Колонка {column.index + 1}',
            'is_required_target': False,
            'column': column,
            'column_index': column.index,
            'parse': parse,
            'sample': sample_text,
            'tag_preview': tag_preview,
        })
    return rows


def _preview_tag_from_column(column: WideColumn, sample_text: str) -> str:
    from apps.materials.imports.staging import _tag_from_column

    if not sample_text or sample_text == '—':
        from apps.materials.imports.staging import _tag_scope_from_column

        scope = _tag_scope_from_column(column.group or '', column.label or '')
        return f'{scope}::…'
    return _tag_from_column(column, sample_text)


def unused_columns_from_mapping(
    columns: list[WideColumn],
    mapping: dict,
    *,
    sample_row: dict | None = None,
) -> list[dict]:
    """Колонки файла без назначенной цели (skip / нет в mapping)."""
    sample = sample_row or {}
    unused: list[dict] = []
    for column in columns:
        key = str(column.index)
        if key in mapping:
            target, _parse = normalize_mapping_entry(mapping[key])
            if target != TARGET_SKIP:
                continue
        unused.append({
            'column': column,
            'index': column.index,
            'label': column.display,
            'sample': _sample_text(sample.get(column.index)),
        })
    return unused


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
            if structure_field.name != field_name:
                continue
            if structure_field.field_type == 'MaterialLink':
                return PARSE_TEXT
            if structure_field.field_type == 'BooleanField':
                return PARSE_BOOLEAN
            if structure_field.field_type in {'DateField', 'DateTimeField'}:
                return PARSE_DATE
    if target.startswith(TARGET_PROPERTY_PREFIX):
        prop_id = target.split(':', 1)[1]
        for prop in properties or []:
            if str(prop.pk) != prop_id:
                continue
            if prop.data_type == Property.MATERIAL_LINK_DATA_TYPE:
                return PARSE_TEXT
            if prop.data_type == 'boolean':
                return PARSE_BOOLEAN
            if prop.data_type == 'date':
                return PARSE_DATE
    if target.startswith(TARGET_STRUCTURE_PREFIX) or target.startswith(TARGET_PROPERTY_PREFIX):
        hay = f'{column.group} {column.label}'.casefold()
        if any(token in hay for token in ('замасливатель', 'плетения', 'производител', 'основа')):
            return PARSE_TEXT
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
    create_missing_dictionaries: bool = False,
    default_tags: str = '',
    default_tag_colors: dict | None = None,
) -> dict:
    """Собирает JSON шаблона импорта: маппинг колонок + тип структуры + настройки листа."""
    colors = {}
    for name, color in (default_tag_colors or {}).items():
        key = str(name or '').strip()
        value = str(color or '').strip().upper()
        if key and value:
            colors[key] = value
    return {
        'sheet': sheet,
        'header_row': header_row,
        'group_row': group_row,
        'match_policy': match_policy,
        'create_missing_dictionaries': bool(create_missing_dictionaries),
        'structure_type_id': str(structure_type_id or '').strip(),
        'default_tags': (default_tags or '').strip(),
        'default_tag_colors': colors,
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
    """Сопоставляет сохранённый шаблон к колонкам текущего файла по label.

    Для каждой колонки файла всегда есть запись: совпавшая цель или skip.
    Иначе UI снова автоподставит поля и шаблон «не применится».
    """
    by_label: dict[str, dict] = {}
    for item in profile_columns:
        label = (item.get('label') or '').strip()
        if not label:
            continue
        by_label[label.casefold()] = item
        # «Группа / Колонка» → также ключ по хвосту после « / »
        if ' / ' in label:
            tail = label.rsplit(' / ', 1)[-1].strip()
            if tail:
                by_label.setdefault(tail.casefold(), item)

    mapping = {}
    for col in columns:
        item = (
            by_label.get(col.display.casefold())
            or by_label.get((col.label or '').casefold())
        )
        if item:
            mapping[str(col.index)] = {
                'target': item.get('target') or TARGET_SKIP,
                'parse': item.get('parse') or PARSE_AUTO,
                'label': col.display,
            }
        else:
            mapping[str(col.index)] = {
                'target': TARGET_SKIP,
                'parse': PARSE_AUTO,
                'label': col.display,
            }
    return mapping


def import_templates_for_workspace(workspace) -> list[dict]:
    """Список шаблонов импорта для UI: имя, тип структуры, число колонок."""
    from apps.materials.models import MaterialImportProfile
    from apps.structures.models import StructureType

    profiles = list(
        MaterialImportProfile.objects.filter(workspace=workspace).order_by('name')
    )
    type_ids = [
        profile.structure_type_id
        for profile in profiles
        if profile.structure_type_id
    ]
    type_names = {
        str(pk): name
        for pk, name in StructureType.objects.filter(pk__in=type_ids).values_list('pk', 'name')
    }
    result = []
    for profile in profiles:
        st_id = profile.structure_type_id
        st_name = type_names.get(st_id, '')
        columns = (profile.config or {}).get('columns') or []
        mapped = sum(
            1
            for col in columns
            if (col.get('target') or TARGET_SKIP) != TARGET_SKIP
        )
        result.append({
            'id': str(profile.pk),
            'name': profile.name,
            'structure_type_id': st_id,
            'structure_type_name': st_name,
            'mapped_column_count': mapped,
            'option_label': (
                f'{profile.name} · {st_name}' if st_name else profile.name
            ),
        })
    return result


def _similarity(a: str, b: str) -> float:
    a_tokens = set(re.findall(r'[\wа-яё]+', a, flags=re.IGNORECASE))
    b_tokens = set(re.findall(r'[\wа-яё]+', b, flags=re.IGNORECASE))
    if not a_tokens or not b_tokens:
        return 1.0 if a.strip() == b.strip() else 0.0
    inter = len(a_tokens & b_tokens)
    return inter / max(len(a_tokens), len(b_tokens))
