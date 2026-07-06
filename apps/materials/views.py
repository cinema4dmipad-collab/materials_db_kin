from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    DEFAULT_CREATOR_FILTER,
    STRUCT_TYPE_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
)
from apps.core.creator import assign_creator
from apps.materials.form_validation import (
    build_material_form_validation_summary,
    validation_flash_message,
    validation_sections,
)
from apps.materials.forms import (
    MaterialForm,
    MaterialPropertyFormSet,
    MaterialVisibilityForm,
    get_composite_layer_formset,
)
from apps.core.property_form_display import enrich_property_form_display
from apps.core.number_utils import format_decimal_display
from apps.materials.models import Material
from apps.materials.services import can_clone_material_to_workspace, clone_material_to_workspace
from apps.materials.structure_display import get_material_structure_context, serialize_structure_context
from apps.structures.models import StructureType
from apps.materials.picker_data import materials_for_picker
from apps.structures.property_mapping import reference_properties_for_picker
from apps.structures.picker_data import structure_types_for_picker
from apps.workspaces.mixins import AppViewMixin, PermissionRequiredMixin
from apps.workspaces.permissions import (
    WorkspacePerm,
    can_delete_in_workspace,
    has_workspace_perm,
    is_editable_in_workspace,
)
from apps.workspaces.visibility import VisibilityMode
from apps.workspaces.services import materials_owned_by, materials_shared_in, materials_visible_in, structure_types_visible_in


MATERIAL_SCOPE_WORKSPACE = 'workspace'
MATERIAL_SCOPE_SHARED = 'shared'
MATERIAL_SCOPE_CHOICES = (MATERIAL_SCOPE_WORKSPACE, MATERIAL_SCOPE_SHARED)


