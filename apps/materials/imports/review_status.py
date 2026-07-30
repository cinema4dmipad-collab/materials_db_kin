"""Статус проверки материалов после импорта (scoped-теги статус::…)."""

from __future__ import annotations

from apps.core.tag_utils import (
    assign_tags,
    get_or_create_tags,
    merge_import_tag_names,
    tag_slug_from_name,
)

IMPORT_STATUS_SCOPE = 'статус'
IMPORT_STATUS_PENDING = 'статус::на проверке'
IMPORT_STATUS_ESTABLISHED = 'статус::учрежден'

# Старые имена тегов (канбан «Утвержден» / «Проверено») — только для выборки.
_IMPORT_STATUS_LEGACY_PENDING = 'статус::утвержден'
_IMPORT_STATUS_LEGACY_ESTABLISHED = 'статус::проверен'

# Обратная совместимость имён констант в коде.
IMPORT_STATUS_APPROVED = IMPORT_STATUS_PENDING
IMPORT_STATUS_VERIFIED = IMPORT_STATUS_ESTABLISHED

IMPORT_STATUS_PENDING_COLOR = '#E6A700'
IMPORT_STATUS_ESTABLISHED_COLOR = '#027A48'

IMPORT_STATUS_APPROVED_COLOR = IMPORT_STATUS_PENDING_COLOR
IMPORT_STATUS_VERIFIED_COLOR = IMPORT_STATUS_ESTABLISHED_COLOR

# Канбан: на проверке (inbox импорта) ↔ учрежден
IMPORT_STATUS_BY_COLUMN = {
    'approved': IMPORT_STATUS_PENDING,
    'verified': IMPORT_STATUS_ESTABLISHED,
}
IMPORT_COLUMN_BY_STATUS = {v: k for k, v in IMPORT_STATUS_BY_COLUMN.items()}

IMPORT_REVIEW_COLUMN_LABELS = {
    'approved': 'На проверке',
    'verified': 'Учрежден',
}

IMPORT_STATUS_COLORS = {
    IMPORT_STATUS_PENDING: IMPORT_STATUS_PENDING_COLOR,
    IMPORT_STATUS_ESTABLISHED: IMPORT_STATUS_ESTABLISHED_COLOR,
    _IMPORT_STATUS_LEGACY_PENDING: IMPORT_STATUS_PENDING_COLOR,
    _IMPORT_STATUS_LEGACY_ESTABLISHED: IMPORT_STATUS_ESTABLISHED_COLOR,
}

_PENDING_STATUS_NAMES = (
    IMPORT_STATUS_PENDING,
    _IMPORT_STATUS_LEGACY_PENDING,
)
_ESTABLISHED_STATUS_NAMES = (
    IMPORT_STATUS_ESTABLISHED,
    _IMPORT_STATUS_LEGACY_ESTABLISHED,
)


def import_status_approved_slug() -> str:
    return tag_slug_from_name(IMPORT_STATUS_PENDING)


def import_status_verified_slug() -> str:
    return tag_slug_from_name(IMPORT_STATUS_ESTABLISHED)


def ensure_import_status_tag_colors(workspace) -> None:
    """Создаёт/подкрашивает теги статуса импорта в workspace."""
    if workspace is None:
        return
    for name, color in IMPORT_STATUS_COLORS.items():
        tags = get_or_create_tags([name], workspace)
        for tag in tags:
            if (tag.color or '').strip().casefold() != color.casefold():
                tag.color = color
                tag.save(update_fields=['color'])


def tag_names_with_import_status_on_create(
    existing_names: list[str],
    import_names: list[str] | None,
    *,
    created: bool,
) -> list[str] | None:
    """
    Для новых материалов добавляет статус::на проверке (inbox после импорта).
    Для обновлений — только теги из файла; None = не трогать tags.

    Теги из импорта (в т.ч. плоские без «::») передаются во второй аргумент
    merge_import_tag_names, чтобы не отбрасывались как legacy existing.
    """
    incoming = list(import_names or [])
    if created:
        return merge_import_tag_names(
            list(existing_names or []),
            incoming + [IMPORT_STATUS_PENDING],
        )
    if not incoming:
        return None
    return merge_import_tag_names(list(existing_names or []), incoming)


tag_names_with_unverified_on_create = tag_names_with_import_status_on_create


def apply_import_tags(
    material,
    *,
    workspace,
    import_names: list[str] | None,
    created: bool,
) -> bool:
    """Назначает теги после импорта. True — теги менялись."""
    existing = list(material.tags.values_list('name', flat=True))
    merged = tag_names_with_import_status_on_create(
        existing,
        import_names,
        created=created,
    )
    if merged is None:
        return False
    assign_tags(material, merged, workspace=workspace)
    if created:
        ensure_import_status_tag_colors(workspace)
    return True


def set_material_import_status(material, *, workspace, column: str) -> str:
    """
    Ставит статус по колонке канбана: approved | verified.
    Возвращает имя тега статуса.
    """
    target = IMPORT_STATUS_BY_COLUMN.get(column)
    if not target:
        raise ValueError(f'Unknown import review column: {column}')
    existing = list(material.tags.values_list('name', flat=True))
    merged = merge_import_tag_names(existing, [target])
    assign_tags(material, merged, workspace=workspace)
    ensure_import_status_tag_colors(workspace)
    return target


def _materials_with_status(
    workspace,
    status_names: str | tuple[str, ...],
    *,
    order_by=('-created_at', 'code'),
):
    from apps.workspaces.services import materials_owned_by

    if isinstance(status_names, str):
        names = (status_names,)
    else:
        names = tuple(status_names)
    return (
        materials_owned_by(workspace)
        .filter(tags__name__in=names)
        .distinct()
        .select_related('struct_type')
        .prefetch_related('tags')
        .order_by(*order_by)
    )


def materials_approved_import_review(workspace, *, limit: int | None = 200):
    """Inbox: статус::на проверке (сюда попадают новые из импорта)."""
    qs = _materials_with_status(workspace, _PENDING_STATUS_NAMES)
    return qs if limit is None else qs[:limit]


def materials_verified_import_review(workspace, *, limit: int = 80):
    """Колонка «Учрежден»: статус::учрежден."""
    return _materials_with_status(
        workspace,
        _ESTABLISHED_STATUS_NAMES,
        order_by=('-updated_at', 'code'),
    )[:limit]


def count_pending_import_review(workspace) -> int:
    """Счётчик дашборда: материалы «на проверке» (ещё не учреждены)."""
    if workspace is None:
        return 0
    return materials_approved_import_review(workspace, limit=None).count()
