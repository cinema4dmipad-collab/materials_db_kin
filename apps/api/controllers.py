from http import HTTPStatus
from typing import ClassVar

from dmr import Body, Controller, FileMetadata, Path, Query, ResponseSpec, modify, validate
from dmr.errors import ErrorModel
from dmr.files import FileResponseSpec
from dmr.parsers import MultiPartParser
from dmr.plugins.pydantic import PydanticSerializer
from dmr.security.base import SyncAuth
from django.core.exceptions import ValidationError
from django.db.models import Count as OrmCount
from django.db.models import Q
from django.http import FileResponse, Http404

from apps.api.access import (
    api_error,
    materials_qs,
    require_perm,
    require_workspace,
    samples_qs,
    scans_qs,
    user_workspaces_qs,
)
from apps.api.auth import API_TOKEN_AUTH
from apps.api.schemas import (
    MaterialDetail,
    MaterialListQuery,
    MaterialListResponse,
    MaterialPath,
    PaginatedMeta,
    SampleDetail,
    SampleListQuery,
    SampleListResponse,
    SamplePath,
    ScanCreateBody,
    ScanFilesPayload,
    ScanListQuery,
    ScanListResponse,
    ScanOut,
    ScanPath,
    WorkspaceOut,
)
from apps.api.serializers import (
    serialize_material_detail,
    serialize_material_list_item,
    serialize_sample,
    serialize_sample_detail,
    serialize_scan,
    serialize_workspace,
)
from apps.core.file_download import StorageUnavailable, build_file_download_response
from apps.scans.models import ScanRecord
from apps.scans.title_utils import default_scan_title
from apps.scans.validators import validate_scan_file
from apps.workspaces.permissions import WorkspacePerm

_ERROR_RESPONSES = (
    ResponseSpec(ErrorModel, status_code=HTTPStatus.BAD_REQUEST),
    ResponseSpec(ErrorModel, status_code=HTTPStatus.UNAUTHORIZED),
    ResponseSpec(ErrorModel, status_code=HTTPStatus.FORBIDDEN),
    ResponseSpec(ErrorModel, status_code=HTTPStatus.NOT_FOUND),
    ResponseSpec(ErrorModel, status_code=HTTPStatus.UNPROCESSABLE_ENTITY),
    ResponseSpec(ErrorModel, status_code=HTTPStatus.SERVICE_UNAVAILABLE),
)


def _paginate(queryset, *, limit: int, offset: int):
    count = queryset.count()
    items = list(queryset[offset : offset + limit])
    meta = PaginatedMeta(count=count, limit=limit, offset=offset)
    return meta, items


class BaseApiController(Controller[PydanticSerializer]):
    auth: ClassVar[list[SyncAuth]] = [API_TOKEN_AUTH]
    responses: ClassVar[list[ResponseSpec]] = list(_ERROR_RESPONSES)


class WorkspaceListController(BaseApiController):
    def get(self) -> list[WorkspaceOut]:
        workspaces = user_workspaces_qs(self.request.user)
        return [serialize_workspace(item) for item in workspaces]


class MaterialListController(BaseApiController):

    def get(self, parsed_query: Query[MaterialListQuery]) -> MaterialListResponse:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.MATERIAL_VIEW)
        queryset = materials_qs(workspace).order_by('code')
        meta, items = _paginate(
            queryset,
            limit=parsed_query.limit,
            offset=parsed_query.offset,
        )
        return MaterialListResponse(
            meta=meta,
            results=[serialize_material_list_item(item) for item in items],
        )


class MaterialDetailController(BaseApiController):
    def get(self, parsed_path: Path[MaterialPath]) -> MaterialDetail:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.MATERIAL_VIEW)
        material = materials_qs(workspace).filter(pk=parsed_path.material_id).first()
        if material is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
        return serialize_material_detail(material)


