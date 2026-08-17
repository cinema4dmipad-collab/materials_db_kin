from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from django.utils.text import slugify

from apps.materials.imports.mapping import (
    TARGET_AVAILABILITY,
    TARGET_CODE,
    TARGET_DESCRIPTION,
    TARGET_MANUFACTURER,
    TARGET_NAME,
    TARGET_OBJECT_TYPE,
    TARGET_PROPERTY_PREFIX,
    TARGET_SKIP,
    TARGET_STRUCTURE_PREFIX,
    TARGET_TAGS,
    TARGET_TECHNOLOGY,
    normalize_mapping_entry,
    resolve_tag_column_indices,
)
from apps.materials.imports.structure_values import build_structure_sql_payload
from django.core.exceptions import ValidationError

from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
)
from apps.materials.imports.value_parse import (
    CONFIDENCE_OK,
    CONFIDENCE_UNCERTAIN,
    PARSE_AUTO,
    PARSE_BOOLEAN,
    PARSE_DATE,
    PARSE_TEXT,
    is_blank_cell,
    needs_manual_recognition,
    parse_property_cell,
)
from apps.materials.imports.wide import WideTable
from apps.materials.models import Material
from apps.references.models import Property
from apps.structures.models import StructureField

MATCH_BY_CODE = 'code'
MATCH_BY_NAME = 'name'
MATCH_ALWAYS_CREATE = 'always_create'

MATCH_POLICIES = (
    (MATCH_BY_NAME, 'По названию'),
    (MATCH_BY_CODE, 'По коду'),
    (MATCH_ALWAYS_CREATE, 'Не проверять — всегда создавать'),
)

RECOGNITION_OK = 'ok'
RECOGNITION_UNRECOGNIZED = 'unrecognized'
RECOGNITION_IGNORED = 'ignored'
RECOGNITION_MANUAL = 'manual'

_NUMERIC_STRUCTURE_FIELD_TYPES = frozenset({'DecimalField', 'IntegerField', 'FloatField'})


@dataclass
class DraftProperty:
    property_name: str
    property_id: str
    column_label: str
    raw: str
    value_kind: str
    value: str
    value_b: str
    confidence: str
    note: str
    include: bool = True
    recognition: str = RECOGNITION_OK
    property_label: str = ''


@dataclass
class DraftStructureValue:
    field_name: str
    field_label: str
    column_label: str
    raw: str
    value_kind: str
    value: str
    value_b: str
    confidence: str
    note: str
    include: bool = True
    recognition: str = RECOGNITION_OK


@dataclass
class DraftMaterial:
    source_row: int
    name: str
    code: str
    description: str
    tags: str
    action: str  # create | update | skip
    existing_pk: str | None = None
    struct_type_id: str = ''
    manufacturer: str = ''
    availability: str = ''
    technology: str = ''
    object_type: str = ''
    warnings: list[str] = field(default_factory=list)
    structure_values: list[DraftStructureValue] = field(default_factory=list)
    properties: list[DraftProperty] = field(default_factory=list)

    @property
    def has_uncertain(self) -> bool:
        uncertain_props = any(
            p.confidence == CONFIDENCE_UNCERTAIN
            and p.include
            and p.recognition not in (RECOGNITION_UNRECOGNIZED, RECOGNITION_IGNORED)
            for p in self.properties
        )
        uncertain_struct = any(
            s.confidence == CONFIDENCE_UNCERTAIN
            and s.include
            and s.recognition not in (RECOGNITION_UNRECOGNIZED, RECOGNITION_IGNORED)
            for s in self.structure_values
        )
        return uncertain_props or uncertain_struct

    @property
    def has_unrecognized(self) -> bool:
        if self.action == 'skip':
            return False
        return any(
            item.recognition == RECOGNITION_UNRECOGNIZED
            for item in (*self.structure_values, *self.properties)
        )


