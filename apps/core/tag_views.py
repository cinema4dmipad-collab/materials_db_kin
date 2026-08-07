from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.bulk import parse_bulk_ids
from apps.core.context_processors import invalidate_all_tag_suggestions_cache, invalidate_tag_suggestions_cache
from apps.core.creator import assign_creator
from apps.core.forms import TagForm
from apps.core.list_filters import QuerySetFilterMixin, CREATOR_SEARCH_SCOPE, DEFAULT_CREATOR_FILTER
from apps.core.models import Tag
from apps.workspaces.mixins import AppViewMixin, PermissionRequiredMixin
from apps.workspaces.permissions import (
    WorkspacePerm,
    can_manage_global_tags,
    can_manage_tag,
    has_workspace_perm,
)
from apps.workspaces.services import tags_in_workspace

TAG_SCOPE_WORKSPACE = 'workspace'
TAG_SCOPE_GLOBAL = 'global'
TAG_SCOPE_CHOICES = (TAG_SCOPE_WORKSPACE, TAG_SCOPE_GLOBAL)
TAG_ARCHIVE_ACTIVE = 'active'
TAG_ARCHIVE_ARCHIVED = 'archived'
TAG_ARCHIVE_CHOICES = (TAG_ARCHIVE_ACTIVE, TAG_ARCHIVE_ARCHIVED)


