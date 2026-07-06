import re

from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.core.models import Tag

TAG_NAME_MAX_LENGTH = 50


def normalize_tag_name(name: str) -> str:
    return ' '.join((name or '').strip().split())


def tag_slug_from_name(name: str) -> str:
    slug = slugify(name, allow_unicode=True)
    if not slug:
        slug = slugify(re.sub(r'[^\w\s-]', '', name, flags=re.UNICODE)) or 'tag'
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


def validate_tag_names(names: list[str]) -> None:
    for name in names:
        if len(name) > TAG_NAME_MAX_LENGTH:
            raise ValidationError(
                f'Тег «{name}» слишком длинный (максимум {TAG_NAME_MAX_LENGTH} символов).',
            )


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
