from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.materials.services import (
    is_material_linked_to_workspace,
    material_attachments_for_material,
    samples_for_material,
)
from apps.workspaces.permissions import is_editable_in_workspace
from apps.workspaces.services import materials_visible_in


class MaterialTabMixin:
    def dispatch(self, request, *args, **kwargs):
        self.material = get_object_or_404(
            materials_visible_in(request.active_workspace),
            pk=kwargs['material_pk'],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['material'] = self.material
        context['active_tab'] = self.active_tab
        workspace = self.request.active_workspace
        context['attachment_count'] = material_attachments_for_material(
            self.material,
            workspace,
        ).count()
        context['sample_count'] = samples_for_material(self.material, workspace).count()
        context['material_is_readonly'] = not is_editable_in_workspace(
            self.request.user, self.material, self.request.active_workspace
        )
        context['material_is_workspace_link'] = is_material_linked_to_workspace(
            self.material,
            self.request.active_workspace,
        )
        return context

    def _require_material_editable(self):
        if not is_editable_in_workspace(
            self.request.user, self.material, self.request.active_workspace
        ):
            raise PermissionDenied
