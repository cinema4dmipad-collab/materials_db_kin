"""Integrity / normalization diagnostics for structure tables and material links."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from apps.materials.models import Material
from apps.references.models import Property
from apps.structures.decimal_range import (
    decimal_base_column_name,
    decimal_storage_columns,
    is_decimal_companion_column,
    legacy_decimal_column_names,
)
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import SERVICE_COLUMNS, get_row


SEVERITY_ERROR = 'error'
SEVERITY_WARNING = 'warning'
SEVERITY_INFO = 'info'


@dataclass
class DiagnosticIssue:
    code: str
    severity: str
    title: str
    detail: str
    structure_code: str = ''
    material_code: str = ''
    count: int = 1
    repair: dict = dc_field(default_factory=dict)


def _expected_columns(structure_type: StructureType) -> set[str]:
    expected = set(SERVICE_COLUMNS)
    for fld in structure_type.fields.exclude(field_type='ForeignKey'):
        if fld.field_type == 'DecimalField':
            expected.update(decimal_storage_columns(fld.name))
            expected.update(legacy_decimal_column_names(fld.name))
        else:
            expected.add(fld.name)
    return expected


def _orphan_base_columns(physical: set[str], expected: set[str]) -> list[str]:
    orphans = []
    for col in sorted(physical - expected):
        if col in SERVICE_COLUMNS:
            continue
        if is_decimal_companion_column(col):
            base = decimal_base_column_name(col)
            # Companion of an expected base is not an orphan base column.
            if base and base in expected:
                continue
            # Companion of an orphan base — skip here; base reported separately.
            continue
        orphans.append(col)
    return orphans


def run_structure_normalization_diagnostics(
    *,
    limit_per_check: int = 50,
) -> list[DiagnosticIssue]:
    """Scan all structure types and materials for link / schema integrity issues."""
    issues: list[DiagnosticIssue] = []
    types = list(StructureType.objects.prefetch_related('fields').order_by('name'))
    property_names = set(Property.objects.values_list('name', flat=True))

    for st in types:
        table_exists = SQLExecutor.table_exists(st)
        if st.is_created and not table_exists:
            issues.append(
                DiagnosticIssue(
                    code='flag_table_drift_missing',
                    severity=SEVERITY_ERROR,
                    title='Флаг is_created, таблицы нет',
                    detail=(
                        f'Тип «{st.name}» помечен как созданный, но таблицы '
                        f'«{st.table_name}» в БД нет.'
                    ),
                    structure_code=st.code,
                )
            )
        elif (not st.is_created) and table_exists:
            issues.append(
                DiagnosticIssue(
                    code='flag_table_drift_orphan_table',
                    severity=SEVERITY_WARNING,
                    title='Таблица есть, флаг is_created=False',
                    detail=(
                        f'Таблица «{st.table_name}» существует, но тип «{st.name}» '
                        'не помечен как созданный.'
                    ),
                    structure_code=st.code,
                )
            )

        if not table_exists:
            continue

        expected = _expected_columns(st)
        physical = set(SQLExecutor.list_column_names(st))
        missing_fields: list[str] = []
        for fld in st.fields.exclude(field_type='ForeignKey'):
            if fld.field_type == 'DecimalField':
                for col in decimal_storage_columns(fld.name):
                    if col not in physical:
                        issues.append(
                            DiagnosticIssue(
                                code='missing_decimal_column',
                                severity=SEVERITY_ERROR,
                                title='Нет колонки DecimalField',
                                detail=f'«{st.name}»: отсутствует колонка «{col}».',
                                structure_code=st.code,
                            )
                        )
                if fld.name not in physical:
                    missing_fields.append(fld.name)
            elif fld.name not in physical:
                missing_fields.append(fld.name)
                issues.append(
                    DiagnosticIssue(
                        code='missing_column',
                        severity=SEVERITY_ERROR,
                        title='Нет колонки поля',
                        detail=(
                            f'«{st.name}»: поле «{fld.name}» есть в метаданных, '
                            'колонки в таблице нет.'
                        ),
                        structure_code=st.code,
                    )
                )

            if fld.name and fld.name not in property_names:
                issues.append(
                    DiagnosticIssue(
                        code='field_without_catalog_property',
                        severity=SEVERITY_WARNING,
                        title='Нет свойства в справочнике',
                        detail=(
                            f'«{st.name}»: поле «{fld.name}» не найдено в справочнике '
                            'свойств (по коду). Колонка структуры может работать, '
                            'но синхронизация/внешние клиенты могут считать тип '
                            'невалидным.'
                        ),
                        structure_code=st.code,
                    )
                )

        orphan_bases = _orphan_base_columns(physical, expected)
        for col in orphan_bases:
            issues.append(
                DiagnosticIssue(
                    code='orphan_sql_column',
                    severity=SEVERITY_WARNING,
                    title='Лишняя SQL-колонка',
                    detail=(
                        f'«{st.name}»: колонка «{col}» есть в таблице, но нет поля '
                        'в метаданных (возможное переименование без ALTER TABLE).'
                    ),
                    structure_code=st.code,
                )
            )

        # Suggest rename when one metadata field is missing and one orphan base remains.
        if len(missing_fields) == 1 and len(orphan_bases) == 1:
            old_name, new_name = orphan_bases[0], missing_fields[0]
            issues.append(
                DiagnosticIssue(
                    code='rename_column_suggested',
                    severity=SEVERITY_ERROR,
                    title='Похоже на переименование без таблицы',
                    detail=(
                        f'«{st.name}»: в метаданных «{new_name}», в таблице осталась '
                        f'«{old_name}». Можно переименовать колонку SQL.'
                    ),
                    structure_code=st.code,
                    repair={
                        'action': 'rename_column',
                        'structure_code': st.code,
                        'old_name': old_name,
                        'new_name': new_name,
                    },
                )
            )

    # Material link integrity
    half_type = Material.objects.filter(struct_type__isnull=False, struct_props_id__isnull=True)
    half_props = Material.objects.filter(struct_type__isnull=True, struct_props_id__isnull=False)
    for material in half_type[:limit_per_check]:
        issues.append(
            DiagnosticIssue(
                code='half_link_type_only',
                severity=SEVERITY_ERROR,
                title='Материал с типом без строки структуры',
                detail=f'{material.code}: struct_type задан, struct_props_id пуст.',
                material_code=material.code,
                structure_code=getattr(material.struct_type, 'code', '') or '',
            )
        )
    if half_type.count() > limit_per_check:
        issues.append(
            DiagnosticIssue(
                code='half_link_type_only_more',
                severity=SEVERITY_ERROR,
                title='Ещё материалы без struct_props_id',
                detail=f'Всего: {half_type.count()}.',
                count=half_type.count(),
            )
        )

    for material in half_props[:limit_per_check]:
        issues.append(
            DiagnosticIssue(
                code='half_link_props_only',
                severity=SEVERITY_ERROR,
                title='struct_props_id без типа структуры',
                detail=f'{material.code}: struct_props_id задан, struct_type пуст.',
                material_code=material.code,
            )
        )

    # Orphan / missing SQL rows + shared rows
    linked = (
        Material.objects.filter(struct_type__isnull=False, struct_props_id__isnull=False)
        .select_related('struct_type')
        .order_by('code')
    )
    shared_keys: dict[tuple, list[str]] = {}
    missing_rows = 0
    for material in linked.iterator(chunk_size=200):
        st = material.struct_type
        key = (st.pk, str(material.struct_props_id))
        shared_keys.setdefault(key, []).append(material.code)
        if not st.is_created or not SQLExecutor.table_exists(st):
            issues.append(
                DiagnosticIssue(
                    code='material_points_to_missing_table',
                    severity=SEVERITY_ERROR,
                    title='Материал ссылается на отсутствующую таблицу',
                    detail=f'{material.code} → тип «{st.name}».',
                    material_code=material.code,
                    structure_code=st.code,
                )
            )
            continue
        row = get_row(st, material.struct_props_id)
        if row is None:
            missing_rows += 1
            if missing_rows <= limit_per_check:
                issues.append(
                    DiagnosticIssue(
                        code='orphan_struct_props_id',
                        severity=SEVERITY_ERROR,
                        title='Нет строки структуры для материала',
                        detail=(
                            f'{material.code}: struct_props_id={material.struct_props_id} '
                            f'не найден в «{st.table_name}».'
                        ),
                        material_code=material.code,
                        structure_code=st.code,
                    )
                )

    if missing_rows > limit_per_check:
        issues.append(
            DiagnosticIssue(
                code='orphan_struct_props_id_more',
                severity=SEVERITY_ERROR,
                title='Ещё потерянные строки структуры',
                detail=f'Всего отсутствующих строк: {missing_rows}.',
                count=missing_rows,
            )
        )

    shared_count = 0
    for (_st_pk, _row_id), codes in shared_keys.items():
        if len(codes) < 2:
            continue
        shared_count += 1
        if shared_count <= limit_per_check:
            issues.append(
                DiagnosticIssue(
                    code='shared_struct_row',
                    severity=SEVERITY_WARNING,
                    title='Несколько материалов на одну SQL-строку',
                    detail='Коды: ' + ', '.join(codes[:10]),
                    count=len(codes),
                )
            )
    if shared_count > limit_per_check:
        issues.append(
            DiagnosticIssue(
                code='shared_struct_row_more',
                severity=SEVERITY_WARNING,
                title='Ещё общие SQL-строки',
                detail=f'Всего групп: {shared_count}.',
                count=shared_count,
            )
        )

    # Orphan SQL rows (no material)
    for st in types:
        if not st.is_created or not SQLExecutor.table_exists(st):
            continue
        result = SQLExecutor.get_all(st, limit=None)
        if not result['success']:
            issues.append(
                DiagnosticIssue(
                    code='scan_failed',
                    severity=SEVERITY_WARNING,
                    title='Не удалось прочитать таблицу',
                    detail=f'«{st.name}»: {result.get("error")}',
                    structure_code=st.code,
                )
            )
            continue
        linked_ids = {
            str(pk)
            for pk in Material.objects.filter(struct_type=st).exclude(
                struct_props_id=None
            ).values_list('struct_props_id', flat=True)
        }
        orphan_rows = [
            rec for rec in result.get('records') or []
            if str(rec.get('id') or '') not in linked_ids
        ]
        if orphan_rows:
            sample = ', '.join(str(r.get('id'))[:8] for r in orphan_rows[:5])
            issues.append(
                DiagnosticIssue(
                    code='orphan_sql_rows',
                    severity=SEVERITY_WARNING,
                    title='SQL-строки без материалов',
                    detail=(
                        f'«{st.name}»: {len(orphan_rows)} строк(и) без ссылок '
                        f'(примеры id: {sample}…).'
                    ),
                    structure_code=st.code,
                    count=len(orphan_rows),
                )
            )

    # Deletion / PROTECT sanity notes (informational)
    issues.append(
        DiagnosticIssue(
            code='deletion_rules_ok',
            severity=SEVERITY_INFO,
            title='Правила удаления (нормализация)',
            detail=(
                'Material.struct_type → PROTECT (тип нельзя удалить, пока есть материалы); '
                'черновик типа удаляется только без материалов; drop table не очищает '
                'ссылки материалов автоматически; Sample → CASCADE от Material; '
                'CompositeLayer.material → PROTECT.'
            ),
        )
    )

    # Sort: errors first
    order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
    issues.sort(key=lambda i: (order.get(i.severity, 9), i.code, i.structure_code))
    return issues


def diagnostics_summary(issues: list[DiagnosticIssue]) -> dict:
    return {
        'errors': sum(1 for i in issues if i.severity == SEVERITY_ERROR),
        'warnings': sum(1 for i in issues if i.severity == SEVERITY_WARNING),
        'info': sum(1 for i in issues if i.severity == SEVERITY_INFO),
        'total': len(issues),
    }
