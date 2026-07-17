import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils.text import slugify

from apps.core.models import Tag

TAG_NAME_MAX_LENGTH = 50
SCOPED_TAG_SEPARATOR = '::'
HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def normalize_tag_name(name: str) -> str:
    return ' '.join((name or '').strip().split())


def parse_scoped_tag_name(name: str) -> tuple[str | None, str]:
    """Возвращает (scope, value). Для обычного тега scope=None."""
    normalized = normalize_tag_name(name)
    if SCOPED_TAG_SEPARATOR not in normalized:
        return None, normalized
    parts = normalized.split(SCOPED_TAG_SEPARATOR)
    if len(parts) != 2:
        raise ValidationError(
            f'Тег «{name}»: используйте один разделитель «{SCOPED_TAG_SEPARATOR}» '
            f'(формат «область{SCOPED_TAG_SEPARATOR}значение»).',
        )
    scope, value = parts[0].strip(), parts[1].strip()
    if not scope or not value:
        raise ValidationError(
            f'Тег «{name}»: укажите формат «область{SCOPED_TAG_SEPARATOR}значение».',
        )
    return scope, value


def tag_scope_key(name: str) -> str | None:
    try:
        scope, _value = parse_scoped_tag_name(name)
    except ValidationError:
        return None
    if scope is None:
        return None
    return scope.casefold()


def _slugify_tag_part(part: str) -> str:
    slug = slugify(part, allow_unicode=True)
    if not slug:
        slug = slugify(re.sub(r'[^\w\s-]', '', part, flags=re.UNICODE), allow_unicode=True)
    return slug


def tag_slug_from_name(name: str) -> str:
    normalized = normalize_tag_name(name)
    if SCOPED_TAG_SEPARATOR in normalized:
        scope, value = normalized.split(SCOPED_TAG_SEPARATOR, 1)
        scope_slug = _slugify_tag_part(scope.strip())
        value_slug = _slugify_tag_part(value.strip())
        if scope_slug and value_slug:
            slug = f'{scope_slug}--{value_slug}'
        else:
            slug = scope_slug or value_slug or 'tag'
    else:
        slug = _slugify_tag_part(normalized) or 'tag'
    return slug[:TAG_NAME_MAX_LENGTH]


def parse_tag_input(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r'[,;]+', value)
    names: list[str] = []
    seen: set[str] = set()
    for part in parts:
        name = normalize_tag_name(part)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def dedupe_scoped_tag_names(names: list[str]) -> list[str]:
    """Не более одного scoped-тега на scope; последний в списке побеждает."""
    result: list[str] = []
    scope_indexes: dict[str, int] = {}
    for name in names:
        scope_key = tag_scope_key(name)
        if scope_key is None:
            result.append(name)
            continue
        if scope_key in scope_indexes:
            result[scope_indexes[scope_key]] = name
        else:
            scope_indexes[scope_key] = len(result)
            result.append(name)
    return result


def validate_tag_names(names: list[str]) -> None:
    for name in names:
        if len(name) > TAG_NAME_MAX_LENGTH:
            raise ValidationError(
                f'Тег «{name}» слишком длинный (максимум {TAG_NAME_MAX_LENGTH} символов).',
            )
        parse_scoped_tag_name(name)


def validate_tag_color(color: str) -> None:
    if not color:
        return
    if not HEX_COLOR_RE.fullmatch(color.strip()):
        raise ValidationError('Укажите цвет в формате #RRGGBB.')


def contrast_text_color(hex_color: str) -> str:
    raw = (hex_color or '').lstrip('#')
    if len(raw) != 6:
        return '#212529'
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return '#212529' if luminance > 0.6 else '#ffffff'


def active_tags_queryset(queryset):
    return queryset.filter(is_archived=False)


def _suggestion_row_rank(row: dict) -> tuple[int, int]:
    """Higher is better: colored first, then workspace-scoped over global."""
    has_color = 1 if str(row.get('color') or '').strip() else 0
    workspace_id = row.get('workspace_id', row.get('workspace'))
    is_workspace_tag = 1 if workspace_id not in (None, '') else 0
    return (has_color, is_workspace_tag)


def dedupe_tag_suggestion_rows(rows: list[dict]) -> list[dict]:
    """Убирает дубли подсказок с одним именем (цветной / workspace важнее)."""
    best_by_name: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        name = normalize_tag_name(str(row.get('name') or ''))
        if not name:
            continue
        key = name.casefold()
        current = best_by_name.get(key)
        if current is None:
            best_by_name[key] = row
            order.append(key)
            continue
        if _suggestion_row_rank(row) > _suggestion_row_rank(current):
            best_by_name[key] = row
    return [best_by_name[key] for key in order]


def resolve_tag_workspace(instance, workspace=None):
    if workspace is not None:
        return workspace
    if hasattr(instance, 'workspace_id') and instance.workspace_id:
        return instance.workspace
    if hasattr(instance, 'home_workspace_id') and instance.home_workspace_id:
        return instance.home_workspace
    return None


