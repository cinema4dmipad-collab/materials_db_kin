from django.conf import settings
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.core.paginator import InvalidPage
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView, View

from pathlib import Path

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    CREATOR_WITH_LABEL_FILTER,
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
    MaterialImportForm,
    MaterialPropertyFormSet,
    MaterialTagsForm,
    MaterialVisibilityForm,
    build_composite_layer_formset,
    build_material_property_formset,
    get_composite_layer_formset,
)
from apps.materials.imports.debug_undo import (
    get_last_import_debug_batch,
    store_last_import_debug_batch,
    undo_last_import_debug_batch,
)
from apps.materials.imports.iterate import (
    append_iterate_log,
    append_iterate_material_ids,
    apply_iterate_row_post,
    clear_iterate_session,
    get_iterate_index,
    get_iterate_log,
    get_iterate_material_ids,
    is_iterate_active,
    iterate_progress,
    next_active_index,
    set_iterate_index,
    start_iterate,
)
from apps.materials.imports.mapping import (
    TARGET_NAME,
    TARGET_PROPERTY_PREFIX,
    TARGET_SKIP,
    apply_profile_to_columns,
    mapping_choices,
    mapping_catalog_groups,
    mapping_for_session,
    find_duplicate_mapping_targets,
    missing_required_targets,
    normalize_mapping_entry,
    profile_payload_from_mapping,
    required_import_targets,
    target_allows_multiple_columns,
    suggest_parse_mode,
    suggest_target,
)
from apps.materials.imports.service import MaterialImporter
from apps.materials.imports.staging import (
    MATCH_POLICIES,
    MATCH_BY_NAME,
    apply_review_post,
    build_staging_draft,
    drafts_from_session,
    drafts_to_session,
)
from apps.materials.imports.upload import (
    clear_import_session,
    get_import_config,
    get_import_session_name,
    get_import_session_path,
    save_uploaded_import_file,
    set_import_config,
    store_import_session,
)
from apps.materials.imports.value_parse import PARSE_MODES_SHORT
from apps.materials.imports.wide import detect_header_layout, list_sheet_names, load_wide_table
from apps.references.models import Property
from apps.core.property_form_display import enrich_property_form_display
from apps.core.number_utils import format_decimal_display
from apps.materials.models import Material, MaterialImportProfile
from apps.materials.services import (
    build_material_create_initial,
    can_link_material_to_workspace,
    can_manage_material_visibility,
    composite_layer_formset_initial,
    get_create_template_material,
    is_material_linked_to_workspace,
    link_material_to_workspace,
    material_pks_linked_in_workspace,
    material_property_formset_initial,
    material_attachments_for_material,
    samples_for_material,
)
from apps.materials.structure_display import get_material_structure_context, serialize_structure_context
from apps.structures.models import StructureField, StructureType
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
from apps.workspaces.services import (
    materials_in_workspace_tab,
    materials_shared_in,
    materials_visible_in,
    structure_types_visible_in,
)


MATERIAL_SCOPE_WORKSPACE = 'workspace'
MATERIAL_SCOPE_SHARED = 'shared'
MATERIAL_SCOPE_CHOICES = (MATERIAL_SCOPE_WORKSPACE, MATERIAL_SCOPE_SHARED)


