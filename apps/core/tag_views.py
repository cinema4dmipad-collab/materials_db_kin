from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

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

    def get_scope_url(self, scope):
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == TAG_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
        query = params.urlencode()
        return reverse('core:tag_list') + (f'?{query}' if query else '')

    def get_queryset(self):
        workspace = self.request.active_workspace
        scope = self.get_tag_scope()
        if scope == TAG_SCOPE_GLOBAL:
            base_qs = Tag.objects.filter(workspace__isnull=True)
        else:
            base_qs = Tag.objects.filter(workspace=workspace)
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
        context['tag_scope'] = scope
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
        if scope != TAG_SCOPE_WORKSPACE:
            context['list_filter_preserve_params'] = [('scope', scope)]
        else:
            context['list_filter_preserve_params'] = []
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == TAG_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
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
