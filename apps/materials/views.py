from django import forms
from django.http import HttpResponseRedirect
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.materials.forms import (
    MaterialForm,
    MaterialPropertyFormSet,
    get_composite_layer_formset,
)
from apps.materials.models import Material
from apps.structures.models import MATERIAL_LINK_FIELD_TYPE, StructureType


class MaterialFormsetMixin:
    def get_initial(self):
        initial = super().get_initial()
        if 'struct_type' in self.request.GET:
            initial['struct_type'] = self.request.GET.get('struct_type')
        return initial

    def get_selected_structure_type(self):
        material = getattr(self, 'object', None)
        if self.request.method == 'POST':
            struct_type_id = self.request.POST.get('struct_type')
        elif material and material.struct_type_id:
            return material.struct_type
        else:
            struct_type_id = self.request.GET.get('struct_type')
            if not struct_type_id:
                initial = self.get_initial()
                struct_type_id = initial.get('struct_type')

        if not struct_type_id:
            return None

        try:
            return StructureType.objects.get(pk=struct_type_id)
        except (StructureType.DoesNotExist, ValueError, TypeError):
            return None

    def layers_allowed(self):
        structure_type = self.get_selected_structure_type()
        return bool(structure_type and structure_type.allow_layers)

    def get_formset(self):
        if self.request.method == 'POST':
            if getattr(self, 'object', None):
                return MaterialPropertyFormSet(self.request.POST, instance=self.object)
            return MaterialPropertyFormSet(self.request.POST)
        if getattr(self, 'object', None):
            return MaterialPropertyFormSet(instance=self.object)
        return MaterialPropertyFormSet()

    def get_layer_formset(self):
        if not self.layers_allowed():
            return None

        formset_class = get_composite_layer_formset()
        kwargs = {'prefix': 'layers'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        return formset_class(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'formset' not in context:
            context['formset'] = self.get_formset()
        if 'layer_formset' not in context:
            context['layer_formset'] = self.get_layer_formset()
            context['layers_allowed'] = self.layers_allowed()
        return context

    def form_valid(self, form):
        formset = self.get_formset()
        layer_formset = self.get_layer_formset()
        if not formset.is_valid() or (
            layer_formset is not None and not layer_formset.is_valid()
        ):
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    formset=formset,
                    layer_formset=layer_formset,
                )
            )
        try:
            with transaction.atomic():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                if layer_formset is not None:
                    layer_formset.instance = self.object
                    layer_formset.save()
        except forms.ValidationError as exc:
            form.add_error(None, exc)
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    formset=formset,
                    layer_formset=layer_formset,
                )
            )
        return HttpResponseRedirect(self.get_success_url())


class MaterialListView(ListView):
    model = Material
    template_name = 'materials/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10

    def get_queryset(self):
        return super().get_queryset().select_related('struct_type')


class MaterialDetailView(DetailView):
    model = Material
    template_name = 'materials/material_detail.html'
    context_object_name = 'material'
    active_tab = 'material'
    structure_service_columns = {'id', 'created_at', 'updated_at', 'created_by'}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = self.active_tab
        context['attachment_count'] = self.object.attachments.count()
        context['sample_count'] = self.object.samples.count()
        context['attachments'] = self.object.attachments.all()[:5]
        context['properties'] = (
            self.object.properties.select_related('property', 'property__group').order_by(
                'property__group__sort_order',
                'property__name',
            )
        )
        context['show_composite_layers'] = self.object.supports_layers
        context['composite_layers'] = (
            self.get_composite_layers() if self.object.supports_layers else []
        )
        context['layer_diagram'] = self.get_layer_diagram(context['composite_layers'])
        context.update(self.get_structure_context())
        return context

    def get_layer_diagram(self, composite_layers):
        from apps.composites.layer_diagram import build_layer_diagram

        return build_layer_diagram(composite_layers)

    def get_composite_layers(self):
        return self.object.composite_layers.select_related('material').order_by('layer_number')

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
                    field,
                    structure_params.get(field.name)
                ),
            }
            for field in fields
        ]

        if not structure_context['structure_properties']:
            structure_context['structure_message'] = 'Параметры структуры не заданы.'
        return structure_context

    def get_structure_display_value(self, field, value):
        if value is None or value == '':
            return '—'
        if field.field_type == MATERIAL_LINK_FIELD_TYPE:
            try:
                material = Material.objects.get(pk=value)
            except (Material.DoesNotExist, ValueError, TypeError):
                return value
            return f'{material.code} - {material.name}'
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
