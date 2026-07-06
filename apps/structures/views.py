from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from apps.core.list_filters import ALL_SEARCH_SCOPE, CREATOR_SEARCH_SCOPE, DEFAULT_CREATOR_FILTER, QuerySetFilterMixin

from apps.core.creator import creator_label
from apps.materials.picker_data import materials_for_picker
from apps.structures.forms import StructureRecordForm
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import (
    count_linked_materials,
    get_display_values,
    get_row,
    structure_record_label,
)
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.permissions import can_edit_structure_records
from apps.workspaces.services import structure_types_visible_in


class StructureTypeMixin:
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(
            structure_types_visible_in(request.active_workspace).prefetch_related('fields'),
            code=kwargs['type_code'],
            is_active=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        return context


class CreatedTableRequiredMixin(StructureTypeMixin):
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not self.structure_type.is_created:
            messages.error(
                request,
                f'Таблица для типа «{self.structure_type.name}» ещё не создана. '
                f'Создайте SQL-таблицу на странице управления типом.',
            )
            return redirect('structures:type_manage', type_code=self.structure_type.code)
        return response


class StructureTypeSelectView(AppViewMixin, QuerySetFilterMixin, ListView):
    template_name = 'structures/select_type.html'
    context_object_name = 'types'
    search_fields = ('name', 'code', 'description', 'table_name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('name', 'code', 'description', 'table_name')),
        ('name', 'Название', ('name',)),
        ('code', 'Код', ('code',)),
        ('description', 'Описание', ('description',)),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
    )
    search_placeholder = 'Введите текст для поиска...'

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: DEFAULT_CREATOR_FILTER,
        }

    def get_queryset(self):
        return self.filter_queryset(
            structure_types_visible_in(self.request.active_workspace)
            .prefetch_related('fields')
            .select_related('created_by_user')
            .order_by('name')
        )


