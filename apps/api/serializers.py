from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.files.storage import FileSystemStorage
from django.urls import reverse

from apps.api.schemas import (
    MaterialDetail,
    MaterialListItem,
    PropertyOut,
    SampleDetail,
    SampleOut,
    ScanOut,
    StructureOut,
    WorkspaceOut,
)
from apps.materials.models import Material, MaterialProperty
from apps.samples.models import Sample, SampleProperty
from apps.scans.models import ScanRecord
from apps.structures.sql_executor import SQLExecutor
from apps.workspaces.models import Workspace


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def serialize_workspace(workspace: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.pk,
        slug=workspace.slug,
        name=workspace.name,
        description=workspace.description or '',
    )


def serialize_material_list_item(material: Material) -> MaterialListItem:
    return MaterialListItem(
        id=material.pk,
        code=material.code,
        name=material.name,
        description=material.description_display,
        home_workspace_id=material.home_workspace_id,
        struct_type_id=material.struct_type_id,
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def _material_properties(material: Material) -> list[PropertyOut]:
    rows = (
        MaterialProperty.objects.filter(material=material)
        .select_related('property')
        .order_by('property__name')
    )
    result: list[PropertyOut] = []
    for row in rows:
        prop = row.property
        display = row.display_value()
        if prop.data_type == prop.CHOICE_DATA_TYPE:
            display = row.choice_display_value()
        result.append(
            PropertyOut(
                id=prop.pk,
                code=prop.name,
                name=prop.display_name,
                data_type=prop.data_type,
                value=row.value,
                display_value=display,
                notes=row.notes or '',
            )
        )
    return result


def _material_structure(material: Material) -> StructureOut | None:
    if not material.struct_type_id:
        return None
    struct_type = material.struct_type
    fields: dict[str, Any] = {}
    if material.struct_props_id and struct_type is not None:
        record = SQLExecutor.get_structure_instance(struct_type, material.struct_props_id)
        if record:
            fields = {
                key: _jsonable(value)
                for key, value in record.items()
                if key != 'id'
            }
    return StructureOut(
        type_id=struct_type.pk if struct_type else None,
        type_code=struct_type.code if struct_type else None,
        type_name=struct_type.name if struct_type else None,
        record_id=material.struct_props_id,
        fields=fields,
    )


def serialize_material_detail(material: Material) -> MaterialDetail:
    base = serialize_material_list_item(material)
    return MaterialDetail(
        **base.model_dump(),
        manufacturer=material.manufacturer.name if material.manufacturer_id else None,
        availability=material.availability.name if material.availability_id else None,
        technology=material.technology.name if material.technology_id else None,
        properties=_material_properties(material),
        structure=_material_structure(material),
    )


def serialize_sample(sample: Sample) -> SampleOut:
    scans_count = getattr(sample, 'scans_count', None)
    if scans_count is None:
        scans_count = sample.scans.count()
    return SampleOut(
        id=sample.pk,
        code=sample.code,
        name=sample.name,
        material_id=sample.material_id,
        workspace_id=sample.workspace_id,
        object_type=sample.object_type,
        created_at=sample.created_at,
        scans_count=int(scans_count),
    )


def serialize_sample_detail(sample: Sample) -> SampleDetail:
    rows = (
        SampleProperty.objects.filter(sample=sample)
        .select_related('property')
        .order_by('property__name')
    )
    properties = [
        PropertyOut(
            id=row.property.pk,
            code=row.property.name,
            name=row.property.display_name,
            data_type=row.property.data_type,
            value=row.value,
            display_value=row.display_value(),
            notes=row.notes or '',
        )
        for row in rows
    ]
    base = serialize_sample(sample)
    return SampleDetail(**base.model_dump(), properties=properties)


def _scan_size(scan: ScanRecord) -> int | None:
    """Return file size only for local storage.

    On S3/SeaweedFS ``FileField.size`` issues a remote HEAD and can hang the
    whole list/detail response when object storage is slow or unreachable.
    """
    if not scan.file:
        return None
    if not isinstance(scan.file.storage, FileSystemStorage):
        return None
    try:
        return scan.file.size
    except Exception:
        return None



def serialize_scan(scan: ScanRecord) -> ScanOut:
    tag_names = []
    # Prefetch-friendly: tags may already be cached on the instance.
    try:
        tag_names = [tag.name for tag in scan.tags.all()]
    except Exception:
        tag_names = []
    return ScanOut(
        id=scan.pk,
        sample_id=scan.sample_id,
        workspace_id=scan.workspace_id,
        title=scan.title,
        description=scan.description or '',
        method=scan.method,
        filename=scan.filename,
        size_bytes=_scan_size(scan),
        uploaded_at=scan.uploaded_at,
        download_url=reverse('api:scan_download', kwargs={'scan_id': scan.pk}),
        tags=tag_names,
    )