def build_staging_draft(
    table: WideTable,
    mapping: dict,
    *,
    workspace,
    match_policy: str = MATCH_BY_NAME,
    structure_type_id: str | None = None,
    tag_columns: list[str] | None = None,
    occupied_codes: set[str] | None = None,
) -> list[DraftMaterial]:
    structure_field_cache = {
        field.name: field
        for field in StructureField.objects.filter(structure_type_id=structure_type_id).order_by('sort_order')
    } if structure_type_id else {}
    property_cache = {
        str(pk): (str(pk), name, data_type, display_name or name)
        for pk, name, display_name, data_type in Property.objects.all().values_list(
            'pk', 'name', 'display_name', 'data_type'
        )
    }
    map_by_index = {}
    parse_by_index = {}
    for key, entry in (mapping or {}).items():
        target, parse_mode = normalize_mapping_entry(entry)
        map_by_index[int(key)] = target
        parse_by_index[int(key)] = parse_mode

    tag_indices = set(
        resolve_tag_column_indices(table.columns, mapping, tag_columns)
    )

    drafts: list[DraftMaterial] = []
    used_codes: set[str] = set(occupied_codes or ())

    for row_offset, wide_row in enumerate(table.rows):
        excel_row = table.header_row + 1 + row_offset
        fields = {
            'code': '',
            'name': '',
            'description': '',
            'tags': [],
            'manufacturer': '',
            'availability': '',
            'technology': '',
            'object_type': '',
        }
        name_column_label = ''
        struct_vals: list[DraftStructureValue] = []
        props: list[DraftProperty] = []
        warnings: list[str] = []

        for col in table.columns:
            target = map_by_index.get(col.index, TARGET_SKIP)
            in_tags = col.index in tag_indices
            if target == TARGET_SKIP and not in_tags:
                continue
            raw = wide_row.get(col.index)
            parse_mode = parse_by_index.get(col.index, PARSE_AUTO)

            if target not in (TARGET_SKIP, TARGET_TAGS):
                if target == TARGET_CODE:
                    fields['code'] = _as_text(raw)
                elif target == TARGET_NAME:
                    fields['name'] = _as_text(raw)
                    name_column_label = col.display or name_column_label
                elif target == TARGET_DESCRIPTION:
                    text = _as_text(raw)
                    if text:
                        fields['description'] = (
                            f'{fields["description"]}; {text}'.strip('; ')
                            if fields['description']
                            else text
                        )
                elif target == TARGET_MANUFACTURER:
                    fields['manufacturer'] = _as_text(raw)
                elif target == TARGET_AVAILABILITY:
                    fields['availability'] = _as_text(raw)
                elif target == TARGET_TECHNOLOGY:
                    fields['technology'] = _as_text(raw)
                elif target == TARGET_OBJECT_TYPE:
                    fields['object_type'] = _as_text(raw)
                elif target.startswith(TARGET_STRUCTURE_PREFIX):
                    field_name = target.split(':', 1)[1]
                    structure_field = structure_field_cache.get(field_name)
                    if not structure_field:
                        warnings.append(f'Поле структуры {field_name} не найдено ({col.display})')
                    else:
                        expects_number = structure_field.field_type in _NUMERIC_STRUCTURE_FIELD_TYPES
                        if structure_field.field_type == 'MaterialLink':
                            parse_mode = PARSE_TEXT
                        elif expects_number and parse_mode == PARSE_TEXT:
                            # Числовое поле нельзя писать «как текст» — иначе «30±3» уйдёт в ручную правку.
                            parse_mode = PARSE_AUTO
                        parsed = parse_property_cell(raw, mode=parse_mode)
                        field_label = (structure_field.label or structure_field.name or '').strip()
                        if parsed is None:
                            # Сопоставлено, но пусто — оставляем в черновике (можно снять галочку).
                            struct_vals.append(
                                DraftStructureValue(
                                    field_name=structure_field.name,
                                    field_label=field_label,
                                    column_label=col.display,
                                    raw='',
                                    value_kind=VALUE_KIND_SCALAR,
                                    value='',
                                    value_b='',
                                    confidence=CONFIDENCE_OK,
                                    note='пусто',
                                    include=True,
                                )
                            )
                        elif _should_mark_unrecognized(
                            expects_number=expects_number,
                            parse_mode=parse_mode,
                            raw=raw,
                            parsed=parsed,
                        ):
                            struct_vals.append(
                                _unrecognized_structure_value(
                                    structure_field=structure_field,
                                    column_label=col.display,
                                    raw=_as_text(raw),
                                )
                            )
                        else:
                            struct_vals.append(
                                DraftStructureValue(
                                    field_name=structure_field.name,
                                    field_label=field_label,
                                    column_label=col.display,
                                    raw=_as_text(raw),
                                    value_kind=parsed['value_kind'],
                                    value=str(parsed['value']),
                                    value_b='' if parsed['value_b'] is None else str(parsed['value_b']),
                                    confidence=parsed.get('confidence', CONFIDENCE_OK),
                                    note=parsed.get('note', ''),
                                    include=True,
                                )
                            )
                elif target.startswith(TARGET_PROPERTY_PREFIX):
                    prop_id = target.split(':', 1)[1]
                    prop_info = property_cache.get(prop_id)
                    if not prop_info:
                        warnings.append(f'Свойство {prop_id} не найдено ({col.display})')
                    else:
                        expects_number = prop_info[2] == 'number'
                        if prop_info[2] == 'material_link':
                            parse_mode = PARSE_TEXT
                        elif expects_number and parse_mode == PARSE_TEXT:
                            parse_mode = PARSE_AUTO
                        parsed = parse_property_cell(raw, mode=parse_mode)
                        if parsed is None:
                            props.append(
                                DraftProperty(
                                    property_name=prop_info[1],
                                    property_id=prop_info[0],
                                    property_label=prop_info[3],
                                    column_label=col.display,
                                    raw='',
                                    value_kind=VALUE_KIND_SCALAR,
                                    value='',
                                    value_b='',
                                    confidence=CONFIDENCE_OK,
                                    note='пусто',
                                    include=True,
                                )
                            )
                        elif _should_mark_unrecognized(
                            expects_number=expects_number,
                            parse_mode=parse_mode,
                            raw=raw,
                            parsed=parsed,
                        ):
                            props.append(
                                _unrecognized_property_value(
                                    prop_info=prop_info,
                                    column_label=col.display,
                                    raw=_as_text(raw),
                                )
                            )
                        else:
                            props.append(
                                DraftProperty(
                                    property_name=prop_info[1],
                                    property_id=prop_info[0],
                                    property_label=prop_info[3],
                                    column_label=col.display,
                                    raw=_as_text(raw),
                                    value_kind=parsed['value_kind'],
                                    value=str(parsed['value']),
                                    value_b='' if parsed['value_b'] is None else str(parsed['value_b']),
                                    confidence=parsed.get('confidence', CONFIDENCE_OK),
                                    note=parsed.get('note', ''),
                                    include=True,
                                )
                            )

            if in_tags:
                text = _as_text(raw)
                if text:
                    tag_name = _tag_from_column(col, text)
                    if tag_name and tag_name not in fields['tags']:
                        fields['tags'].append(tag_name)

        _append_duplicate_field_warnings(struct_vals, props, warnings)

        name = fields['name'].strip()
        code = fields['code'].strip()
        tags = '; '.join(t for t in fields['tags'] if t)
        if not name and not code and not props and not struct_vals:
            continue
        if _is_header_like_identity(name, code):
            continue
        if not name and code:
            name = code
            warnings.append('Название взято из кода')

        # Пустое название/код при наличии прочих колонок: не блокируем весь импорт —
        # строку пропускаем (типично пустая «Марка» при сопоставлении Марка→Название).
        if not name and not code:
            col_hint = f'«{name_column_label}»' if name_column_label else '«Название»'
            warnings.append(
                f'Пропущено: пустое значение в колонке {col_hint}. '
                'Материал не будет создан — заполните ячейку, сопоставьте другую колонку '
                'или оставьте пропуск.'
            )
            drafts.append(
                DraftMaterial(
                    source_row=excel_row,
                    name='',
                    code='',
                    description=fields['description'],
                    tags=tags,
                    action='skip',
                    existing_pk=None,
                    struct_type_id=str(structure_type_id or ''),
                    manufacturer=fields['manufacturer'],
                    availability=fields['availability'],
                    technology=fields['technology'],
                    object_type=fields['object_type'],
                    warnings=warnings,
                    structure_values=struct_vals,
                    properties=props,
                )
            )
            continue

        action, existing_pk, code, extra_warnings = _resolve_identity(
            workspace=workspace,
            name=name,
            code=code,
            match_policy=match_policy,
            used_codes=used_codes,
        )
        warnings.extend(extra_warnings)
        uncertain = any(p.confidence == CONFIDENCE_UNCERTAIN for p in props)
        uncertain = uncertain or any(s.confidence == CONFIDENCE_UNCERTAIN for s in struct_vals)
        if uncertain:
            warnings.append('Есть значения, требующие проверки')

        drafts.append(
            DraftMaterial(
                source_row=excel_row,
                name=name,
                code=code,
                description=fields['description'],
                tags=tags,
                action=action,
                existing_pk=existing_pk,
                struct_type_id=str(structure_type_id or ''),
                manufacturer=fields['manufacturer'],
                availability=fields['availability'],
                technology=fields['technology'],
                object_type=fields['object_type'],
                warnings=warnings,
                structure_values=struct_vals,
                properties=props,
            )
        )
    return drafts


