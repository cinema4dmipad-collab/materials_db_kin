"""Repair actions for structure normalization diagnostics."""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.shortcuts import redirect

from apps.materials.models import Material
from apps.structures.decimal_range import (
    decimal_base_column_name,
    decimal_storage_columns,
    legacy_decimal_column_names,
)
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import delete_table_row, get_row, insert_row, load_field_data


REPAIR_UI: dict[str, dict[str, str]] = {
    'rename_column': {
        'title': 'Переименовать колонку',
        'message': 'Переименовать «{old_name}» → «{new_name}» в таблице «{table_name}»?',
        'submit': 'Переименовать',
        'btn_class': 'btn-primary',
    },
    'create_missing_table': {
        'title': 'Создать SQL-таблицу',
        'message': 'Создать таблицу «{table_name}» по текущим полям типа «{structure_name}»?',
        'submit': 'Создать таблицу',
        'btn_class': 'btn-primary',
    },
    'sync_created_flag': {
        'title': 'Подтвердить созданную таблицу',
        'message': 'Пометить тип «{structure_name}» как созданный (таблица «{table_name}» уже в БД)?',
        'submit': 'Подтвердить',
        'btn_class': 'btn-primary',
    },
    'add_missing_column': {
        'title': 'Добавить колонку',
        'message': 'Добавить колонку поля «{field_name}» в таблицу «{table_name}»?',
        'submit': 'Добавить колонку',
        'btn_class': 'btn-primary',
    },
    'drop_orphan_column': {
        'title': 'Удалить лишнюю колонку',
        'message': 'Удалить колонку «{column_name}» из «{table_name}»? Данные в колонке будут потеряны.',
        'submit': 'Удалить колонку',
        'btn_class': 'btn-danger',
    },
    'create_material_structure_row': {
        'title': 'Создать строку параметров',
        'message': 'Создать новую SQL-строку для материала «{material_code}» и привязать к карточке?',
        'submit': 'Создать строку',
        'btn_class': 'btn-primary',
    },
    'clear_struct_props_id': {
        'title': 'Очистить ссылку на строку',
        'message': 'Очистить struct_props_id у материала «{material_code}» (тип структуры не задан)?',
        'submit': 'Очистить ссылку',
        'btn_class': 'btn-warning',
    },
    'split_shared_structure_row': {
        'title': 'Разделить общую SQL-строку',
        'message': 'Скопировать параметры в отдельные строки для остальных материалов ({material_codes})?',
        'submit': 'Разделить',
        'btn_class': 'btn-primary',
    },
    'delete_orphan_sql_rows': {
        'title': 'Удалить строки без материалов',
        'message': 'Удалить {orphan_count} SQL-строк(и) типа «{structure_name}» без привязки к материалам?',
        'submit': 'Удалить строки',
        'btn_class': 'btn-danger',
    },
}


def build_repair(action: str, **params) -> dict:
    ui = REPAIR_UI[action]
    context = {
        'structure_name': params.get('structure_name', ''),
        'table_name': params.get('table_name', ''),
        'field_name': params.get('field_name', ''),
        'column_name': params.get('column_name', ''),
        'old_name': params.get('old_name', ''),
        'new_name': params.get('new_name', ''),
        'material_code': params.get('material_code', ''),
        'material_codes': params.get('material_codes', ''),
        'orphan_count': params.get('orphan_count', ''),
    }
    return {
        'action': action,
        **params,
        'confirm_title': ui['title'],
        'confirm_message': ui['message'].format(**context),
        'submit_label': ui['submit'],
        'submit_class': ui.get('btn_class', 'btn-primary'),
    }


def _structure_type(code: str) -> StructureType | None:
    if not code:
        return None
    return StructureType.objects.filter(code=code).prefetch_related('fields').first()


def _material_by_code(code: str) -> Material | None:
    if not code:
        return None
    return Material.objects.filter(code=code).select_related('struct_type').first()