class MaterialFormsetMixin:
    def get_template_material(self):
        if not isinstance(self, CreateView):
            return None
        based_on = self.request.GET.get('based_on') or self.request.POST.get('based_on')
        if not based_on:
            return None
        return get_create_template_material(
            self.request.user,
            self.request.active_workspace,
            based_on,
        )

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
        template_material = self.get_template_material()
        if template_material is not None:
            kwargs['template_material'] = template_material
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        template_material = self.get_template_material()
        if template_material is not None:
            initial.update(
                build_material_create_initial(template_material, self.request.active_workspace)
            )
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
        workspace = self.request.active_workspace
        if getattr(self, 'object', None):
            kwargs = {
                'prefix': 'properties',
                'instance': self.object,
                'workspace': workspace,
            }
            if self.request.method == 'POST':
                kwargs['data'] = self.request.POST
            return MaterialPropertyFormSet(**kwargs)

        template_material = self.get_template_material()
        if template_material is not None:
            if self.request.method == 'POST':
                return MaterialPropertyFormSet(
                    self.request.POST,
                    instance=Material(),
                    prefix='properties',
                    workspace=workspace,
                )
            return build_material_property_formset(
                workspace=workspace,
                initial=material_property_formset_initial(template_material),
            )

        kwargs = {'prefix': 'properties', 'workspace': workspace}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        return MaterialPropertyFormSet(**kwargs)

    def get_layer_formset(self):
        if not self.layers_allowed():
            return None

        template_material = self.get_template_material()
        if getattr(self, 'object', None):
            formset_class = get_composite_layer_formset()
            kwargs = {'prefix': 'layers', 'instance': self.object, 'workspace': self.request.active_workspace}
            if self._has_formset_management_data('layers'):
                kwargs['data'] = self.request.POST
            return formset_class(**kwargs)

        if template_material is not None:
            if self.request.method == 'POST' and self._has_formset_management_data('layers'):
                return build_composite_layer_formset(
                    workspace=self.request.active_workspace,
                    data=self.request.POST,
                    prefix='layers',
                )
            return build_composite_layer_formset(
                workspace=self.request.active_workspace,
                initial=composite_layer_formset_initial(template_material),
                prefix='layers',
            )

        formset_class = get_composite_layer_formset()
        kwargs = {'prefix': 'layers', 'workspace': self.request.active_workspace}
        if self._has_formset_management_data('layers'):
            kwargs['data'] = self.request.POST
        if getattr(self, 'object', None):
            kwargs['instance'] = self.object
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
        if isinstance(self, CreateView):
            context['show_create_based_on'] = True
            context['template_material'] = self.get_template_material()
            if self.request.GET.get('based_on') and context['template_material'] is None:
                messages.warning(
                    self.request,
                    'Материал-образец не найден или недоступен в текущем пространстве.',
                )
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
            template_material=self.get_template_material(),
            **self._visibility_form_kwargs(),
        )
        template_material = self.get_template_material()
        if template_material is not None and 'properties-TOTAL_FORMS' not in self.request.POST:
            formset = build_material_property_formset(
                workspace=self.request.active_workspace,
                instance=instance or Material(),
                initial=material_property_formset_initial(template_material),
            )
        else:
            formset = MaterialPropertyFormSet(
                self.request.POST,
                instance=instance,
                prefix='properties',
                workspace=self.request.active_workspace,
            )
        layer_formset = None
        if self.layers_allowed():
            if template_material is not None and not self._has_formset_management_data('layers'):
                layer_formset = build_composite_layer_formset(
                    workspace=self.request.active_workspace,
                    instance=instance or Material(),
                    initial=composite_layer_formset_initial(template_material),
                    prefix='layers',
                )
            else:
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
                    workspace=self.request.active_workspace,
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
    choice_filters = (
        ('struct_type', 'struct_type_id'),
        ('import_source', 'import_source_filename'),
    )
    choice_filter_labels = {
        'struct_type': 'Тип структуры',
        'import_source': 'Источник импорта',
    }

    def paginate_queryset(self, queryset, page_size):
        """Avoid 404 when page number is stale after bulk delete / filters."""
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1
        try:
            page_number = int(page)
        except (TypeError, ValueError):
            page_number = 1
        try:
            page = paginator.page(page_number)
        except InvalidPage:
            page = paginator.page(1)
        return (paginator, page, page.object_list, page.has_other_pages())

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
            base_qs = materials_in_workspace_tab(workspace)
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
        context['material_linkable_pks'] = {
            material.pk
            for material in materials
            if can_link_material_to_workspace(user, material, workspace)
        }
        context['material_linked_pks'] = material_pks_linked_in_workspace(workspace)
        context.update(_import_debug_context(self.request))
        return context

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: CREATOR_WITH_LABEL_FILTER,
        }

    def get_choice_filter_options(self):
        workspace = self.request.active_workspace
        scope = self.get_material_scope()
        if scope == MATERIAL_SCOPE_SHARED:
            source_qs = materials_shared_in(workspace)
        else:
            source_qs = materials_in_workspace_tab(workspace)
        import_sources = list(
            source_qs.exclude(import_source_filename='')
            .order_by('import_source_filename')
            .values_list('import_source_filename', flat=True)
            .distinct()
        )
        return {
            'struct_type': list(
                structure_types_visible_in(workspace)
                .order_by('name')
                .values_list('pk', 'name')
            ),
            'import_source': [(name, name) for name in import_sources],
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
        context['material_is_workspace_link'] = is_material_linked_to_workspace(
            self.object,
            active_ws,
        )
        context['can_publish_material'] = can_manage_material_visibility(
            self.request.user,
            self.object,
            active_ws,
        )
        context['can_delete_material'] = can_delete_in_workspace(
            self.request.user,
            self.object,
            active_ws,
        )
        context['can_link_material'] = can_link_material_to_workspace(
            self.request.user,
            self.object,
            active_ws,
        )
        # Tags are editable only in the material's home workspace — not for
        # linked/published read-only copies (even for system admins).
        if (
            not context['material_is_readonly']
            and not context['material_is_workspace_link']
            and self.object.is_editable_in(active_ws)
        ):
            tag_workspace = self.object.home_workspace or active_ws
            context['tags_form'] = MaterialTagsForm(
                instance=self.object,
                workspace=tag_workspace,
            )
        context['active_tab'] = self.active_tab
        context['attachment_count'] = material_attachments_for_material(
            self.object,
            active_ws,
        ).count()
        context['sample_count'] = samples_for_material(self.object, active_ws).count()
        context['attachments'] = material_attachments_for_material(
            self.object,
            active_ws,
        )[:5]
        context['properties'] = (
            self.object.properties.select_related('property', 'property__group')
            .prefetch_related('property__choices')
            .order_by(
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


class MaterialTagsUpdateView(
    AppViewMixin,
    PermissionRequiredMixin,
    MaterialEditableMixin,
    UpdateView,
):
    """Сохранение тегов с карточки материала без полной формы редактирования."""

    permission_codename = WorkspacePerm.MATERIAL_EDIT
    model = Material
    form_class = MaterialTagsForm
    http_method_names = ['post']
    context_object_name = 'material'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        workspace = self.request.active_workspace
        if (
            is_material_linked_to_workspace(obj, workspace)
            or not obj.is_editable_in(workspace)
        ):
            raise PermissionDenied
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        material = self.object
        kwargs['workspace'] = material.home_workspace or self.request.active_workspace
        return kwargs


    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Теги материала сохранены.')
        return redirect('materials:detail', pk=self.object.pk)

    def form_invalid(self, form):
        for error in form.errors.get('tag_names', form.non_field_errors()):
            messages.error(self.request, error)
        return redirect('materials:detail', pk=self.object.pk)


class MaterialLinkView(AppViewMixin, PermissionRequiredMixin, View):
    permission_codename = WorkspacePerm.MATERIAL_CREATE
    http_method_names = ['post']

    def post(self, request, pk):
        source = get_object_or_404(
            materials_visible_in(request.active_workspace).select_related('struct_type'),
            pk=pk,
        )
        try:
            material = link_material_to_workspace(source, request.active_workspace, request.user)
        except PermissionError:
            raise PermissionDenied

        messages.success(
            request,
            f'Материал «{material.code}» добавлен в пространство как ссылка.',
        )
        return redirect('materials:detail', pk=material.pk)


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


def _serialize_material_property(item):
    from apps.references.models import Property

    linked = None
    value = item.value
    if item.property.data_type == 'number':
        value = item.display_value()
    elif item.property.data_type == Property.MATERIAL_LINK_DATA_TYPE:
        linked = item.linked_material()
        if linked is not None:
            value = f'{linked.code} - {linked.name}'
    elif item.property.data_type == Property.CHOICE_DATA_TYPE:
        value = item.choice_display_value()
    return {
        'property_id': str(item.property_id),
        'display_name': item.property.display_name,
        'unit': item.property.effective_unit(),
        'data_type': item.property.data_type,
        'value': value,
        'value_kind': item.value_kind,
        'value_b': str(item.value_b) if item.value_b is not None else None,
        'material_id': str(linked.pk) if linked is not None else None,
    }


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
                'properties': [_serialize_material_property(item) for item in properties],
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
        if not can_manage_material_visibility(
            self.request.user,
            obj,
            self.request.active_workspace,
        ):
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


def _import_debug_context(request):
    batch = get_last_import_debug_batch(request.session)
    workspace = request.active_workspace
    show = bool(
        settings.IMPORT_BATCH_UNDO
        and batch
        and batch.get('workspace_slug') == workspace.slug
        and batch.get('materials')
    )
    return {
        'show_import_debug_undo': show,
        'import_debug_batch': batch if show else None,
        'import_debug_count': len(batch.get('materials') or []) if show else 0,
    }


class MaterialImportView(AppViewMixin, PermissionRequiredMixin, FormView):
    """Мастер: файл → лист → маппинг → staging/review → применение."""

    permission_codename = WorkspacePerm.MATERIAL_CREATE
    template_name = 'materials/material_import.html'
    form_class = MaterialImportForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.request.session
        path = get_import_session_path(session)
        config = get_import_config(session)
        context['workspace'] = self.request.active_workspace
        context['staged_filename'] = get_import_session_name(session)
        context['has_staged_file'] = path is not None
        context['import_report'] = getattr(self, 'import_report', None)
        context['step'] = getattr(self, 'wizard_step', 'upload')
        wizard_steps = (
            ('upload', 'Загрузка'),
            ('configure', 'Лист и уникальность'),
            ('mapping', 'Сопоставление колонок'),
            ('review', 'Запись'),
        )
        step_key = 'review' if context['step'] == 'iterate' else context['step']
        step_num = 1
        step_label = wizard_steps[0][1]
        for index, (key, label) in enumerate(wizard_steps, start=1):
            if key == step_key:
                step_num = index
                step_label = label
                break
        context['wizard_steps'] = wizard_steps
        context['wizard_step_num'] = step_num
        context['wizard_step_total'] = len(wizard_steps)
        context['wizard_step_label'] = step_label
        context['wizard_step_percent'] = int(round(100 * step_num / len(wizard_steps)))
        context['sheet_names'] = getattr(self, 'sheet_names', [])
        context['config'] = config
        context['wide_table'] = getattr(self, 'wide_table', None)
        context['mapping_rows'] = getattr(self, 'mapping_rows', [])
        context['target_choices'] = getattr(self, 'target_choices', mapping_choices())
        context['mapping_catalog_groups'] = getattr(self, 'mapping_catalog_groups', [])
        context['required_import_targets'] = getattr(self, 'required_import_targets', [])
        context['missing_required_targets'] = getattr(self, 'missing_required_targets', [])
        context['duplicate_mapping_targets'] = getattr(self, 'duplicate_mapping_targets', [])
        context['required_target_keys'] = {
            target for target, _label in context['required_import_targets']
        }
        context['parse_modes'] = PARSE_MODES_SHORT
        context['match_policies'] = MATCH_POLICIES
        context['draft_rows'] = getattr(self, 'draft_rows', [])
        context['profiles'] = MaterialImportProfile.objects.filter(
            workspace=self.request.active_workspace,
        ).order_by('name')
        draft_rows = context['draft_rows']
        context['uncertain_count'] = sum(
            1 for d in draft_rows if getattr(d, 'has_uncertain', False)
        )
        context['draft_create_count'] = sum(1 for d in draft_rows if d.action == 'create')
        context['draft_update_count'] = sum(1 for d in draft_rows if d.action == 'update')
        context['draft_skip_count'] = sum(1 for d in draft_rows if d.action == 'skip')
        has_errors = bool(
            getattr(self, 'import_report', None) and not self.import_report.ok
        )
        context['import_has_errors'] = has_errors
        # При ошибках валидации запись запрещена — только возврат к сопоставлению.
        context['can_apply'] = bool(draft_rows) and not has_errors
        context['layout_hint'] = getattr(self, 'layout_hint', '')
        context['detected_layout'] = getattr(self, 'detected_layout', None)
        context['structure_types'] = getattr(
            self,
            'structure_types',
            StructureType.objects.filter(is_active=True, is_created=True).order_by('name'),
        )
        context['selected_structure_type'] = getattr(self, 'selected_structure_type', None)
        context['iterate_draft'] = getattr(self, 'iterate_draft', None)
        context['iterate_index'] = getattr(self, 'iterate_index', None)
        context['iterate_position'] = getattr(self, 'iterate_position', 0)
        context['iterate_total'] = getattr(self, 'iterate_total', 0)
        context['iterate_done'] = getattr(self, 'iterate_done', 0)
        context['iterate_percent'] = getattr(self, 'iterate_percent', 0)
        context['iterate_log'] = getattr(self, 'iterate_log', [])
        context['iterate_report'] = getattr(self, 'iterate_report', None)
        context['show_structure_type_error'] = getattr(self, 'show_structure_type_error', False)
        context['show_mapping_errors'] = getattr(self, 'show_mapping_errors', False)
        context.update(_import_debug_context(self.request))
        return context

    def _importable_structure_types(self):
        return StructureType.objects.filter(is_active=True, is_created=True).order_by('name')

    def _resolve_structure_type(self, config):
        raw = (config.get('structure_type_id') or '').strip()
        if not raw:
            return None
        return self._importable_structure_types().filter(pk=raw).first()

    def _structure_fields_for_config(self, config):
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            return [], None
        fields = list(
            StructureField.objects.filter(structure_type=structure_type).order_by('sort_order', 'label')
        )
        return fields, structure_type

    def get(self, request, *args, **kwargs):
        if request.GET.get('cancel') == '1':
            clear_import_session(request.session, delete_file=True)
            messages.info(request, 'Импорт сброшен.')
            return redirect('materials:import')
        path = get_import_session_path(request.session)
        if path is None:
            self.wizard_step = 'upload'
            return super().get(request, *args, **kwargs)
        config = get_import_config(request.session)
        step = request.GET.get('step')
        if step == 'configure' or not config.get('mapping'):
            return self._render_configure(request, path)
        if step == 'mapping':
            return self._render_mapping(request, path)
        if step == 'review':
            return self._render_review(request, path)
        if step == 'iterate' or is_iterate_active(request.session):
            return self._render_iterate(request, path)
        if config.get('draft'):
            return self._render_review(request, path)
        return self._render_mapping(request, path)

    def post(self, request, *args, **kwargs):
        action = (request.POST.get('action') or '').strip()
        # Если action потерялся (например, submit-кнопка стала disabled до отправки),
        # не сбрасываем сессию через upload — возвращаем к текущему шагу.
        if not action:
            path = get_import_session_path(request.session)
            if path is None:
                action = 'upload'
            else:
                config = get_import_config(request.session)
                messages.error(
                    request,
                    'Не удалось определить действие формы. Повторите шаг ещё раз.',
                )
                if config.get('draft'):
                    return self._render_review(request, path)
                if config.get('mapping'):
                    return self._render_mapping(request, path)
                return self._render_configure(request, path)
        handlers = {
            'upload': self._handle_upload,
            'configure': self._handle_configure,
            'map_preview': self._handle_map_preview,
            'map_iterate': self._handle_map_iterate,
            'review_apply': self._handle_review_apply,
            'review_recheck': self._handle_review_recheck,
            'review_iterate_start': self._handle_review_iterate_start,
            'iterate_apply': self._handle_iterate_apply,
            'iterate_skip': self._handle_iterate_skip,
            'iterate_finish': self._handle_iterate_finish,
            'iterate_back_review': self._handle_iterate_back_review,
            'save_profile': self._handle_save_profile,
            'load_profile': self._handle_load_profile,
            'undo_last_import': self._handle_undo_last_import,
        }
        handler = handlers.get(action)
        if handler is None:
            messages.error(request, 'Неизвестное действие.')
            return redirect('materials:import')
        return handler(request)

    def _handle_upload(self, request):
        form = self.get_form()
        if not form.is_valid():
            self.wizard_step = 'upload'
            return self.form_invalid(form)
        try:
            temp_path = save_uploaded_import_file(form.cleaned_data['file'])
        except ValueError as exc:
            form.add_error('file', str(exc))
            self.wizard_step = 'upload'
            return self.form_invalid(form)
        original_name = Path(form.cleaned_data['file'].name or 'import.csv').name
        store_import_session(request.session, temp_path=temp_path, original_name=original_name)
        suffix = temp_path.suffix.lower()
        sheets = list_sheet_names(temp_path) if suffix != '.csv' else ['CSV']
        sheet = sheets[0] if sheets else ''
        default_header, default_group = detect_header_layout(temp_path, sheet_name=sheet)
        set_import_config(
            request.session,
            sheet=sheet,
            header_row=default_header,
            group_row=default_group,
            mapping={},
            match_policy=MATCH_BY_NAME,
            mode='mapped',
            clear_draft=True,
        )
        messages.info(
            request,
            'Файл загружен. Для большой таблицы Excel обычно: строка заголовков = 2, строка групп = 1. '
            'В сопоставлении должна быть колонка «Наименование» → поле «Название».',
        )
        return redirect('materials:import')

    def _handle_configure(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return redirect('materials:import')
        try:
            header_row = int(request.POST.get('header_row') or 1)
            group_raw = (request.POST.get('group_row') or '').strip()
            group_row = int(group_raw) if group_raw else 0
        except ValueError:
            messages.error(request, 'Номера строк должны быть числами.')
            return self._render_configure(request, path)
        match_policy = (request.POST.get('match_policy') or MATCH_BY_NAME).strip()
        sheet = (request.POST.get('sheet') or '').strip()
        structure_type_id = (request.POST.get('structure_type_id') or '').strip()
        if not structure_type_id:
            messages.error(request, 'Выберите тип структуры для импорта.')
            self.show_structure_type_error = True
            return self._render_configure(request, path)
        if not self._importable_structure_types().filter(pk=structure_type_id).exists():
            messages.error(request, 'Выбранный тип структуры недоступен.')
            self.show_structure_type_error = True
            return self._render_configure(request, path)
        set_import_config(
            request.session,
            sheet=sheet,
            header_row=header_row,
            group_row=group_row,
            match_policy=match_policy,
            structure_type_id=structure_type_id,
            mapping={},
            clear_draft=True,
        )
        return self._render_mapping(request, path)

    def _save_mapping_from_post(self, request, path):
        """Сохраняет маппинг из POST. Возвращает path-response при ошибке, иначе None."""
        mapping = {}
        for key, value in request.POST.items():
            if not key.startswith('map_'):
                continue
            try:
                col_index = int(key.removeprefix('map_'))
            except ValueError:
                continue
            parse_mode = request.POST.get(f'parse_{col_index}') or 'auto'
            mapping[str(col_index)] = {
                'target': value or TARGET_SKIP,
                'parse': parse_mode,
            }
        match_policy = (request.POST.get('match_policy') or MATCH_BY_NAME).strip()
        set_import_config(request.session, mapping=mapping, match_policy=match_policy)
        targets = [normalize_mapping_entry(v)[0] for v in mapping.values()]
        if TARGET_NAME not in targets:
            messages.error(
                request,
                'Сопоставьте колонку «Наименование» (или аналог) с полем «Название». '
                'Если такой колонки нет в списке — вернитесь к настройке листа: '
                'строка заголовков = 2, строка групп = 1.',
            )
            self.show_mapping_errors = True
            return self._render_mapping(request, path)

        config = get_import_config(request.session)
        try:
            table = self._load_table(path, config)
        except (ValueError, FileNotFoundError) as exc:
            messages.error(request, str(exc))
            return self._render_configure(request, path)
        label_by_index = {str(column.index): column.display for column in table.columns}
        mapping_rows = [
            {
                'target': normalize_mapping_entry(entry)[0],
                'column_label': label_by_index.get(key, f'колонка {key}'),
            }
            for key, entry in mapping.items()
        ]
        duplicates = find_duplicate_mapping_targets(mapping_rows)
        if duplicates:
            details = '; '.join(
                f'{item["target"]} ← {", ".join(item["columns"])}'
                for item in duplicates[:5]
            )
            messages.error(
                request,
                'Нельзя сопоставлять несколько колонок с одним полем или свойством — '
                'непонятно, какое значение записывать. '
                f'Исправьте: {details}. '
                'Вторую колонку назначьте на другое поле, доп. свойство или «пропустить».',
            )
            self.show_mapping_errors = True
            return self._render_mapping(request, path)
        return None

    def _handle_map_preview(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return redirect('materials:import')
        error_response = self._save_mapping_from_post(request, path)
        if error_response is not None:
            return error_response
        return self._build_and_show_review(request, path)

    def _handle_map_iterate(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return redirect('materials:import')
        error_response = self._save_mapping_from_post(request, path)
        if error_response is not None:
            return error_response
        drafts, _structure_type, build_error = self._build_drafts(request, path)
        if build_error is not None:
            return build_error
        if not drafts:
            messages.warning(request, 'Нет строк для построчного импорта.')
            return self._render_mapping(request, path)
        index = start_iterate(request.session, drafts)
        if index is None:
            clear_iterate_session(request.session)
            messages.warning(request, 'Нет строк для построчного импорта (все пропущены).')
            return self._render_review(request, path)
        messages.info(
            request,
            'Построчный режим: проверяйте и записывайте по одной строке. '
            'Уже записанные строки сохраняются даже при ошибке на следующей.',
        )
        return redirect(f"{reverse('materials:import')}?step=iterate")

    def _load_review_drafts(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return None, None, None, redirect('materials:import')
        config = get_import_config(request.session)
        drafts = drafts_from_session(config.get('draft'))
        if not drafts:
            messages.error(request, 'Нет черновика — сначала выполните проверку маппинга.')
            return path, None, None, redirect('materials:import')
        if request.POST.get('review_marker'):
            drafts = apply_review_post(drafts, request.POST)
            set_import_config(request.session, draft=drafts_to_session(drafts))
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            messages.error(request, 'Не выбран тип структуры.')
            return path, None, None, redirect('materials:import')
        return path, drafts, structure_type, None

    def _handle_review_recheck(self, request):
        path, drafts, structure_type, early = self._load_review_drafts(request)
        if early is not None:
            return early
        self.import_report = MaterialImporter(
            workspace=request.active_workspace,
            dry_run=True,
        ).import_drafts(drafts, structure_type=structure_type)
        if self.import_report.ok:
            messages.success(
                request,
                'Перепроверка пройдена. Можно применять импорт или вернуться к сопоставлению.',
            )
        else:
            messages.error(
                request,
                'Ошибки остались. Пропустите проблемные строки, снимите поля в черновике '
                'или вернитесь к сопоставлению колонок.',
            )
        return self._render_review(request, path)

    def _handle_review_apply(self, request):
        path, drafts, structure_type, early = self._load_review_drafts(request)
        if early is not None:
            return early
        report = MaterialImporter(
            workspace=request.active_workspace,
            dry_run=False,
            source_filename=get_import_session_name(request.session),
        ).import_drafts(drafts, structure_type=structure_type)
        if not report.ok:
            self.import_report = report
            messages.error(
                request,
                'Импорт не выполнен: есть ошибки валидации. '
                'Исправьте сопоставление колонок и соберите черновик заново.',
            )
            return self._render_review(request, path)
        if report.affected_material_ids:
            store_last_import_debug_batch(
                request.session,
                workspace=request.active_workspace,
                material_ids=report.affected_material_ids,
            )
        clear_import_session(request.session, delete_file=True)
        messages.success(
            request,
            'Импорт выполнен: '
            f'материалов создано {report.materials_created}, обновлено {report.materials_updated}; '
            f'свойств создано {report.properties_created}, обновлено {report.properties_updated}.'
            + (
                f' Отладка: можно удалить {len(report.affected_material_ids)} материал(ов) одной кнопкой.'
                if settings.IMPORT_BATCH_UNDO and report.affected_material_ids
                else ''
            ),
        )
        return redirect('materials:list')

    def _handle_review_iterate_start(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return redirect('materials:import')
        config = get_import_config(request.session)
        drafts = drafts_from_session(config.get('draft'))
        if not drafts:
            messages.error(request, 'Нет черновика — сначала выполните проверку маппинга.')
            return redirect('materials:import')
        drafts = apply_review_post(drafts, request.POST)
        set_import_config(request.session, draft=drafts_to_session(drafts))
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            messages.error(request, 'Не выбран тип структуры.')
            return redirect('materials:import')
        report = MaterialImporter(
            workspace=request.active_workspace,
            dry_run=True,
        ).import_drafts(drafts, structure_type=structure_type)
        if not report.ok:
            self.import_report = report
            messages.error(
                request,
                'Построчный режим недоступен: есть ошибки валидации. '
                'Исправьте сопоставление колонок.',
            )
            return self._render_review(request, path)
        index = start_iterate(request.session, drafts)
        if index is None:
            clear_iterate_session(request.session)
            messages.warning(request, 'Нет строк для построчного импорта (все пропущены).')
            return self._render_review(request, path)
        messages.info(
            request,
            'Построчный режим: проверяйте и записывайте по одной строке. '
            'Уже записанные строки сохраняются даже при ошибке на следующей.',
        )
        return redirect(f"{reverse('materials:import')}?step=iterate")

    def _handle_iterate_apply(self, request):
        path = get_import_session_path(request.session)
        if path is None or not is_iterate_active(request.session):
            return redirect('materials:import')
        config = get_import_config(request.session)
        drafts = drafts_from_session(config.get('draft'))
        index = get_iterate_index(request.session)
        if index is None or index < 0 or index >= len(drafts):
            messages.error(request, 'Текущая строка построчного импорта не найдена.')
            clear_iterate_session(request.session)
            return self._render_review(request, path)
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            messages.error(request, 'Не выбран тип структуры.')
            return redirect('materials:import')

        draft = apply_iterate_row_post(drafts[index], request.POST)
        if draft.existing_pk:
            draft.action = 'update'
        else:
            draft.action = 'create'
        drafts[index] = draft
        set_import_config(request.session, draft=drafts_to_session(drafts))

        report = MaterialImporter(
            workspace=request.active_workspace,
            dry_run=False,
            source_filename=get_import_session_name(request.session),
        ).import_drafts([draft], structure_type=structure_type)
        if not report.ok:
            self.iterate_report = report
            append_iterate_log(
                request.session,
                {
                    'source_row': draft.source_row,
                    'code': draft.code,
                    'name': draft.name,
                    'status': 'error',
                    'message': '; '.join(item.message for item in report.errors[:3]),
                },
            )
            messages.error(request, 'Строка не записана — исправьте данные или пропустите.')
            return self._render_iterate(request, path)

        append_iterate_material_ids(request.session, report.affected_material_ids)
        append_iterate_log(
            request.session,
            {
                'source_row': draft.source_row,
                'code': draft.code,
                'name': draft.name,
                'status': 'applied',
                'message': (
                    f'создано {report.materials_created}, обновлено {report.materials_updated}'
                ),
            },
        )
        drafts[index].action = 'skip'
        set_import_config(request.session, draft=drafts_to_session(drafts))
        nxt = next_active_index(drafts, start_at=index + 1)
        set_iterate_index(request.session, nxt)
        if nxt is None:
            return self._finish_iterate(request, done_message='Построчный импорт завершён.')
        messages.success(request, f'Строка {draft.source_row} записана.')
        return redirect(f"{reverse('materials:import')}?step=iterate")

    def _handle_iterate_skip(self, request):
        path = get_import_session_path(request.session)
        if path is None or not is_iterate_active(request.session):
            return redirect('materials:import')
        config = get_import_config(request.session)
        drafts = drafts_from_session(config.get('draft'))
        index = get_iterate_index(request.session)
        if index is None or index < 0 or index >= len(drafts):
            clear_iterate_session(request.session)
            return self._render_review(request, path)
        draft = drafts[index]
        append_iterate_log(
            request.session,
            {
                'source_row': draft.source_row,
                'code': draft.code,
                'name': draft.name,
                'status': 'skipped',
                'message': 'пропущено оператором',
            },
        )
        drafts[index].action = 'skip'
        set_import_config(request.session, draft=drafts_to_session(drafts))
        nxt = next_active_index(drafts, start_at=index + 1)
        set_iterate_index(request.session, nxt)
        if nxt is None:
            return self._finish_iterate(request, done_message='Построчный импорт завершён.')
        return redirect(f"{reverse('materials:import')}?step=iterate")

    def _handle_iterate_finish(self, request):
        return self._finish_iterate(request, done_message='Построчный импорт остановлен.')

    def _handle_iterate_back_review(self, request):
        material_ids = get_iterate_material_ids(request.session)
        if material_ids:
            store_last_import_debug_batch(
                request.session,
                workspace=request.active_workspace,
                material_ids=material_ids,
            )
        clear_iterate_session(request.session)
        path = get_import_session_path(request.session)
        if path is None:
            return redirect('materials:import')
        messages.info(
            request,
            'Построчный режим закрыт. Можно применить пакетно или вернуться к сопоставлению.',
        )
        return self._render_review(request, path)

    def _finish_iterate(self, request, *, done_message: str):
        material_ids = get_iterate_material_ids(request.session)
        log = get_iterate_log(request.session)
        applied = sum(1 for item in log if item.get('status') == 'applied')
        skipped = sum(1 for item in log if item.get('status') == 'skipped')
        errors = sum(1 for item in log if item.get('status') == 'error')
        if material_ids:
            store_last_import_debug_batch(
                request.session,
                workspace=request.active_workspace,
                material_ids=material_ids,
            )
        clear_import_session(request.session, delete_file=True)
        messages.success(
            request,
            f'{done_message} Записано: {applied}, пропущено: {skipped}, ошибок: {errors}.'
            + (
                f' Отладка: можно удалить {len(material_ids)} материал(ов) одной кнопкой.'
                if settings.IMPORT_BATCH_UNDO and material_ids
                else ''
            ),
        )
        return redirect('materials:list')

    def _handle_undo_last_import(self, request):
        if not settings.IMPORT_BATCH_UNDO:
            messages.error(
                request,
                'Откат импорта выключен. Включите IMPORT_BATCH_UNDO=true или DEBUG=True.',
            )
            return redirect('materials:list')
        result = undo_last_import_debug_batch(
            request.session,
            workspace=request.active_workspace,
        )
        if result.ok:
            messages.success(request, f'Откат импорта: {result.message}')
        else:
            messages.error(request, result.message)
        # Always land on list page 1 — POST next often keeps ?page=N which 404s after delete.
        return redirect('materials:list')

    def _handle_save_profile(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            return redirect('materials:import')
        name = (request.POST.get('profile_name') or '').strip()
        if not name:
            messages.error(request, 'Укажите название профиля.')
            return self._render_mapping(request, path)
        config = get_import_config(request.session)
        # enrich labels
        table = self._load_table(path, config)
        mapping = config.get('mapping') or {}
        for col in table.columns:
            key = str(col.index)
            if key in mapping and isinstance(mapping[key], dict):
                mapping[key]['label'] = col.display
        payload = profile_payload_from_mapping(
            mapping,
            sheet=config.get('sheet'),
            header_row=config.get('header_row'),
            group_row=config.get('group_row'),
            match_policy=config.get('match_policy'),
            structure_type_id=config.get('structure_type_id'),
        )
        MaterialImportProfile.objects.update_or_create(
            workspace=request.active_workspace,
            name=name,
            defaults={'config': payload},
        )
        messages.success(request, f'Профиль «{name}» сохранён.')
        return self._render_mapping(request, path)

    def _handle_load_profile(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            return redirect('materials:import')
        profile_id = request.POST.get('profile_id')
        profile = get_object_or_404(
            MaterialImportProfile,
            pk=profile_id,
            workspace=request.active_workspace,
        )
        config = get_import_config(request.session)
        table = self._load_table(path, config)
        mapping = apply_profile_to_columns(table.columns, profile.config.get('columns') or [])
        set_import_config(
            request.session,
            mapping=mapping,
            match_policy=profile.config.get('match_policy') or MATCH_BY_NAME,
            structure_type_id=profile.config.get('structure_type_id') or '',
            header_row=int(profile.config.get('header_row') or config.get('header_row') or 1),
            group_row=int(profile.config.get('group_row') or 0),
            clear_draft=True,
        )
        messages.success(request, f'Загружен профиль «{profile.name}». Проверьте сопоставление.')
        return self._render_mapping(request, path)

    def _build_drafts(self, request, path):
        """
        Собирает черновик из текущего маппинга сессии.
        Возвращает (drafts, structure_type, error_response).
        error_response не None — нужно вернуть его клиенту.
        """
        config = get_import_config(request.session)
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            messages.error(request, 'Выберите тип структуры перед сборкой черновика.')
            self.show_structure_type_error = True
            return None, None, self._render_configure(request, path)
        table = self._load_table(path, config)
        structure_fields, _ = self._structure_fields_for_config(config)
        mapping_rows = []
        properties = list(Property.objects.order_by('display_name', 'name'))
        stored = config.get('mapping') or {}
        claimed_targets: set[str] = set()
        for column in table.columns:
            key = str(column.index)
            entry = stored.get(key)
            if entry is None:
                target = suggest_target(
                    column,
                    properties,
                    structure_fields,
                    claimed_targets=claimed_targets,
                )
                parse = suggest_parse_mode(
                    column,
                    target,
                    structure_fields=structure_fields,
                    properties=properties,
                )
            else:
                target, parse = normalize_mapping_entry(entry)
            if not target_allows_multiple_columns(target):
                claimed_targets.add(target)
            mapping_rows.append({'column': column, 'target': target, 'parse': parse})
        mapping = mapping_for_session(mapping_rows)
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=request.active_workspace,
            match_policy=config.get('match_policy') or MATCH_BY_NAME,
            structure_type_id=str(structure_type.pk),
        )
        clear_iterate_session(request.session)
        set_import_config(request.session, mapping=mapping, draft=drafts_to_session(drafts))
        return drafts, structure_type, None

    def _build_and_show_review(self, request, path):
        drafts, structure_type, build_error = self._build_drafts(request, path)
        if build_error is not None:
            return build_error
        self.import_report = MaterialImporter(
            workspace=request.active_workspace,
            dry_run=True,
        ).import_drafts(drafts, structure_type=structure_type)
        uncertain = sum(1 for d in drafts if d.has_uncertain)
        if self.import_report.ok and uncertain:
            messages.warning(
                request,
                f'Черновик готов, но {uncertain} строк(и) содержат сомнительные значения — проверьте.',
            )
        elif self.import_report.ok:
            messages.success(request, 'Черновик готов. Проверьте строки и примените импорт.')
        else:
            messages.error(request, 'В черновике есть ошибки валидации.')
        return self._render_review(request, path)

    def _render_configure(self, request, path):
        try:
            self.sheet_names = list_sheet_names(path)
        except ValueError as exc:
            messages.error(request, str(exc))
            clear_import_session(request.session, delete_file=True)
            return redirect('materials:import')
        config = get_import_config(request.session)
        sheet = config.get('sheet') or (self.sheet_names[0] if self.sheet_names else '')
        detected_header, detected_group = detect_header_layout(path, sheet_name=sheet)
        self.detected_layout = {'header_row': detected_header, 'group_row': detected_group}
        # превью первых строк листа для выбора заголовков
        try:
            preview_table = load_wide_table(
                path,
                sheet_name=sheet or None,
                header_row=detected_header,
                group_row=detected_group or None,
                max_preview=3,
            )
            self.layout_hint = (
                f'Авто: заголовки={detected_header}, группы={detected_group or "нет"}; '
                f'колонок={len(preview_table.columns)}. '
                f'Должны быть «Наименование», «Марка»…'
            )
        except (ValueError, FileNotFoundError):
            self.layout_hint = ''
        self.structure_types = self._importable_structure_types()
        self.selected_structure_type = self._resolve_structure_type(config)
        self.wizard_step = 'configure'
        return self.render_to_response(self.get_context_data(form=self.get_form_class()()))

    def _render_mapping(self, request, path):
        config = get_import_config(request.session)
        structure_fields, structure_type = self._structure_fields_for_config(config)
        if structure_type is None:
            messages.error(request, 'Выберите тип структуры.')
            self.show_structure_type_error = True
            return self._render_configure(request, path)
        properties = list(Property.objects.order_by('display_name', 'name'))
        match_policy = config.get('match_policy') or MATCH_BY_NAME
        self.target_choices = mapping_choices(
            properties,
            structure_fields,
            match_policy=match_policy,
        )
        self.mapping_catalog_groups = mapping_catalog_groups(self.target_choices)
        self.required_import_targets = required_import_targets(match_policy)
        self.selected_structure_type = structure_type
        try:
            self.wide_table = self._load_table(path, config)
        except (ValueError, FileNotFoundError) as exc:
            messages.error(request, str(exc))
            return self._render_configure(request, path)

        stored = config.get('mapping') or {}
        sample = self.wide_table.preview_rows[0] if self.wide_table.preview_rows else {}
        mapping_rows = []
        claimed_targets: set[str] = set()
        required_keys = {t for t, _ in self.required_import_targets}
        target_labels = dict(self.target_choices)
        for column in self.wide_table.columns:
            key = str(column.index)
            if key in stored:
                target, parse = normalize_mapping_entry(stored[key])
            else:
                target = suggest_target(
                    column,
                    properties,
                    structure_fields,
                    claimed_targets=claimed_targets,
                )
                parse = suggest_parse_mode(
                    column,
                    target,
                    structure_fields=structure_fields,
                    properties=properties,
                )
            if not target_allows_multiple_columns(target):
                claimed_targets.add(target)
            sample_value = sample.get(column.index)
            if sample_value is not None:
                sample_text = str(sample_value).replace('\n', ' ').strip()
                if len(sample_text) > 80:
                    sample_text = sample_text[:77] + '…'
            else:
                sample_text = '—'
            mapping_rows.append({
                'column': column,
                'target': target,
                'parse': parse,
                'sample': sample_text,
                'is_required_target': target in required_keys,
                'target_label': target_labels.get(target, target_labels.get(TARGET_SKIP, '— пропустить —')),
            })
        self.mapping_rows = mapping_rows
        self.missing_required_targets = missing_required_targets(
            mapping_rows,
            match_policy=match_policy,
        )
        self.duplicate_mapping_targets = find_duplicate_mapping_targets(mapping_rows)
        self.sheet_names = list_sheet_names(path)
        self.wizard_step = 'mapping'
        if not stored:
            set_import_config(request.session, mapping=mapping_for_session(mapping_rows))
        return self.render_to_response(self.get_context_data(form=self.get_form_class()()))

    def _render_review(self, request, path):
        config = get_import_config(request.session)
        structure_type = self._resolve_structure_type(config)
        self.draft_rows = drafts_from_session(config.get('draft'))
        if not self.draft_rows:
            return self._build_and_show_review(request, path)
        if structure_type is None:
            messages.error(request, 'Не выбран тип структуры.')
            return self._render_configure(request, path)
        # Не перетираем отчёт, если его уже посчитали в этом запросе (apply/recheck).
        if getattr(self, 'import_report', None) is None:
            self.import_report = MaterialImporter(
                workspace=request.active_workspace,
                dry_run=True,
            ).import_drafts(self.draft_rows, structure_type=structure_type)
        self.selected_structure_type = structure_type
        self.wizard_step = 'review'
        self.sheet_names = list_sheet_names(path)
        try:
            self.wide_table = self._load_table(path, config)
        except (ValueError, FileNotFoundError):
            self.wide_table = None
        return self.render_to_response(self.get_context_data(form=self.get_form_class()()))

    def _render_iterate(self, request, path):
        if not is_iterate_active(request.session):
            return self._render_review(request, path)
        config = get_import_config(request.session)
        drafts = drafts_from_session(config.get('draft'))
        index = get_iterate_index(request.session)
        if index is None or index < 0 or index >= len(drafts):
            nxt = next_active_index(drafts, start_at=0)
            if nxt is None:
                return self._finish_iterate(request, done_message='Построчный импорт завершён.')
            set_iterate_index(request.session, nxt)
            index = nxt
        structure_type = self._resolve_structure_type(config)
        self.selected_structure_type = structure_type
        self.iterate_draft = drafts[index]
        self.iterate_index = index
        position, total, done, percent = iterate_progress(request.session, drafts)
        self.iterate_position = position
        self.iterate_total = total
        self.iterate_done = done
        self.iterate_percent = percent
        self.iterate_log = get_iterate_log(request.session)
        self.draft_rows = drafts
        self.wizard_step = 'iterate'
        if getattr(self, 'iterate_report', None) is None and structure_type is not None:
            self.iterate_report = MaterialImporter(
                workspace=request.active_workspace,
                dry_run=True,
            ).import_drafts([self.iterate_draft], structure_type=structure_type)
        return self.render_to_response(self.get_context_data(form=self.get_form_class()()))

    def _load_table(self, path, config):
        group_row = config.get('group_row')
        return load_wide_table(
            path,
            sheet_name=config.get('sheet') or None,
            header_row=config.get('header_row') or 1,
            group_row=int(group_row) if group_row else None,
        )


class MaterialImportExampleView(AppViewMixin, PermissionRequiredMixin, View):
    permission_codename = WorkspacePerm.MATERIAL_CREATE
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        examples_dir = Path(__file__).resolve().parent / 'fixtures' / 'import_examples'
        kind = (request.GET.get('kind') or 'wide').strip().lower()
        if kind == 'cli':
            path = examples_dir / 'materials_sample.csv'
            filename = 'materials_import_example.csv'
            content_type = 'text/csv; charset=utf-8'
        elif kind == 'csv':
            path = examples_dir / 'materials_wide_demo.csv'
            filename = 'materials_wide_demo.csv'
            content_type = 'text/csv; charset=utf-8'
        else:
            path = examples_dir / 'materials_wide_demo.xlsx'
            filename = 'materials_wide_demo.xlsx'
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        if not path.is_file():
            raise Http404('Пример файла не найден')
        return FileResponse(
            path.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )
