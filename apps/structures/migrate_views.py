"""Wizard: migrate materials between structure types + normalization diagnostics."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.structures.diagnostics import diagnostics_summary, run_structure_normalization_diagnostics
from apps.structures.migrate_service import (
    SESSION_KEY,
    materials_for_structure,
    migrate_materials,
    parse_mapping_from_post,
    suggest_field_mapping,
    supported_fields,
    validate_mapping,
)
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.workspaces.mixins import AppViewMixin, SystemAdminRequiredMixin
from apps.workspaces.services import structure_types_visible_in


def _created_types(request):
    return (
        structure_types_visible_in(request.active_workspace)
        .filter(is_active=True, is_created=True)
        .order_by('name')
    )


class StructureMigrateWizardView(SystemAdminRequiredMixin, AppViewMixin, View):
    """Steps: select → map → confirm → done."""

    template_select = 'structures/migrate_select.html'
    template_map = 'structures/migrate_map.html'
    template_confirm = 'structures/migrate_confirm.html'

    def get(self, request):
        step = request.GET.get('step') or 'select'
        state = request.session.get(SESSION_KEY) or {}
        if step == 'map':
            return self._render_map(request, state)
        if step == 'confirm':
            return self._render_confirm(request, state)
        return self._render_select(request, state)

    def post(self, request):
        action = request.POST.get('action') or 'select'
        if action == 'select':
            return self._post_select(request)
        if action == 'map':
            return self._post_map(request)
        if action == 'confirm':
            return self._post_confirm(request)
        messages.error(request, 'Неизвестное действие.')
        return redirect('structures:migrate')

    def _render_select(self, request, state):
        types = []
        for st in _created_types(request):
            st.material_count = materials_for_structure(st).count()
            types.append(st)
        return render(
            request,
            self.template_select,
            {
                'types': types,
                'source_id': state.get('source_id', ''),
                'target_id': state.get('target_id', ''),
                'step': 'select',
            },
        )

    def _post_select(self, request):
        source = get_object_or_404(_created_types(request), pk=request.POST.get('source_id'))
        target = get_object_or_404(_created_types(request), pk=request.POST.get('target_id'))
        if source.pk == target.pk:
            messages.error(request, 'Выберите разные исходный и целевой типы.')
            return redirect('structures:migrate')
        if not SQLExecutor.table_exists(source) or not SQLExecutor.table_exists(target):
            messages.error(request, 'У обоих типов должна существовать SQL-таблица.')
            return redirect('structures:migrate')

        suggested = suggest_field_mapping(source, target)
        mapping = {row.target.name: row.source_name for row in suggested}
        request.session[SESSION_KEY] = {
            'source_id': str(source.pk),
            'target_id': str(target.pk),
            'mapping': mapping,
        }
        request.session.modified = True
        return redirect(f'{reverse("structures:migrate")}?step=map')

    def _load_pair(self, request, state):
        source_id = state.get('source_id')
        target_id = state.get('target_id')
        if not source_id or not target_id:
            return None, None
        qs = _created_types(request)
        source = qs.filter(pk=source_id).first()
        target = qs.filter(pk=target_id).first()
        return source, target

    def _render_map(self, request, state):
        source, target = self._load_pair(request, state)
        if source is None or target is None:
            messages.warning(request, 'Сначала выберите типы структур.')
            return redirect('structures:migrate')
        mapping = state.get('mapping') or {}
        suggested = suggest_field_mapping(source, target)
        source_by_name = {f.name: f for f in supported_fields(source)}
        rows = []
        for row in suggested:
            source_name = mapping.get(row.target.name, row.source_name)
            source_field = source_by_name.get(source_name)
            rows.append(
                {
                    'target': row.target,
                    'source_name': source_name or '',
                    'source_label': source_field.label if source_field else '',
                    'auto': row.auto and source_name == row.source_name and bool(source_name),
                    'warning': row.warning,
                }
            )
        return render(
            request,
            self.template_map,
            {
                'source': source,
                'target': target,
                'rows': rows,
                'source_fields': supported_fields(source),
                'material_count': materials_for_structure(source).count(),
                'step': 'map',
            },
        )

    def _post_map(self, request):
        state = request.session.get(SESSION_KEY) or {}
        source, target = self._load_pair(request, state)
        if source is None or target is None:
            messages.warning(request, 'Сначала выберите типы структур.')
            return redirect('structures:migrate')
        mapping = parse_mapping_from_post(request.POST, target)
        errors = validate_mapping(source, target, mapping)
        if errors:
            for err in errors:
                messages.error(request, err)
            state['mapping'] = mapping
            request.session[SESSION_KEY] = state
            request.session.modified = True
            return redirect(f'{reverse("structures:migrate")}?step=map')
        state['mapping'] = mapping
        request.session[SESSION_KEY] = state
        request.session.modified = True
        return redirect(f'{reverse("structures:migrate")}?step=confirm')

    def _render_confirm(self, request, state):
        source, target = self._load_pair(request, state)
        if source is None or target is None:
            messages.warning(request, 'Сначала выберите типы структур.')
            return redirect('structures:migrate')
        mapping = state.get('mapping') or {}
        errors = validate_mapping(source, target, mapping)
        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect(f'{reverse("structures:migrate")}?step=map')
        source_by_name = {f.name: f for f in supported_fields(source)}
        map_rows = []
        for field in supported_fields(target):
            src = mapping.get(field.name) or ''
            map_rows.append(
                {
                    'target': field,
                    'source': source_by_name.get(src),
                    'skipped': not src,
                }
            )
        return render(
            request,
            self.template_confirm,
            {
                'source': source,
                'target': target,
                'map_rows': map_rows,
                'material_count': materials_for_structure(source).count(),
                'step': 'confirm',
            },
        )

    def _post_confirm(self, request):
        state = request.session.get(SESSION_KEY) or {}
        source, target = self._load_pair(request, state)
        if source is None or target is None:
            messages.warning(request, 'Сначала выберите типы структур.')
            return redirect('structures:migrate')
        mapping = state.get('mapping') or {}
        delete_source = request.POST.get('delete_source') == 'on'
        try:
            stats = migrate_materials(
                source=source,
                target=target,
                mapping=mapping,
                delete_source=delete_source,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f'{reverse("structures:migrate")}?step=confirm')

        request.session.pop(SESSION_KEY, None)
        request.session.modified = True
        messages.success(
            request,
            (
                f'Перенесено материалов: {stats["migrated"]} '
                f'(«{stats["source_name"]}» → «{stats["target_name"]}»).'
            ),
        )
        if stats.get('skipped_missing_row'):
            messages.warning(
                request,
                f'Без исходной SQL-строки (создана пустая целевая): {stats["skipped_missing_row"]}.',
            )
        if stats.get('deleted_source_type'):
            messages.info(request, f'Исходный тип «{stats["source_name"]}» удалён вместе с таблицей.')
        return redirect('structures:type_manage', type_code=target.code)


class StructureNormalizationDiagnosticsView(SystemAdminRequiredMixin, AppViewMixin, View):
    template_name = 'structures/diagnostics.html'

    def get(self, request):
        issues = run_structure_normalization_diagnostics()
        return render(
            request,
            self.template_name,
            {
                'issues': issues,
                'summary': diagnostics_summary(issues),
            },
        )
