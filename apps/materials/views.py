from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.materials.forms import MaterialForm, MaterialPropertyFormSet
from apps.materials.models import Material


class MaterialFormsetMixin:
    def get_formset(self):
        if self.request.method == 'POST':
            if getattr(self, 'object', None):
                return MaterialPropertyFormSet(self.request.POST, instance=self.object)
            return MaterialPropertyFormSet(self.request.POST)
        if getattr(self, 'object', None):
            return MaterialPropertyFormSet(instance=self.object)
        return MaterialPropertyFormSet()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['formset'] = self.get_formset()
        return context

    def form_valid(self, form):
        formset = self.get_formset()
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        self.object = form.save()
        formset.instance = self.object
        formset.save()
        return HttpResponseRedirect(self.get_success_url())


class MaterialListView(ListView):
    model = Material
    template_name = 'materials/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10


class MaterialDetailView(DetailView):
    model = Material
    template_name = 'materials/material_detail.html'
    context_object_name = 'material'
    structure_service_columns = {'id', 'created_at', 'updated_at', 'created_by'}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['properties'] = (
            self.object.properties.select_related('property', 'property__group').order_by(
                'property__group__sort_order',
                'property__name',
            )
        )
        context.update(self.get_structure_context())
        return context

    def get_structure_context(self):
        material = self.object
        structure_context = {
            'structure_type': material.struct_type,
            'structure_properties': [],
            'structure_message': '',
        }

        if not material.struct_type_id:
            structure_context['structure_message'] = 'Структура не выбрана.'
            return structure_context

        if not material.struct_props_id:
            structure_context['structure_message'] = 'Запись параметров структуры не выбрана.'
            return structure_context

        structure_params = material.get_structure_params()
        if structure_params is None:
            structure_context['structure_message'] = 'Запись параметров структуры не найдена.'
            return structure_context

        fields = (
            material.struct_type.fields.exclude(name__in=self.structure_service_columns)
            .exclude(field_type='ForeignKey')
            .order_by('sort_order', 'name')
        )
        structure_context['structure_properties'] = [
            {
                'label': field.label,
                'name': field.name,
                'field_type': field.field_type,
                'value': structure_params.get(field.name),
                'display_value': self.get_structure_display_value(
                    structure_params.get(field.name)
                ),
            }
            for field in fields
        ]

        if not structure_context['structure_properties']:
            structure_context['structure_message'] = 'Параметры структуры не заданы.'
        return structure_context

    def get_structure_display_value(self, value):
        if value is None or value == '':
            return '—'
        return value


class MaterialCreateView(MaterialFormsetMixin, CreateView):
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    success_url = reverse_lazy('materials:list')


class MaterialUpdateView(MaterialFormsetMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    context_object_name = 'material'

    def get_success_url(self):
        return reverse_lazy('materials:detail', kwargs={'pk': self.object.pk})


class MaterialDeleteView(DeleteView):
    model = Material
    template_name = 'materials/material_confirm_delete.html'
    context_object_name = 'material'
    success_url = reverse_lazy('materials:list')
