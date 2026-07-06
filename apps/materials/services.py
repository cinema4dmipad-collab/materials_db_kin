from django.core.exceptions import ValidationError
from django.db import transaction

from apps.composites.models import CompositeLayer
from apps.core.creator import assign_creator
from apps.core.tag_utils import assign_tags
from apps.materials.forms import STRUCTURE_SERVICE_FIELDS
from apps.materials.models import Material, MaterialProperty
from apps.structures.sql_executor import SQLExecutor
from apps.workspaces.visibility import VisibilityMode


def unique_material_code(base_code: str, workspace) -> str:
    if not Material.objects.filter(home_workspace=workspace, code=base_code).exists():
        return base_code
    for index in range(2, 100):
        candidate = f'{base_code}-{index}'
        if not Material.objects.filter(home_workspace=workspace, code=candidate).exists():
            return candidate
    return f'{base_code}-копия'


def can_clone_material_to_workspace(user, material, workspace) -> bool:
    from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm
    from apps.workspaces.services import materials_visible_in

    if material is None or workspace is None:
        return False
    if not has_workspace_perm(user, workspace, WorkspacePerm.MATERIAL_CREATE):
        return False
    if not materials_visible_in(workspace).filter(pk=material.pk).exists():
        return False
    return not material.is_editable_in(workspace)


def _structure_row_payload(source_material, user):
    params = source_material.get_structure_params()
    if not params:
        return None

    data = {}
    for key, value in params.items():
        if key in STRUCTURE_SERVICE_FIELDS:
            continue
        if value not in (None, ''):
            data[key] = value
    if user is not None and getattr(user, 'is_authenticated', False):
        from apps.core.creator import creator_label

        data['created_by'] = creator_label(user)
    return data


def _copy_structure_row(source_material, user):
    structure_type = source_material.struct_type
    if not structure_type or not source_material.struct_props_id:
        return None

    payload = _structure_row_payload(source_material, user)
    if payload is None:
        return None

    result = SQLExecutor.insert(structure_type, payload)
    if not result.get('success'):
        raise ValidationError(result.get('error') or 'Не удалось скопировать параметры структуры.')
    return result['id']


@transaction.atomic
def clone_material_to_workspace(source: Material, workspace, user) -> Material:
    if not can_clone_material_to_workspace(user, source, workspace):
        raise PermissionError('Нельзя клонировать этот материал в текущее пространство.')

    source = (
        Material.objects.select_related('struct_type')
        .prefetch_related('properties', 'properties__property', 'composite_layers', 'tags')
        .get(pk=source.pk)
    )

    clone = Material(
        code=unique_material_code(source.code, workspace),
        name=source.name,
        description=source.description,
        struct_type=source.struct_type,
        home_workspace=workspace,
        visibility_mode=VisibilityMode.PRIVATE,
    )
    assign_creator(clone, user)
    clone.struct_props_id = _copy_structure_row(source, user)
    clone.save()

    for link in source.properties.all():
        MaterialProperty.objects.create(
            material=clone,
            property=link.property,
            value=link.value,
            notes=link.notes,
        )

    tag_names = list(source.tags.values_list('name', flat=True))
    if tag_names:
        assign_tags(clone, tag_names, workspace=workspace)

    for layer in source.composite_layers.select_related('material').order_by('layer_number'):
        CompositeLayer.objects.create(
            parent_material=clone,
            material=layer.material,
            layer_number=layer.layer_number,
            angle=layer.angle,
            thickness=layer.thickness,
        )

    return clone
