from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
)
from apps.core.tag_utils import dedupe_scoped_tag_names, parse_tag_input
from apps.materials.imports.material_link import (
    MaterialLinkIndex,
    ensure_material_ref_known,
)
from apps.materials.imports.report import ImportReport
from apps.materials.imports.staging import (
    RECOGNITION_UNRECOGNIZED,
    DraftMaterial,
)
from apps.materials.imports.structure_values import (
    build_structure_sql_payload,
    empty_structure_sql_payload,
    merge_structure_sql_payloads,
)
from apps.materials.imports.value_parse import is_blank_cell
from apps.core.models import Tag
from apps.materials.models import Material, MaterialProperty
from apps.references.dictionaries import (
    DICTIONARY_LABELS,
    resolve_or_create_dictionary_item,
)
from apps.references.models import Availability, Manufacturer, Property, Technology
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE, StructureField, StructureType
from apps.workspaces.models import Workspace

_MATERIAL_NAME_MAX = Material._meta.get_field('name').max_length
_MATERIAL_CODE_MAX = Material._meta.get_field('code').max_length
_PROPERTY_VALUE_MAX = MaterialProperty._meta.get_field('value').max_length
_TAG_NAME_MAX = Tag._meta.get_field('name').max_length


@dataclass
class PropertyImportItem:
    row_number: int
    property_ref: Property
    value_kind: str
    value: str
    value_b: str | None
    notes: str


@dataclass
class MaterialImportItem:
    code: str
    name: str | None
    description: str
    struct_type: StructureType | None
    tag_names: list[str]
    properties: list[PropertyImportItem] = field(default_factory=list)
    row_numbers: list[int] = field(default_factory=list)
    exists: bool = False


@dataclass
class HybridImportItem:
    code: str
    name: str | None
    description: str
    tag_names: list[str]
    action: str
    existing_pk: str | None
    existing_struct_type_id: str | None
    existing_struct_props_id: str | None
    structure_sql: dict
    properties: list[PropertyImportItem] = field(default_factory=list)
    structure_link_refs: dict[str, str] = field(default_factory=dict)
    row_number: int | None = None
    manufacturer_id: str | None = None
    availability_id: str | None = None
    technology_id: str | None = None
    manufacturer_create: tuple[str, str] | None = None
    availability_create: tuple[str, str] | None = None
    technology_create: tuple[str, str] | None = None


def validate_drafts(
    drafts: list[DraftMaterial],
    *,
    structure_type: StructureType,
    workspace: Workspace,
    report: ImportReport,
    create_missing_dictionaries: bool = False,
    dry_run: bool = False,
) -> list[HybridImportItem]:
    if not structure_type.is_created:
        report.add_error('Выбранный тип структуры ещё не создан (нет SQL-таблицы).')
        return []
    if not structure_type.is_active:
        report.add_error('Выбранный тип структуры неактивен.')
        return []

    structure_fields = {
        field.name: field
        for field in StructureField.objects.filter(structure_type=structure_type).order_by('sort_order')
    }
    property_cache: dict[str, Property | None] = {}
    draft_index = MaterialLinkIndex.from_drafts(drafts)
    dictionary_pending: dict = {}
    items: list[HybridImportItem] = []

    for draft in drafts:
        if draft.action == 'skip':
            continue
        if not draft.name and draft.action == 'create':
            # Staging normally marks such rows as skip; keep a soft fallback for
            # hand-edited drafts / iterate so one empty name does not hard-block apply.
            draft.action = 'skip'
            draft.warnings.append(
                'Пропущено: нет названия — материал не будет создан '
                '(сопоставьте колонку с полем «Название» или заполните ячейку).'
            )
            continue
        if draft.name and len(draft.name) > _MATERIAL_NAME_MAX:
            report.add_error(
                f'Название длиннее {_MATERIAL_NAME_MAX} символов ({len(draft.name)}). '
                f'Сократите в Excel или разбейте запись.',
                row=draft.source_row,
                column='name',
            )
            continue
        if draft.code and len(draft.code) > _MATERIAL_CODE_MAX:
            report.add_error(
                f'Код длиннее {_MATERIAL_CODE_MAX} символов ({len(draft.code)}).',
                row=draft.source_row,
                column='code',
            )
            continue

        existing = None
        if draft.existing_pk:
            existing = Material.objects.filter(pk=draft.existing_pk, home_workspace=workspace).first()
        if draft.existing_pk and existing is None:
            report.add_error('Материал для обновления не найден.', row=draft.source_row, column='code')
            continue
        if existing and existing.struct_type_id and str(existing.struct_type_id) != str(structure_type.pk):
            report.add_error(
                f'Материал {existing.code} уже привязан к другому типу структуры '
                f'({existing.struct_type.name}).',
                row=draft.source_row,
                column='struct_type',
            )
            continue

        sql_payloads = []
        structure_link_refs: dict[str, str] = {}
        for struct_val in draft.structure_values:
            if getattr(struct_val, 'recognition', '') == RECOGNITION_UNRECOGNIZED:
                # На dry_run предупреждение показывает UI шага записи; при реальной записи — блок.
                if not dry_run:
                    report.add_error(
                        f'Поле «{struct_val.field_label or struct_val.field_name}» не распознано — '
                        f'исправьте значение или проигнорируйте на шаге записи.',
                        row=draft.source_row,
                        column=struct_val.field_name,
                    )
                continue
            if not struct_val.include:
                continue
            structure_field = structure_fields.get(struct_val.field_name)
            if structure_field is None:
                report.add_error(
                    f'Поле структуры «{struct_val.field_name}» не найдено.',
                    row=draft.source_row,
                    column=struct_val.field_name,
                )
                continue
            if is_blank_cell(struct_val.value) and is_blank_cell(struct_val.value_b):
                # Сопоставлено и включено, но пусто → NULL на карточке материала.
                sql_payloads.append(empty_structure_sql_payload(structure_field))
                continue
            if structure_field.field_type == MATERIAL_LINK_FIELD_TYPE:
                try:
                    ref = ensure_material_ref_known(
                        struct_val.value,
                        workspace=workspace,
                        draft_index=draft_index,
                    )
                except ValidationError as exc:
                    message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                    report.add_error(message, row=draft.source_row, column=struct_val.field_name)
                    continue
                structure_link_refs[structure_field.name] = ref
                continue
            parsed = {
                'value_kind': struct_val.value_kind,
                'value': struct_val.value,
                'value_b': struct_val.value_b or None,
            }
            try:
                payload = build_structure_sql_payload(structure_field, parsed)
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=draft.source_row, column=struct_val.field_name)
                continue
            if payload:
                sql_payloads.append(payload)

        structure_sql = merge_structure_sql_payloads(sql_payloads)
        prop_items: list[PropertyImportItem] = []
        for prop in draft.properties:
            if getattr(prop, 'recognition', '') == RECOGNITION_UNRECOGNIZED:
                if not dry_run:
                    label = getattr(prop, 'property_label', '') or prop.property_name
                    report.add_error(
                        f'Свойство «{label}» не распознано — '
                        f'исправьте значение или проигнорируйте на шаге записи.',
                        row=draft.source_row,
                        column='value',
                    )
                continue
            if not prop.include:
                continue
            property_ref = _resolve_property(prop.property_name, property_cache)
            if property_ref is None:
                report.add_error(
                    f'Свойство «{prop.property_name}» не найдено в справочнике.',
                    row=draft.source_row,
                    column='property_name',
                )
                continue
            if is_blank_cell(prop.value) and is_blank_cell(prop.value_b):
                # Пустая ячейка — не создаём пустое MaterialProperty (иначе карточка
                # забивается «пустыми» доп. свойствами без значений).
                continue
            row = {
                'value_kind': prop.value_kind,
                'value': prop.value,
                'value_b': prop.value_b,
                'notes': prop.note,
            }
            try:
                payload = _clean_property_value(
                    row,
                    property_ref,
                    workspace=workspace,
                    draft_index=draft_index,
                    resolve_links=False,
                )
            except ValidationError as exc:
                message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                report.add_error(message, row=draft.source_row, column='value')
                continue
            prop_items.append(
                PropertyImportItem(
                    row_number=draft.source_row,
                    property_ref=property_ref,
                    value_kind=payload['value_kind'],
                    value=payload['value'],
                    value_b=payload.get('value_b'),
                    notes=prop.note,
                )
            )
        prop_items = _dedupe_property_items_prefer_nonblank(prop_items)

        tag_names = parse_tag_input(draft.tags or '')
        long_tags = [tag for tag in tag_names if len(tag) > _TAG_NAME_MAX]
        if long_tags:
            sample = long_tags[0]
            report.add_error(
                f'Тег длиннее {_TAG_NAME_MAX} символов ({len(sample)}): «{sample[:40]}…». '
                f'Сократите значение в Excel.',
                row=draft.source_row,
                column='tags',
            )
            continue

        manufacturer_id = None
        manufacturer_create = None
        manufacturer = None
        if (draft.manufacturer or '').strip():
            resolved = resolve_or_create_dictionary_item(
                Manufacturer,
                draft.manufacturer,
                create_missing=create_missing_dictionaries,
                dry_run=dry_run,
                pending=dictionary_pending,
            )
            if resolved.error:
                report.add_error(
                    resolved.error,
                    row=draft.source_row,
                    column='manufacturer',
                )
                continue
            if resolved.linked_by_code and resolved.item is not None:
                report.add_dictionary_linked_by_code(
                    DICTIONARY_LABELS[Manufacturer],
                    draft.manufacturer.strip(),
                    resolved.item.name,
                    resolved.item.code,
                )
            if resolved.deferred_create:
                report.add_dictionary_created(
                    DICTIONARY_LABELS[Manufacturer],
                    resolved.create_name,
                    resolved.create_code,
                )
                manufacturer_create = (resolved.create_name, resolved.create_code)
            elif resolved.item is not None:
                if not resolved.matched_existing and not resolved.linked_by_code:
                    report.add_dictionary_created(
                        DICTIONARY_LABELS[Manufacturer],
                        resolved.item.name,
                        resolved.item.code,
                    )
                manufacturer = resolved.item
                manufacturer_id = str(resolved.item.pk)

        availability_id = None
        availability_create = None
        availability = None
        if (draft.availability or '').strip():
            resolved = resolve_or_create_dictionary_item(
                Availability,
                draft.availability,
                create_missing=create_missing_dictionaries,
                dry_run=dry_run,
                pending=dictionary_pending,
            )
            if resolved.error:
                report.add_error(
                    resolved.error,
                    row=draft.source_row,
                    column='availability',
                )
                continue
            if resolved.linked_by_code and resolved.item is not None:
                report.add_dictionary_linked_by_code(
                    DICTIONARY_LABELS[Availability],
                    draft.availability.strip(),
                    resolved.item.name,
                    resolved.item.code,
                )
            if resolved.deferred_create:
                report.add_dictionary_created(
                    DICTIONARY_LABELS[Availability],
                    resolved.create_name,
                    resolved.create_code,
                )
                availability_create = (resolved.create_name, resolved.create_code)
            elif resolved.item is not None:
                if not resolved.matched_existing and not resolved.linked_by_code:
                    report.add_dictionary_created(
                        DICTIONARY_LABELS[Availability],
                        resolved.item.name,
                        resolved.item.code,
                    )
                availability = resolved.item
                availability_id = str(resolved.item.pk)

        technology_id = None
        technology_create = None
        technology = None
        if (draft.technology or '').strip():
            resolved = resolve_or_create_dictionary_item(
                Technology,
                draft.technology,
                create_missing=create_missing_dictionaries,
                dry_run=dry_run,
                pending=dictionary_pending,
            )
            if resolved.error:
                report.add_error(
                    resolved.error,
                    row=draft.source_row,
                    column='technology',
                )
                continue
            if resolved.linked_by_code and resolved.item is not None:
                report.add_dictionary_linked_by_code(
                    DICTIONARY_LABELS[Technology],
                    draft.technology.strip(),
                    resolved.item.name,
                    resolved.item.code,
                )
            if resolved.deferred_create:
                report.add_dictionary_created(
                    DICTIONARY_LABELS[Technology],
                    resolved.create_name,
                    resolved.create_code,
                )
                technology_create = (resolved.create_name, resolved.create_code)
            elif resolved.item is not None:
                if not resolved.matched_existing and not resolved.linked_by_code:
                    report.add_dictionary_created(
                        DICTIONARY_LABELS[Technology],
                        resolved.item.name,
                        resolved.item.code,
                    )
                technology = resolved.item
                technology_id = str(resolved.item.pk)

        # Пустые ячейки → NULL/пропуск; достаточно названия/кода, чтобы создать материал.
        has_identity = bool(draft.name or draft.code)
        has_payload = bool(
            structure_sql
            or structure_link_refs
            or prop_items
            or tag_names
            or draft.description
            or manufacturer
            or availability
            or technology
            or manufacturer_create
            or availability_create
            or technology_create
        )
        if not has_identity and not has_payload:
            report.add_error(
                'Строка не содержит данных для импорта.',
                row=draft.source_row,
            )
            continue

        items.append(
            HybridImportItem(
                code=draft.code,
                name=draft.name or None,
                description=draft.description,
                tag_names=tag_names,
                action=draft.action,
                existing_pk=draft.existing_pk,
                existing_struct_type_id=str(existing.struct_type_id) if existing and existing.struct_type_id else None,
                existing_struct_props_id=str(existing.struct_props_id) if existing and existing.struct_props_id else None,
                structure_sql=structure_sql,
                properties=prop_items,
                structure_link_refs=structure_link_refs,
                row_number=draft.source_row,
                manufacturer_id=manufacturer_id,
                availability_id=availability_id,
                technology_id=technology_id,
                manufacturer_create=manufacturer_create,
                availability_create=availability_create,
                technology_create=technology_create,
            )
        )
    return items