class MaterialFormsetMixin:
    def get_tag_workspace(self, instance=None):
        material = instance if instance is not None else getattr(self, 'object', None)
        if material and material.home_workspace_id:
            return material.home_workspace
        return self.request.active_workspace

    def _visibility_form_kwargs(self):
        return {
            'show_visibility': isinstance(self, CreateView),
            'can_publish': has_workspace_perm(
                self.request.user,
                self.request.active_workspace,
                WorkspacePerm.MATERIAL_PUBLISH,
            ),
        }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.get_tag_workspace()
        kwargs.update(self._visibility_form_kwargs())
        return kwargs

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

    def _has_formset_management_data(self, prefix: str) -> bool:
        return (
            self.request.method == 'POST'
            and f'{prefix}-TOTAL_FORMS' in self.request.POST
            and f'{prefix}-INITIAL_FORMS' in self.request.POST
        )

    def get_formset(self):
        kwargs = {'prefix': 'properties'}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        return MaterialPropertyFormSet(**kwargs)

    def get_layer_formset(self):
        if not self.layers_allowed():
            return None

        formset_class = get_composite_layer_formset()
        kwargs = {'prefix': 'layers'}
        if self._has_formset_management_data('layers'):
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
        kwargs['workspace'] = self.request.active_workspace
        return formset_class(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'formset' not in context:
            context['formset'] = self.get_formset()
        formset = context.get('formset')
        if formset is not None:
            for property_form in formset:
                enrich_property_form_display(property_form)
        if 'layer_formset' not in context:
            context['layer_formset'] = self.get_layer_formset()
            context['layers_allowed'] = self.layers_allowed()
        context['reference_properties'] = reference_properties_for_picker()
        context['reference_materials'] = materials_for_picker(self.request.active_workspace)
        context['reference_structure_types'] = structure_types_for_picker()
        self._attach_validation_summary(context)
        return context

    def _validate_related_formsets(self, formset, layer_formset):
        if self.request.method != 'POST':
            return
        if formset is not None:
            formset.is_valid()
        if layer_formset is not None:
            layer_formset.is_valid()

    def _attach_validation_summary(self, context):
        form = context.get('form')
        if form is None:
            return
        summary = build_material_form_validation_summary(
            form,
            properties_formset=context.get('formset'),
            layers_formset=context.get('layer_formset'),
        )
        context['form_validation_summary'] = summary
        context['form_validation_sections'] = set(validation_sections(summary))

    def _notify_validation_errors(self, form, formset, layer_formset):
        summary = build_material_form_validation_summary(form, formset, layer_formset)
        message = validation_flash_message(summary)
        if message:
            messages.error(self.request, message)

    def form_invalid(self, form):
        formset = self.get_formset()
        layer_formset = self.get_layer_formset()
        self._validate_related_formsets(formset, layer_formset)
        self._notify_validation_errors(form, formset, layer_formset)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                formset=formset,
                layer_formset=layer_formset,
            )
        )

    def post(self, request, *args, **kwargs):
        if request.POST.get('_apply_struct_type'):
            if isinstance(self, UpdateView):
                self.object = self.get_object()
            return self.render_apply_struct_type()
        return super().post(request, *args, **kwargs)

    def render_apply_struct_type(self):
        instance = getattr(self, 'object', None)
        if not isinstance(self, UpdateView):
            self.object = None
        form = MaterialForm(
            self.request.POST,
            instance=instance,
            skip_validation=True,
            workspace=self.get_tag_workspace(instance),
            **self._visibility_form_kwargs(),
        )
        formset = MaterialPropertyFormSet(
            self.request.POST,
            instance=instance,
            prefix='properties',
        )
        layer_formset = None
        if self.layers_allowed():
            layer_kwargs = {
                'instance': instance,
                'prefix': 'layers',
                'workspace': self.request.active_workspace,
            }
            if self._has_formset_management_data('layers'):
                layer_kwargs['data'] = self.request.POST
            layer_formset = get_composite_layer_formset()(**layer_kwargs)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                formset=formset,
                layer_formset=layer_formset,
            )
        )

    def form_valid(self, form):
        is_update = isinstance(self, UpdateView)
        original_pk = self.object.pk if is_update else None
        formset = None
        layer_formset = None
        saved = False

        try:
            with transaction.atomic():
                if not is_update:
                    form.instance.home_workspace = self.request.active_workspace
                    assign_creator(form.instance, self.request.user)
                    if not form.show_visibility:
                        form.instance.visibility_mode = VisibilityMode.PRIVATE
                self.object = form.save()
                formset = MaterialPropertyFormSet(
                    self.request.POST,
                    instance=self.object,
                    prefix='properties',
                )
                if self.layers_allowed():
                    layer_kwargs = {
                        'instance': self.object,
                        'prefix': 'layers',
                        'workspace': self.request.active_workspace,
                    }
                    if self._has_formset_management_data('layers'):
                        layer_kwargs['data'] = self.request.POST
                    layer_formset = get_composite_layer_formset()(**layer_kwargs)
                properties_valid = formset.is_valid()
                layers_valid = layer_formset is None or layer_formset.is_valid()
                if not properties_valid or not layers_valid:
                    transaction.set_rollback(True)
                else:
                    formset.save()
                    if layer_formset is not None:
                        layer_formset.save()
                    saved = True
        except forms.ValidationError as exc:
            form.add_error(None, exc)

        if saved:
            return HttpResponseRedirect(self.get_success_url())

        if is_update and original_pk:
            self.object = Material.objects.get(pk=original_pk)
        elif not is_update:
            self.object = None

        if formset is None:
            formset = self.get_formset()
        if layer_formset is None:
            layer_formset = self.get_layer_formset()
        self._validate_related_formsets(formset, layer_formset)
        self._notify_validation_errors(form, formset, layer_formset)

        return self.render_to_response(
            self.get_context_data(
                form=form,
                formset=formset,
                layer_formset=layer_formset,
            )
        )