def _find_existing_tag(name: str, slug: str, workspace) -> Tag | None:
    """Resolve tag for assignment: reuse colored global over colorless workspace clone."""
    workspace_tag = (
        Tag.objects.filter(workspace=workspace, slug=slug).first()
        or Tag.objects.filter(workspace=workspace, name__iexact=name).first()
    )
    global_tag = (
        Tag.objects.filter(workspace__isnull=True, slug=slug).first()
        or Tag.objects.filter(workspace__isnull=True, name__iexact=name).first()
    )
    if workspace_tag and global_tag:
        workspace_has_color = bool((workspace_tag.color or '').strip())
        global_has_color = bool((global_tag.color or '').strip())
        if global_has_color and not workspace_has_color:
            return global_tag
        return workspace_tag
    return workspace_tag or global_tag


def coalesce_tags_for_display(tags) -> list[Tag]:
    """
    For list/detail badges: if a workspace tag has no color but a global twin does,
    show the global color (in-memory). Also de-duplicates identical names.
    """
    tag_list = list(tags)
    if not tag_list:
        return []

    missing = [tag for tag in tag_list if not (tag.color or '').strip()]
    globals_by_slug: dict[str, Tag] = {}
    globals_by_name: dict[str, Tag] = {}
    if missing:
        slugs = [tag.slug for tag in missing]
        names = [tag.name for tag in missing]
        for global_tag in Tag.objects.filter(workspace__isnull=True).filter(
            Q(slug__in=slugs) | Q(name__in=names)
        ).exclude(color=''):
            globals_by_slug.setdefault(global_tag.slug, global_tag)
            globals_by_name.setdefault(global_tag.name.casefold(), global_tag)

    display_tags: list[Tag] = []
    seen_names: set[str] = set()
    for tag in tag_list:
        name_key = tag.name.casefold()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        if not (tag.color or '').strip():
            twin = globals_by_slug.get(tag.slug) or globals_by_name.get(name_key)
            if twin is not None:
                tag.color = twin.color
        display_tags.append(tag)
    return display_tags


def repair_colorless_workspace_tag_links(instance, workspace=None) -> bool:
    """Replace colorless workspace tag links with matching global tags."""
    if not hasattr(instance, 'tags'):
        return False
    workspace = resolve_tag_workspace(instance, workspace)
    current = list(instance.tags.all())
    if not current:
        return False

    replacement: list[Tag] = []
    changed = False
    seen: set = set()
    for tag in current:
        chosen = tag
        if tag.workspace_id is not None and not (tag.color or '').strip():
            global_tag = (
                Tag.objects.filter(workspace__isnull=True, slug=tag.slug).first()
                or Tag.objects.filter(workspace__isnull=True, name__iexact=tag.name).first()
            )
            if global_tag is not None:
                chosen = global_tag
                changed = True
        if chosen.pk in seen:
            changed = True
            continue
        seen.add(chosen.pk)
        replacement.append(chosen)

    if changed:
        instance.tags.set(replacement)
    return changed


def get_or_create_tags(names: list[str], workspace) -> list[Tag]:
    if workspace is None:
        raise ValueError('workspace is required for tag assignment')
    names = dedupe_scoped_tag_names(names)
    tags: list[Tag] = []
    seen_slugs: set[str] = set()
    for name in names:
        slug = tag_slug_from_name(name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        tag = _find_existing_tag(name, slug, workspace)
        if tag is None:
            try:
                tag = Tag.objects.create(
                    workspace=workspace,
                    slug=slug,
                    name=name,
                )
            except IntegrityError:
                # Гонка или старый slug при том же name — берём существующий.
                tag = _find_existing_tag(name, slug, workspace)
                if tag is None:
                    raise
        elif (
            tag.workspace_id is not None
            and tag.slug != slug
            and not Tag.objects.filter(
                workspace=workspace,
                slug=slug,
            ).exclude(pk=tag.pk).exists()
        ):
            # Подтянуть slug к актуальному формату (напр. scope--value).
            tag.slug = slug
            tag.save(update_fields=['slug'])
        tags.append(tag)
    return tags


def assign_tags(instance, names: list[str], workspace=None) -> None:
    workspace = resolve_tag_workspace(instance, workspace)
    if workspace is None:
        return
    tags = get_or_create_tags(names, workspace)
    instance.tags.set(tags)
    repair_colorless_workspace_tag_links(instance, workspace=workspace)


def format_tags_for_input(tags) -> str:
    return ', '.join(tag.name for tag in tags)


def split_scoped_tag_display(name: str) -> tuple[str | None, str | None, str]:
    """Возвращает (scope, value, plain_name) для отображения scoped-тега."""
    normalized = normalize_tag_name(name)
    if SCOPED_TAG_SEPARATOR not in normalized:
        return None, None, normalized
    try:
        scope, value = parse_scoped_tag_name(normalized)
    except ValidationError:
        return None, None, normalized
    if scope is None:
        return None, None, normalized
    return scope, value, normalized