class StructureRecordListView(AppViewMixin, CreatedTableRequiredMixin, QuerySetFilterMixin, TemplateView):
    template_name = 'structures/list.html'
    search_fields = ('label',)
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('label',)),
        ('label', 'Название', ('label',)),
    )
    search_placeholder = 'Введите текст для поиска...'

    def _build_records(self, raw_records):
        return [
            {
                'id': record['id'],
                'created_at': record.get('created_at'),
                'created_by': record.get('created_by') or '',
                'label': structure_record_label(record, self.structure_type),
            }
            for record in raw_records
        ]

    def _filter_records(self, records, query, active_scopes):
        if not query:
            return records
        if active_scopes and 'label' not in active_scopes:
            return records
        query_lower = query.lower()
        return [
            record for record in records
            if query_lower in record['label'].lower()
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get(self.search_param, '').strip()
        active_scopes = self._get_active_search_scope_values()
        page_number = self.request.GET.get('page', 1)
        try:
            page_number = max(int(page_number), 1)
        except (TypeError, ValueError):
            page_number = 1

        if search_query:
            result = SQLExecutor.get_all(self.structure_type, limit=None, offset=0)
            raw_records = result.get('records', []) if result.get('success') else []
            records = self._build_records(raw_records)
            records = self._filter_records(records, search_query, active_scopes)
            total = len(records)
            offset = (page_number - 1) * self.paginate_by
            records = records[offset:offset + self.paginate_by]
        else:
            offset = (page_number - 1) * self.paginate_by
            result = SQLExecutor.get_all(
                self.structure_type,
                limit=self.paginate_by,
                offset=offset,
            )
            records = self._build_records(result.get('records', []) if result.get('success') else [])
            total = result.get('total', 0) if result.get('success') else 0

        num_pages = max((total + self.paginate_by - 1) // self.paginate_by, 1)

        context['records'] = records
        context['page_number'] = page_number
        context['num_pages'] = num_pages
        context['total'] = total
        context['has_previous'] = page_number > 1
        context['has_next'] = page_number < num_pages
        context.update(self.get_filter_context())
        return context


class StructureRecordCreateView(AppViewMixin, CreatedTableRequiredMixin, FormView):
    template_name = 'structures/dynamic_form.html'
    form_class = StructureRecordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['structure_type'] = self.structure_type
        kwargs['workspace'] = self.request.active_workspace
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        context['reference_materials'] = materials_for_picker(self.request.active_workspace)
        return context

    def form_valid(self, form):
        if not can_edit_structure_records(
            self.request.user, self.structure_type, self.request.active_workspace
        ):
            raise PermissionDenied
        row_id = form.save(created_by=creator_label(self.request.user))
        messages.success(self.request, 'Запись структуры создана.')
        return redirect(
            'structures:detail',
            type_code=self.structure_type.code,
            pk=row_id,
        )


class StructureRecordDetailView(AppViewMixin, CreatedTableRequiredMixin, DetailView):
    template_name = 'structures/detail.html'
    context_object_name = 'record'

    def get_object(self):
        record = get_row(self.structure_type, self.kwargs['pk'])
        if not record:
            raise Http404('Запись не найдена.')
        return record

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = context.get('object')
        if record:
            context['record_label'] = structure_record_label(record, self.structure_type)
            context['display_values'] = get_display_values(self.structure_type, record['id'])
            context['linked_materials_count'] = count_linked_materials(
                self.structure_type,
                record['id'],
            )
        return context


class StructureRecordUpdateView(AppViewMixin, CreatedTableRequiredMixin, FormView):
    template_name = 'structures/dynamic_form.html'
    form_class = StructureRecordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['structure_type'] = self.structure_type
        kwargs['workspace'] = self.request.active_workspace
        record = get_row(self.structure_type, self.kwargs['pk'])
        if record is None:
            raise Http404('Запись не найдена.')
        kwargs['record'] = record
        self.record = record
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        context['record'] = self.record
        context['record_label'] = structure_record_label(self.record, self.structure_type)
        context['reference_materials'] = materials_for_picker(self.request.active_workspace)
        return context

    def form_valid(self, form):
        if not can_edit_structure_records(
            self.request.user, self.structure_type, self.request.active_workspace
        ):
            raise PermissionDenied
        row_id = form.save()
        messages.success(self.request, 'Запись сохранена.')
        return redirect(
            'structures:detail',
            type_code=self.structure_type.code,
            pk=row_id,
        )


class StructureRecordDeleteView(AppViewMixin, CreatedTableRequiredMixin, View):
    template_name = 'structures/confirm_delete.html'

    def get(self, request, type_code, pk):
        record = get_row(self.structure_type, pk)
        if record is None:
            messages.error(request, 'Запись не найдена.')
            return redirect('structures:list', type_code=type_code)

        return self.render(request, record)

    def post(self, request, type_code, pk):
        if not can_edit_structure_records(
            request.user, self.structure_type, request.active_workspace
        ):
            raise PermissionDenied
        record = get_row(self.structure_type, pk)
        if record is None:
            messages.error(request, 'Запись не найдена.')
            return redirect('structures:list', type_code=type_code)

        if count_linked_materials(self.structure_type, pk):
            messages.error(
                request,
                'Нельзя удалить запись: она используется в карточках материалов.',
            )
            return redirect(
                'structures:detail',
                type_code=type_code,
                pk=pk,
            )

        result = SQLExecutor.delete(self.structure_type, pk)
        if not result['success']:
            messages.error(request, result.get('error') or 'Не удалось удалить запись.')
            return redirect(
                'structures:detail',
                type_code=type_code,
                pk=pk,
            )

        messages.success(request, 'Запись удалена.')
        return redirect('structures:list', type_code=type_code)

    def render(self, request, record):
        from django.shortcuts import render

        context = {
            'structure_type': self.structure_type,
            'record': record,
            'record_label': structure_record_label(record, self.structure_type),
            'linked_materials_count': count_linked_materials(self.structure_type, record['id']),
        }
        return render(request, self.template_name, context)
