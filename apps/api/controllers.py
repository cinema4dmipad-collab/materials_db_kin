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
from apps.api.desktop import (
    claim_commands,
    connect_desktop,
    disconnect_desktop,
    heartbeat_desktop,
)
from apps.api.schemas import (
    DesktopCommandOut,
    DesktopCommandsOut,
    DesktopCommandsQuery,
    DesktopConnectBody,
    DesktopConnectOut,
    DesktopDisconnectBody,
    DesktopDisconnectOut,
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
    ScanOptionsOut,
    ScanOut,
    ScanPath,
    ScanPreviewKindPath,
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
from apps.scans.previews import (
    apply_uploaded_previews,
    delete_replaced_preview_files,
    preview_file,
    resolve_preview_kind,
    scan_options_payload,
)
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


class DesktopConnectController(BaseApiController):
    """KeenetiX registers as active desktop for the PAT owner (last connect wins)."""

    def post(self, parsed_body: Body[DesktopConnectBody]) -> DesktopConnectOut:
        try:
            session = connect_desktop(self.request.user, parsed_body.device_id)
        except ValueError as exc:
            raise api_error(str(exc), HTTPStatus.BAD_REQUEST) from exc
        return DesktopConnectOut(device_id=session.device_id, active=session.is_active)


class DesktopDisconnectController(BaseApiController):
    """KeenetiX releases the active desktop role (Lab status goes offline immediately)."""

    def post(self, parsed_body: Body[DesktopDisconnectBody]) -> DesktopDisconnectOut:
        try:
            disconnect_desktop(self.request.user, parsed_body.device_id)
        except ValueError as exc:
            raise api_error(str(exc), HTTPStatus.BAD_REQUEST) from exc
        return DesktopDisconnectOut(device_id=parsed_body.device_id.strip(), active=False)


class DesktopCommandsController(BaseApiController):
    """Poll pending desktop commands; only the active device receives them."""

    def get(self, parsed_query: Query[DesktopCommandsQuery]) -> DesktopCommandsOut:
        device_id = parsed_query.device_id.strip()
        active = heartbeat_desktop(self.request.user, device_id)
        if not active:
            return DesktopCommandsOut(active=False, commands=[])
        raw = claim_commands(self.request.user, device_id)
        commands = [
            DesktopCommandOut(
                id=item['id'],  # UUID string from desktop.claim_commands
                command=item['command'],
                payload=item['payload'],
                created_at=item['created_at'],
            )
            for item in raw
        ]
        return DesktopCommandsOut(active=True, commands=commands)


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
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(description__icontains=search)
            )
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
        queryset = scans_qs(workspace).prefetch_related('tags').order_by('-uploaded_at')
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
    parsers = (MultiPartParser(),)

    def get(self, parsed_path: Path[ScanPath]) -> ScanOut:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_VIEW)
        scan = (
            scans_qs(workspace)
            .prefetch_related('tags')
            .filter(pk=parsed_path.scan_id)
            .first()
        )
        if scan is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
        return serialize_scan(scan)

    def put(
        self,
        parsed_path: Path[ScanPath],
        parsed_file_metadata: FileMetadata[ScanFilesPayload],
        parsed_body: Body[ScanCreateBody],
    ) -> ScanOut:
        """Replace HDF5 (required) and optionally preview/metadata for an existing scan."""
        del parsed_file_metadata
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_EDIT)
        scan = (
            scans_qs(workspace)
            .prefetch_related('tags')
            .filter(pk=parsed_path.scan_id)
            .first()
        )
        if scan is None:
            raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)

        uploaded = self.request.FILES.get('file')
        if uploaded is None:
            raise api_error('Файл скана обязателен (поле file).', HTTPStatus.BAD_REQUEST)
        try:
            validate_scan_file(uploaded)
        except ValidationError as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            raise api_error(message, HTTPStatus.BAD_REQUEST) from exc

        try:
            old_preview_names = apply_uploaded_previews(scan, self.request.FILES)
        except ValidationError as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            raise api_error(message, HTTPStatus.BAD_REQUEST) from exc

        if parsed_body.method:
            allowed_methods = {choice[0] for choice in ScanRecord.METHODS}
            if parsed_body.method not in allowed_methods:
                raise api_error('Некорректный method.', HTTPStatus.BAD_REQUEST)
            scan.method = parsed_body.method

        title = (parsed_body.title or '').strip()
        if title:
            scan.title = title
        if parsed_body.description:
            scan.description = parsed_body.description

        old_file_name = scan.file.name if scan.file else ''
        scan.file = uploaded
        scan.uploaded_by = self.request.user.get_username()
        scan.uploaded_by_user = self.request.user
        scan.save()

        if old_file_name and old_file_name != (scan.file.name if scan.file else ''):
            try:
                scan.file.storage.delete(old_file_name)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        delete_replaced_preview_files(scan, old_preview_names)

        from apps.api.scan_meta import parse_tag_names
        from apps.core.tag_utils import assign_tags

        tag_names = parse_tag_names(parsed_body.tag_names)
        if tag_names:
            assign_tags(scan, tag_names, workspace=scan.workspace or workspace)

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
        try:
            apply_uploaded_previews(scan, self.request.FILES)
        except ValidationError as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            raise api_error(message, HTTPStatus.BAD_REQUEST) from exc
        scan.save()

        from apps.api.scan_meta import (
            KEENETIX_CLIENT_HEADER,
            KEENETIX_CLIENT_VALUE,
            KEENETIX_SOURCE_TAG,
            parse_tag_names,
        )
        from apps.core.tag_utils import assign_tags

        tag_names = parse_tag_names(parsed_body.tag_names)
        client = (self.request.headers.get(KEENETIX_CLIENT_HEADER) or '').strip()
        if client.casefold() == KEENETIX_CLIENT_VALUE.casefold():
            if KEENETIX_SOURCE_TAG.casefold() not in {n.casefold() for n in tag_names}:
                tag_names.append(KEENETIX_SOURCE_TAG)
        if tag_names:
            assign_tags(scan, tag_names, workspace=sample.workspace or workspace)

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