class MaterialListView(AppViewMixin, QuerySetFilterMixin, ListView):
    model = Material
    template_name = 'materials/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10
    enable_tag_filter = True
    search_fields = ('code', 'name', 'description', 'struct_type__name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('code', 'name', 'description', 'struct_type__name')),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        ('description', 'Описание', ('description',)),
        (STRUCT_TYPE_SEARCH_SCOPE, 'Тип структуры', ('struct_type__name',)),
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('struct_type', 'struct_type_id'),)
    choice_filter_labels = {'struct_type': 'Тип структуры'}

    def get_material_scope(self):
        scope = self.request.GET.get('scope', MATERIAL_SCOPE_WORKSPACE)
        if scope not in MATERIAL_SCOPE_CHOICES:
            return MATERIAL_SCOPE_WORKSPACE
        return scope

    def get_scope_url(self, scope):
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == MATERIAL_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
        query = params.urlencode()
        return reverse('materials:list') + (f'?{query}' if query else '')

    def get_queryset(self):
        workspace = self.request.active_workspace
        scope = self.get_material_scope()
        if scope == MATERIAL_SCOPE_SHARED:
            base_qs = materials_shared_in(workspace)
        else:
            base_qs = materials_owned_by(workspace)
        return self.filter_queryset(
            base_qs.select_related('struct_type', 'home_workspace', 'created_by_user')
            .prefetch_related('tags')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope = self.get_material_scope()
        context['material_scope'] = scope
        context['material_scope_tabs'] = [
            {
                'key': MATERIAL_SCOPE_WORKSPACE,
                'label': 'Пространство',
                'url': self.get_scope_url(MATERIAL_SCOPE_WORKSPACE),
            },
            {
                'key': MATERIAL_SCOPE_SHARED,
                'label': 'Общие',
                'url': self.get_scope_url(MATERIAL_SCOPE_SHARED),
            },
        ]
        if scope != MATERIAL_SCOPE_WORKSPACE:
            context['list_filter_preserve_params'] = [('scope', scope)]
        else:
            context['list_filter_preserve_params'] = []
        params = self.request.GET.copy()
        params.pop('page', None)
        if scope == MATERIAL_SCOPE_WORKSPACE:
            params.pop('scope', None)
        else:
            params['scope'] = scope
        context['pagination_query'] = params.urlencode()
        context['filter_reset_url'] = self.get_scope_url(scope)
        materials = context.get('materials') or context.get('object_list') or []
        user = self.request.user
        workspace = self.request.active_workspace
        context['material_editable_pks'] = {
            material.pk
            for material in materials
            if is_editable_in_workspace(user, material, workspace)
        }
        context['material_deletable_pks'] = {
            material.pk
            for material in materials
            if can_delete_in_workspace(user, material, workspace)
        }
        context['material_cloneable_pks'] = {
            material.pk
            for material in materials
            if can_clone_material_to_workspace(user, material, workspace)
        }
        return context

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: DEFAULT_CREATOR_FILTER,
        }

    def get_choice_filter_options(self):
        return {
            'struct_type': list(
                structure_types_visible_in(self.request.active_workspace)
                .order_by('name')
                .values_list('pk', 'name')
            ),
        }


class MaterialEditableMixin:
    def get_queryset(self):
        return materials_visible_in(self.request.active_workspace).select_related('struct_type')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not is_editable_in_workspace(self.request.user, obj, self.request.active_workspace):
            raise PermissionDenied
        return obj


