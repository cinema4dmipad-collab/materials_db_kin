from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from django.utils.text import slugify

from apps.materials.imports.mapping import (
    TARGET_CODE,
    TARGET_DESCRIPTION,
    TARGET_NAME,
    TARGET_PROPERTY_PREFIX,
    TARGET_SKIP,
    TARGET_STRUCTURE_PREFIX,
    TARGET_TAGS,
    normalize_mapping_entry,
)
from apps.materials.imports.structure_values import build_structure_sql_payload
from apps.core.property_number_value import VALUE_KIND_SCALAR
from apps.materials.imports.value_parse import (
    CONFIDENCE_OK,
    CONFIDENCE_UNCERTAIN,
    PARSE_AUTO,
    PARSE_TEXT,
    is_blank_cell,
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
    (MATCH_BY_NAME, 'По названию (удобно для больших таблиц Excel)'),
    (MATCH_BY_CODE, 'По коду материала'),
    (MATCH_ALWAYS_CREATE, 'Всегда создавать новые записи'),
)


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
    warnings: list[str] = field(default_factory=list)
    structure_values: list[DraftStructureValue] = field(default_factory=list)
    properties: list[DraftProperty] = field(default_factory=list)

    @property
    def has_uncertain(self) -> bool:
        uncertain_props = any(p.confidence == CONFIDENCE_UNCERTAIN and p.include for p in self.properties)
        uncertain_struct = any(
            s.confidence == CONFIDENCE_UNCERTAIN and s.include for s in self.structure_values
        )
        return uncertain_props or uncertain_struct


