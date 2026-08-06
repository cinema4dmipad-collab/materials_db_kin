"""Закладки пользователя на материалы, образцы, сканы, записи, типы структур и произвольные URL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.core.models import BookmarkEntityType, UserBookmark
from apps.workspaces.permissions import WorkspacePerm, has_workspace_perm


SIDEBAR_BOOKMARK_LIMIT = 10
STRUCTURE_TYPE_BOOKMARK_NAMESPACE = uuid.UUID('6b8c9f2a-4d1e-4a5b-9c3d-2e1f0a9b8c7d')
PAGE_BOOKMARK_NAMESPACE = uuid.UUID('a1b2c3d4-e5f6-7890-abcd-ef1234567890')

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
    BookmarkEntityType.PAGE: 'bi-bookmark',
}

# Curated Bootstrap Icons for page bookmarks (no free-form classes).
PAGE_BOOKMARK_ICONS = (
    'bi-bookmark',
    'bi-star',
    'bi-house',
    'bi-question-circle',
    'bi-journal-text',
    'bi-list-ul',
    'bi-box-seam',
    'bi-collection',
    'bi-hdd-stack',
    'bi-diagram-3',
    'bi-gear',
    'bi-link-45deg',
)
DEFAULT_PAGE_BOOKMARK_ICON = 'bi-bookmark'


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


def normalize_page_bookmark_url(raw_url: str) -> str:
    """
    Accept only same-site relative URLs (path + optional query).
    Drop fragment; collapse trailing slash so /help and /help/ are the same bookmark.
    """
    text = (raw_url or '').strip()
    if not text or text.startswith('//'):
        raise ValueError('Укажите относительный путь страницы, например /help/.')
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc:
        raise ValueError('В закладку можно сохранить только путь этого сайта.')
    path = parsed.path or '/'
    if not path.startswith('/'):
        path = '/' + path
    if len(path) > 1:
        path = path.rstrip('/')
    if len(path) > 1800:
        raise ValueError('Слишком длинный адрес страницы.')
    # Fragment ignored — otherwise the same page bookmarks twice (#section).
    normalized = urlunparse(('', '', path, '', parsed.query, ''))
    if len(normalized) > 2000:
        raise ValueError('Слишком длинный адрес страницы.')
    return normalized


def page_bookmark_entity_id(url: str) -> uuid.UUID:
    return uuid.uuid5(PAGE_BOOKMARK_NAMESPACE, f'page:{url}')


def _page_bookmarks_matching_url(*, user, workspace, normalized_url: str) -> list[UserBookmark]:
    """Find page bookmarks that canonicalize to the same URL (incl. legacy slash variants)."""
    matches: list[UserBookmark] = []
    canonical_id = page_bookmark_entity_id(normalized_url)
    for bookmark in UserBookmark.objects.filter(
        user=user,
        workspace=workspace,
        entity_type=BookmarkEntityType.PAGE,
    ):
        if bookmark.entity_id == canonical_id:
            matches.append(bookmark)
            continue
        try:
            if normalize_page_bookmark_url(bookmark.url or '') == normalized_url:
                matches.append(bookmark)
        except ValueError:
            continue
    return matches


@dataclass(frozen=True)
class PageBookmarkSaveResult:
    bookmark: UserBookmark
    created: bool
    updated: bool


def normalize_page_bookmark_icon(raw_icon: str | None) -> str:
    icon = (raw_icon or '').strip()
    if not icon:
        return DEFAULT_PAGE_BOOKMARK_ICON
    if icon not in PAGE_BOOKMARK_ICONS:
        raise ValueError('Выберите иконку из списка.')
    return icon


def save_page_bookmark(
    *,
    user,
    workspace,
    url: str,
    label: str,
    icon: str = '',
) -> PageBookmarkSaveResult:
    if workspace is None:
        raise ValueError('Пространство не выбрано.')
    normalized_url = normalize_page_bookmark_url(url)
    name = (label or '').strip()
    if not name:
        raise ValueError('Укажите название закладки.')
    if len(name) > 300:
        raise ValueError('Название закладки слишком длинное.')
    chosen_icon = normalize_page_bookmark_icon(icon)
    entity_id = page_bookmark_entity_id(normalized_url)
    matches = _page_bookmarks_matching_url(
        user=user,
        workspace=workspace,
        normalized_url=normalized_url,
    )
    if matches:
        # Keep newest; drop slash/# duplicates of the same page.
        matches.sort(key=lambda row: row.created_at, reverse=True)
        existing = matches[0]
        stale_ids = [row.pk for row in matches[1:]]
        if stale_ids:
            UserBookmark.objects.filter(pk__in=stale_ids).delete()
        existing.label = name
        existing.url = normalized_url
        existing.icon = chosen_icon
        # Rebuild entity_id if an older slash-variant row was kept.
        update_fields = ['label', 'url', 'icon']
        if existing.entity_id != entity_id:
            existing.entity_id = entity_id
            update_fields.append('entity_id')
        existing.save(update_fields=update_fields)
        return PageBookmarkSaveResult(bookmark=existing, created=False, updated=True)
    bookmark = UserBookmark.objects.create(
        user=user,
        workspace=workspace,
        entity_type=BookmarkEntityType.PAGE,
        entity_id=entity_id,
        url=normalized_url,
        icon=chosen_icon,
        label=name,
    )
    return PageBookmarkSaveResult(bookmark=bookmark, created=True, updated=False)


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
    if bookmark.entity_type == BookmarkEntityType.PAGE:
        try:
            url = normalize_page_bookmark_url(bookmark.url or '')
        except ValueError:
            return None
        icon = bookmark.icon if bookmark.icon in PAGE_BOOKMARK_ICONS else DEFAULT_PAGE_BOOKMARK_ICON
        return ResolvedBookmark(
            bookmark=bookmark,
            label=(bookmark.label or url).strip() or url,
            url=url,
            icon=icon,
            entity_type_label=bookmark.get_entity_type_display(),
            subtitle=url,
        )

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
    seen_page_urls: set[str] = set()
    for bookmark in bookmarks:
        if bookmark.entity_type == BookmarkEntityType.PAGE:
            try:
                page_key = normalize_page_bookmark_url(bookmark.url or '')
            except ValueError:
                stale_ids.append(bookmark.pk)
                continue
            if page_key in seen_page_urls:
                stale_ids.append(bookmark.pk)
                continue
            seen_page_urls.add(page_key)
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
                'remove_url': reverse(
                    'core:bookmark_remove',
                    kwargs={'pk': resolved.bookmark.pk},
                ),
            }
        )
    return items
