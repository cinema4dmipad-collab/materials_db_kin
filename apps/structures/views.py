from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, TemplateView, View

from apps.structures.forms import StructureRecordForm
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import (
    count_linked_materials,
    get_display_values,
    get_row,
    structure_record_label,
)


class StructureTypeMixin:
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(
            StructureType.objects.prefetch_related('fields'),
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


class StructureTypeSelectView(TemplateView):
    template_name = 'structures/select_type.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['types'] = (
            StructureType.objects.filter(is_active=True)
            .prefetch_related('fields')
            .order_by('name')
        )
        return context


class StructureRecordListView(CreatedTableRequiredMixin, TemplateView):
    template_name = 'structures/list.html'

    def _build_records(self, raw_records):
        return [
            {
                'id': record['id'],
                'created_at': record.get('created_at'),
                'label': structure_record_label(record, self.structure_type),
            }
            for record in raw_records
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get('q', '').strip()
        page_number = self.request.GET.get('page', 1)
        try:
            page_number = max(int(page_number), 1)
        except (TypeError, ValueError):
            page_number = 1

        if search_query:
            result = SQLExecutor.get_all(self.structure_type, limit=None, offset=0)
            raw_records = result.get('records', []) if result.get('success') else []
            records = self._build_records(raw_records)
            records = [
                record for record in records
                if search_query.lower() in record['label'].lower()
            ]
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

        pagination_query = self.request.GET.copy()
        pagination_query.pop('page', None)

        context['records'] = records
        context['page_number'] = page_number
        context['num_pages'] = num_pages
        context['total'] = total
        context['has_previous'] = page_number > 1
        context['has_next'] = page_number < num_pages
        context['search_query'] = search_query
        context['search_param'] = 'q'
        context['search_placeholder'] = 'Название или параметры записи...'
        context['list_filters'] = []
        context['has_active_filters'] = bool(search_query)
        context['filter_reset_url'] = self.request.path
        context['pagination_query'] = pagination_query.urlencode()
        return context


class StructureRecordCreateView(CreatedTableRequiredMixin, FormView):
    template_name = 'structures/dynamic_form.html'
    form_class = StructureRecordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['structure_type'] = self.structure_type
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        row_id = form.save()
        messages.success(self.request, 'Запись структуры создана.')
        return redirect(
            'structures:detail',
            type_code=self.structure_type.code,
            pk=row_id,
        )


class StructureRecordDetailView(CreatedTableRequiredMixin, DetailView):
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


class StructureRecordUpdateView(CreatedTableRequiredMixin, FormView):
    template_name = 'structures/dynamic_form.html'
    form_class = StructureRecordForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['structure_type'] = self.structure_type
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
        return context

    def form_valid(self, form):
        row_id = form.save()
        messages.success(self.request, 'Запись сохранена.')
        return redirect(
            'structures:detail',
            type_code=self.structure_type.code,
            pk=row_id,
        )


class StructureRecordDeleteView(CreatedTableRequiredMixin, View):
    template_name = 'structures/confirm_delete.html'

    def get(self, request, type_code, pk):
        record = get_row(self.structure_type, pk)
        if record is None:
            messages.error(request, 'Запись не найдена.')
            return redirect('structures:list', type_code=type_code)

        return self.render(request, record)

    def post(self, request, type_code, pk):
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
