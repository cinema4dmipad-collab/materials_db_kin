from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.structures import table_storage
from apps.structures.forms import get_dynamic_form
from apps.structures.models import StructureInstance, StructureType


class StructureTypeSelectView(ListView):
    model = StructureType
    template_name = 'structures/select_type.html'
    context_object_name = 'types'

    def get_queryset(self):
        return StructureType.objects.filter(is_active=True).prefetch_related('fields')


class StructureInstanceListView(ListView):
    model = StructureInstance
    template_name = 'structures/list.html'
    context_object_name = 'instances'
    paginate_by = 20

    def get_queryset(self):
        qs = StructureInstance.objects.select_related('structure_type')
        type_code = self.kwargs.get('type_code')
        if type_code:
            qs = qs.filter(structure_type__code=type_code)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        type_code = self.kwargs.get('type_code')
        if type_code:
            context['structure_type'] = get_object_or_404(
                StructureType, code=type_code, is_active=True
            )
        return context


class DynamicStructureCreateView(CreateView):
    model = StructureInstance
    template_name = 'structures/dynamic_form.html'

    def get_structure_type(self):
        return get_object_or_404(
            StructureType, code=self.kwargs['type_code'], is_active=True
        )

    def get_form_class(self):
        return get_dynamic_form(self.get_structure_type())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        st = self.get_structure_type()
        context['structure_type'] = st
        if not st.is_created:
            context['table_not_ready'] = True
        return context

    def get_success_url(self):
        return reverse('structures:list')

    def form_valid(self, form):
        messages.success(self.request, f'Структура «{form.instance.code}» создана.')
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        st = self.get_structure_type()
        if not st.is_created:
            messages.error(
                request,
                f'Таблица для типа «{st.name}» ещё не создана. Обратитесь к администратору.',
            )
            return self.get(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)


class DynamicStructureUpdateView(UpdateView):
    model = StructureInstance
    template_name = 'structures/dynamic_form.html'
    context_object_name = 'instance'

    def get_structure_type(self):
        return self.object.structure_type

    def get_form_class(self):
        return get_dynamic_form(self.get_structure_type())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.get_structure_type()
        context['edit_mode'] = True
        return context

    def get_success_url(self):
        return reverse('structures:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, f'Структура «{form.instance.code}» обновлена.')
        return super().form_valid(form)


StructureInstanceEditView = DynamicStructureUpdateView


class StructureInstanceDetailView(DetailView):
    model = StructureInstance
    template_name = 'structures/detail.html'
    context_object_name = 'instance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        st = self.object.structure_type
        if st.is_created and self.object.dynamic_row_id:
            context['field_values'] = table_storage.get_display_values(
                st, self.object.dynamic_row_id
            )
            context['uses_dynamic_table'] = True
        else:
            context['field_values'] = (
                self.object.values.select_related('field')
                .order_by('field__sort_order', 'field__name')
            )
        return context


class StructureInstanceDeleteView(DeleteView):
    model = StructureInstance
    template_name = 'structures/confirm_delete.html'
    context_object_name = 'instance'
    success_url = reverse_lazy('structures:list')

    def form_valid(self, form):
        obj = self.object
        if obj.structure_type.is_created and obj.dynamic_row_id:
            table_storage.delete_table_row(obj.structure_type, obj.dynamic_row_id)
        messages.success(self.request, f'Структура «{obj.code}» удалена.')
        return super().form_valid(form)