def repair_rename_column(request) -> redirect:
    code = (request.POST.get('structure_code') or '').strip()
    old_name = (request.POST.get('old_name') or '').strip()
    new_name = (request.POST.get('new_name') or '').strip()
    st = _structure_type(code)
    if st is None:
        messages.error(request, f'Тип структуры «{code}» не найден.')
        return redirect('structures:diagnostics')
    if not st.fields.filter(name=new_name).exists():
        messages.error(
            request,
            f'В метаданных «{st.name}» нет поля «{new_name}» — переименование отменено.',
        )
        return redirect('structures:diagnostics')
    if st.fields.filter(name=old_name).exists():
        messages.error(
            request,
            f'В метаданных ещё есть поле «{old_name}» — сначала уберите конфликт имён.',
        )
        return redirect('structures:diagnostics')

    result = SQLExecutor.rename_column(st, old_name, new_name)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось переименовать колонку.')
    else:
        renamed = ', '.join(result.get('renamed') or [])
        messages.success(request, f'«{st.name}»: колонки переименованы ({renamed}).')
    return redirect('structures:diagnostics')


def repair_create_missing_table(request) -> redirect:
    st = _structure_type((request.POST.get('structure_code') or '').strip())
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    result = SQLExecutor.create_missing_table(st)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось создать таблицу.')
    else:
        messages.success(request, f'Таблица «{st.table_name}» создана.')
    return redirect('structures:diagnostics')


def repair_sync_created_flag(request) -> redirect:
    st = _structure_type((request.POST.get('structure_code') or '').strip())
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    result = SQLExecutor.sync_created_flag(st)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось подтвердить таблицу.')
    else:
        messages.success(request, f'Тип «{st.name}» помечен как созданный.')
    return redirect('structures:diagnostics')


def repair_add_missing_column(request) -> redirect:
    code = (request.POST.get('structure_code') or '').strip()
    field_name = (request.POST.get('field_name') or '').strip()
    st = _structure_type(code)
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    field = st.fields.filter(name=field_name).first()
    if field is None:
        messages.error(request, f'Поле «{field_name}» не найдено в типе «{st.name}».')
        return redirect('structures:diagnostics')
    if field.field_type == 'ForeignKey':
        messages.error(request, 'ForeignKey не хранится в SQL-таблице.')
        return redirect('structures:diagnostics')
    result = SQLExecutor.add_column(st, field)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось добавить колонку.')
    else:
        messages.success(request, f'«{st.name}»: колонка «{field_name}» добавлена.')
    return redirect('structures:diagnostics')


def repair_drop_orphan_column(request) -> redirect:
    code = (request.POST.get('structure_code') or '').strip()
    column_name = (request.POST.get('column_name') or '').strip()
    st = _structure_type(code)
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    result = SQLExecutor.drop_column(st, column_name)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось удалить колонку.')
    else:
        dropped = ', '.join(result.get('dropped') or [column_name])
        messages.success(request, f'«{st.name}»: удалены колонки ({dropped}).')
    return redirect('structures:diagnostics')


def _default_structure_row_payload(st: StructureType, material: Material) -> dict:
    payload: dict = {}
    for field in st.fields.exclude(field_type='ForeignKey'):
        default = (field.default_value or '').strip()
        if default:
            payload[field.name] = default
        elif field.is_required and field.field_type == 'CharField':
            payload[field.name] = (material.name or material.code)[: field.max_length or 255]
    return payload


