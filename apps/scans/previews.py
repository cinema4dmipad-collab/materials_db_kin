"""C-scan / B-scan preview kinds for ScanRecord and KeenetiX uploads."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.scans.validators import validate_scan_preview


@dataclass(frozen=True)
class ScanPreviewKind:
    key: str
    slug: str
    field: str
    label: str


PREVIEW_KINDS: tuple[ScanPreviewKind, ...] = (
    ScanPreviewKind('b_xz', 'b-xz', 'preview_b_xz', 'B-скан-XZ'),
    ScanPreviewKind('b_yz', 'b-yz', 'preview_b_yz', 'B-скан-YZ'),
    ScanPreviewKind('c', 'c', 'preview', 'C-скан'),
)

DEFAULT_PREVIEW_KIND = PREVIEW_KINDS[-1]

_KIND_LOOKUP: dict[str, ScanPreviewKind] = {}
for _kind in PREVIEW_KINDS:
    _KIND_LOOKUP[_kind.key] = _kind
    _KIND_LOOKUP[_kind.slug] = _kind
    _KIND_LOOKUP[_kind.field] = _kind
    _KIND_LOOKUP[_kind.key.replace('_', '-')] = _kind


def resolve_preview_kind(value: str | None) -> ScanPreviewKind | None:
    if value is None or str(value).strip() == '':
        return DEFAULT_PREVIEW_KIND
    raw = str(value).strip()
    if raw in _KIND_LOOKUP:
        return _KIND_LOOKUP[raw]
    normalized = raw.lower().replace('_', '-')
    return _KIND_LOOKUP.get(normalized)


def preview_file(scan, kind: ScanPreviewKind):
    field = getattr(scan, kind.field, None)
    if not field:
        return None
    return field


def _preview_upload_from_files(files, kind: ScanPreviewKind):
    """Accept official field names and KeenetiX aliases (kind / slug)."""
    aliases = (
        kind.field,
        kind.key,
        kind.slug,
        kind.key.replace('_', '-'),
        f'preview_{kind.key}',
        f'preview-{kind.slug}',
    )
    for alias in aliases:
        uploaded = files.get(alias)
        if uploaded is not None:
            return uploaded
    return None


def has_any_preview(scan) -> bool:
    return any(preview_file(scan, kind) for kind in PREVIEW_KINDS)


def delete_preview_files(scan) -> None:
    for kind in PREVIEW_KINDS:
        field = preview_file(scan, kind)
        if not field:
            continue
        try:
            field.delete(save=False)
        except OSError:
            pass


def apply_uploaded_previews(scan, files) -> dict[str, str]:
    """Validate and assign preview uploads. Returns old storage names to delete after save."""
    old_names: dict[str, str] = {}
    first_error: ValidationError | None = None
    for kind in PREVIEW_KINDS:
        uploaded = _preview_upload_from_files(files, kind)
        if uploaded is None:
            continue
        try:
            validate_scan_preview(uploaded)
        except ValidationError as exc:
            if first_error is None:
                first_error = exc
            continue
        current = getattr(scan, kind.field)
        if current:
            old_names[kind.field] = current.name
        setattr(scan, kind.field, uploaded)
    if first_error is not None:
        raise first_error
    return old_names


def delete_replaced_preview_files(scan, old_names: dict[str, str]) -> None:
    for field_name, old_name in old_names.items():
        current = getattr(scan, field_name, None)
        new_name = current.name if current else ''
        if not old_name or old_name == new_name:
            continue
        storage = current.storage if current else None
        if storage is None:
            continue
        try:
            storage.delete(old_name)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass


def _preview_url_version(scan, kind: ScanPreviewKind) -> str:
    field = preview_file(scan, kind)
    if not field or not field.name:
        return ''
    token = field.name.rsplit('/', 1)[-1]
    return f'?v={quote(token, safe="")}'


def web_preview_url(scan, kind: ScanPreviewKind) -> str:
    kwargs = {'sample_pk': scan.sample_id, 'pk': scan.pk}
    if kind.key == 'c':
        url = reverse('scans:preview', kwargs=kwargs)
    else:
        kwargs['kind'] = kind.slug
        url = reverse('scans:preview_kind', kwargs=kwargs)
    return url + _preview_url_version(scan, kind)


def api_preview_url(scan, kind: ScanPreviewKind) -> str | None:
    if not preview_file(scan, kind):
        return None
    if kind.key == 'c':
        url = reverse('api:scan_preview', kwargs={'scan_id': scan.pk})
    else:
        url = reverse(
            'api:scan_preview_kind',
            kwargs={'scan_id': scan.pk, 'kind': kind.slug},
        )
    return url + _preview_url_version(scan, kind)


def scan_options_payload() -> dict:
    from apps.scans.models import ScanRecord
    from apps.scans.validators import MAX_SCAN_PREVIEW_SIZE

    return {
        'methods': [
            {'value': value, 'label': label}
            for value, label in ScanRecord.METHODS
        ],
        'preview_fields': [
            {
                'field': kind.field,
                'kind': kind.key,
                'label': kind.label,
                'slug': kind.slug,
            }
            for kind in PREVIEW_KINDS
        ],
        'max_preview_bytes': MAX_SCAN_PREVIEW_SIZE,
    }
