from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, Http404
from django.views import View

from apps.workspaces.mixins import AppViewMixin, PermissionRequiredMixin
from apps.workspaces.permissions import WorkspacePerm
from apps.materials.imports.mapping import (
    OPTIONAL_SAMPLE_TARGETS,
    SAMPLE_TARGETS,
)
from apps.materials.picker_data import materials_for_picker, materials_for_picker_queryset
from apps.materials.views import MaterialImportView
from apps.samples.imports.service import SampleImporter
from apps.samples.imports.session import PrefixedSessionProxy
from apps.samples.models import Sample

_SESSION_OLD_PREFIX = 'material_import'
_SESSION_NEW_PREFIX = 'sample_import'


class SampleImportView(MaterialImportView):
    permission_codename = WorkspacePerm.SAMPLE_CREATE
    import_kind = 'sample'
    import_url_name = 'samples:import'
    list_url_name = 'samples:list'
    import_page_title = 'Импорт образцов'
    wizard_configure_label = 'Лист и материал'
    show_dictionaries = False
    show_templates = False
    show_examples = True
    addon_field_label = 'Поле образца'
    mapping_identity_section_title = 'Поля образца'
    created_noun = 'образцов'

    def dispatch(self, request, *args, **kwargs):
        request.session = PrefixedSessionProxy(
            request.session,
            _SESSION_OLD_PREFIX,
            _SESSION_NEW_PREFIX,
        )
        return super().dispatch(request, *args, **kwargs)

    def _requires_structure_type(self) -> bool:
        return False

    def _optional_addon_targets(self):
        return OPTIONAL_SAMPLE_TARGETS

    def _mapping_identity_targets(self):
        return SAMPLE_TARGETS

    def _resolve_import_material(self, config):
        raw = (config.get('material_id') or '').strip()
        if not raw:
            return None
        return (
            materials_for_picker_queryset(self.request.active_workspace)
            .filter(pk=raw)
            .select_related('struct_type')
            .first()
        )

    def _resolve_structure_type(self, config):
        material = self._resolve_import_material(config)
        if material is None or not material.struct_type_id:
            return None
        structure_type = material.struct_type
        if not structure_type.is_active or not structure_type.is_created:
            return None
        return structure_type

    def _mapping_extra_properties(self, config):
        material = self._resolve_import_material(config)
        if material is None:
            return []
        return [
            item.property
            for item in material.properties.select_related('property').order_by(
                'property__group__sort_order',
                'property__name',
            )
        ]

    def _occupied_codes(self, request) -> set[str]:
        return set(
            Sample.objects.filter(workspace=request.active_workspace).values_list('code', flat=True)
        )

    def _name_collisions(self, request, drafts):
        from apps.materials.imports.staging import name_collisions_for_drafts

        return name_collisions_for_drafts(
            request.active_workspace,
            drafts,
            queryset=(
                Sample.objects.filter(workspace=request.active_workspace)
                .only('pk', 'name', 'code')
                .order_by('created_at')
            ),
        )

    def _prepare_entity_context(self, request, config):
        self.import_materials = list(materials_for_picker_queryset(request.active_workspace))
        self.reference_materials = materials_for_picker(request.active_workspace)
        self.selected_material = self._resolve_import_material(config)
        self.selected_structure_type = self._resolve_structure_type(config)

    def _configure_entity_error(self, request) -> str | None:
        material_id = (request.POST.get('material_id') or '').strip()
        if not material_id:
            return 'Выберите материал для импорта.'
        material = (
            materials_for_picker_queryset(request.active_workspace)
            .filter(pk=material_id)
            .select_related('struct_type')
            .first()
        )
        if material is None:
            return 'Выбранный материал недоступен в этом пространстве.'
        if material.struct_type_id and material.struct_type and not material.struct_type.is_created:
            return (
                'У материала тип структуры без SQL-таблицы — '
                'параметры структуры недоступны.'
            )
        return None

    def _configure_entity_session_kwargs(self, request) -> dict:
        return {
            'material_id': (request.POST.get('material_id') or '').strip(),
            'structure_type_id': '',
        }

    def _ensure_configure_entity_for_mapping(self, request, config, path):
        if self._resolve_import_material(config) is None:
            messages.error(request, 'Выберите материал.')
            self.show_material_error = True
            return self._render_configure(request, path)
        return None

    def _missing_configure_entity_message(self, config) -> str | None:
        if self._resolve_import_material(config) is None:
            return 'Выберите материал перед сборкой черновика.'
        return None

    def _material_importer(self, request, *, dry_run: bool, source_filename: str | None = None):
        from apps.materials.imports.upload import get_import_config

        config = get_import_config(request.session)
        material = self._resolve_import_material(config)
        return SampleImporter(
            workspace=request.active_workspace,
            material=material,
            user=request.user,
            dry_run=dry_run,
            source_filename=source_filename,
        )

    def _handle_save_template(self, request):
        messages.error(request, 'Шаблоны маппинга для импорта образцов пока не поддерживаются.')
        path = self._session_path(request)
        if path is None:
            return self._import_redirect()
        return self._render_mapping(request, path)

    def _handle_load_template(self, request):
        return self._handle_save_template(request)

    def _session_path(self, request):
        from apps.materials.imports.upload import get_import_session_path

        return get_import_session_path(request.session)

    def _handle_undo_last_import(self, request):
        messages.error(request, 'Откат партии импорта образцов не поддерживается.')
        return self._list_redirect()


class SampleImportExampleView(AppViewMixin, PermissionRequiredMixin, View):
    permission_codename = WorkspacePerm.SAMPLE_CREATE
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        examples_dir = Path(__file__).resolve().parent / 'fixtures' / 'import_examples'
        kind = (request.GET.get('kind') or 'csv').strip().lower()
        path = examples_dir / 'samples_wide_demo.csv'
        filename = 'samples_wide_demo.csv'
        content_type = 'text/csv; charset=utf-8'
        if kind == 'xlsx':
            xlsx = examples_dir / 'samples_wide_demo.xlsx'
            if xlsx.is_file():
                path = xlsx
                filename = 'samples_wide_demo.xlsx'
                content_type = (
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
        if not path.is_file():
            raise Http404('Пример файла не найден')
        return FileResponse(
            path.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )
