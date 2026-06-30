from django.contrib import messages
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.context_processors import invalidate_tag_suggestions_cache
from apps.core.forms import TagForm
from apps.core.list_filters import QuerySetFilterMixin
from apps.core.models import Tag
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import tags_in_workspace


class TagListView(AppViewMixin, QuerySetFilterMixin, ListView):
    model = Tag
    template_name = 'core/tag_list.html'
    context_object_name = 'tags'
    paginate_by = 30
    search_fields = ('name',)
    search_scopes = (
        ('', 'Везде', ('name',)),
        ('name', 'Название', ('name',)),
    )
    search_placeholder = 'Поиск по названию...'

    def get_queryset(self):
        return self.filter_queryset(
            tags_in_workspace(self.request.active_workspace).annotate(
                material_count=Count('materials', distinct=True),
                sample_count=Count('samples', distinct=True),
                scan_count=Count('scans', distinct=True),
            ).order_by('name')
        )


class TagCreateView(AppViewMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'core/tag_form.html'
    success_url = reverse_lazy('core:tag_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.request.active_workspace
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        return context

    def form_valid(self, form):
        form.instance.workspace = self.request.active_workspace
        response = super().form_valid(form)
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.request.active_workspace
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        tag = self.object
        context['material_count'] = tag.materials.count()
        context['sample_count'] = tag.samples.count()
        context['scan_count'] = tag.scans.count()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        invalidate_tag_suggestions_cache(self.request.active_workspace.pk)
        messages.success(self.request, f'Тег «{form.instance.name}» сохранён.')
        return response


class TagDeleteView(AppViewMixin, DeleteView):
    model = Tag
    template_name = 'core/tag_confirm_delete.html'
    context_object_name = 'tag_obj'
    success_url = reverse_lazy('core:tag_list')

    def get_queryset(self):
        return tags_in_workspace(self.request.active_workspace)

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
        workspace_id = self.object.workspace_id
        response = super().form_valid(form)
        invalidate_tag_suggestions_cache(workspace_id)
        messages.success(self.request, f'Тег «{name}» удалён.')
        return response