class TagListView(AppViewMixin, PermissionRequiredMixin, QuerySetFilterMixin, ListView):
    permission_codename = WorkspacePerm.TAG_VIEW
    model = Tag
    template_name = 'core/tag_list.html'
    context_object_name = 'tags'
    paginate_by = 30
    search_fields = ('name',)
    search_scopes = (
        ('', 'Везде', ('name',)),
        ('name', 'Название', ('name',)),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
    )
    search_placeholder = 'Поиск по названию...'

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: DEFAULT_CREATOR_FILTER,
        }

    def get_tag_scope(self):
        scope = self.request.GET.get('scope', TAG_SCOPE_WORKSPACE)
        if scope not in TAG_SCOPE_CHOICES:
            return TAG_SCOPE_WORKSPACE
        return scope

    def get_archive_filter(self):
        archive = self.request.GET.get('archive', TAG_ARCHIVE_ACTIVE)
        if archive not in TAG_ARCHIVE_CHOICES:
            return TAG_ARCHIVE_ACTIVE
        return archive

    def get_scope_url(self, scope, archive=None):
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == TAG_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
        archive = archive if archive is not None else self.get_archive_filter()
        if archive == TAG_ARCHIVE_ACTIVE:
            params.pop('archive', None)
        else:
            params['archive'] = archive
        query = params.urlencode()
        return reverse('core:tag_list') + (f'?{query}' if query else '')

    def get_archive_url(self, archive):
        return self.get_scope_url(self.get_tag_scope(), archive=archive)

    def get_queryset(self):
        workspace = self.request.active_workspace
        scope = self.get_tag_scope()
        archive = self.get_archive_filter()
        if scope == TAG_SCOPE_GLOBAL:
            base_qs = Tag.objects.filter(workspace__isnull=True)
        else:
            base_qs = Tag.objects.filter(workspace=workspace)
        if archive == TAG_ARCHIVE_ARCHIVED:
            base_qs = base_qs.filter(is_archived=True)
        else:
            base_qs = base_qs.filter(is_archived=False)
        return self.filter_queryset(
            base_qs.annotate(
                material_count=Count('materials', distinct=True),
                sample_count=Count('samples', distinct=True),
                scan_count=Count('scans', distinct=True),
            )
            .select_related('created_by_user')
            .order_by('name')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workspace = self.request.active_workspace
        user = self.request.user
        scope = self.get_tag_scope()
        archive = self.get_archive_filter()
        context['tag_scope'] = scope
        context['tag_archive'] = archive
        context['tag_scope_tabs'] = [
            {
                'key': TAG_SCOPE_WORKSPACE,
                'label': 'Пространство',
                'url': self.get_scope_url(TAG_SCOPE_WORKSPACE),
            },
            {
                'key': TAG_SCOPE_GLOBAL,
                'label': 'Общие',
                'url': self.get_scope_url(TAG_SCOPE_GLOBAL),
            },
        ]
        context['tag_archive_tabs'] = [
            {
                'key': TAG_ARCHIVE_ACTIVE,
                'label': 'Активные',
                'url': self.get_archive_url(TAG_ARCHIVE_ACTIVE),
            },
            {
                'key': TAG_ARCHIVE_ARCHIVED,
                'label': 'Архив',
                'url': self.get_archive_url(TAG_ARCHIVE_ARCHIVED),
            },
        ]
        preserve = []
        if scope != TAG_SCOPE_WORKSPACE:
            preserve.append(('scope', scope))
        if archive != TAG_ARCHIVE_ACTIVE:
            preserve.append(('archive', archive))
        context['list_filter_preserve_params'] = preserve
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == TAG_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
        if archive == TAG_ARCHIVE_ACTIVE:
            params.pop('archive', None)
        else:
            params['archive'] = archive
        context['pagination_query'] = params.urlencode()
        context['can_create_workspace_tag'] = has_workspace_perm(
            user, workspace, WorkspacePerm.TAG_CREATE
        )
        context['can_manage_global_tags'] = can_manage_global_tags(user, workspace)
        context['show_create_button'] = (
            scope == TAG_SCOPE_GLOBAL and can_manage_global_tags(user, workspace)
        ) or (scope == TAG_SCOPE_WORKSPACE and context['can_create_workspace_tag'])
        context['manageable_tag_ids'] = {
            tag.pk for tag in context['tags'] if can_manage_tag(user, tag, workspace)
        }
        return context


class TagCreateView(AppViewMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'core/tag_form.html'
    success_url = reverse_lazy('core:tag_list')

    def dispatch(self, request, *args, **kwargs):
        workspace = request.active_workspace
        can_create_workspace = has_workspace_perm(request.user, workspace, WorkspacePerm.TAG_CREATE)
        if not can_create_workspace and not can_manage_global_tags(request.user, workspace):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.request.active_workspace
        kwargs['allow_global'] = can_manage_global_tags(
            self.request.user,
            self.request.active_workspace,
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        context['can_manage_global_tags'] = can_manage_global_tags(
            self.request.user,
            self.request.active_workspace,
        )
        return context

    def form_valid(self, form):
        is_global = form.cleaned_data.get('is_global', False)
        if is_global:
            if not can_manage_global_tags(self.request.user, self.request.active_workspace):
                raise PermissionDenied
            form.instance.workspace = None
        else:
            if not has_workspace_perm(
                self.request.user,
                self.request.active_workspace,
                WorkspacePerm.TAG_CREATE,
            ):
                raise PermissionDenied
            form.instance.workspace = self.request.active_workspace
        assign_creator(form.instance, self.request.user)
        response = super().form_valid(form)
        if form.instance.is_global:
            invalidate_all_tag_suggestions_cache()
        else:
            invalidate_tag_suggestions_cache(self.request.active_workspace.pk)
        messages.success(self.request, f'Тег «{form.instance.name}» создан.')
        return response


class TagUpdateView(AppViewMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = 'core/tag_form.html'
    context_object_name = 'tag_obj'
    success_url = reverse_lazy('core:tag_list')

    def get_queryset(self):
        return tags_in_workspace(self.request.active_workspace)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_manage_tag(self.request.user, obj, self.request.active_workspace):
            raise PermissionDenied
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.object.workspace or self.request.active_workspace
        kwargs['allow_global'] = can_manage_global_tags(
            self.request.user,
            self.request.active_workspace,
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        context['can_manage_global_tags'] = can_manage_global_tags(
            self.request.user,
            self.request.active_workspace,
        )
        tag = self.object
        context['material_count'] = tag.materials.count()
        context['sample_count'] = tag.samples.count()
        context['scan_count'] = tag.scans.count()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if form.instance.is_global:
            invalidate_all_tag_suggestions_cache()
        else:
            invalidate_tag_suggestions_cache(form.instance.workspace_id)
        messages.success(self.request, f'Тег «{form.instance.name}» сохранён.')
        return response


class TagDeleteView(AppViewMixin, DeleteView):
    model = Tag
    template_name = 'core/tag_confirm_delete.html'
    context_object_name = 'tag_obj'
    success_url = reverse_lazy('core:tag_list')

    def get_queryset(self):
        return tags_in_workspace(self.request.active_workspace)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_manage_tag(self.request.user, obj, self.request.active_workspace):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tag = self.object
        context['material_count'] = tag.materials.count()
        context['sample_count'] = tag.samples.count()
        context['scan_count'] = tag.scans.count()
        context['usage_count'] = (
            context['material_count'] + context['sample_count'] + context['scan_count']
        )
        return context

    def form_valid(self, form):
        name = self.object.name
        is_global = self.object.is_global
        workspace_id = self.object.workspace_id
        response = super().form_valid(form)
        if is_global:
            invalidate_all_tag_suggestions_cache()
        else:
            invalidate_tag_suggestions_cache(workspace_id)
        messages.success(self.request, f'Тег «{name}» удалён.')
        return response


class TagBulkDeleteView(AppViewMixin, View):
    template_name = 'includes/bulk_confirm_delete.html'
    max_items = 100

    def get(self, request, *args, **kwargs):
        return redirect('core:tag_list')

    def post(self, request, *args, **kwargs):
        ids = parse_bulk_ids(request, max_items=self.max_items)
        if not ids:
            messages.warning(request, 'Не выбрано ни одного тега.')
            return redirect('core:tag_list')

        workspace = request.active_workspace
        tags = list(tags_in_workspace(workspace).filter(pk__in=ids))
        by_pk = {str(t.pk): t for t in tags}
        deletable = []
        blocked = []
        for key in ids:
            tag = by_pk.get(key)
            if tag is None:
                continue
            if not can_manage_tag(request.user, tag, workspace):
                blocked.append({'label': tag.name, 'code': '', 'reason': 'нет прав'})
                continue
            deletable.append(tag)

        if request.POST.get('confirm') != '1':
            return TemplateResponse(
                request,
                self.template_name,
                {
                    'page_title': 'Удаление выбранных тегов',
                    'warning_text': (
                        f'Будут удалены <strong>{len(deletable)}</strong> тег(ов). '
                        'Связи с материалами, образцами и сканами снимутся.'
                    ),
                    'deletable': [
                        {'label': t.name, 'code': ''} for t in deletable
                    ],
                    'blocked': blocked,
                    'ids': [str(t.pk) for t in deletable],
                    'cancel_url': reverse('core:tag_list'),
                },
            )

        if not deletable:
            messages.warning(request, 'Нет тегов, которые можно удалить.')
            return redirect('core:tag_list')

        deleted = 0
        touched_global = False
        workspace_ids: set = set()
        for tag in deletable:
            if not can_manage_tag(request.user, tag, workspace):
                continue
            name = tag.name
            if tag.is_global:
                touched_global = True
            elif tag.workspace_id:
                workspace_ids.add(tag.workspace_id)
            tag.delete()
            deleted += 1
        if touched_global:
            invalidate_all_tag_suggestions_cache()
        for ws_id in workspace_ids:
            invalidate_tag_suggestions_cache(ws_id)
        if deleted:
            messages.success(request, f'Удалено тегов: {deleted}.')
        if blocked:
            messages.warning(request, f'Пропущено (нет прав): {len(blocked)}.')
        return redirect('core:tag_list')