def merge_default_tags_into_drafts(
    drafts: list[DraftMaterial],
    default_tags: str | None,
) -> list[DraftMaterial]:
    """
    Добавляет общие теги импорта ко всем не-пропущенным строкам черновика.
    Теги из файла (колонка) сохраняются; при конфликте scoped-тегов побеждает
    значение из файла (оно уже в draft.tags), затем дополняем default.
    """
    from apps.core.tag_utils import (
        dedupe_scoped_tag_names,
        parse_tag_input,
    )

    extra = parse_tag_input(default_tags or '')
    if not extra:
        return drafts
    for draft in drafts:
        if draft.action == 'skip':
            continue
        # Сначала общие, потом из файла — файл перекрывает тот же scope.
        merged = dedupe_scoped_tag_names(extra + parse_tag_input(draft.tags or ''))
        draft.tags = '; '.join(merged)
    return drafts


def draft_to_import_rows(drafts: list[DraftMaterial]) -> list[dict]:
    rows: list[dict] = []
    for draft in drafts:
        if draft.action == 'skip':
            continue
        included = [p for p in draft.properties if p.include]
        if not included:
            rows.append(
                {
                    'code': draft.code,
                    'name': draft.name,
                    'description': draft.description,
                    'tags': draft.tags,
                    'property_name': '',
                    'value_kind': 'scalar',
                    'value': '',
                    'value_b': '',
                    'notes': '',
                    '_row_number': draft.source_row,
                }
            )
            continue
        first = True
        for prop in included:
            rows.append(
                {
                    'code': draft.code,
                    'name': draft.name if first else draft.name,
                    'description': draft.description if first else '',
                    'tags': draft.tags if first else '',
                    'property_name': prop.property_name,
                    'value_kind': prop.value_kind,
                    'value': prop.value,
                    'value_b': prop.value_b,
                    'notes': prop.note if prop.confidence == CONFIDENCE_UNCERTAIN else '',
                    '_row_number': draft.source_row,
                }
            )
            first = False
    return rows


def drafts_to_session(drafts: list[DraftMaterial]) -> list[dict]:
    return [asdict(d) for d in drafts]


def drafts_from_session(raw: list[dict] | None) -> list[DraftMaterial]:
    if not raw:
        return []
    result = []
    for item in raw:
        props = []
        for p in item.get('properties') or []:
            payload = dict(p)
            payload.setdefault('property_label', payload.get('property_name') or '')
            props.append(DraftProperty(**payload))
        struct_vals = [DraftStructureValue(**s) for s in item.get('structure_values') or []]
        result.append(
            DraftMaterial(
                source_row=item['source_row'],
                name=item.get('name') or '',
                code=item.get('code') or '',
                description=item.get('description') or '',
                tags=item.get('tags') or '',
                action=item.get('action') or 'create',
                existing_pk=item.get('existing_pk'),
                struct_type_id=item.get('struct_type_id') or '',
                manufacturer=item.get('manufacturer') or '',
                availability=item.get('availability') or '',
                technology=item.get('technology') or '',
                object_type=item.get('object_type') or '',
                warnings=list(item.get('warnings') or []),
                structure_values=struct_vals,
                properties=props,
            )
        )
    return result


def apply_review_post(drafts: list[DraftMaterial], post) -> list[DraftMaterial]:
    """Обновляет draft из POST формы review (skip/include).

    Чекбоксы include_* живут в свёрнутом блоке деталей. Если их нет в POST
    (блок не раскрывали / JS отключил перед submit) — сохраняем флаги из сессии,
    иначе все поля стали бы include=False и импорт «молчал» или писал пустышки.

    Перезапись существующих материалов запрещена: existing_pk сбрасывается,
    action только create|skip.
    """
    if post.get('review_marker') != '1':
        return drafts
    includes_posted = any(
        key.startswith('include_') for key in post.keys()
    )
    for index, draft in enumerate(drafts):
        if post.get(f'skip_{index}') == '1':
            draft.action = 'skip'
        else:
            draft.action = 'create'
            draft.existing_pk = None
        if not includes_posted:
            continue
        for p_index, prop in enumerate(draft.properties):
            prop.include = post.get(f'include_{index}_{p_index}') == '1'
        for s_index, struct_val in enumerate(draft.structure_values):
            struct_val.include = post.get(f'include_struct_{index}_{s_index}') == '1'
    return drafts


DUPLICATE_NAME_SKIP = 'skip'
DUPLICATE_NAME_PREFIX = 'prefix'
DUPLICATE_NAME_POSTFIX = 'postfix'


def name_collisions_for_drafts(workspace, drafts: list[DraftMaterial], *, queryset=None) -> list[dict]:
    """
    Строки черновика, чьё название уже есть у материала пространства (без учёта регистра).
    Пропущенные строки не учитываются.
    """
    candidates: list[tuple[int, DraftMaterial, str]] = []
    for index, draft in enumerate(drafts):
        if draft.action == 'skip':
            continue
        name = (draft.name or '').strip()
        if not name:
            continue
        candidates.append((index, draft, name))
    if not candidates:
        return []

    keys = {name.casefold() for _i, _d, name in candidates}
    existing_by_key: dict[str, object] = {}
    qs = queryset
    if qs is None:
        qs = (
            Material.objects.filter(home_workspace=workspace)
            .only('pk', 'name', 'code')
            .order_by('created_at')
        )
    for existing in qs:
        key = (existing.name or '').casefold()
        if key in keys and key not in existing_by_key:
            existing_by_key[key] = existing

    collisions: list[dict] = []
    for index, draft, name in candidates:
        existing = existing_by_key.get(name.casefold())
        if existing is None:
            continue
        collisions.append(
            {
                'draft_index': index,
                'source_row': draft.source_row,
                'name': name,
                'existing_pk': str(existing.pk),
                'existing_code': existing.code,
                'existing_name': existing.name,
            }
        )
    return collisions


def apply_duplicate_name_policy(
    drafts: list[DraftMaterial],
    collisions: list[dict],
    *,
    mode: str,
    prefix: str = '',
    postfix: str = '',
) -> list[DraftMaterial]:
    """
    mode=skip — не записывать строки с совпавшим названием.
    mode=prefix — добавить префикс к названию и создать как новые.
    mode=postfix — добавить постфикс к названию и создать как новые.
    """
    if not collisions:
        return drafts
    indexes = {int(item['draft_index']) for item in collisions}
    mode = (mode or DUPLICATE_NAME_SKIP).strip() or DUPLICATE_NAME_SKIP
    prefix = (prefix or '').strip()
    postfix = (postfix or '').strip()
    if mode == DUPLICATE_NAME_PREFIX and not prefix:
        raise ValueError('Укажите префикс для дубликатов по названию.')
    if mode == DUPLICATE_NAME_POSTFIX and not postfix:
        raise ValueError('Укажите постфикс для дубликатов по названию.')

    used_codes = {draft.code for draft in drafts if draft.code}
    for index, draft in enumerate(drafts):
        if index not in indexes or draft.action == 'skip':
            continue
        if mode == DUPLICATE_NAME_SKIP:
            draft.action = 'skip'
            draft.existing_pk = None
            draft.warnings.append(
                'Пропущен: материал с таким названием уже есть в пространстве'
            )
            continue
        if mode == DUPLICATE_NAME_POSTFIX:
            draft.name = f'{draft.name}{postfix}'
        else:
            draft.name = f'{prefix}{draft.name}'
        draft.code = _make_code(draft.name or draft.code or 'material', used_codes)
        draft.existing_pk = None
        draft.action = 'create'
        draft.warnings.append(f'Создаётся с новым названием «{draft.name}»')
    return drafts


def has_unresolved_unrecognized(drafts: list[DraftMaterial]) -> bool:
    return any(draft.has_unrecognized for draft in drafts)


def iter_unrecognized_fields(drafts: list[DraftMaterial], post=None) -> list[dict]:
    """Только нераспознанные ячейки (для счётчика и обратной совместимости)."""
    return [
        item
        for item in iter_review_editable_fields(drafts, post=post)
        if item.get('is_unrecognized')
    ]


def iter_review_editable_fields(drafts: list[DraftMaterial], post=None) -> list[dict]:
    """Все ячейки таблицы на шаге «Запись», которые можно править вручную."""
    active_drafts = [d for d in drafts if d.action != 'skip']
    material_columns = [
        (key, label, attr)
        for key, label, attr in _MATERIAL_GRID_FIELDS
        if any(str(getattr(d, attr, '') or '').strip() for d in active_drafts)
    ]
    items: list[dict] = []
    for draft_index, draft in enumerate(drafts):
        if draft.action == 'skip':
            continue
        material_label = draft.name or draft.code or f'строка {draft.source_row}'
        name_input = f'fix_material_{draft_index}_name'
        name_skip = f'skip_{name_input}'
        items.append(
            {
                'draft_index': draft_index,
                'field_index': -1,
                'kind': 'material',
                'attr': 'name',
                'source_row': draft.source_row,
                'material_label': material_label,
                'column_label': '',
                'target_label': 'Название',
                'raw': draft.name or '',
                'fix_value': _fix_value_from_post(post, name_input, draft.name or ''),
                'input_name': name_input,
                'skip_name': name_skip,
                'skip_checked': post is not None and post.get(name_skip) == '1',
                'is_unrecognized': False,
                'allow_skip': False,
            }
        )
        for key, label, attr in material_columns:
            text = str(getattr(draft, attr, '') or '').strip()
            input_name = f'fix_material_{draft_index}_{attr}'
            skip_name = f'skip_{input_name}'
            items.append(
                {
                    'draft_index': draft_index,
                    'field_index': -1,
                    'kind': 'material',
                    'attr': attr,
                    'column_key': key,
                    'source_row': draft.source_row,
                    'material_label': material_label,
                    'column_label': '',
                    'target_label': label,
                    'raw': text,
                    'fix_value': _fix_value_from_post(post, input_name, text),
                    'input_name': input_name,
                    'skip_name': skip_name,
                    'skip_checked': post is not None and post.get(skip_name) == '1',
                    'is_unrecognized': False,
                    'allow_skip': True,
                }
            )
        for struct_index, struct in enumerate(draft.structure_values):
            is_bad = struct.recognition == RECOGNITION_UNRECOGNIZED
            input_name = f'fix_struct_{draft_index}_{struct_index}'
            skip_name = f'skip_{input_name}'
            default = (
                (struct.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=struct.raw,
                    value=struct.value,
                    value_b=struct.value_b,
                    value_kind=struct.value_kind,
                    is_unrecognized=False,
                )
            )
            items.append(
                {
                    'draft_index': draft_index,
                    'field_index': struct_index,
                    'kind': 'struct',
                    'source_row': draft.source_row,
                    'material_label': material_label,
                    'column_label': struct.column_label,
                    'target_label': struct.field_label,
                    'raw': struct.raw or '',
                    'fix_value': _fix_value_from_post(post, input_name, default),
                    'input_name': input_name,
                    'skip_name': skip_name,
                    'skip_checked': post is not None and post.get(skip_name) == '1',
                    'is_unrecognized': is_bad,
                    'allow_skip': True,
                }
            )
        for prop_index, prop in enumerate(draft.properties):
            is_bad = prop.recognition == RECOGNITION_UNRECOGNIZED
            input_name = f'fix_prop_{draft_index}_{prop_index}'
            skip_name = f'skip_{input_name}'
            default = (
                (prop.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=prop.raw,
                    value=prop.value,
                    value_b=prop.value_b,
                    value_kind=prop.value_kind,
                    is_unrecognized=False,
                )
            )
            items.append(
                {
                    'draft_index': draft_index,
                    'field_index': prop_index,
                    'kind': 'prop',
                    'source_row': draft.source_row,
                    'material_label': material_label,
                    'column_label': prop.column_label,
                    'target_label': prop.property_label or prop.property_name,
                    'raw': prop.raw or '',
                    'fix_value': _fix_value_from_post(post, input_name, default),
                    'input_name': input_name,
                    'skip_name': skip_name,
                    'skip_checked': post is not None and post.get(skip_name) == '1',
                    'is_unrecognized': is_bad,
                    'allow_skip': True,
                }
            )
    return items


def _fix_value_from_post(post, input_name: str, raw: str) -> str:
    if post is not None and input_name in post:
        return (post.get(input_name) or '').strip()
    return raw or ''


def _excel_col_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    if index < 0:
        return ''
    result: list[str] = []
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return ''.join(reversed(result))


def _cell_display_value(*, raw: str, value: str, value_b: str, value_kind: str, is_unrecognized: bool) -> str:
    if is_unrecognized:
        return (raw or '').strip()
    text = (value or '').strip()
    extra = (value_b or '').strip()
    if not text:
        return ''
    kind = value_kind or ''
    if extra and kind == 'range':
        return f'{text}–{extra}'
    if extra and kind == 'tolerance':
        return f'{text}±{extra}'
    return text


_MATERIAL_GRID_FIELDS = (
    ('material:code', 'Код', 'code'),
    ('material:tags', 'Теги', 'tags'),
    ('material:description', 'Описание', 'description'),
    ('material:manufacturer', 'Производитель', 'manufacturer'),
    ('material:availability', 'Доступность', 'availability'),
    ('material:technology', 'Технология', 'technology'),
)


def _empty_grid_cell(*, label: str, kind: str, draft_index: int) -> dict:
    return {
        'display': '',
        'raw': '',
        'is_unrecognized': False,
        'is_excluded': False,
        'is_editable': False,
        'allow_skip': True,
        'target_label': label,
        'column_label': '',
        'input_name': '',
        'skip_name': '',
        'fix_value': '',
        'skip_checked': False,
        'draft_index': draft_index,
        'field_index': -1,
        'kind': kind,
    }


def build_review_fix_grid(drafts: list[DraftMaterial], post=None) -> dict:
    """
    Таблица значений к записи на шаге «Запись».
    Строки — все draft create/update; колонки — метаданные, структура и свойства.
    Все ячейки редактируемы; жёлтые — нераспознанные системой.
    """
    row_indices = [
        index
        for index, draft in enumerate(drafts)
        if draft.action != 'skip'
    ]
    if not row_indices:
        return {'columns': [], 'rows': [], 'unrecognized_count': 0}

    columns: list[dict] = []
    seen_keys: set[str] = set()

    def _add_column(key: str, label: str, kind: str) -> None:
        if key in seen_keys:
            return
        seen_keys.add(key)
        columns.append({
            'key': key,
            'label': label,
            'kind': kind,
            'letter': _excel_col_letter(len(columns) + 1),  # A = Название
        })

    active_drafts = [drafts[index] for index in row_indices]
    for key, label, attr in _MATERIAL_GRID_FIELDS:
        if any(str(getattr(draft, attr, '') or '').strip() for draft in active_drafts):
            _add_column(key, label, 'material')

    for draft in active_drafts:
        for struct in draft.structure_values:
            _add_column(
                f'struct:{struct.field_name}',
                struct.field_label or struct.field_name,
                'struct',
            )
        for prop in draft.properties:
            _add_column(
                f'prop:{prop.property_id}',
                prop.property_label or prop.property_name,
                'prop',
            )

    rows: list[dict] = []
    unrecognized_count = 0
    for draft_index in row_indices:
        draft = drafts[draft_index]
        material_label = draft.name or draft.code or f'строка {draft.source_row}'
        name_input = f'fix_material_{draft_index}_name'
        name_skip = f'skip_{name_input}'
        name_fix = _fix_value_from_post(post, name_input, draft.name or '')
        name_cell = {
            'display': name_fix or material_label,
            'raw': draft.name or '',
            'is_unrecognized': False,
            'is_excluded': False,
            'is_editable': True,
            'allow_skip': False,
            'target_label': 'Название',
            'column_label': '',
            'input_name': name_input,
            'skip_name': name_skip,
            'fix_value': name_fix,
            'skip_checked': False,
            'draft_index': draft_index,
            'field_index': -1,
            'kind': 'material',
            'attr': 'name',
            'col_index': 0,
            'letter': 'A',
        }
        cells: dict[str, dict] = {}

        for key, label, attr in _MATERIAL_GRID_FIELDS:
            if key not in seen_keys:
                continue
            text = str(getattr(draft, attr, '') or '').strip()
            input_name = f'fix_material_{draft_index}_{attr}'
            skip_name = f'skip_{input_name}'
            fix_value = _fix_value_from_post(post, input_name, text)
            skip_checked = bool(post is not None and post.get(skip_name) == '1')
            cells[key] = {
                'display': '' if skip_checked else fix_value,
                'raw': text,
                'is_unrecognized': False,
                'is_excluded': skip_checked,
                'is_editable': True,
                'allow_skip': True,
                'target_label': label,
                'column_label': '',
                'input_name': input_name,
                'skip_name': skip_name,
                'fix_value': fix_value,
                'skip_checked': skip_checked,
                'draft_index': draft_index,
                'field_index': -1,
                'kind': 'material',
                'attr': attr,
            }

        for struct_index, struct in enumerate(draft.structure_values):
            key = f'struct:{struct.field_name}'
            is_bad = struct.recognition == RECOGNITION_UNRECOGNIZED
            is_excluded = not struct.include and not is_bad
            input_name = f'fix_struct_{draft_index}_{struct_index}'
            skip_name = f'skip_{input_name}'
            default = (
                (struct.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=struct.raw,
                    value=struct.value,
                    value_b=struct.value_b,
                    value_kind=struct.value_kind,
                    is_unrecognized=False,
                )
            )
            fix_value = _fix_value_from_post(post, input_name, default)
            skip_checked = bool(post is not None and post.get(skip_name) == '1')
            if is_bad:
                unrecognized_count += 1
                display = (fix_value or '').strip()
            else:
                display = fix_value if post is not None and input_name in post else default
            if is_excluded and not (post is not None and input_name in post):
                display = ''
            if skip_checked:
                display = (struct.raw or default or '').strip()
            cells[key] = {
                'display': display,
                'raw': struct.raw or '',
                'is_unrecognized': is_bad,
                'is_excluded': is_excluded or skip_checked,
                'is_editable': True,
                'allow_skip': True,
                'target_label': struct.field_label or struct.field_name,
                'column_label': struct.column_label,
                'input_name': input_name,
                'skip_name': skip_name,
                'fix_value': fix_value,
                'skip_checked': skip_checked,
                'draft_index': draft_index,
                'field_index': struct_index,
                'kind': 'struct',
            }

        for prop_index, prop in enumerate(draft.properties):
            key = f'prop:{prop.property_id}'
            is_bad = prop.recognition == RECOGNITION_UNRECOGNIZED
            is_excluded = not prop.include and not is_bad
            input_name = f'fix_prop_{draft_index}_{prop_index}'
            skip_name = f'skip_{input_name}'
            default = (
                (prop.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=prop.raw,
                    value=prop.value,
                    value_b=prop.value_b,
                    value_kind=prop.value_kind,
                    is_unrecognized=False,
                )
            )
            fix_value = _fix_value_from_post(post, input_name, default)
            skip_checked = bool(post is not None and post.get(skip_name) == '1')
            if is_bad:
                unrecognized_count += 1
                display = (fix_value or '').strip()
            else:
                display = fix_value if post is not None and input_name in post else default
            if is_excluded and not (post is not None and input_name in post):
                display = ''
            if skip_checked:
                display = (prop.raw or default or '').strip()
            cells[key] = {
                'display': display,
                'raw': prop.raw or '',
                'is_unrecognized': is_bad,
                'is_excluded': is_excluded or skip_checked,
                'is_editable': True,
                'allow_skip': True,
                'target_label': prop.property_label or prop.property_name,
                'column_label': prop.column_label,
                'input_name': input_name,
                'skip_name': skip_name,
                'fix_value': fix_value,
                'skip_checked': skip_checked,
                'draft_index': draft_index,
                'field_index': prop_index,
                'kind': 'prop',
            }

        rows.append(
            {
                'draft_index': draft_index,
                'source_row': draft.source_row,
                'material_label': name_fix or material_label,
                'action': draft.action,
                'name_cell': name_cell,
                'cells': cells,
                'cell_list': [
                    {
                        **(
                            cells.get(column['key'])
                            or _empty_grid_cell(
                                label=column['label'],
                                kind=column['kind'],
                                draft_index=draft_index,
                            )
                        ),
                        'letter': column['letter'],
                        'col_index': col_index + 1,
                    }
                    for col_index, column in enumerate(columns)
                ],
            }
        )

    return {
        'columns': columns,
        'rows': rows,
        'unrecognized_count': unrecognized_count,
        'name_column_letter': 'A',
        'row_count': len(rows),
    }


