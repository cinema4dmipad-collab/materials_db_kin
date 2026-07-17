import re

from django.core.exceptions import ValidationError
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


def resolve_tag_workspace(instance, workspace=None):
    if workspace is not None:
        return workspace
    if hasattr(instance, 'workspace_id') and instance.workspace_id:
        return instance.workspace
    if hasattr(instance, 'home_workspace_id') and instance.home_workspace_id:
        return instance.home_workspace
    return None


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
        tag, _created = Tag.objects.get_or_create(
            slug=slug,
            workspace=workspace,
            defaults={'name': name},
        )
        tags.append(tag)
    return tags


def assign_tags(instance, names: list[str], workspace=None) -> None:
    workspace = resolve_tag_workspace(instance, workspace)
    if workspace is None:
        return
    tags = get_or_create_tags(names, workspace)
    instance.tags.set(tags)


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
