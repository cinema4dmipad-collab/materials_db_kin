import logging
from pathlib import Path

from django.conf import settings
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.core.paginator import InvalidPage
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView, View

logger = logging.getLogger(__name__)

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    CREATOR_WITH_LABEL_FILTER,
    STRUCT_TYPE_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
)
from apps.core.creator import assign_creator
from apps.materials.bulk import bulk_delete_materials
from apps.materials.export import (
    EXPORT_ROW_LIMIT,
    MaterialExportError,
    materials_xlsx_response,
)
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
    addon_catalog_groups,
    apply_profile_to_columns,
    build_field_mapping_rows,
    import_templates_for_workspace,
    mapping_choices,
    mapping_catalog_groups,
    mapping_for_session,
    find_duplicate_mapping_targets,
    missing_required_targets,
    normalize_mapping_entry,
    primary_import_targets,
    profile_payload_from_mapping,
    required_import_targets,
    target_allows_multiple_columns,
    suggest_parse_mode,
    suggest_target,
    unused_columns_from_mapping,
)
from apps.materials.imports.service import MaterialImporter
from apps.materials.imports.staging import (
    MATCH_ALWAYS_CREATE,
    MATCH_POLICIES,
    MATCH_BY_NAME,
    DUPLICATE_NAME_PREFIX,
    DUPLICATE_NAME_SKIP,
    apply_duplicate_name_policy,
    apply_review_post,
    apply_unrecognized_ignore_all,
    apply_unrecognized_manual_fixes,
    build_review_fix_grid,
    build_staging_draft,
    drafts_from_session,
    drafts_to_session,
    has_unresolved_unrecognized,
    iter_unrecognized_fields,
    merge_default_tags_into_drafts,
    name_collisions_for_drafts,
)
from apps.materials.imports.upload import (
    SESSION_ACTIVE_TEMPLATE_ID,
    clear_import_session,
    get_import_config,
    get_import_session_name,
    get_import_session_path,
    save_uploaded_import_file,
    set_import_config,
    store_import_session,
)
from apps.materials.imports.value_parse import PARSE_MODES_SHORT
from apps.materials.imports.wide import (
    build_import_layout_schema,
    detect_header_layout,
    list_sheet_names,
    load_wide_table,
)
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
        ('manufacturer', 'manufacturer_id'),
        ('availability', 'availability_id'),
        ('technology', 'technology_id'),
        ('import_source', 'import_source_filename'),
    )
    choice_filter_labels = {
        'struct_type': 'Тип структуры',
        'manufacturer': 'Производитель',
        'availability': 'Доступность',
        'technology': 'Технология',
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
            base_qs.select_related(
                'struct_type',
                'home_workspace',
                'created_by_user',
                'manufacturer',
                'availability',
                'technology',
            ).prefetch_related('tags')
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
        from apps.references.models import Availability, Manufacturer, Technology

        return {
            'struct_type': list(
                structure_types_visible_in(workspace)
                .order_by('name')
                .values_list('pk', 'name')
            ),
            'manufacturer': list(
                Manufacturer.objects.order_by('name').values_list('pk', 'name')
            ),
            'availability': list(
                Availability.objects.order_by('name').values_list('pk', 'name')
            ),
            'technology': list(
                Technology.objects.order_by('name').values_list('pk', 'name')
            ),
            'import_source': [(name, name) for name in import_sources],
        }


class MaterialExportView(AppViewMixin, View):
    """Download selected materials as a convenient XLSX table."""

    def _wants_json(self, request) -> bool:
        # Native form download opens a new tab; prefer flash+redirect there.
        # JSON only when the client explicitly asks (tests / tooling).
        accept = (request.headers.get('Accept') or '').lower()
        if 'application/json' in accept and 'text/html' not in accept:
            return True
        return request.GET.get('format') == 'json'

    def _error_response(self, request, message: str, *, status: int = 400):
        if self._wants_json(request):
            return JsonResponse({'ok': False, 'error': message}, status=status)
        messages.warning(request, message)
        return redirect('materials:list')

    def get(self, request, *args, **kwargs):
        return self._error_response(
            request,
            'Чтобы выгрузить материалы в Excel, нажмите «Выбрать», отметьте строки '
            'одного типа структуры и снова «Выгрузить в Excel».',
            status=405,
        )

    def _parse_ids(self, request) -> list:
        raw = request.POST.getlist('ids')
        seen: set[str] = set()
        ids = []
        for value in raw:
            key = (value or '').strip()
            if not key or key in seen:
                continue
            seen.add(key)
            ids.append(key)
            if len(ids) >= EXPORT_ROW_LIMIT:
                break
        return ids

    def post(self, request, *args, **kwargs):
        ids = self._parse_ids(request)
        if not ids:
            return self._error_response(
                request,
                'Сначала выберите материалы в списке, затем нажмите «Выгрузить в Excel».',
            )

        workspace = request.active_workspace
        scope = (request.POST.get('scope') or MATERIAL_SCOPE_WORKSPACE).strip()
        if scope not in MATERIAL_SCOPE_CHOICES:
            scope = MATERIAL_SCOPE_WORKSPACE
        if scope == MATERIAL_SCOPE_SHARED:
            base_qs = materials_shared_in(workspace)
        else:
            base_qs = materials_in_workspace_tab(workspace)

        queryset = base_qs.filter(pk__in=ids)
        if not queryset.exists():
            return self._error_response(
                request,
                'Среди выбранных нет материалов, доступных для выгрузки.',
            )

        order_map = {str(pk): index for index, pk in enumerate(ids)}
        ordered_pks = sorted(
            queryset.values_list('pk', flat=True),
            key=lambda pk: order_map.get(str(pk), 10**9),
        )
        stamp = timezone.localdate().isoformat()
        try:
            return materials_xlsx_response(
                queryset,
                row_limit=EXPORT_ROW_LIMIT,
                filename=f'materials_{stamp}.xlsx',
                preferred_order=ordered_pks,
            )
        except MaterialExportError as exc:
            return self._error_response(request, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception('Material Excel export failed')
            return self._error_response(
                request,
                'Не удалось сформировать файл Excel. Попробуйте ещё раз или уменьшите выборку.',
                status=500,
            )


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
            .select_related(
                'struct_type',
                'home_workspace',
                'manufacturer',
                'availability',
                'technology',
            )
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


class MaterialBulkDeleteView(AppViewMixin, PermissionRequiredMixin, View):
    """Confirm and delete several materials from the list (select mode)."""

    permission_codename = WorkspacePerm.MATERIAL_DELETE
    template_name = 'materials/material_bulk_confirm_delete.html'
    max_items = 100

    def get(self, request, *args, **kwargs):
        return redirect('materials:list')

    def _parse_ids(self, request) -> list[str]:
        raw = request.POST.getlist('ids')
        seen: set[str] = set()
        ids: list[str] = []
        for value in raw:
            key = (value or '').strip()
            if not key or key in seen:
                continue
            seen.add(key)
            ids.append(key)
            if len(ids) >= self.max_items:
                break
        return ids

    def post(self, request, *args, **kwargs):
        ids = self._parse_ids(request)
        if not ids:
            messages.warning(request, 'Не выбрано ни одного материала.')
            return redirect('materials:list')

        workspace = request.active_workspace
        materials = list(
            materials_visible_in(workspace)
            .filter(pk__in=ids)
            .select_related('struct_type')
            .prefetch_related('used_in_composite_layers__parent_material')
        )
        by_pk = {str(m.pk): m for m in materials}
        ordered = [by_pk[i] for i in ids if i in by_pk]
        deletable = []
        blocked = []
        for material in ordered:
            if not can_delete_in_workspace(request.user, material, workspace):
                blocked.append({'material': material, 'reason': 'нет прав на удаление'})
                continue
            if material.used_in_composite_layers.exists():
                blocked.append(
                    {
                        'material': material,
                        'reason': 'используется как слой в другом материале',
                    }
                )
                continue
            deletable.append(material)

        if request.POST.get('confirm') != '1':
            return self.render_to_response(
                {
                    'deletable': deletable,
                    'blocked': blocked,
                    'ids': [str(m.pk) for m in deletable],
                }
            )

        if not deletable:
            messages.warning(request, 'Нет материалов, которые можно удалить.')
            return redirect('materials:list')

        result = bulk_delete_materials(
            user=request.user,
            workspace=workspace,
            pks=[str(m.pk) for m in deletable],
        )
        if result.deleted_count:
            messages.success(
                request,
                f'Удалено материалов: {result.deleted_count}.',
            )
        if result.skipped_protected:
            messages.warning(
                request,
                'Не удалены (используются как слой): '
                + '; '.join(result.skipped_protected[:5])
                + ('…' if len(result.skipped_protected) > 5 else ''),
            )
        if result.skipped_forbidden:
            messages.warning(
                request,
                'Не удалены (нет прав): '
                + '; '.join(result.skipped_forbidden[:5])
                + ('…' if len(result.skipped_forbidden) > 5 else ''),
            )
        if result.errors:
            messages.error(request, 'Ошибки: ' + '; '.join(result.errors[:3]))
        return redirect('materials:list')

    def render_to_response(self, context):
        from django.template.response import TemplateResponse

        return TemplateResponse(self.request, self.template_name, context)


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


class MaterialImportReviewView(AppViewMixin, PermissionRequiredMixin, View):
    """Канбан: утвержден (inbox) ↔ проверено."""

    permission_codename = WorkspacePerm.MATERIAL_EDIT
    template_name = 'materials/material_import_review.html'

    def get(self, request, *args, **kwargs):
        from apps.core.tag_utils import coalesce_tags_for_display
        from apps.materials.imports.review_status import (
            IMPORT_STATUS_APPROVED,
            IMPORT_STATUS_VERIFIED,
            materials_approved_import_review,
            materials_verified_import_review,
        )

        workspace = request.active_workspace
        approved = list(materials_approved_import_review(workspace, limit=200))
        verified = list(materials_verified_import_review(workspace, limit=80))
        for material in approved + verified:
            material.display_tags = coalesce_tags_for_display(list(material.tags.all()))
        return render(
            request,
            self.template_name,
            {
                'approved_materials': approved,
                'verified_materials': verified,
                'approved_count': len(approved),
                'verified_count': len(verified),
                'status_approved': IMPORT_STATUS_APPROVED,
                'status_verified': IMPORT_STATUS_VERIFIED,
            },
        )

    def post(self, request, *args, **kwargs):
        from apps.materials.imports.review_status import (
            IMPORT_STATUS_BY_COLUMN,
            set_material_import_status,
        )
        from apps.workspaces.services import materials_owned_by

        workspace = request.active_workspace
        action = (request.POST.get('action') or '').strip()
        material_id = (request.POST.get('material_id') or '').strip()
        column = (request.POST.get('status') or '').strip()
        if action == 'set_status':
            pass
        elif action == 'mark_verified':
            column = 'verified'
        elif action in {'mark_unverified', 'mark_approved'}:
            column = 'approved'
        else:
            column = ''

        if column not in IMPORT_STATUS_BY_COLUMN or not material_id:
            messages.error(request, 'Некорректное действие проверки импорта.')
            return redirect('materials:import_review')
        material = get_object_or_404(
            materials_owned_by(workspace),
            pk=material_id,
        )
        if not material.is_editable_in(workspace):
            raise PermissionDenied
        tag_name = set_material_import_status(
            material, workspace=workspace, column=column,
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'ok': True,
                'material_id': str(material.pk),
                'status': column,
                'tag': tag_name,
            })
        messages.success(request, f'«{material.name}» — {tag_name}.')
        return redirect('materials:import_review')


class MaterialImportView(AppViewMixin, PermissionRequiredMixin, FormView):
    """Мастер: файл → лист → маппинг → staging/review → применение."""

    permission_codename = WorkspacePerm.MATERIAL_CREATE
    template_name = 'materials/material_import.html'
    form_class = MaterialImportForm

    def _material_importer(self, request, *, dry_run: bool, source_filename: str | None = None):
        config = get_import_config(request.session)
        return MaterialImporter(
            workspace=request.active_workspace,
            dry_run=dry_run,
            source_filename=source_filename,
            create_missing_dictionaries=bool(config.get('create_missing_dictionaries')),
        )

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
        wizard_step_defs = (
            ('upload', 'Загрузка'),
            ('configure', 'Лист и структура'),
            ('mapping', 'Сопоставление колонок'),
            ('review', 'Запись'),
        )
        step_key = 'review' if context['step'] == 'iterate' else context['step']
        step_num = 1
        step_label = wizard_step_defs[0][1]
        for index, (key, label) in enumerate(wizard_step_defs, start=1):
            if key == step_key:
                step_num = index
                step_label = label
                break
        context['wizard_step_defs'] = wizard_step_defs
        context['wizard_step_num'] = step_num
        context['wizard_step_total'] = len(wizard_step_defs)
        context['wizard_step_label'] = step_label
        context['wizard_step_percent'] = int(round(100 * step_num / len(wizard_step_defs)))
        import_url = reverse('materials:import')
        wizard_back = {
            'configure': f'{import_url}?step=upload',
            'mapping': f'{import_url}?step=configure',
            'review': f'{import_url}?step=mapping',
            'iterate': f'{import_url}?step=review',
        }
        context['wizard_back_url'] = wizard_back.get(context['step'])
        context['wizard_back_label'] = 'Назад'
        context['wizard_forward_label'] = (
            'Записать' if context['step'] == 'review' else 'Вперёд'
        )
        context['sheet_names'] = getattr(self, 'sheet_names', [])
        context['config'] = config
        context['wide_table'] = getattr(self, 'wide_table', None)
        context['mapping_rows'] = getattr(self, 'mapping_rows', [])
        context['field_mapping_rows'] = getattr(self, 'field_mapping_rows', [])
        context['unused_columns'] = getattr(self, 'unused_columns', [])
        context['file_columns'] = getattr(self, 'file_columns', [])
        context['addon_catalog_groups'] = getattr(self, 'addon_catalog_groups', [])
        context['reference_properties'] = getattr(
            self,
            'reference_properties',
            reference_properties_for_picker(),
        )
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
        context['required_targets_by_policy'] = {
            value: [target for target, _label in required_import_targets(value)]
            for value, _label in MATCH_POLICIES
        }
        context['draft_rows'] = getattr(self, 'draft_rows', [])
        context['profiles'] = MaterialImportProfile.objects.filter(
            workspace=self.request.active_workspace,
        ).order_by('name')
        context['import_templates'] = import_templates_for_workspace(
            self.request.active_workspace,
        )
        context['selected_template_id'] = str(
            config.get('active_template_id') or ''
        )
        context['import_default_tags'] = config.get('default_tags') or ''
        context['import_default_tag_colors'] = config.get('default_tag_colors') or {}
        if context.get('step') == 'mapping':
            context['import_default_tags_widget'] = self._import_default_tags_widget_html(
                self.request,
                context['import_default_tags'],
                colors=context['import_default_tag_colors'],
            )
        draft_rows = context['draft_rows']
        context['uncertain_count'] = sum(
            1 for d in draft_rows if getattr(d, 'has_uncertain', False)
        )
        context['draft_create_count'] = sum(1 for d in draft_rows if d.action == 'create')
        context['draft_update_count'] = sum(1 for d in draft_rows if d.action == 'update')
        context['draft_skip_count'] = sum(1 for d in draft_rows if d.action == 'skip')
        name_collisions = name_collisions_for_drafts(
            self.request.active_workspace,
            draft_rows,
        )
        context['name_collisions'] = name_collisions
        context['name_collision_count'] = len(name_collisions)
        post = self.request.POST if self.request.method == 'POST' else None
        context['unrecognized_fields'] = iter_unrecognized_fields(draft_rows, post=post)
        context['review_fix_grid'] = build_review_fix_grid(draft_rows, post=post)
        context['has_unrecognized'] = bool(context['unrecognized_fields'])
        context['unrecognized_count'] = len(context['unrecognized_fields'])
        has_validation_errors = bool(
            getattr(self, 'import_report', None) and not self.import_report.ok
        )
        context['import_has_validation_errors'] = has_validation_errors
        # Обратная совместимость шаблонов/тестов
        context['import_has_errors'] = has_validation_errors
        context['import_needs_field_review'] = context['has_unrecognized']
        # Ошибки валидации и нераспознанные поля блокируют запись по разным причинам.
        context['can_apply'] = (
            bool(draft_rows)
            and not has_validation_errors
            and not context['has_unrecognized']
        )
        context['layout_hint'] = getattr(self, 'layout_hint', '')
        context['detected_layout'] = getattr(self, 'detected_layout', None)
        context['show_header_layout_fields'] = getattr(self, 'show_header_layout_fields', True)
        context['layout_schema'] = getattr(self, 'layout_schema', None)
        context['layout_form_header_row'] = getattr(
            self,
            'layout_form_header_row',
            (context.get('config') or {}).get('header_row') or 1,
        )
        context['layout_form_group_row'] = getattr(
            self,
            'layout_form_group_row',
            (context.get('config') or {}).get('group_row') or 0,
        )
        context['structure_types'] = getattr(
            self,
            'structure_types',
            StructureType.objects.filter(is_active=True, is_created=True).order_by('name'),
        )
        context['reference_structure_types'] = structure_types_for_picker(
            context['structure_types']
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
        step_status = self._wizard_step_status(context)
        context['wizard_step_status'] = step_status
        context['wizard_steps'] = [
            {
                'key': key,
                'label': label,
                'status': step_status.get(key, ''),
            }
            for key, label in context['wizard_step_defs']
        ]
        context.update(_import_debug_context(self.request))
        return context

    def _wizard_step_status(self, context) -> dict[str, str]:
        """Статус кружка шага: error (красный) | warning (жёлтый) | ''."""
        status: dict[str, str] = {
            'upload': '',
            'configure': '',
            'mapping': '',
            'review': '',
        }
        if context.get('show_structure_type_error'):
            status['configure'] = 'error'
        if (
            context.get('show_mapping_errors')
            or context.get('missing_required_targets')
            or context.get('duplicate_mapping_targets')
        ):
            status['mapping'] = 'error'
        if context.get('import_has_validation_errors'):
            status['review'] = 'error'
        elif context.get('has_unrecognized'):
            status['review'] = 'warning'
        return status

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
        if step == 'upload':
            self.wizard_step = 'upload'
            return self.render_to_response(self.get_context_data(form=self.get_form_class()()))
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
            'review_resolve_ignore': self._handle_review_resolve_ignore,
            'review_resolve_manual': self._handle_review_resolve_manual,
            'review_iterate_start': self._handle_review_iterate_start,
            'iterate_apply': self._handle_iterate_apply,
            'iterate_skip': self._handle_iterate_skip,
            'iterate_finish': self._handle_iterate_finish,
            'iterate_back_review': self._handle_iterate_back_review,
            'save_profile': self._handle_save_template,
            'load_profile': self._handle_load_template,
            'save_template': self._handle_save_template,
            'load_template': self._handle_load_template,
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
            match_policy=MATCH_ALWAYS_CREATE,
            mode='mapped',
            clear_draft=True,
        )
        if default_header > 1 or default_group > 0:
            messages.info(
                request,
                'Файл загружен. Похоже на таблицу с группами колонок: '
                f'строка заголовков = {default_header}, строка групп = {default_group or "нет"}. '
                'В сопоставлении должна быть колонка «Наименование» → поле «Название».',
            )
        else:
            messages.info(
                request,
                'Файл загружен. Заголовки в первой строке — номера строк парсера скрыты. '
                'В сопоставлении должна быть колонка «Наименование» → поле «Название».',
            )
        return redirect('materials:import')

    def _resolve_configure_layout(self, path, *, sheet: str, post) -> tuple[int, int]:
        """Номера строк шапки: при простой раскладке (1 / без групп) не даём сбить вручную."""
        detected_header, detected_group = detect_header_layout(path, sheet_name=sheet or None)
        if detected_header <= 1 and detected_group <= 0:
            return 1, 0
        try:
            header_row = int(post.get('header_row') or detected_header or 1)
            group_raw = (post.get('group_row') or '').strip()
            if group_raw == '':
                group_row = int(detected_group or 0)
            else:
                group_row = int(group_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError('Номера строк должны быть числами.') from exc
        if header_row < 1:
            raise ValueError('Номер строки заголовка должен быть ≥ 1.')
        return header_row, max(0, group_row)

    def _handle_configure(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            messages.error(request, 'Сначала загрузите файл.')
            return redirect('materials:import')
        sheet = (request.POST.get('sheet') or '').strip()
        if request.POST.get('refresh_layout') == '1':
            prev = get_import_config(request.session)
            sheet_changed = sheet != (prev.get('sheet') or '')
            try:
                if sheet_changed:
                    # Новый лист — заново автоопределяем шапку, а не тянем номера со старого.
                    detected_header, detected_group = detect_header_layout(
                        path, sheet_name=sheet or None,
                    )
                    if detected_header <= 1 and detected_group <= 0:
                        header_row, group_row = 1, 0
                    else:
                        header_row, group_row = int(detected_header), int(detected_group or 0)
                else:
                    header_row, group_row = self._resolve_configure_layout(
                        path, sheet=sheet, post=request.POST,
                    )
            except ValueError as exc:
                messages.error(request, str(exc))
                return self._render_configure(request, path)
            set_import_config(
                request.session,
                sheet=sheet,
                header_row=header_row,
                group_row=group_row,
            )
            return self._render_configure(request, path)
        try:
            header_row, group_row = self._resolve_configure_layout(
                path, sheet=sheet, post=request.POST,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return self._render_configure(request, path)
        create_missing_dictionaries = request.POST.get('create_missing_dictionaries') == '1'
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
            create_missing_dictionaries=create_missing_dictionaries,
            structure_type_id=structure_type_id,
            mapping={},
            clear_draft=True,
        )
        return self._render_mapping(request, path)

    def _mapping_from_post(self, request) -> dict:
        """Читает map_*/parse_* из POST (текущий UI конструктора)."""
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
        return mapping

    def _default_tags_from_post(self, request) -> str:
        raw = request.POST.get('import_default_tags')
        if raw is None:
            return (get_import_config(request.session).get('default_tags') or '').strip()
        return (raw or '').strip()

    def _default_tag_colors_from_post(self, request) -> dict:
        from apps.core.tag_utils import parse_tag_colors_payload

        raw = request.POST.get('import_default_tags_colors')
        if raw is None:
            return dict(get_import_config(request.session).get('default_tag_colors') or {})
        return parse_tag_colors_payload(raw)

    def _import_default_tags_widget_html(
        self,
        request,
        value: str = '',
        *,
        colors: dict | None = None,
    ) -> str:
        from django.utils.safestring import mark_safe

        from apps.core.models import Tag
        from apps.core.tag_utils import active_tags_queryset
        from apps.core.widgets import TagNamesWidget

        workspace = request.active_workspace
        suggestions = list(
            active_tags_queryset(Tag.objects.filter(workspace=workspace))
            .order_by('name')
            .values('name', 'slug', 'color', 'description', 'workspace_id')
        )
        colors_payload = colors if colors is not None else {}
        import json

        widget = TagNamesWidget(
            attrs={'id': 'import-default-tags-typing'},
            tag_suggestions=suggestions,
            allow_colors=True,
            colors_value=json.dumps(colors_payload, ensure_ascii=False) if colors_payload else '',
        )
        return mark_safe(widget.render('import_default_tags', value or '', attrs=widget.attrs))

    def _save_mapping_from_post(self, request, path):
        """Сохраняет маппинг из POST. Возвращает path-response при ошибке, иначе None."""
        mapping = self._mapping_from_post(request)
        set_import_config(
            request.session,
            mapping=mapping,
            match_policy=MATCH_ALWAYS_CREATE,
            default_tags=self._default_tags_from_post(request),
            default_tag_colors=self._default_tag_colors_from_post(request),
        )
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
        self.import_report = self._material_importer(request, dry_run=True).import_drafts(
            drafts, structure_type=structure_type
        )
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

    def _handle_review_resolve_ignore(self, request):
        path, drafts, structure_type, early = self._load_review_drafts(request)
        if early is not None:
            return early
        drafts = apply_unrecognized_ignore_all(drafts)
        set_import_config(request.session, draft=drafts_to_session(drafts))
        return self._apply_import_drafts(
            request,
            path,
            drafts,
            structure_type,
            ignored_unrecognized=True,
        )

    def _handle_review_resolve_manual(self, request):
        path, drafts, structure_type, early = self._load_review_drafts(request)
        if early is not None:
            return early
        drafts, errors = apply_unrecognized_manual_fixes(drafts, request.POST)
        # Сохраняем и частичный успех: иначе после ошибки в одном поле
        # исправленные ячейки снова выглядят «нераспознанными».
        set_import_config(request.session, draft=drafts_to_session(drafts))
        if errors:
            for error in errors[:8]:
                messages.error(request, error)
            if len(errors) > 8:
                messages.error(request, f'… и ещё {len(errors) - 8} полей без корректного значения.')
            return self._render_review(request, path)
        return self._apply_import_drafts(request, path, drafts, structure_type)

    def _handle_review_apply(self, request):
        path, drafts, structure_type, early = self._load_review_drafts(request)
        if early is not None:
            return early
        if has_unresolved_unrecognized(drafts):
            messages.warning(
                request,
                'Сначала исправьте или пропустите нераспознанные поля — '
                'это не ошибка черновика, а значения, которые система не разобрала автоматически.',
            )
            return self._render_review(request, path)
        return self._apply_import_drafts(request, path, drafts, structure_type)

    def _apply_duplicate_name_choice(self, request, drafts):
        """Применяет выбор оператора по совпадениям названий. Возвращает (drafts, error_message)."""
        collisions = name_collisions_for_drafts(request.active_workspace, drafts)
        if not collisions:
            return drafts, None
        mode = (request.POST.get('duplicate_name_policy') or DUPLICATE_NAME_SKIP).strip()
        prefix = (request.POST.get('duplicate_name_prefix') or '').strip()
        try:
            drafts = apply_duplicate_name_policy(
                drafts,
                collisions,
                mode=mode,
                prefix=prefix,
            )
        except ValueError as exc:
            return drafts, str(exc)
        set_import_config(request.session, draft=drafts_to_session(drafts))
        return drafts, None

    def _apply_import_drafts(
        self,
        request,
        path,
        drafts,
        structure_type,
        *,
        ignored_unrecognized: bool = False,
    ):
        drafts, dup_error = self._apply_duplicate_name_choice(request, drafts)
        if dup_error:
            messages.error(request, dup_error)
            self.draft_rows = drafts
            return self._render_review(request, path)
        # На всякий случай: перезапись запрещена.
        for draft in drafts:
            if draft.action == 'update':
                draft.action = 'create'
            draft.existing_pk = None
        report = self._material_importer(
            request,
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
        from apps.core.tag_utils import apply_workspace_tag_colors

        apply_workspace_tag_colors(
            request.active_workspace,
            get_import_config(request.session).get('default_tag_colors') or {},
        )
        clear_import_session(request.session, delete_file=True)
        ignored_note = (
            ' Нераспознанные поля проигнорированы и остались пустыми.'
            if ignored_unrecognized
            else ''
        )
        messages.success(
            request,
            'Импорт выполнен: '
            f'материалов создано {report.materials_created}'
            + (
                f', обновлено {report.materials_updated}'
                if report.materials_updated
                else ''
            )
            + f'; свойств создано {report.properties_created}'
            + (
                f', обновлено {report.properties_updated}'
                if report.properties_updated
                else ''
            )
            + '.'
            + ignored_note
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
        drafts, dup_error = self._apply_duplicate_name_choice(request, drafts)
        if dup_error:
            messages.error(request, dup_error)
            self.draft_rows = drafts
            return self._render_review(request, path)
        set_import_config(request.session, draft=drafts_to_session(drafts))
        structure_type = self._resolve_structure_type(config)
        if structure_type is None:
            messages.error(request, 'Не выбран тип структуры.')
            return redirect('materials:import')
        if has_unresolved_unrecognized(drafts):
            messages.warning(
                request,
                'Построчный режим станет доступен после исправления или пропуска нераспознанных полей.',
            )
            return self._render_review(request, path)
        report = self._material_importer(request, dry_run=True).import_drafts(
            drafts, structure_type=structure_type
        )
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
        # Перезапись запрещена: всегда создаём. Совпадения по названию уже
        # обработаны при входе в построчный режим (пропуск / префикс).
        draft.existing_pk = None
        draft.action = 'create'
        drafts[index] = draft
        set_import_config(request.session, draft=drafts_to_session(drafts))

        report = self._material_importer(
            request,
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
        from apps.core.tag_utils import apply_workspace_tag_colors

        apply_workspace_tag_colors(
            request.active_workspace,
            get_import_config(request.session).get('default_tag_colors') or {},
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

    def _handle_save_template(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            return redirect('materials:import')
        name = (
            request.POST.get('template_name')
            or request.POST.get('profile_name')
            or ''
        ).strip()
        if not name:
            messages.error(request, 'Укажите название шаблона.')
            return self._render_mapping(request, path)
        config = get_import_config(request.session)
        structure_type_id = (config.get('structure_type_id') or '').strip()
        if not structure_type_id:
            messages.error(
                request,
                'Выберите тип структуры перед сохранением шаблона.',
            )
            return self._render_mapping(request, path)
        if self._resolve_structure_type(config) is None:
            messages.error(
                request,
                'Тип структуры из сессии недоступен. Выберите тип заново.',
            )
            return self._render_mapping(request, path)
        # Берём маппинг из POST (текущий UI). Сессия — только запасной вариант
        # для старых клиентов / тестов без map_*.
        mapping = self._mapping_from_post(request)
        if mapping:
            set_import_config(
                request.session,
                mapping=mapping,
                match_policy=MATCH_ALWAYS_CREATE,
                default_tags=self._default_tags_from_post(request),
                default_tag_colors=self._default_tag_colors_from_post(request),
            )
            config = get_import_config(request.session)
        else:
            mapping = dict(config.get('mapping') or {})
            # Даже без map_* сохраняем теги из POST, если пришли.
            if 'import_default_tags' in request.POST:
                set_import_config(
                    request.session,
                    default_tags=self._default_tags_from_post(request),
                    default_tag_colors=self._default_tag_colors_from_post(request),
                )
                config = get_import_config(request.session)
        table = self._load_table(path, config)
        for col in table.columns:
            key = str(col.index)
            if key in mapping and isinstance(mapping[key], dict):
                mapping[key]['label'] = col.display
            elif key not in mapping:
                mapping[key] = {
                    'target': TARGET_SKIP,
                    'parse': 'auto',
                    'label': col.display,
                }
        payload = profile_payload_from_mapping(
            mapping,
            sheet=config.get('sheet'),
            header_row=config.get('header_row'),
            group_row=config.get('group_row'),
            match_policy=config.get('match_policy'),
            structure_type_id=structure_type_id,
            create_missing_dictionaries=bool(config.get('create_missing_dictionaries')),
            default_tags=config.get('default_tags') or '',
            default_tag_colors=config.get('default_tag_colors') or {},
        )
        profile, _created = MaterialImportProfile.objects.update_or_create(
            workspace=request.active_workspace,
            name=name,
            defaults={'config': payload},
        )
        request.session[SESSION_ACTIVE_TEMPLATE_ID] = str(profile.pk)
        request.session.modified = True
        messages.success(request, f'Шаблон «{name}» сохранён.')
        return self._render_mapping(request, path)

    def _handle_load_template(self, request):
        path = get_import_session_path(request.session)
        if path is None:
            return redirect('materials:import')
        template_id = (
            request.POST.get('template_id') or request.POST.get('profile_id') or ''
        ).strip()
        if not template_id:
            messages.error(request, 'Выберите шаблон для применения.')
            return self._render_mapping(request, path)
        profile = get_object_or_404(
            MaterialImportProfile,
            pk=template_id,
            workspace=request.active_workspace,
        )
        config = get_import_config(request.session)
        table = self._load_table(path, config)
        mapping = apply_profile_to_columns(table.columns, profile.config.get('columns') or [])
        structure_type_id = (profile.config.get('structure_type_id') or '').strip()
        resolved = self._resolve_structure_type({'structure_type_id': structure_type_id})
        if structure_type_id and resolved is None:
            messages.warning(
                request,
                'Тип структуры из шаблона недоступен — выберите тип вручную.',
            )
            structure_type_id = ''
        set_import_config(
            request.session,
            mapping=mapping,
            match_policy=profile.config.get('match_policy') or MATCH_BY_NAME,
            create_missing_dictionaries=bool(profile.config.get('create_missing_dictionaries')),
            structure_type_id=structure_type_id,
            header_row=int(profile.config.get('header_row') or config.get('header_row') or 1),
            group_row=int(profile.config.get('group_row') or 0),
            default_tags=(profile.config.get('default_tags') or '').strip(),
            default_tag_colors=dict(profile.config.get('default_tag_colors') or {}),
            clear_draft=True,
        )
        request.session[SESSION_ACTIVE_TEMPLATE_ID] = str(profile.pk)
        request.session.modified = True
        mapped_count = sum(
            1
            for entry in mapping.values()
            if normalize_mapping_entry(entry)[0] != TARGET_SKIP
        )
        st_label = f' · структура «{resolved.name}»' if resolved else ''
        messages.success(
            request,
            f'Применён шаблон «{profile.name}»{st_label} '
            f'({mapped_count} колонок). Проверьте сопоставление.',
        )
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
                    [],
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
            match_policy=MATCH_ALWAYS_CREATE,
            structure_type_id=str(structure_type.pk),
        )
        drafts = merge_default_tags_into_drafts(
            drafts,
            config.get('default_tags') or '',
        )
        clear_iterate_session(request.session)
        set_import_config(request.session, mapping=mapping, draft=drafts_to_session(drafts))
        return drafts, structure_type, None

    def _build_and_show_review(self, request, path):
        drafts, structure_type, build_error = self._build_drafts(request, path)
        if build_error is not None:
            return build_error
        self.import_report = self._material_importer(request, dry_run=True).import_drafts(
            drafts, structure_type=structure_type
        )
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
        self.show_header_layout_fields = detected_header > 1 or detected_group > 0
        if not self.show_header_layout_fields:
            # Простая шапка: фиксируем 1 / 0 в сессии, чтобы UI и apply не расходились.
            if config.get('header_row') != 1 or int(config.get('group_row') or 0) != 0:
                set_import_config(request.session, header_row=1, group_row=0)
                config = get_import_config(request.session)
        schema_header = max(1, int(config.get('header_row') or detected_header or 1))
        schema_group = max(0, int(config.get('group_row') if config.get('group_row') is not None else (detected_group or 0)))
        if not self.show_header_layout_fields:
            schema_header, schema_group = 1, 0
        # превью первых строк листа для выбора заголовков + схема для оператора
        try:
            preview_table = load_wide_table(
                path,
                sheet_name=sheet or None,
                header_row=schema_header,
                group_row=schema_group or None,
                max_preview=3,
            )
            self.layout_schema = build_import_layout_schema(
                path,
                sheet_name=sheet or None,
                header_row=schema_header,
                group_row=schema_group,
                max_cols=14,
                max_data_rows=8,
            )
            self.layout_form_header_row = schema_header
            self.layout_form_group_row = schema_group
            if self.show_header_layout_fields:
                self.layout_hint = (
                    f'Авто: заголовки={detected_header}, группы={detected_group or "нет"}; '
                    f'сейчас: заголовки={schema_header}, группы={schema_group or "нет"}; '
                    f'колонок={len(preview_table.columns)}. '
                    f'Должны быть «Наименование», «Марка»…'
                )
            else:
                self.layout_hint = (
                    f'Заголовки в строке 1, групп колонок нет · колонок={len(preview_table.columns)}'
                )
        except (ValueError, FileNotFoundError):
            self.layout_hint = ''
            self.layout_schema = None
            self.layout_form_header_row = schema_header
            self.layout_form_group_row = schema_group
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
        match_policy = MATCH_BY_NAME
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
                # Автоподстановка только primary (название / код / структура).
                target = suggest_target(
                    column,
                    [],
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
            raw_sample = sample.get(column.index)
            if raw_sample is None:
                sample_text = '—'
            else:
                sample_text = str(raw_sample).replace('\n', ' ').strip()
                if len(sample_text) > 80:
                    sample_text = sample_text[:77] + '…'
                if not sample_text:
                    sample_text = '—'
            mapping_rows.append({
                'column': column,
                'target': target,
                'parse': parse,
                'sample': sample_text,
                'is_required_target': target in required_keys,
                'target_label': target_labels.get(target, target_labels.get(TARGET_SKIP, '— пропустить —')),
            })
        if not stored:
            stored = mapping_for_session(mapping_rows)
            set_import_config(request.session, mapping=stored)

        self.mapping_rows = mapping_rows
        self.file_columns = [
            {
                'index': column.index,
                'label': column.display,
                'sample': next(
                    (row['sample'] for row in mapping_rows if row['column'].index == column.index),
                    '—',
                ),
            }
            for column in self.wide_table.columns
        ]
        self.field_mapping_rows = build_field_mapping_rows(
            columns=list(self.wide_table.columns),
            mapping=stored,
            structure_fields=structure_fields,
            match_policy=match_policy,
            target_labels=target_labels,
            sample_row=sample,
        )
        self.unused_columns = unused_columns_from_mapping(
            list(self.wide_table.columns),
            stored,
            sample_row=sample,
        )
        used_targets = {row['target'] for row in self.field_mapping_rows}
        # Свойства справочника — через ту же модалку «Выбор свойств», что в форме материала.
        self.addon_catalog_groups = addon_catalog_groups(
            properties=[],
            exclude_targets=used_targets,
        )
        self.reference_properties = reference_properties_for_picker()
        self.missing_required_targets = missing_required_targets(
            self.field_mapping_rows,
            match_policy=match_policy,
        )
        self.duplicate_mapping_targets = find_duplicate_mapping_targets(mapping_rows)
        self.sheet_names = list_sheet_names(path)
        self.wizard_step = 'mapping'
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
            self.import_report = self._material_importer(request, dry_run=True).import_drafts(
                self.draft_rows, structure_type=structure_type
            )
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
            self.iterate_report = self._material_importer(request, dry_run=True).import_drafts(
                [self.iterate_draft], structure_type=structure_type
            )
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