def apply_unrecognized_ignore_all(drafts: list[DraftMaterial]) -> list[DraftMaterial]:
    for draft in drafts:
        for struct in draft.structure_values:
            if struct.recognition == RECOGNITION_UNRECOGNIZED:
                struct.recognition = RECOGNITION_IGNORED
                struct.include = False
                struct.value = ''
                struct.value_b = ''
                struct.note = 'игнорировано'
        for prop in draft.properties:
            if prop.recognition == RECOGNITION_UNRECOGNIZED:
                prop.recognition = RECOGNITION_IGNORED
                prop.include = False
                prop.value = ''
                prop.value_b = ''
                prop.note = 'игнорировано'
    return drafts


def apply_unrecognized_manual_fixes(drafts: list[DraftMaterial], post) -> tuple[list[DraftMaterial], list[str]]:
    """
    Применяет правки из таблицы на шаге «Запись».
    Нераспознанные поля по-прежнему требуют значение или «Пропустить»;
    остальные поля можно переписать или очистить (пустой → не записывать).
    """
    errors: list[str] = []
    used_codes = {
        draft.code
        for draft in drafts
        if draft.action != 'skip' and draft.code
    }
    for draft_index, draft in enumerate(drafts):
        if draft.action == 'skip':
            continue

        name_key = f'fix_material_{draft_index}_name'
        if name_key in post:
            new_name = (post.get(name_key) or '').strip()
            if not new_name:
                errors.append(
                    f'Строка {draft.source_row}: укажите название материала.'
                )
            else:
                old_name = (draft.name or '').strip()
                draft.name = new_name
                if new_name != old_name:
                    if draft.code:
                        used_codes.discard(draft.code)
                    draft.code = _make_code(new_name, used_codes)
                    used_codes.add(draft.code)

        for _key, label, attr in _MATERIAL_GRID_FIELDS:
            field_key = f'fix_material_{draft_index}_{attr}'
            if field_key not in post and post.get(f'skip_{field_key}') != '1':
                continue
            if post.get(f'skip_{field_key}') == '1':
                setattr(draft, attr, '')
                continue
            setattr(draft, attr, (post.get(field_key) or '').strip())

        for struct_index, struct in enumerate(draft.structure_values):
            key = f'fix_struct_{draft_index}_{struct_index}'
            is_bad = struct.recognition == RECOGNITION_UNRECOGNIZED
            posted = key in post or post.get(f'skip_{key}') == '1'
            if not posted and not is_bad:
                continue
            if post.get(f'skip_{key}') == '1':
                _ignore_unrecognized_structure(struct)
                continue
            raw_fix = (post.get(key) or '').strip()
            if not raw_fix:
                if is_bad:
                    errors.append(
                        f'Строка {draft.source_row}, «{struct.column_label}» → {struct.field_label}: '
                        f'введите значение или отметьте «Пропустить».'
                    )
                else:
                    _ignore_unrecognized_structure(struct)
                continue
            current_display = (
                (struct.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=struct.raw,
                    value=struct.value,
                    value_b=struct.value_b,
                    value_kind=struct.value_kind,
                    is_unrecognized=False,
                )
            )
            if not is_bad and raw_fix == (current_display or '').strip():
                continue
            error = _apply_manual_fix_to_structure(struct, raw_fix, draft.source_row)
            if error:
                errors.append(error)

        for prop_index, prop in enumerate(draft.properties):
            key = f'fix_prop_{draft_index}_{prop_index}'
            is_bad = prop.recognition == RECOGNITION_UNRECOGNIZED
            posted = key in post or post.get(f'skip_{key}') == '1'
            if not posted and not is_bad:
                continue
            if post.get(f'skip_{key}') == '1':
                _ignore_unrecognized_property(prop)
                continue
            raw_fix = (post.get(key) or '').strip()
            if not raw_fix:
                if is_bad:
                    errors.append(
                        f'Строка {draft.source_row}, «{prop.column_label}» → {prop.property_name}: '
                        f'введите значение или отметьте «Пропустить».'
                    )
                else:
                    _ignore_unrecognized_property(prop)
                continue
            current_display = (
                (prop.raw or '')
                if is_bad
                else _cell_display_value(
                    raw=prop.raw,
                    value=prop.value,
                    value_b=prop.value_b,
                    value_kind=prop.value_kind,
                    is_unrecognized=False,
                )
            )
            if not is_bad and raw_fix == (current_display or '').strip():
                continue
            error = _apply_manual_fix_to_property(prop, raw_fix, draft.source_row)
            if error:
                errors.append(error)
    return drafts, errors