def validate_rows(
    rows: list[dict],
    *,
    workspace: Workspace,
    report: ImportReport,
) -> list[MaterialImportItem]:
    if not rows:
        report.add_error('Файл не содержит строк данных.')
        return []

    property_cache: dict[str, Property | None] = {}
    struct_cache: dict[str, StructureType | None] = {}
    grouped: dict[str, MaterialImportItem] = {}
    batch_index = MaterialLinkIndex()
    for row in rows:
        code = (row.get('code') or '').strip()
        name = (row.get('name') or '').strip()
        if code:
            batch_index.by_code[code.casefold()] = code
        if name and code:
            batch_index.by_name.setdefault(name.casefold(), [])
            if code not in batch_index.by_name[name.casefold()]:
                batch_index.by_name[name.casefold()].append(code)

    for row in rows:
        row_number = row.get('_row_number')
        code = (row.get('code') or '').strip()
        if not code:
            report.add_error('Укажите code материала.', row=row_number, column='code')
            continue
        if len(code) > _MATERIAL_CODE_MAX:
            report.add_error(
                f'Код длиннее {_MATERIAL_CODE_MAX} символов ({len(code)}).',
                row=row_number,
                column='code',
            )
            continue
        name_raw = (row.get('name') or '').strip()
        if name_raw and len(name_raw) > _MATERIAL_NAME_MAX:
            report.add_error(
                f'Название длиннее {_MATERIAL_NAME_MAX} символов ({len(name_raw)}). '
                f'Сократите в Excel или разбейте запись.',
                row=row_number,
                column='name',
            )
            continue

        home_workspace_raw = (row.get('home_workspace') or '').strip()
        if home_workspace_raw and home_workspace_raw != workspace.slug:
            report.add_error(
                f'Колонка home_workspace должна совпадать с --workspace ({workspace.slug}).',
                row=row_number,
                column='home_workspace',
            )
            continue

        material = grouped.get(code)
        if material is None:
            material = MaterialImportItem(
                code=code,
                name=(row.get('name') or '').strip() or None,
                description=(row.get('description') or '').strip(),
                struct_type=_resolve_struct_type(row.get('struct_type'), struct_cache, report, row_number),
                tag_names=parse_tag_input(row.get('tags') or ''),
                row_numbers=[row_number],
            )
            grouped[code] = material
        else:
            material.row_numbers.append(row_number)
            if row.get('name'):
                material.name = row['name'].strip()
            if row.get('description'):
                material.description = row['description'].strip()
            if row.get('struct_type'):
                resolved = _resolve_struct_type(row['struct_type'], struct_cache, report, row_number)
                if resolved is not None:
                    material.struct_type = resolved
            material.tag_names = dedupe_scoped_tag_names(
                material.tag_names + parse_tag_input(row.get('tags') or '')
            )

        property_name = (row.get('property_name') or '').strip()
        if not property_name:
            continue

        # Пустая ячейка / прочерк — не создаём свойство и не считаем ошибкой
        if is_blank_cell(row.get('value')) and is_blank_cell(row.get('value_b')):
            continue

        property_ref = _resolve_property(property_name, property_cache)
        if property_ref is None:
            report.add_error(
                f'Свойство «{property_name}» не найдено в справочнике.',
                row=row_number,
                column='property_name',
            )
            continue

        try:
            payload = _clean_property_value(
                row,
                property_ref,
                workspace=workspace,
                draft_index=batch_index,
                resolve_links=False,
            )
        except ValidationError as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            report.add_error(message, row=row_number, column='value')
            continue

        # Пустой результат очистки (оба слота пусты) — пропускаем, не затираем существующее
        if not str(payload.get('value') or '').strip() and payload.get('value_b') in (None, ''):
            continue

        prop_item = PropertyImportItem(
            row_number=row_number,
            property_ref=property_ref,
            value_kind=payload['value_kind'],
            value=payload['value'],
            value_b=payload.get('value_b'),
            notes=(row.get('notes') or '').strip(),
        )
        _upsert_property_item(material, prop_item)

    from apps.materials.models import Material

    existing_codes = set(
        Material.objects.filter(home_workspace=workspace, code__in=grouped.keys()).values_list(
            'code',
            flat=True,
        )
    )
    items: list[MaterialImportItem] = []
    for code, material in grouped.items():
        material.exists = code in existing_codes
        if not material.exists and not material.name:
            first_row = material.row_numbers[0]
            report.add_error(
                'Для нового материала укажите name хотя бы в одной строке.',
                row=first_row,
                column='name',
            )
            continue
        items.append(material)
    return items