class MaterialDetailView(AppViewMixin, DetailView):
    model = Material
    template_name = 'materials/material_detail.html'
    context_object_name = 'material'
    active_tab = 'material'

    def get_queryset(self):
        return (
            materials_visible_in(self.request.active_workspace)
            .select_related('struct_type', 'home_workspace')
            .prefetch_related('tags')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_ws = self.request.active_workspace
        context['material_is_readonly'] = not is_editable_in_workspace(
            self.request.user, self.object, active_ws
        )
        context['can_publish_material'] = (
            not context['material_is_readonly']
            and has_workspace_perm(self.request.user, active_ws, WorkspacePerm.MATERIAL_PUBLISH)
        )
        context['can_delete_material'] = can_delete_in_workspace(
            self.request.user,
            self.object,
            active_ws,
        )
        context['can_clone_material'] = can_clone_material_to_workspace(
            self.request.user,
            self.object,
            active_ws,
        )
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
        context.update(get_material_structure_context(self.object))
        return context

    def get_layer_diagram(self, composite_layers):
        from apps.composites.layer_diagram import build_layer_diagram

        return build_layer_diagram(composite_layers)

    def get_composite_layers(self):
        return self.object.composite_layers.select_related('material').order_by('layer_number')


class MaterialCreateView(AppViewMixin, PermissionRequiredMixin, MaterialFormsetMixin, CreateView):
    permission_codename = WorkspacePerm.MATERIAL_CREATE
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    success_url = reverse_lazy('materials:list')


class MaterialUpdateView(
    AppViewMixin,
    PermissionRequiredMixin,
    MaterialEditableMixin,
    MaterialFormsetMixin,
    UpdateView,
):
    permission_codename = WorkspacePerm.MATERIAL_EDIT
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    context_object_name = 'material'

    def get_success_url(self):
        return reverse_lazy('materials:detail', kwargs={'pk': self.object.pk})


class MaterialCloneView(AppViewMixin, PermissionRequiredMixin, View):
    permission_codename = WorkspacePerm.MATERIAL_CREATE
    http_method_names = ['post']

    def post(self, request, pk):
        source = get_object_or_404(
            materials_visible_in(request.active_workspace).select_related('struct_type'),
            pk=pk,
        )
        try:
            clone = clone_material_to_workspace(source, request.active_workspace, request.user)
        except PermissionError:
            raise PermissionDenied
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect('materials:detail', pk=source.pk)

        messages.success(
            request,
            f'Материал «{source.code}» скопирован в пространство как «{clone.code}».',
        )
        return redirect('materials:detail', pk=clone.pk)


class MaterialDeleteView(AppViewMixin, PermissionRequiredMixin, MaterialEditableMixin, DeleteView):
    permission_codename = WorkspacePerm.MATERIAL_DELETE
    model = Material
    template_name = 'materials/material_confirm_delete.html'
    context_object_name = 'material'
    success_url = reverse_lazy('materials:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        material = self.object
        context['used_as_layer'] = material.used_in_composite_layers.select_related(
            'parent_material'
        ).all()
        context['has_layers'] = material.composite_layers.exists()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                'Нельзя удалить материал — он используется как слой в композитных материалах. '
                'Сначала удалите связи из композитных материалов.',
            )
            return redirect('materials:detail', pk=self.object.pk)


class MaterialPropertiesJSONView(AppViewMixin, View):
    def get(self, request, pk):
        material = get_object_or_404(
            materials_visible_in(request.active_workspace).select_related('struct_type'),
            pk=pk,
        )
        properties = material.properties.select_related('property').order_by(
            'property__group__sort_order',
            'property__name',
        )
        structure_context = get_material_structure_context(material)
        return JsonResponse(
            {
                'properties': [
                    {
                        'property_id': str(item.property_id),
                        'display_name': item.property.display_name,
                        'unit': item.property.unit,
                        'value': (
                            format_decimal_display(item.value)
                            if item.property.data_type == 'number'
                            else item.value
                        ),
                    }
                    for item in properties
                ],
                **serialize_structure_context(structure_context),
            }
        )


class MaterialVisibilityView(AppViewMixin, PermissionRequiredMixin, UpdateView):
    permission_codename = WorkspacePerm.MATERIAL_PUBLISH
    model = Material
    form_class = MaterialVisibilityForm
    template_name = 'materials/material_visibility.html'
    context_object_name = 'material'

    def get_queryset(self):
        return materials_visible_in(self.request.active_workspace)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not is_editable_in_workspace(self.request.user, obj, self.request.active_workspace):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = reverse('materials:detail', kwargs={'pk': self.object.pk})
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Настройки видимости материала сохранены.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('materials:detail', kwargs={'pk': self.object.pk})
