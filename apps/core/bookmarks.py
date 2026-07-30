"""Закладки пользователя на материалы, образцы, сканы, записи и типы структур."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.core.models import BookmarkEntityType, UserBookmark
from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm


SIDEBAR_BOOKMARK_LIMIT = 10
STRUCTURE_TYPE_BOOKMARK_NAMESPACE = uuid.UUID('6b8c9f2a-4d1e-4a5b-9c3d-2e1f0a9b8c7d')

ENTITY_VIEW_PERM = {
    BookmarkEntityType.MATERIAL: WorkspacePerm.MATERIAL_VIEW,
    BookmarkEntityType.SAMPLE: WorkspacePerm.SAMPLE_VIEW,
    BookmarkEntityType.SCAN: WorkspacePerm.SCAN_VIEW,
    BookmarkEntityType.STRUCTURE_RECORD: WorkspacePerm.STRUCTURE_VIEW,
    BookmarkEntityType.STRUCTURE_TYPE: WorkspacePerm.STRUCTURE_VIEW,
}

ENTITY_ICONS = {
    BookmarkEntityType.MATERIAL: 'bi-box-seam',
    BookmarkEntityType.SAMPLE: 'bi-collection',
    BookmarkEntityType.SCAN: 'bi-hdd-stack',
    BookmarkEntityType.STRUCTURE_RECORD: 'bi-diagram-3',
    BookmarkEntityType.STRUCTURE_TYPE: 'bi-diagram-3',
}


@dataclass(frozen=True)
class BookmarkToggleResult:
    bookmark: UserBookmark | None
    removed: bool


@dataclass(frozen=True)
class ResolvedBookmark:
    bookmark: UserBookmark
    label: str
    url: str
    icon: str
    entity_type_label: str
    subtitle: str


def _require_view_perm(user, workspace, entity_type: str) -> None:
    perm = ENTITY_VIEW_PERM.get(entity_type)
    if not perm or not has_workspace_perm(user, workspace, perm):
        raise PermissionDenied


def structure_type_bookmark_entity_id(code: str) -> uuid.UUID:
    return uuid.uuid5(STRUCTURE_TYPE_BOOKMARK_NAMESPACE, f'structure-type:{code}')


def _load_structure_record(*, workspace, entity_id, context_slug: str | None):
    from apps.structures.table_storage import get_row
    from apps.workspaces.services import structure_types_visible_in

    if not context_slug:
        return None
    structure_type = (
        structure_types_visible_in(workspace)
        .filter(code=context_slug, is_created=True)
        .prefetch_related('fields')
        .first()
    )
    if structure_type is None:
        return None
    record = get_row(structure_type, entity_id)
    if not record:
        return None
    return {'structure_type': structure_type, 'record': record}


def _load_entity(*, workspace, entity_type: str, entity_id, parent_id=None, context_slug=None):
    from apps.materials.models import Material
    from apps.samples.models import Sample
    from apps.scans.models import ScanRecord
    from apps.workspaces.services import materials_visible_in, samples_visible_in, scans_visible_in

    if entity_type == BookmarkEntityType.MATERIAL:
        return materials_visible_in(workspace).filter(pk=entity_id).first()
    if entity_type == BookmarkEntityType.SAMPLE:
        return samples_visible_in(workspace).filter(pk=entity_id).first()
    if entity_type == BookmarkEntityType.SCAN:
        qs = scans_visible_in(workspace).filter(pk=entity_id)
        if parent_id:
            qs = qs.filter(sample_id=parent_id)
        return qs.select_related('sample').first()
    if entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        return _load_structure_record(
            workspace=workspace,
            entity_id=entity_id,
            context_slug=context_slug,
        )
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        from apps.workspaces.services import structure_types_visible_in

        queryset = structure_types_visible_in(workspace)
        if context_slug:
            return queryset.filter(code=context_slug).first()
        return None
    return None


def _entity_label(entity, *, entity_type: str, workspace=None) -> str:
    if entity is None:
        return ''
    if entity_type == BookmarkEntityType.MATERIAL:
        return (entity.name or entity.code or str(entity.pk)).strip()
    if entity_type == BookmarkEntityType.SAMPLE:
        name = (entity.name or '').strip()
        code = (entity.code or '').strip()
        return f'{code} — {name}' if name else code
    if entity_type == BookmarkEntityType.SCAN:
        return (entity.title or entity.filename or str(entity.pk)).strip()
    if entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        from apps.structures.table_storage import structure_record_display_label

        return structure_record_display_label(
            entity['record'],
            entity['structure_type'],
            workspace=workspace,
        )
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        return (entity.name or entity.code or str(entity.pk)).strip()
    return str(entity.pk) if hasattr(entity, 'pk') else ''


def _entity_subtitle(entity, *, entity_type: str) -> str:
    if entity is None:
        return ''
    if entity_type == BookmarkEntityType.MATERIAL:
        return (entity.code or '').strip()
    if entity_type == BookmarkEntityType.SAMPLE:
        material = getattr(entity, 'material', None)
        return material.code if material else ''
    if entity_type == BookmarkEntityType.SCAN:
        sample = getattr(entity, 'sample', None)
        return sample.code if sample else ''
    if entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        return entity['structure_type'].name
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        return 'Создать материал'
    return ''


def _entity_url(entity, *, entity_type: str) -> str:
    if entity is None:
        return ''
    if entity_type == BookmarkEntityType.MATERIAL:
        return reverse('materials:detail', kwargs={'pk': entity.pk})
    if entity_type == BookmarkEntityType.SAMPLE:
        return reverse('samples:detail', kwargs={'pk': entity.pk})
    if entity_type == BookmarkEntityType.SCAN:
        return reverse(
            'scans:detail',
            kwargs={'sample_pk': entity.sample_id, 'pk': entity.pk},
        )
    if entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        return reverse(
            'structures:detail',
            kwargs={
                'type_code': entity['structure_type'].code,
                'pk': entity['record']['id'],
            },
        )
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        return f"{reverse('materials:create')}?{urlencode({'struct_type': str(entity.pk)})}"
    return ''


def _parent_id_for_entity(entity, *, entity_type: str):
    if entity_type == BookmarkEntityType.SCAN:
        return entity.sample_id
    return None


def _context_slug_for_entity(entity, *, entity_type: str) -> str:
    if entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        return entity['structure_type'].code
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        return entity.code
    return ''


def _resolve_entity_id(entity, *, entity_type: str = '') -> Any:
    if entity_type == BookmarkEntityType.STRUCTURE_TYPE and entity is not None and hasattr(entity, 'code'):
        return structure_type_bookmark_entity_id(entity.code)
    if isinstance(entity, dict):
        return entity.get('id')
    return getattr(entity, 'pk', None)


def bookmarked_entity_ids(*, user, workspace, entity_type: str) -> set[str]:
    if user is None or not getattr(user, 'is_authenticated', False) or workspace is None:
        return set()
    return {
        str(entity_id)
        for entity_id in UserBookmark.objects.filter(
            user=user,
            workspace=workspace,
            entity_type=entity_type,
        ).values_list('entity_id', flat=True)
    }


def is_bookmarked(*, user, workspace, entity_type: str, entity_id) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False) or workspace is None:
        return False
    return UserBookmark.objects.filter(
        user=user,
        workspace=workspace,
        entity_type=entity_type,
        entity_id=entity_id,
    ).exists()


def bookmark_context(
    request,
    *,
    entity_type: str,
    entity=None,
    entity_id=None,
    parent_id=None,
    context_slug='',
) -> dict[str, Any]:
    workspace = getattr(request, 'active_workspace', None)
    if entity_id is None:
        entity_id = _resolve_entity_id(entity, entity_type=entity_type)
    if parent_id is None and entity_type == BookmarkEntityType.SCAN and entity is not None:
        parent_id = getattr(entity, 'sample_id', None)
    if not context_slug and entity_type == BookmarkEntityType.STRUCTURE_RECORD:
        if isinstance(entity, dict) and 'structure_type' in entity:
            context_slug = entity['structure_type'].code
    if not context_slug and entity_type == BookmarkEntityType.STRUCTURE_TYPE:
        if entity is not None and hasattr(entity, 'code'):
            context_slug = entity.code
    return {
        'bookmark_entity_type': entity_type,
        'bookmark_entity_id': entity_id,
        'bookmark_parent_id': parent_id,
        'bookmark_context_slug': context_slug or '',
        'is_bookmarked': is_bookmarked(
            user=request.user,
            workspace=workspace,
            entity_type=entity_type,
            entity_id=entity_id,
        ),
    }


def toggle_bookmark(
    *,
    user,
    workspace,
    entity_type: str,
    entity_id,
    parent_id=None,
    context_slug=None,
) -> BookmarkToggleResult:
    if workspace is None:
        raise ValueError('Пространство не выбрано.')
    if entity_type not in ENTITY_VIEW_PERM:
        raise ValueError('Неизвестный тип закладки.')
    _require_view_perm(user, workspace, entity_type)

    existing = UserBookmark.objects.filter(
        user=user,
        workspace=workspace,
        entity_type=entity_type,
        entity_id=entity_id,
    ).first()
    if existing:
        existing.delete()
        return BookmarkToggleResult(bookmark=None, removed=True)

    entity = _load_entity(
        workspace=workspace,
        entity_type=entity_type,
        entity_id=entity_id,
        parent_id=parent_id,
        context_slug=context_slug,
    )
    if entity is None:
        raise ValueError('Объект недоступен или не найден.')

    stored_parent = parent_id or _parent_id_for_entity(entity, entity_type=entity_type)
    stored_context_slug = (context_slug or '').strip() or _context_slug_for_entity(
        entity,
        entity_type=entity_type,
    )
    bookmark = UserBookmark.objects.create(
        user=user,
        workspace=workspace,
        entity_type=entity_type,
        entity_id=entity_id,
        parent_id=stored_parent,
        context_slug=stored_context_slug,
        label=_entity_label(entity, entity_type=entity_type, workspace=workspace),
    )
    return BookmarkToggleResult(bookmark=bookmark, removed=False)


def resolve_bookmark(bookmark: UserBookmark, *, workspace) -> ResolvedBookmark | None:
    entity = _load_entity(
        workspace=workspace,
        entity_type=bookmark.entity_type,
        entity_id=bookmark.entity_id,
        parent_id=bookmark.parent_id,
        context_slug=bookmark.context_slug or None,
    )
    if entity is None:
        return None
    label = _entity_label(entity, entity_type=bookmark.entity_type, workspace=workspace) or bookmark.label
    url = _entity_url(entity, entity_type=bookmark.entity_type)
    if not url:
        return None
    return ResolvedBookmark(
        bookmark=bookmark,
        label=label,
        url=url,
        icon=ENTITY_ICONS.get(bookmark.entity_type, 'bi-bookmark'),
        entity_type_label=bookmark.get_entity_type_display(),
        subtitle=_entity_subtitle(entity, entity_type=bookmark.entity_type),
    )


def list_resolved_bookmarks(*, user, workspace) -> list[ResolvedBookmark]:
    if user is None or not getattr(user, 'is_authenticated', False) or workspace is None:
        return []
    bookmarks = UserBookmark.objects.filter(user=user, workspace=workspace)
    resolved: list[ResolvedBookmark] = []
    stale_ids: list = []
    for bookmark in bookmarks:
        item = resolve_bookmark(bookmark, workspace=workspace)
        if item is None:
            stale_ids.append(bookmark.pk)
            continue
        resolved.append(item)
    if stale_ids:
        UserBookmark.objects.filter(pk__in=stale_ids).delete()
    return resolved


def _path_is_active(*, request_path: str, target_url: str) -> bool:
    if not request_path or not target_url:
        return False
    parsed = urlparse(target_url)
    target_path = parsed.path or target_url
    return request_path == target_path or request_path.rstrip('/') == target_path.rstrip('/')


def sidebar_bookmark_items(
    *,
    user,
    workspace,
    request_path: str = '',
    limit: int = SIDEBAR_BOOKMARK_LIMIT,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for resolved in list_resolved_bookmarks(user=user, workspace=workspace)[:limit]:
        items.append(
            {
                'label': resolved.label,
                'icon': resolved.icon,
                'url': resolved.url,
                'visible': True,
                'active': _path_is_active(request_path=request_path, target_url=resolved.url),
                'subtitle': resolved.subtitle,
            }
        )
    return items
