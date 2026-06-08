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


def get_or_create_tags(names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    seen_slugs: set[str] = set()
    for name in names:
        slug = tag_slug_from_name(name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        tag, _created = Tag.objects.get_or_create(slug=slug, defaults={'name': name})
        tags.append(tag)
    return tags


def assign_tags(instance, names: list[str]) -> None:
    tags = get_or_create_tags(names)
    instance.tags.set(tags)


def format_tags_for_input(tags) -> str:
    return ', '.join(tag.name for tag in tags)
