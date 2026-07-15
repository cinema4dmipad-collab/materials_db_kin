from __future__ import annotations

from typing import Any

from apps.structures.models import CHOICE_FIELD_TYPE


def normalize_choice_options(raw: Any) -> list[dict[str, str]]:
    if raw in (None, '', []):
        return []
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        value = str(item.get('value') or '').strip()
        label = str(item.get('label') or value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append({'value': value, 'label': label or value})
    return result


def choice_pairs(options: list[dict[str, str]]) -> list[tuple[str, str]]:
    return [(item['value'], item['label']) for item in options]


def choice_label_for_value(options: list[dict[str, str]], value) -> str:
    raw = '' if value is None else str(value).strip()
    if not raw:
        return ''
    for item in options:
        if item['value'] == raw:
            return item['label']
    return raw


def resolved_choice_options(structure_field) -> list[dict[str, str]]:
    stored = normalize_choice_options(getattr(structure_field, 'choice_options', None))
    if stored:
        return stored

    field_type = getattr(structure_field, 'field_type', '')
    if field_type not in {CHOICE_FIELD_TYPE, 'CharField'}:
        return []

    from apps.references.models import Property

    prop = (
        Property.objects.filter(
            name=getattr(structure_field, 'name', ''),
            data_type=Property.CHOICE_DATA_TYPE,
        )
        .prefetch_related('choices')
        .first()
    )
    if prop is None:
        return []
    return [
        {'value': item.value, 'label': item.label}
        for item in prop.choice_options()
    ]