def _ignore_unrecognized_structure(struct: DraftStructureValue) -> None:
    struct.recognition = RECOGNITION_IGNORED
    struct.include = False
    struct.value = ''
    struct.value_b = ''
    struct.note = 'игнорировано'


def _ignore_unrecognized_property(prop: DraftProperty) -> None:
    prop.recognition = RECOGNITION_IGNORED
    prop.include = False
    prop.value = ''
    prop.value_b = ''
    prop.note = 'игнорировано'


def _apply_manual_fix_to_structure(struct: DraftStructureValue, raw_fix: str, source_row: int) -> str | None:
    parsed = parse_property_cell(raw_fix, mode=PARSE_AUTO)
    if parsed is None or _should_mark_unrecognized(
        expects_number=True,
        parse_mode=PARSE_AUTO,
        raw=raw_fix,
        parsed=parsed,
    ):
        return (
            f'Строка {source_row}, «{struct.column_label}»: '
            f'«{raw_fix[:40]}» не удалось распознать как число.'
        )
    struct.raw = raw_fix
    struct.value_kind = parsed['value_kind']
    struct.value = str(parsed['value'])
    struct.value_b = '' if parsed['value_b'] is None else str(parsed['value_b'])
    struct.confidence = parsed.get('confidence', CONFIDENCE_OK)
    struct.note = parsed.get('note', '')
    struct.recognition = RECOGNITION_MANUAL
    struct.include = True
    return None


def _apply_manual_fix_to_property(prop: DraftProperty, raw_fix: str, source_row: int) -> str | None:
    parsed = parse_property_cell(raw_fix, mode=PARSE_AUTO)
    if parsed is None or _should_mark_unrecognized(
        expects_number=True,
        parse_mode=PARSE_AUTO,
        raw=raw_fix,
        parsed=parsed,
    ):
        return (
            f'Строка {source_row}, «{prop.column_label}»: '
            f'«{raw_fix[:40]}» не удалось распознать как число.'
        )
    prop.raw = raw_fix
    prop.value_kind = parsed['value_kind']
    prop.value = str(parsed['value'])
    prop.value_b = '' if parsed['value_b'] is None else str(parsed['value_b'])
    prop.confidence = parsed.get('confidence', CONFIDENCE_OK)
    prop.note = parsed.get('note', '')
    prop.recognition = RECOGNITION_MANUAL
    prop.include = True
    return None


def _should_mark_unrecognized(*, expects_number: bool, parse_mode: str, raw, parsed: dict) -> bool:
    """True если значение нельзя записать без участия техника.

    Режим колонки «Текст» больше не обходит проверку для числовых полей: иначе значение
    уходит в черновик строкой и падает на валидации («Введите корректное число»), минуя
    форму исправления.
    """
    if parse_mode in {PARSE_BOOLEAN, PARSE_DATE}:
        return parsed.get('confidence') == CONFIDENCE_UNCERTAIN
    if not expects_number:
        return False
    if parse_mode != PARSE_TEXT:
        if needs_manual_recognition(raw, parsed, expects_number=True):
            return True
        if not _is_numeric_parse(parsed):
            return True
    return not _parsed_is_storable_number(parsed)


def _parsed_is_storable_number(parsed: dict) -> bool:
    """Та же проверка, что на шаге валидации импорта для number-полей."""
    kind = parsed.get('value_kind') or VALUE_KIND_SCALAR
    value = parsed.get('value')
    value_b = parsed.get('value_b')
    try:
        if kind == VALUE_KIND_RANGE:
            clean_number_property_fields(
                value_kind=VALUE_KIND_RANGE,
                value='',
                value_min=value,
                value_max=value_b,
                decimal_places=None,
            )
        elif kind == VALUE_KIND_TOLERANCE:
            clean_number_property_fields(
                value_kind=VALUE_KIND_TOLERANCE,
                value=value,
                value_min=None,
                value_max=None,
                value_tolerance=value_b,
                decimal_places=None,
            )
        else:
            clean_number_property_fields(
                value_kind=VALUE_KIND_SCALAR,
                value=value,
                value_min=None,
                value_max=None,
                decimal_places=None,
            )
    except (ValidationError, TypeError, ValueError):
        return False
    return True


def _unrecognized_structure_value(*, structure_field, column_label: str, raw: str) -> DraftStructureValue:
    return DraftStructureValue(
        field_name=structure_field.name,
        field_label=(structure_field.label or structure_field.name or '').strip(),
        column_label=column_label,
        raw=raw,
        value_kind=VALUE_KIND_SCALAR,
        value='',
        value_b='',
        confidence=CONFIDENCE_UNCERTAIN,
        note='не распознано автоматически',
        include=True,
        recognition=RECOGNITION_UNRECOGNIZED,
    )


def _unrecognized_property_value(*, prop_info, column_label: str, raw: str) -> DraftProperty:
    return DraftProperty(
        property_name=prop_info[1],
        property_id=prop_info[0],
        property_label=prop_info[3] if len(prop_info) > 3 else prop_info[1],
        column_label=column_label,
        raw=raw,
        value_kind=VALUE_KIND_SCALAR,
        value='',
        value_b='',
        confidence=CONFIDENCE_UNCERTAIN,
        note='не распознано автоматически',
        include=True,
        recognition=RECOGNITION_UNRECOGNIZED,
    )