def _property_item_is_blank(item: PropertyImportItem) -> bool:
    return is_blank_cell(item.value) and is_blank_cell(item.value_b)


def _dedupe_property_items_prefer_nonblank(
    items: list[PropertyImportItem],
) -> list[PropertyImportItem]:
    """Одно свойство несколько раз — оставляем последнее непустое."""
    by_pk: dict[str, PropertyImportItem] = {}
    order: list[str] = []
    for item in items:
        key = str(item.property_ref.pk)
        prev = by_pk.get(key)
        if prev is None:
            order.append(key)
            by_pk[key] = item
            continue
        if _property_item_is_blank(item) and not _property_item_is_blank(prev):
            continue
        by_pk[key] = item
    return [by_pk[key] for key in order]


def _upsert_property_item(material: MaterialImportItem, prop_item: PropertyImportItem) -> None:
    for index, existing in enumerate(material.properties):
        if existing.property_ref.pk == prop_item.property_ref.pk:
            material.properties[index] = prop_item
            return
    material.properties.append(prop_item)


def _resolve_property(name: str, cache: dict[str, Property | None]) -> Property | None:
    key = name.casefold()
    if key not in cache:
        cache[key] = Property.objects.filter(name__iexact=name).first()
    return cache[key]


def _resolve_struct_type(
    raw: str | None,
    cache: dict[str, StructureType | None],
    report: ImportReport,
    row_number: int | None,
) -> StructureType | None:
    text = (raw or '').strip()
    if not text:
        return None
    key = text.casefold()
    if key not in cache:
        cache[key] = (
            StructureType.objects.filter(code__iexact=text).first()
            or StructureType.objects.filter(name__iexact=text).first()
        )
    struct_type = cache[key]
    if struct_type is None:
        report.add_error(
            f'Тип структуры «{text}» не найден.',
            row=row_number,
            column='struct_type',
        )
    return struct_type