class ScanPreviewController(BaseApiController):
    """Inline scan preview image (proxied; S3 may be unreachable from clients)."""

    validate_responses: ClassVar[bool] = False

    @validate(
        FileResponseSpec(as_attachment=False, status_code=HTTPStatus.OK),
        *_ERROR_RESPONSES,
    )
    def get(self, parsed_path: Path[ScanPath]) -> FileResponse:
        return _scan_preview_response(self.request, parsed_path.scan_id, kind_slug=None)


class ScanPreviewKindController(BaseApiController):
    validate_responses: ClassVar[bool] = False

    @validate(
        FileResponseSpec(as_attachment=False, status_code=HTTPStatus.OK),
        *_ERROR_RESPONSES,
    )
    def get(self, parsed_path: Path[ScanPreviewKindPath]) -> FileResponse:
        return _scan_preview_response(
            self.request,
            parsed_path.scan_id,
            kind_slug=parsed_path.kind,
        )


class ScanOptionsController(BaseApiController):
    """Catalog for KeenetiX save dialog: methods and preview field names."""

    def get(self) -> ScanOptionsOut:
        workspace = require_workspace(self.request)
        require_perm(self.request.user, workspace, WorkspacePerm.SCAN_VIEW)
        payload = scan_options_payload()
        return ScanOptionsOut(**payload)


def _scan_preview_response(request, scan_id, *, kind_slug: str | None) -> FileResponse:
    workspace = require_workspace(request)
    require_perm(request.user, workspace, WorkspacePerm.SCAN_VIEW)
    scan = scans_qs(workspace).filter(pk=scan_id).first()
    kind = resolve_preview_kind(kind_slug)
    field = preview_file(scan, kind) if scan is not None and kind is not None else None
    if field is None:
        raise api_error('Не найдено.', HTTPStatus.NOT_FOUND)
    filename = field.name.rsplit('/', 1)[-1]
    try:
        return build_file_download_response(
            field,
            filename=filename,
            as_attachment=False,
            cache_control='private, no-store',
        )
    except Http404 as exc:
        raise api_error('Не найдено.', HTTPStatus.NOT_FOUND) from exc
    except StorageUnavailable as exc:
        raise api_error(
            'Файловое хранилище недоступно (S3/SeaweedFS).',
            HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc
