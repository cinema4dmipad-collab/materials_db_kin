"""Export selected materials to a convenient XLSX table (not an import round-trip)."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Iterable
from uuid import UUID

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from apps.materials.models import Material, MaterialProperty
from apps.materials.structure_display import (
    STRUCTURE_SERVICE_COLUMNS,
    structure_field_display_value,
)
from apps.references.models import Property
from apps.structures.models import StructureType

EXPORT_ROW_LIMIT = 10_000
_XLSX_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

_THIN_BLACK = Side(style='thin', color='000000')
_TABLE_BORDER = Border(
    left=_THIN_BLACK,
    right=_THIN_BLACK,
    top=_THIN_BLACK,
    bottom=_THIN_BLACK,
)
_HEADER_FILL = PatternFill('solid', fgColor='D9D9D9')
_HEADER_FONT = Font(bold=True)
_CELL_ALIGN = Alignment(vertical='center', wrap_text=True)

_REQUIRED_COLUMNS = (
    ('code', 'Код'),
    ('name', 'Название'),
)

_OPTIONAL_COLUMNS = (
    ('description', 'Описание'),
    ('manufacturer', 'Производитель'),
    ('availability', 'Доступность'),
    ('technology', 'Технология'),
    ('struct_type', 'Тип структуры'),
    ('import_source', 'Источник импорта'),
)


class MaterialExportError(ValueError):
    """User-facing export validation error."""


def validate_single_structure_export(materials: Iterable[Material]) -> StructureType:
    """Ensure selection is one structure type (required)."""
    materials = list(materials)
    if not materials:
        raise MaterialExportError('Среди выбранных нет материалов, доступных для выгрузки.')

    type_ids = {material.struct_type_id for material in materials}
    if None in type_ids or '' in type_ids:
        raise MaterialExportError(
            'Выгрузка возможна только для материалов с типом структуры. '
            'Уберите из выбора материалы без типа.'
        )
    if len(type_ids) > 1:
        names = sorted(
            {
                material.struct_type.name
                for material in materials
                if material.struct_type_id
            }
        )
        shown = ', '.join(names[:5])
        extra = '…' if len(names) > 5 else ''
        raise MaterialExportError(
            'В одном файле можно выгрузить только один тип структуры. '
            f'Сейчас выбрано несколько: {shown}{extra}. '
            'Отметьте материалы одного типа и повторите выгрузку.'
        )

    structure_type = materials[0].struct_type
    if structure_type is None:
        raise MaterialExportError(
            'Выгрузка возможна только для материалов с типом структуры.'
        )
    return structure_type


def _clean_cell(value) -> str:
    """Keep Excel-safe text (strip control chars that break openpyxl / Excel)."""
    if value is None:
        return ''
    text = value if isinstance(value, str) else str(value)
    return ILLEGAL_CHARACTERS_RE.sub('', text)


def _as_uuid(value) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _property_cell_text(mp: MaterialProperty) -> str:
    prop = mp.property
    try:
        if prop.data_type == Property.CHOICE_DATA_TYPE:
            text = mp.choice_display_value() or ''
        elif prop.data_type == Property.MATERIAL_LINK_DATA_TYPE:
            linked = mp.linked_material()
            if linked is not None:
                text = f'{linked.code} — {linked.name}'
            else:
                text = (mp.value or '').strip()
        elif prop.data_type == 'number':
            text = mp.display_value()
        else:
            text = (mp.value or '').strip()
    except Exception:  # noqa: BLE001 — keep export resilient per cell
        text = (mp.value or '').strip()
    return _clean_cell(text)


def _property_column_headers(properties: Iterable[Property]) -> list[tuple[str, str]]:
    seen: dict[str, int] = {}
    columns: list[tuple[str, str]] = []
    for prop in properties:
        label = (prop.display_name or prop.name or 'Свойство').strip()
        count = seen.get(label, 0) + 1
        seen[label] = count
        if count > 1:
            suffix = prop.name or str(prop.pk)[:8]
            label = f'{label} ({suffix})'
        columns.append((str(prop.pk), label))
    return columns


def _structure_field_columns(structure_type: StructureType) -> list:
    return list(
        structure_type.fields.exclude(name__in=STRUCTURE_SERVICE_COLUMNS)
        .exclude(field_type='ForeignKey')
        .order_by('sort_order', 'name')
    )


def _structure_column_headers(fields) -> list[tuple[str, str]]:
    """Return (field.name, header) with unique labels; prefix to avoid clashing with catalog."""
    seen: dict[str, int] = {}
    columns: list[tuple[str, str]] = []
    for field in fields:
        label = (field.label or field.name or 'Поле').strip()
        count = seen.get(label, 0) + 1
        seen[label] = count
        if count > 1:
            label = f'{label} ({field.name})'
        columns.append((field.name, label))
    return columns


def _structure_cell_text(field, structure_params: dict | None) -> str:
    if not structure_params:
        return ''
    try:
        text = structure_field_display_value(
            field,
            structure_params.get(field.name),
            structure_params=structure_params,
        )
    except Exception:  # noqa: BLE001
        raw = structure_params.get(field.name)
        text = '' if raw is None else str(raw)
    if text == '—':
        return ''
    return _clean_cell(text)


def _material_base_map(material: Material) -> dict[str, str]:
    return {
        'code': _clean_cell(material.code or ''),
        'name': _clean_cell(material.name or ''),
        'description': _clean_cell((material.description or '').strip()),
        'manufacturer': _clean_cell(
            material.manufacturer.name if material.manufacturer_id else ''
        ),
        'availability': _clean_cell(
            material.availability.name if material.availability_id else ''
        ),
        'technology': _clean_cell(
            material.technology.name if material.technology_id else ''
        ),
        'struct_type': _clean_cell(
            material.struct_type.name if material.struct_type_id else ''
        ),
        'import_source': _clean_cell((material.import_source_filename or '').strip()),
    }


def _active_optional_columns(base_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    active: list[tuple[str, str]] = []
    for key, title in _OPTIONAL_COLUMNS:
        if any((row.get(key) or '').strip() for row in base_rows):
            active.append((key, title))
    return active


def build_materials_workbook(
    queryset: QuerySet,
    *,
    row_limit: int = EXPORT_ROW_LIMIT,
    preferred_order: list | None = None,
) -> tuple[Workbook, int, bool]:
    """Build workbook for one structure type. Raises MaterialExportError on mixed/missing types."""
    if preferred_order:
        raw_ids = list(preferred_order)[: row_limit + 1]
        truncated = len(preferred_order) > row_limit
    else:
        ordered = queryset.order_by('code', 'pk')
        raw_ids = list(ordered.values_list('pk', flat=True)[: row_limit + 1])
        truncated = len(raw_ids) > row_limit
    material_ids: list[UUID] = []
    for raw in raw_ids[:row_limit]:
        pk = _as_uuid(raw)
        if pk is not None:
            material_ids.append(pk)

    materials_by_id = {
        material.pk: material
        for material in Material.objects.filter(pk__in=material_ids)
        .select_related(
            'struct_type',
            'manufacturer',
            'availability',
            'technology',
        )
        .prefetch_related(
            'struct_type__fields',
            Prefetch(
                'properties',
                queryset=MaterialProperty.objects.select_related('property').order_by(
                    'property__display_name',
                    'property__name',
                ),
            ),
        )
    }
    materials = [materials_by_id[pk] for pk in material_ids if pk in materials_by_id]
    structure_type = validate_single_structure_export(materials)
    structure_fields = _structure_field_columns(structure_type)
    structure_columns = _structure_column_headers(structure_fields)
    structure_field_by_name = {field.name: field for field in structure_fields}

    base_rows = [_material_base_map(material) for material in materials]
    # Always show structure type name for single-type export.
    optional = _active_optional_columns(base_rows)
    if not any(key == 'struct_type' for key, _ in optional):
        optional = [('struct_type', 'Тип структуры')] + optional
    base_columns = list(_REQUIRED_COLUMNS) + optional

    property_map: dict = {}
    for material in materials:
        for mp in material.properties.all():
            property_map[mp.property_id] = mp.property
    properties = sorted(
        property_map.values(),
        key=lambda p: (
            (p.display_name or '').lower(),
            (p.name or '').lower(),
        ),
    )
    property_columns = _property_column_headers(properties)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Материалы'

    headers = (
        [title for _, title in base_columns]
        + [title for _, title in structure_columns]
        + [title for _, title in property_columns]
    )
    ws.append(headers)

    prop_index = {prop_id: idx for idx, (prop_id, _) in enumerate(property_columns)}
    base_width = len(base_columns)
    structure_width = len(structure_columns)

    for material, base_map in zip(materials, base_rows):
        row = (
            [base_map.get(key, '') for key, _ in base_columns]
            + [''] * structure_width
            + [''] * len(property_columns)
        )
        try:
            params = material.get_structure_params()
        except Exception:  # noqa: BLE001 — missing/broken SQL row must not abort export
            params = None
        for offset, (field_name, _) in enumerate(structure_columns):
            field = structure_field_by_name[field_name]
            row[base_width + offset] = _structure_cell_text(field, params)
        for mp in material.properties.all():
            key = str(mp.property_id)
            idx = prop_index.get(key)
            if idx is None:
                continue
            row[base_width + structure_width + idx] = _property_cell_text(mp)
        ws.append(row)

    _style_data_table(ws, row_count=1 + len(materials), col_count=len(headers))

    if truncated:
        meta = wb.create_sheet('Служебно', 0)
        meta.append(['Примечание'])
        meta.append(
            [
                f'Выгружены первые {row_limit} выбранных материалов типа «{structure_type.name}». '
                'Уменьшите выборку и повторите выгрузку.'
            ]
        )

    return wb, len(materials), truncated


def _style_data_table(ws, *, row_count: int, col_count: int) -> None:
    """Black grid + header emphasis so the table reads as a clear block in Excel."""
    if row_count < 1 or col_count < 1:
        return
    for row in ws.iter_rows(min_row=1, max_row=row_count, min_col=1, max_col=col_count):
        for cell in row:
            cell.border = _TABLE_BORDER
            cell.alignment = _CELL_ALIGN
            if cell.row == 1:
                cell.font = _HEADER_FONT
                cell.fill = _HEADER_FILL
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = 'A2'


def materials_xlsx_response(
    queryset: QuerySet,
    *,
    row_limit: int = EXPORT_ROW_LIMIT,
    filename: str | None = None,
    preferred_order: list | None = None,
) -> HttpResponse:
    wb, _count, _truncated = build_materials_workbook(
        queryset,
        row_limit=row_limit,
        preferred_order=preferred_order,
    )
    buffer = BytesIO()
    wb.save(buffer)
    payload = buffer.getvalue()
    if not filename:
        stamp = timezone.localtime().strftime('%Y-%m-%d')
        filename = f'materials_{stamp}.xlsx'
    # ASCII fallback + RFC 5987 for browsers that mishandle quoted UTF-8 names.
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('._') or 'materials.xlsx'
    if not safe_name.lower().endswith('.xlsx'):
        safe_name = f'{safe_name}.xlsx'
    response = HttpResponse(payload, content_type=_XLSX_CONTENT_TYPE)
    # Keep Content-Disposition simple: some proxies/Chrome builds mishandle filename*.
    response['Content-Disposition'] = f'attachment; filename="{safe_name}"'
    response['Content-Length'] = str(len(payload))
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'no-store'
    return response