def _clean_property_value(
    row: dict,
    property_ref: Property,
    *,
    workspace: Workspace | None = None,
    draft_index: MaterialLinkIndex | None = None,
    resolve_links: bool = True,
) -> dict:
    data_type = property_ref.data_type
    value_kind = (row.get('value_kind') or VALUE_KIND_SCALAR).strip().lower() or VALUE_KIND_SCALAR
    raw_value = row.get('value') or ''
    raw_value_b = row.get('value_b') or ''

    if data_type == Property.MATERIAL_LINK_DATA_TYPE:
        if value_kind != VALUE_KIND_SCALAR:
            raise ValidationError('value_kind применим только к числовым свойствам.')
        if raw_value_b:
            raise ValidationError('value_b применим только к числовым свойствам (range/tolerance).')
        if workspace is None:
            raise ValidationError('Для material_link нужен контекст пространства.')
        if resolve_links:
            from apps.materials.imports.material_link import resolve_material_ref

            linked = resolve_material_ref(raw_value, workspace=workspace)
            return {
                'value_kind': VALUE_KIND_SCALAR,
                'value': str(linked.pk),
                'value_b': None,
            }
        ref = ensure_material_ref_known(
            raw_value,
            workspace=workspace,
            draft_index=draft_index,
        )
        return {
            'value_kind': VALUE_KIND_SCALAR,
            'value': ref,
            'value_b': None,
        }

    if data_type == 'number':
        if value_kind == VALUE_KIND_RANGE:
            return clean_number_property_fields(
                value_kind=value_kind,
                value='',
                value_min=raw_value,
                value_max=raw_value_b,
                decimal_places=property_ref.decimal_places,
            )
        if value_kind == VALUE_KIND_TOLERANCE:
            return clean_number_property_fields(
                value_kind=value_kind,
                value=raw_value,
                value_min=None,
                value_max=None,
                value_tolerance=raw_value_b,
                decimal_places=property_ref.decimal_places,
            )
        return clean_number_property_fields(
            value_kind=VALUE_KIND_SCALAR,
            value=raw_value,
            value_min=None,
            value_max=None,
            decimal_places=property_ref.decimal_places,
        )

    if not str(raw_value).strip():
        return {
            'value_kind': VALUE_KIND_SCALAR,
            'value': '',
            'value_b': None,
        }
    if value_kind != VALUE_KIND_SCALAR:
        raise ValidationError('value_kind применим только к числовым свойствам.')
    if raw_value_b:
        raise ValidationError('value_b применим только к числовым свойствам (range/tolerance).')
    text = str(raw_value).strip()
    if len(text) > _PROPERTY_VALUE_MAX:
        raise ValidationError(
            f'Значение длиннее {_PROPERTY_VALUE_MAX} символов ({len(text)}). Сократите в Excel.'
        )
    return {
        'value_kind': VALUE_KIND_SCALAR,
        'value': text,
        'value_b': None,
    }
