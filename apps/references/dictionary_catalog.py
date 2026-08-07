"""UI registry for global material metadata dictionaries."""
from __future__ import annotations

from apps.references.models import Availability, Manufacturer, Technology

DICTIONARY_CATALOGS = {
    'manufacturers': {
        'model': Manufacturer,
        'slug': 'manufacturers',
        'label': 'Производители',
        'singular': 'производитель',
        'create_label': 'Новый производитель',
        'related_name': 'materials',
    },
    'availabilities': {
        'model': Availability,
        'slug': 'availabilities',
        'label': 'Доступность',
        'singular': 'доступность',
        'create_label': 'Новая доступность',
        'related_name': 'materials',
    },
    'technologies': {
        'model': Technology,
        'slug': 'technologies',
        'label': 'Технологии',
        'singular': 'технология',
        'create_label': 'Новая технология',
        'related_name': 'materials',
    },
}


def get_dictionary_catalog(slug: str) -> dict | None:
    return DICTIONARY_CATALOGS.get(slug)
