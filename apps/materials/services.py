from django.db import transaction

from apps.materials.models import Material
from apps.workspaces.models import WorkspaceMaterialLink
from apps.workspaces.services import (
    materials_in_workspace_tab,
    materials_shared_in,
    materials_visible_in,
)
from apps.workspaces.visibility import VisibilityMode


def build_material_create_initial(template: Material, workspace) -> dict:
    from apps.core.tag_utils import format_tags_for_input

    return {
        'code': (template.code or '').strip() or 'MAT',
        'name': template.name,
        'description': template.description,
        'manufacturer': template.manufacturer_id,
        'availability': template.availability_id,
        'technology': template.technology_id,
        'struct_type': template.struct_type_id,
        'tag_names': format_tags_for_input(template.tags.all()),
        'visibility_mode': VisibilityMode.PRIVATE,
    }


def materials_usable_as_create_template(workspace):
    if workspace is None:
        return Material.objects.none()
    workspace_materials = materials_in_workspace_tab(workspace)
    shared_materials = materials_shared_in(workspace)
    return workspace_materials | shared_materials


def get_create_template_material(user, workspace, material_id):
    from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm

    if not material_id or workspace is None:
        return None
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_CREATE):
        return None
    try:
        material = (
            Material.objects.select_related('struct_type')
            .prefetch_related('tags', 'properties', 'properties__property', 'composite_layers')
            .get(pk=material_id)
        )
    except (Material.DoesNotExist, ValueError, TypeError):
        return None
    if not materials_usable_as_create_template(workspace).filter(pk=material.pk).exists():
        return None
    return material


def material_property_formset_initial(template: Material) -> list[dict]:
    return [
        {
            'property': link.property_id,
            'value': link.value,
        }
        for link in template.properties.select_related('property')
    ]


def composite_layer_formset_initial(template: Material) -> list[dict]:
    return [
        {
            'material': layer.material_id,
            'angle': layer.angle,
            'thickness': layer.thickness,
            'layer_number': layer.layer_number,
        }
        for layer in template.composite_layers.select_related('material').order_by('layer_number')
    ]


def find_shared_materials_by_name(name, workspace, *, exclude_material_id=None):
    normalized_name = (name or '').strip()
    if not normalized_name or workspace is None:
        return Material.objects.none()
    queryset = materials_shared_in(workspace).filter(name__iexact=normalized_name)
    if exclude_material_id:
        queryset = queryset.exclude(pk=exclude_material_id)
    return queryset


def find_shared_materials_by_code(code, workspace, *, exclude_material_id=None):
    normalized_code = (code or '').strip()
    if not normalized_code or workspace is None:
        return Material.objects.none()
    queryset = materials_shared_in(workspace).filter(code=normalized_code)
    if exclude_material_id:
        queryset = queryset.exclude(pk=exclude_material_id)
    return queryset


def can_link_material_to_workspace(user, material, workspace) -> bool:
    from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm

    if material is None or workspace is None:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_CREATE):
        return False
    if not materials_visible_in(workspace).filter(pk=material.pk).exists():
        return False
    if material.is_editable_in(workspace):
        return False
    if WorkspaceMaterialLink.objects.filter(workspace=workspace, material=material).exists():
        return False
    return True


def is_material_linked_to_workspace(material, workspace) -> bool:
    if material is None or workspace is None:
        return False
    return WorkspaceMaterialLink.objects.filter(workspace=workspace, material=material).exists()


def material_pks_linked_in_workspace(workspace) -> frozenset:
    if workspace is None:
        return frozenset()
    return frozenset(
        WorkspaceMaterialLink.objects.filter(workspace=workspace).values_list(
            'material_id',
            flat=True,
        )
    )


def can_manage_material_visibility(user, material, workspace) -> bool:
    from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm, is_editable_in_workspace

    if is_material_linked_to_workspace(material, workspace):
        return False
    if not is_editable_in_workspace(user, material, workspace):
        return False
    return has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_PUBLISH)


def samples_for_material(material, workspace):
    from apps.samples.models import Sample

    if material is None:
        return Sample.objects.none()
    queryset = Sample.objects.filter(material=material)
    if workspace is None:
        return queryset
    if material.is_editable_in(workspace):
        return queryset.filter(workspace=workspace)
    if material.home_workspace_id:
        return queryset.filter(workspace=material.home_workspace_id)
    return queryset


def material_attachments_for_material(material, workspace):
    from django.db.models import Q

    from apps.materials.models import MaterialAttachment

    if material is None:
        return MaterialAttachment.objects.none()
    queryset = MaterialAttachment.objects.filter(material=material)
    if workspace is None:
        return queryset
    if material.is_editable_in(workspace):
        return queryset.filter(Q(workspace=workspace) | Q(workspace__isnull=True))
    if material.home_workspace_id:
        return queryset.filter(
            Q(workspace=material.home_workspace_id) | Q(workspace__isnull=True),
        )
    return queryset


@transaction.atomic
def link_material_to_workspace(source: Material, workspace, user) -> Material:
    if not can_link_material_to_workspace(user, source, workspace):
        raise PermissionError('Нельзя добавить этот материал в текущее пространство.')

    WorkspaceMaterialLink.objects.get_or_create(
        workspace=workspace,
        material=source,
    )
    return source
