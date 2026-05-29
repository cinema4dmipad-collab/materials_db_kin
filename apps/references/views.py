from django.contrib import messages
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.list_filters import QuerySetFilterMixin
from apps.references.forms import PropertyForm
from apps.references.models import Property, PropertyGroup


class PropertyListView(QuerySetFilterMixin, ListView):
    model = Property
    template_name = 'references/property_list.html'
    context_object_name = 'properties'
    paginate_by = 20
    search_fields = ('name', 'display_name', 'unit', 'description')
    search_placeholder = 'Имя, название, единица или описание...'
    choice_filters = (('group', 'group_id'), ('data_type', 'data_type'))
    choice_filter_labels = {'group': 'Группа', 'data_type': 'Тип данных'}

    def get_queryset(self):
        return self.filter_queryset(
            Property.objects.select_related('group').annotate(
                material_count=Count('material_values'),
            )
        )

    def get_choice_filter_options(self):
        return {
            'group': list(
                PropertyGroup.objects.order_by('sort_order', 'name').values_list('pk', 'name')
            ),
            'data_type': Property.DATA_TYPES,
        }


class PropertyCreateView(CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'references/property_form.html'
    success_url = reverse_lazy('references:list')

    def form_valid(self, form):
        messages.success(self.request, f'Свойство «{form.instance.display_name}» создано.')
        return super().form_valid(form)


class PropertyUpdateView(UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'references/property_form.html'
    context_object_name = 'property_obj'

    def form_valid(self, form):
        messages.success(self.request, f'Свойство «{form.instance.display_name}» сохранено.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('references:list')


class PropertyDeleteView(DeleteView):
    model = Property
    template_name = 'references/property_confirm_delete.html'
    context_object_name = 'property_obj'
    success_url = reverse_lazy('references:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['material_count'] = self.object.material_values.count()
        return context

    def form_valid(self, form):
        display_name = self.object.display_name
        response = super().form_valid(form)
        messages.success(self.request, f'Свойство «{display_name}» удалено.')
        return response
