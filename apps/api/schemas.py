from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str = ''


class PaginatedMeta(BaseModel):
    count: int
    limit: int
    offset: int


class DesktopConnectBody(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)


class DesktopConnectOut(BaseModel):
    ok: bool = True
    device_id: str
    active: bool = True


class DesktopDisconnectBody(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)


class DesktopDisconnectOut(BaseModel):
    ok: bool = True
    device_id: str
    active: bool = False


class DesktopCommandsQuery(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)


class DesktopCommandOut(BaseModel):
    id: UUID
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DesktopCommandsOut(BaseModel):
    ok: bool = True
    active: bool
    commands: list[DesktopCommandOut] = Field(default_factory=list)


class PropertyOut(BaseModel):
    id: UUID
    code: str
    name: str
    data_type: str
    value: str
    display_value: str
    notes: str = ''


class StructureOut(BaseModel):
    type_id: int | None = None
    type_code: str | None = None
    type_name: str | None = None
    record_id: UUID | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class MaterialListItem(BaseModel):
    id: UUID
    code: str
    name: str
    description: str = ''
    home_workspace_id: UUID | None = None
    struct_type_id: int | None = None
    created_at: datetime
    updated_at: datetime


class MaterialDetail(MaterialListItem):
    manufacturer: str | None = None
    availability: str | None = None
    technology: str | None = None
    properties: list[PropertyOut] = Field(default_factory=list)
    structure: StructureOut | None = None


class MaterialListResponse(BaseModel):
    meta: PaginatedMeta
    results: list[MaterialListItem]


class SampleOut(BaseModel):
    id: UUID
    code: str
    name: str
    material_id: UUID
    workspace_id: UUID | None = None
    object_type: str
    created_at: datetime
    scans_count: int = 0


class SampleListResponse(BaseModel):
    meta: PaginatedMeta
    results: list[SampleOut]


class SampleDetail(SampleOut):
    properties: list[PropertyOut] = Field(default_factory=list)


class ScanOut(BaseModel):
    id: UUID
    sample_id: UUID
    workspace_id: UUID | None = None
    title: str
    description: str = ''
    method: str
    filename: str = ''
    size_bytes: int | None = None
    uploaded_at: datetime
    download_url: str
    tags: list[str] = Field(default_factory=list)


class ScanListResponse(BaseModel):
    meta: PaginatedMeta
    results: list[ScanOut]


class ScanCreateBody(BaseModel):
    model_config = ConfigDict(extra='ignore')

    title: str | None = None
    description: str = ''
    method: str = 'echo'
    # Comma-separated tag names (same convention as web UI tag_names).
    tag_names: str = ''


class ScanFileMeta(BaseModel):
    model_config = ConfigDict(extra='ignore')

    name: str
    size: int
    content_type: str | None = None


class ScanFilesPayload(BaseModel):
    file: ScanFileMeta


class SamplePath(BaseModel):
    sample_id: UUID


class MaterialPath(BaseModel):
    material_id: UUID


class ScanPath(BaseModel):
    scan_id: UUID


class PaginationQuery(BaseModel):
    model_config = ConfigDict(extra='ignore')

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MaterialListQuery(PaginationQuery):
    pass


class SampleListQuery(PaginationQuery):
    material_id: UUID | None = None
    search: str | None = Field(
        default=None,
        max_length=200,
        description='Case-insensitive substring match on sample code or name.',
    )


class ScanListQuery(PaginationQuery):
    sample_id: UUID | None = None