def _resolve_identity(*, workspace, name, code, match_policy, used_codes):
    warnings: list[str] = []
    policy = match_policy or MATCH_BY_NAME

    if policy == MATCH_ALWAYS_CREATE:
        final_code = _make_code(name or code or 'material', used_codes)
        return 'create', None, final_code, warnings

    if policy == MATCH_BY_NAME and name:
        # Совпадения по названию обрабатываются на шаге записи (пропуск / префикс).
        # Здесь никогда не обновляем существующий материал.
        final_code = code or _make_code(name, used_codes)
        if code:
            final_code = _unique_code(code, used_codes)
        else:
            final_code = _make_code(name, used_codes)
        return 'create', None, final_code, warnings

    # match by code — тоже без перезаписи: при занятом коде выдаём уникальный
    if code:
        existing = Material.objects.filter(home_workspace=workspace, code=code).first()
        if existing:
            final_code = _unique_code(code, used_codes)
            warnings.append(
                f'Код «{code}» уже занят ({existing.name}) — будет создан с кодом «{final_code}»'
            )
            return 'create', None, final_code, warnings
        return 'create', None, _unique_code(code, used_codes), warnings

    final_code = _make_code(name or 'material', used_codes)
    return 'create', None, final_code, warnings


def _append_duplicate_field_warnings(
    struct_vals: list[DraftStructureValue],
    props: list[DraftProperty],
    warnings: list[str],
) -> None:
    """Предупреждает, если несколько колонок попали в одно поле/свойство."""
    struct_cols: dict[str, list[str]] = {}
    struct_labels: dict[str, str] = {}
    for item in struct_vals:
        struct_cols.setdefault(item.field_name, []).append(item.column_label)
        struct_labels[item.field_name] = item.field_label or item.field_name
    for field_name, columns in struct_cols.items():
        if len(columns) < 2:
            continue
        joined = ', '.join(f'«{col}»' for col in columns)
        warnings.append(
            f'{joined} → одно поле структуры «{struct_labels[field_name]}»; '
            f'при записи останется последнее непустое значение'
        )

    prop_cols: dict[str, list[str]] = {}
    prop_labels: dict[str, str] = {}
    for item in props:
        prop_cols.setdefault(item.property_id, []).append(item.column_label)
        prop_labels[item.property_id] = item.property_name
    for property_id, columns in prop_cols.items():
        if len(columns) < 2:
            continue
        joined = ', '.join(f'«{col}»' for col in columns)
        warnings.append(
            f'{joined} → одно доп. свойство «{prop_labels[property_id]}»; '
            f'при записи останется последнее непустое значение'
        )


_HEADER_LIKE_IDENTITY = frozenset({
    'наименование',
    'название',
    'name',
    'марка',
    'код',
    'code',
    'артикул',
})


def _is_header_like_identity(name: str, code: str) -> bool:
    """Отсекает строку-заголовок, попавшую в данные (name=Наименование, code=Марка)."""
    name_key = name.casefold()
    code_key = code.casefold()
    if name_key in _HEADER_LIKE_IDENTITY and (not code_key or code_key in _HEADER_LIKE_IDENTITY):
        return True
    if code_key in _HEADER_LIKE_IDENTITY and (not name_key or name_key in _HEADER_LIKE_IDENTITY):
        return True
    return False


def _tag_from_column(column, value: str) -> str:
    """
    Импорт всегда пишет scoped-тег «область::значение» (split в UI).
    Для «Марка» учитывает группу колонки: основа / уток.
    """
    from apps.core.tag_utils import TAG_NAME_MAX_LENGTH

    text = (value or '').strip()
    if not text:
        return ''
    if '::' in text:
        return text[:TAG_NAME_MAX_LENGTH]

    # Значение вида «Уток: EC9…» / «Основа: …» → отдельный scope
    prefix_match = re.match(
        r'^(уток|основа)\s*[:：]\s*(.+)$',
        text,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if prefix_match:
        side = prefix_match.group(1).casefold()
        return _scoped_tag_name(f'марка {side}', prefix_match.group(2).strip())

    group = ''
    label = ''
    if hasattr(column, 'group'):
        group = (column.group or '').strip()
        label = (column.label or '').strip()
    else:
        label = str(column or '').strip()
    hay = f'{group} {label}'.casefold()

    if 'марка' in hay:
        if 'уток' in hay:
            return _scoped_tag_name('марка уток', text)
        if 'основ' in hay:
            return _scoped_tag_name('марка основа', text)
        # ячейка «Основа: …» / «Уток: …» при колонке просто «Марка»
        cell_side = re.match(
            r'^(уток|основа)\s*[:：]\s*(.+)$',
            text,
            flags=re.IGNORECASE | re.UNICODE,
        )
        if cell_side:
            return _scoped_tag_name(
                f'марка {cell_side.group(1).casefold()}',
                cell_side.group(2).strip(),
            )
        return _scoped_tag_name('марка', text)

    scope = _tag_scope_from_column(group, label)
    return _scoped_tag_name(scope, text)


def _scoped_tag_name(scope: str, value: str) -> str:
    from apps.core.tag_utils import TAG_NAME_MAX_LENGTH

    scope = (scope or 'тег').strip()
    value = (value or '').strip()
    sep = '::'
    budget = TAG_NAME_MAX_LENGTH - len(sep) - len(scope)
    if budget < 1:
        scope = scope[:20]
        budget = TAG_NAME_MAX_LENGTH - len(sep) - len(scope)
    return f'{scope}{sep}{value[:budget]}'


def _tag_scope_from_column(group: str, label: str) -> str:
    """Короткое имя области для split-тега из заголовка колонки."""
    parts = [p for p in (group, label) if p]
    raw = ' / '.join(parts) if len(parts) > 1 else (parts[0] if parts else 'тег')
    # убрать единицы в хвосте «, Н», «(МПа)»
    cleaned = re.sub(r'\s*[\(,].*$', '', raw).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return (cleaned or 'тег')[:40]


def _is_numeric_parse(parsed: dict) -> bool:
    """True если parse_property_cell вернул число / диапазон / ±."""
    if parsed.get('value_kind') in ('range', 'tolerance'):
        return True
    note = parsed.get('note') or ''
    if note in {'число', 'диапазон', '± погрешность'} or note.startswith('± погрешность'):
        return True
    # «число извлечено из … (единицы отброшены)» и аналоги
    return note.startswith('число извлечено')


def _as_text(value) -> str:
    if is_blank_cell(value):
        return ''
    return str(value).replace('\u00a0', ' ').strip()


def _make_code(name: str, used: set[str]) -> str:
    base = slugify(name, allow_unicode=True) or 'material'
    return _unique_code(base[:40], used)


def _unique_code(code: str, used: set[str]) -> str:
    candidate = code[:50]
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while True:
        suffix = f'-{index}'
        candidate = f'{code[: 50 - len(suffix)]}{suffix}'
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1
