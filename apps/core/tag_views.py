from django.contrib import messages
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.forms import TagForm
from apps.core.list_filters import QuerySetFilterMixin
from apps.core.models import Tag


class TagListView(QuerySetFilterMixin, ListView):
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
            Tag.objects.annotate(
                material_count=Count('materials', distinct=True),
                sample_count=Count('samples', distinct=True),
                scan_count=Count('scans', distinct=True),
            ).order_by('name')
        )


class TagCreateView(CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'core/tag_form.html'
    success_url = reverse_lazy('core:tag_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Тег «{form.instance.name}» создан.')
        return super().form_valid(form)


class TagUpdateView(UpdateView):
    model = Tag
    form_class = TagForm
    template_name = 'core/tag_form.html'
    context_object_name = 'tag_obj'
    success_url = reverse_lazy('core:tag_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse_lazy('core:tag_list')
        tag = self.object
        context['material_count'] = tag.materials.count()
        context['sample_count'] = tag.samples.count()
        context['scan_count'] = tag.scans.count()
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Тег «{form.instance.name}» сохранён.')
        return super().form_valid(form)


class TagDeleteView(DeleteView):
    model = Tag
    template_name = 'core/tag_confirm_delete.html'
    context_object_name = 'tag_obj'
    success_url = reverse_lazy('core:tag_list')

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
        response = super().form_valid(form)
        messages.success(self.request, f'Тег «{name}» удалён.')
        return response