def repair_create_material_structure_row(request) -> redirect:
    material = _material_by_code((request.POST.get('material_code') or '').strip())
    if material is None:
        messages.error(request, 'Материал не найден.')
        return redirect('structures:diagnostics')
    st = material.struct_type
    if st is None or not st.is_created or not SQLExecutor.table_exists(st):
        messages.error(request, f'У материала «{material.code}» нет рабочей таблицы структуры.')
        return redirect('structures:diagnostics')
    try:
        row_id = insert_row(
            st,
            material.code,
            _default_structure_row_payload(st, material),
            created_by=getattr(material, 'created_by', '') or '',
            allow_empty_null=True,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('structures:diagnostics')
    material.struct_props_id = row_id
    material.save(update_fields=['struct_props_id', 'updated_at'])
    messages.success(
        request,
        f'Материал «{material.code}»: создана строка параметров ({row_id}).',
    )
    return redirect('structures:diagnostics')


def repair_clear_struct_props_id(request) -> redirect:
    material = _material_by_code((request.POST.get('material_code') or '').strip())
    if material is None:
        messages.error(request, 'Материал не найден.')
        return redirect('structures:diagnostics')
    if material.struct_type_id:
        messages.error(
            request,
            f'У «{material.code}» задан тип структуры — очистка ссылки отменена.',
        )
        return redirect('structures:diagnostics')
    material.struct_props_id = None
    material.save(update_fields=['struct_props_id', 'updated_at'])
    messages.success(request, f'Материал «{material.code}»: ссылка на строку очищена.')
    return redirect('structures:diagnostics')


def repair_split_shared_structure_row(request) -> redirect:
    code = (request.POST.get('structure_code') or '').strip()
    row_id_raw = (request.POST.get('row_id') or '').strip()
    st = _structure_type(code)
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    try:
        row_id = uuid.UUID(row_id_raw)
    except ValueError:
        messages.error(request, 'Некорректный идентификатор строки.')
        return redirect('structures:diagnostics')

    materials = list(
        Material.objects.filter(struct_type=st, struct_props_id=row_id).order_by('code')
    )
    if len(materials) < 2:
        messages.info(request, 'Общая строка уже разделена.')
        return redirect('structures:diagnostics')

    source_row = get_row(st, row_id)
    if source_row is None:
        messages.error(request, 'Исходная SQL-строка не найдена.')
        return redirect('structures:diagnostics')

    payload = load_field_data(st, row_id)
    split = 0
    for material in materials[1:]:
        try:
            new_id = insert_row(
                st,
                material.code,
                payload,
                created_by=getattr(material, 'created_by', '') or '',
                allow_empty_null=True,
            )
        except ValueError as exc:
            messages.error(request, f'«{material.code}»: {exc}')
            return redirect('structures:diagnostics')
        material.struct_props_id = new_id
        material.save(update_fields=['struct_props_id', 'updated_at'])
        split += 1

    messages.success(
        request,
        f'«{st.name}»: для {split} материал(ов) созданы отдельные SQL-строки.',
    )
    return redirect('structures:diagnostics')


def repair_delete_orphan_sql_rows(request) -> redirect:
    st = _structure_type((request.POST.get('structure_code') or '').strip())
    if st is None:
        messages.error(request, 'Тип структуры не найден.')
        return redirect('structures:diagnostics')
    if not st.is_created or not SQLExecutor.table_exists(st):
        messages.error(request, 'Таблица структуры недоступна.')
        return redirect('structures:diagnostics')

    result = SQLExecutor.get_all(st, limit=None)
    if not result.get('success'):
        messages.error(request, result.get('error') or 'Не удалось прочитать таблицу.')
        return redirect('structures:diagnostics')

    linked_ids = {
        str(pk)
        for pk in Material.objects.filter(struct_type=st).exclude(
            struct_props_id=None
        ).values_list('struct_props_id', flat=True)
    }
    deleted = 0
    for record in result.get('records') or []:
        record_id = str(record.get('id') or '')
        if not record_id or record_id in linked_ids:
            continue
        try:
            delete_table_row(st, uuid.UUID(record_id))
            deleted += 1
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('structures:diagnostics')

    if deleted:
        messages.success(request, f'«{st.name}»: удалено строк без материалов: {deleted}.')
    else:
        messages.info(request, 'Строк без материалов не осталось.')
    return redirect('structures:diagnostics')


REPAIR_HANDLERS = {
    'rename_column': repair_rename_column,
    'create_missing_table': repair_create_missing_table,
    'sync_created_flag': repair_sync_created_flag,
    'add_missing_column': repair_add_missing_column,
    'drop_orphan_column': repair_drop_orphan_column,
    'create_material_structure_row': repair_create_material_structure_row,
    'clear_struct_props_id': repair_clear_struct_props_id,
    'split_shared_structure_row': repair_split_shared_structure_row,
    'delete_orphan_sql_rows': repair_delete_orphan_sql_rows,
}


def execute_repair(request):
    action = (request.POST.get('action') or '').strip()
    handler = REPAIR_HANDLERS.get(action)
    if handler is None:
        messages.error(request, 'Неизвестное действие диагностики.')
        return redirect('structures:diagnostics')
    return handler(request)


def field_name_for_sql_column(st: StructureType, column_name: str) -> str | None:
    """Resolve StructureField.name for a missing SQL column label."""
    if st.fields.filter(name=column_name).exists():
        return column_name
    base = decimal_base_column_name(column_name)
    if base and st.fields.filter(name=base).exists():
        return base
    return None


def structure_repair_context(st: StructureType) -> dict:
    return {
        'structure_code': st.code,
        'structure_name': st.name,
        'table_name': st.table_name,
    }