def build_staging_draft(
    table: WideTable,
    mapping: dict,
    *,
    workspace,
    match_policy: str = MATCH_BY_NAME,
    structure_type_id: str | None = None,
) -> list[DraftMaterial]:
    structure_field_cache = {
        field.name: field
        for field in StructureField.objects.filter(structure_type_id=structure_type_id).order_by('sort_order')
    } if structure_type_id else {}
    property_cache = {
        str(pk): (str(pk), name, data_type)
        for pk, name, data_type in Property.objects.all().values_list('pk', 'name', 'data_type')
    }
    map_by_index = {}
    parse_by_index = {}
    for key, entry in (mapping or {}).items():
        target, parse_mode = normalize_mapping_entry(entry)
        map_by_index[int(key)] = target
        parse_by_index[int(key)] = parse_mode

    drafts: list[DraftMaterial] = []
    used_codes: set[str] = set()

    for row_offset, wide_row in enumerate(table.rows):
        excel_row = table.header_row + 1 + row_offset
        fields = {'code': '', 'name': '', 'description': '', 'tags': []}
        struct_vals: list[DraftStructureValue] = []
        props: list[DraftProperty] = []
        warnings: list[str] = []

        for col in table.columns:
            target = map_by_index.get(col.index, TARGET_SKIP)
            if target == TARGET_SKIP:
                continue
            raw = wide_row.get(col.index)
            parse_mode = parse_by_index.get(col.index, PARSE_AUTO)

            if target == TARGET_CODE:
                fields['code'] = _as_text(raw)
            elif target == TARGET_NAME:
                fields['name'] = _as_text(raw)
            elif target == TARGET_DESCRIPTION:
                text = _as_text(raw)
                if text:
                    fields['description'] = (
                        f'{fields["description"]}; {text}'.strip('; ')
                        if fields['description']
                        else text
                    )
            elif target == TARGET_TAGS:
                text = _as_text(raw)
                if text:
                    fields['tags'].append(_tag_from_column(col, text))
            elif target.startswith(TARGET_STRUCTURE_PREFIX):
                field_name = target.split(':', 1)[1]
                structure_field = structure_field_cache.get(field_name)
                if not structure_field:
                    warnings.append(f'Поле структуры {field_name} не найдено ({col.display})')
                    continue
                if structure_field.field_type == 'MaterialLink':
                    parse_mode = PARSE_TEXT
                parsed = parse_property_cell(raw, mode=parse_mode)
                if parsed is None:
                    # Сопоставлено, но пусто — оставляем в черновике (можно снять галочку).
                    struct_vals.append(
                        DraftStructureValue(
                            field_name=structure_field.name,
                            field_label=structure_field.label,
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
                    continue
                if structure_field.field_type == 'DecimalField' and not _is_numeric_parse(parsed):
                    if parse_mode != 'text':
                        warnings.append(
                            f'«{col.display}»: нечисловое «{_as_text(raw)[:30]}» — пропущено'
                        )
                        continue
                struct_vals.append(
                    DraftStructureValue(
                        field_name=structure_field.name,
                        field_label=structure_field.label,
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
                    continue
                if prop_info[2] == 'material_link':
                    parse_mode = PARSE_TEXT
                parsed = parse_property_cell(raw, mode=parse_mode)
                if parsed is None:
                    props.append(
                        DraftProperty(
                            property_name=prop_info[1],
                            property_id=prop_info[0],
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
                    continue
                # Числовое свойство + нераспознанное значение → не тащим в импорт как ошибку
                if prop_info[2] == 'number' and not _is_numeric_parse(parsed):
                    if parse_mode == 'text':
                        pass  # пользователь явно хочет текст — упадёт на валидации
                    else:
                        warnings.append(
                            f'«{col.display}»: нечисловое «{_as_text(raw)[:30]}» — пропущено'
                        )
                        continue
                props.append(
                    DraftProperty(
                        property_name=prop_info[1],
                        property_id=prop_info[0],
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

        # Без названия и кода строку не пропускаем тихо: пусть валидация покажет ошибку.
        if not name and not code:
            warnings.append('Нет названия и кода')

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
                warnings=warnings,
                structure_values=struct_vals,
                properties=props,
            )
        )
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
        props = [DraftProperty(**p) for p in item.get('properties') or []]
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
    """
    if post.get('review_marker') != '1':
        return drafts
    includes_posted = any(
        key.startswith('include_') for key in post.keys()
    )
    for index, draft in enumerate(drafts):
        if post.get(f'skip_{index}') == '1':
            draft.action = 'skip'
        elif draft.existing_pk:
            draft.action = 'update'
        else:
            draft.action = 'create'
        if not includes_posted:
            continue
        for p_index, prop in enumerate(draft.properties):
            prop.include = post.get(f'include_{index}_{p_index}') == '1'
        for s_index, struct_val in enumerate(draft.structure_values):
            struct_val.include = post.get(f'include_struct_{index}_{s_index}') == '1'
    return drafts

def _resolve_identity(*, workspace, name, code, match_policy, used_codes):
    warnings: list[str] = []
    policy = match_policy or MATCH_BY_NAME

    if policy == MATCH_ALWAYS_CREATE:
        final_code = _make_code(name or code or 'material', used_codes)
        return 'create', None, final_code, warnings

    if policy == MATCH_BY_NAME and name:
        existing = (
            Material.objects.filter(home_workspace=workspace, name__iexact=name)
            .order_by('created_at')
            .first()
        )
        if existing:
            used_codes.add(existing.code)
            warnings.append(f'Найден материал с таким названием ({existing.code}) — будет обновлён')
            return 'update', str(existing.pk), existing.code, warnings
        final_code = code or _make_code(name, used_codes)
        if code:
            final_code = _unique_code(code, used_codes)
        else:
            final_code = _make_code(name, used_codes)
        return 'create', None, final_code, warnings

    # match by code
    if code:
        existing = Material.objects.filter(home_workspace=workspace, code=code).first()
        final_code = _unique_code(code, used_codes) if not existing else code
        if existing:
            used_codes.add(existing.code)
            return 'update', str(existing.pk), existing.code, warnings
        return 'create', None, final_code, warnings

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