class SampleListController(BaseApiController):
    def get(self, parsed_query: Query[SampleListQuery]) -> SampleListResponse:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SAMPLE_VIEW)
        queryset = (
            samples_qs(workspace).annotate(scans_count=OrmCount('scans')).order_by('code')
        )
        if parsed_query.material_id is not None:
            queryset = queryset.filter(material_id=parsed_query.material_id)
        search = (parsed_query.search or '').strip()
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        meta, items = _paginate(
            queryset,
            limit=parsed_query.limit,
            offset=parsed_query.offset,
        )
        return SampleListResponse(
            meta=meta,
            results=[serialize_sample(item) for item in items],
        )


class SampleDetailController(BaseApiController):
    def get(self, parsed_path: Path[SamplePath]) -> SampleDetail:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SAMPLE_VIEW)
        sample = (
            samples_qs(workspace)
            .annotate(scans_count=OrmCount('scans'))
            .filter(pk=parsed_path.sample_id)
            .first()
        )
        if sample is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
        return serialize_sample_detail(sample)


class ScanListController(BaseApiController):
    def get(self, parsed_query: Query[ScanListQuery]) -> ScanListResponse:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_VIEW)
        queryset = scans_qs(workspace).order_by('-uploaded_at')
        if parsed_query.sample_id is not None:
            queryset = queryset.filter(sample_id=parsed_query.sample_id)
        meta, items = _paginate(
            queryset,
            limit=parsed_query.limit,
            offset=parsed_query.offset,
        )
        return ScanListResponse(
            meta=meta,
            results=[serialize_scan(item) for item in items],
        )


class ScanDetailController(BaseApiController):
    def get(self, parsed_path: Path[ScanPath]) -> ScanOut:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_VIEW)
        scan = scans_qs(workspace).filter(pk=parsed_path.scan_id).first()
        if scan is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
        return serialize_scan(scan)


class ScanCreateController(BaseApiController):
    parsers = (MultiPartParser(),)

    @modify(status_code=HTTPStatus.CREATED)
    def post(
        self,
        parsed_path: Path[SamplePath],
        parsed_file_metadata: FileMetadata[ScanFilesPayload],
        parsed_body: Body[ScanCreateBody],
    ) -> ScanOut:
        del parsed_file_metadata
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_CREATE)
        sample = samples_qs(workspace).filter(pk=parsed_path.sample_id).first()
        if sample is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)

        uploaded = self.request.FILES.get('file')
        if uploaded is None:
            raise api_error('Файл скана обязателен (поле file).', HTTPStatus.BAD_REQUEST)
        try:
            validate_scan_file(uploaded)
        except ValidationError as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            raise api_error(message, HTTPStatus.BAD_REQUEST) from exc

        method = parsed_body.method or 'echo'
        allowed_methods = {choice[0] for choice in ScanRecord.METHODS}
        if method not in allowed_methods:
            raise api_error('Некорректный method.', HTTPStatus.BAD_REQUEST)

        title = (parsed_body.title or '').strip() or default_scan_title(sample)
        description = parsed_body.description or ''
        scan = ScanRecord(
            sample=sample,
            workspace=workspace,
            title=title,
            description=description,
            method=method,
            uploaded_by=self.request.user.get_username(),
            uploaded_by_user=self.request.user,
        )
        scan.file = uploaded
        scan.save()
        return serialize_scan(scan)


class ScanDownloadController(BaseApiController):
    # Binary FileResponse: skip JSON response validation.
    validate_responses: ClassVar[bool] = False

    @validate(
        FileResponseSpec(as_attachment=True, status_code=HTTPStatus.OK),
        *_ERROR_RESPONSES,
    )
    def get(self, parsed_path: Path[ScanPath]) -> FileResponse:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_VIEW)
        scan = scans_qs(workspace).filter(pk=parsed_path.scan_id).first()
        if scan is None or not scan.file:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
        try:
            return build_file_download_response(scan.file, filename=scan.filename)
        except Http404 as exc:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND) from exc
        except StorageUnavailable as exc:
            raise api_error(
                'Файловое хранилище недоступно (S3/SeaweedFS).',
                HTTPStatus.SERVICE_UNAVAILABLE,
            ) from exc
