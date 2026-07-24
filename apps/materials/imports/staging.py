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
    TARGET_PROPERTY_PREFIX,
    TARGET_SKIP,
    TARGET_STRUCTURE_PREFIX,
    TARGET_TAGS,
    TARGET_TECHNOLOGY,
    normalize_mapping_entry,
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
    (MATCH_BY_NAME, 'По названию (удобно для больших таблиц Excel)'),
    (MATCH_BY_CODE, 'По коду материала'),
    (MATCH_ALWAYS_CREATE, 'Всегда создавать новые записи'),
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

    drafts: list[DraftMaterial] = []
    used_codes: set[str] = set()

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
        }
        name_column_label = ''
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
                    continue
                if _should_mark_unrecognized(
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
                    continue
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
                    continue
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
                    continue
                if _should_mark_unrecognized(
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
                    continue
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


def has_unresolved_unrecognized(drafts: list[DraftMaterial]) -> bool:
    return any(draft.has_unrecognized for draft in drafts)


def iter_unrecognized_fields(drafts: list[DraftMaterial], post=None) -> list[dict]:
    items: list[dict] = []
    for draft_index, draft in enumerate(drafts):
        if draft.action == 'skip':
            continue
        material_label = draft.name or draft.code or f'строка {draft.source_row}'
        for struct_index, struct in enumerate(draft.structure_values):
            if struct.recognition != RECOGNITION_UNRECOGNIZED:
                continue
            input_name = f'fix_struct_{draft_index}_{struct_index}'
            fix_value = _fix_value_from_post(post, input_name, struct.raw)
            items.append(
                {
                    'draft_index': draft_index,
                    'field_index': struct_index,
                    'kind': 'struct',
                    'source_row': draft.source_row,
                    'material_label': material_label,
                    'column_label': struct.column_label,
                    'target_label': struct.field_label,
                    'raw': struct.raw,
                    'fix_value': fix_value,
                    'input_name': input_name,
                    'skip_name': f'skip_{input_name}',
                    'skip_checked': post is not None and post.get(f'skip_{input_name}') == '1',
                }
            )
        for prop_index, prop in enumerate(draft.properties):
            if prop.recognition != RECOGNITION_UNRECOGNIZED:
                continue
            input_name = f'fix_prop_{draft_index}_{prop_index}'
            fix_value = _fix_value_from_post(post, input_name, prop.raw)
            items.append(
                {
                    'draft_index': draft_index,
                    'field_index': prop_index,
                    'kind': 'prop',
                    'source_row': draft.source_row,
                    'material_label': material_label,
                    'column_label': prop.column_label,
                    'target_label': prop.property_label or prop.property_name,
                    'raw': prop.raw,
                    'fix_value': fix_value,
                    'input_name': input_name,
                    'skip_name': f'skip_{input_name}',
                    'skip_checked': post is not None and post.get(f'skip_{input_name}') == '1',
                }
            )
    return items


def _fix_value_from_post(post, input_name: str, raw: str) -> str:
    if post is not None and input_name in post:
        return (post.get(input_name) or '').strip()
    return raw or ''


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
    errors: list[str] = []
    for draft_index, draft in enumerate(drafts):
        if draft.action == 'skip':
            continue
        for struct_index, struct in enumerate(draft.structure_values):
            if struct.recognition != RECOGNITION_UNRECOGNIZED:
                continue
            key = f'fix_struct_{draft_index}_{struct_index}'
            if post.get(f'skip_{key}') == '1':
                _ignore_unrecognized_structure(struct)
                continue
            raw_fix = (post.get(key) or '').strip()
            if not raw_fix:
                errors.append(
                    f'Строка {draft.source_row}, «{struct.column_label}» → {struct.field_label}: '
                    f'введите значение или отметьте «Пропустить».'
                )
                continue
            error = _apply_manual_fix_to_structure(struct, raw_fix, draft.source_row)
            if error:
                errors.append(error)
        for prop_index, prop in enumerate(draft.properties):
            if prop.recognition != RECOGNITION_UNRECOGNIZED:
                continue
            key = f'fix_prop_{draft_index}_{prop_index}'
            if post.get(f'skip_{key}') == '1':
                _ignore_unrecognized_property(prop)
                continue
            raw_fix = (post.get(key) or '').strip()
            if not raw_fix:
                errors.append(
                    f'Строка {draft.source_row}, «{prop.column_label}» → {prop.property_name}: '
                    f'введите значение или отметьте «Пропустить».'
                )
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
    prop.value_kind = parsed['value_kind']
    prop.value = str(parsed['value'])
    prop.value_b = '' if parsed['value_b'] is None else str(parsed['value_b'])
    prop.confidence = parsed.get('confidence', CONFIDENCE_OK)
    prop.note = parsed.get('note', '')
    prop.recognition = RECOGNITION_MANUAL
    prop.include = True
    return None


def _should_mark_unrecognized(*, expects_number: bool, parse_mode: str, raw, parsed: dict) -> bool:
    """True если числовое поле нельзя записать без участия техника.

    Режим колонки «Текст» больше не обходит проверку: иначе значение уходит в черновик
    строкой и падает на валидации («Введите корректное число»), минуя форму исправления.
    """
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
