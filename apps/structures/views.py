from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    CREATOR_WITH_LABEL_FILTER,
    DEFAULT_CREATOR_FILTER,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
)

from apps.core.creator import creator_label
from apps.materials.picker_data import materials_for_picker
from apps.structures.forms import StructureRecordForm
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import (
    count_linked_materials,
    get_display_values,
    get_row,
    linked_materials_for_record,
    linked_materials_display_label,
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.bookmarks import bookmarked_entity_ids, structure_type_bookmark_entity_id
        from apps.core.models import BookmarkEntityType

        bookmarked_ids = bookmarked_entity_ids(
            user=self.request.user,
            workspace=self.request.active_workspace,
            entity_type=BookmarkEntityType.STRUCTURE_TYPE,
        )
        for structure_type in context.get('types') or []:
            structure_type.bookmark_entity_id = structure_type_bookmark_entity_id(structure_type.code)
            structure_type.is_bookmarked = str(structure_type.bookmark_entity_id) in bookmarked_ids
        context['structure_type_bookmark_entity_type'] = BookmarkEntityType.STRUCTURE_TYPE
        return context


class StructureRecordListView(AppViewMixin, StructureTypeMixin, QuerySetFilterMixin, TemplateView):
    template_name = 'structures/list.html'
    enable_tag_filter = True
    search_fields = (
        'code',
        'name',
        'description',
        'manufacturer__name',
        'availability__name',
        'technology__name',
        'import_source_filename',
    )
    search_scopes = (
        (
            ALL_SEARCH_SCOPE,
            'Везде',
            (
                'code',
                'name',
                'description',
                'manufacturer__name',
                'availability__name',
                'technology__name',
                'import_source_filename',
            ),
        ),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        ('description', 'Описание', ('description',)),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: CREATOR_WITH_LABEL_FILTER,
        }

    def _materials_queryset(self):
        # Only home-workspace materials — shared/published rows from other spaces
        # break tag search and mix unrelated data into the structure matrix.
        from apps.workspaces.services import materials_owned_by

        return self.filter_queryset(
            materials_owned_by(self.request.active_workspace)
            .filter(struct_type=self.structure_type)
            .select_related('manufacturer', 'availability', 'technology', 'created_by_user')
            .order_by('code', 'name')
        )

    def get_context_data(self, **kwargs):
        from apps.structures.materials_grid import build_structure_materials_grid

        context = super().get_context_data(**kwargs)
        page_number = self.request.GET.get('page', 1)
        try:
            page_number = max(int(page_number), 1)
        except (TypeError, ValueError):
            page_number = 1

        materials_qs = self._materials_queryset()
        total = materials_qs.count()
        offset = (page_number - 1) * self.paginate_by
        page_materials = list(materials_qs[offset:offset + self.paginate_by])
        if self.structure_type.is_created:
            grid = build_structure_materials_grid(self.structure_type, page_materials)
        else:
            from apps.structures.materials_grid import structure_data_fields, structure_field_headers

            fields = structure_data_fields(self.structure_type)
            grid = {
                'columns': structure_field_headers(fields),
                'rows': [
                    {
                        'material': material,
                        'structure_record_id': material.struct_props_id,
                        'cells': ['—'] * len(fields),
                    }
                    for material in page_materials
                ],
                'fields': fields,
            }

        num_pages = max((total + self.paginate_by - 1) // self.paginate_by, 1)

        context['materials_grid'] = grid
        context['page_number'] = page_number
        context['num_pages'] = num_pages
        context['total'] = total
        context['has_previous'] = page_number > 1
        context['has_next'] = page_number < num_pages
        context['table_not_created'] = not self.structure_type.is_created
        context.update(self.get_filter_context())
        from apps.core.bookmarks import bookmark_context
        from apps.core.models import BookmarkEntityType

        context.update(
            bookmark_context(
                self.request,
                entity_type=BookmarkEntityType.STRUCTURE_TYPE,
                entity=self.structure_type,
                context_slug=self.structure_type.code,
            )
        )
        from apps.materials.picker_data import materials_for_picker

        context['reference_materials'] = materials_for_picker(self.request.active_workspace)
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
            context['linked_materials'] = linked_materials_for_record(
                self.structure_type,
                record['id'],
                workspace=self.request.active_workspace,
            )
            context['display_label'] = (
                linked_materials_display_label(context['linked_materials'])
                or context['record_label']
            )
            from apps.core.bookmarks import bookmark_context
            from apps.core.models import BookmarkEntityType

            context.update(
                bookmark_context(
                    self.request,
                    entity_type=BookmarkEntityType.STRUCTURE_RECORD,
                    entity={
                        'structure_type': self.structure_type,
                        'record': record,
                    },
                    entity_id=record['id'],
                    context_slug=self.structure_type.code,
                )
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
