from django import template
from django.utils.html import json_script
from django.utils.safestring import mark_safe

from apps.core.number_utils import format_decimal_display
from apps.core.property_form_display import property_label_with_unit as format_property_label_with_unit
from apps.core.creator import get_creator_display

register = template.Library()

TONE_CLASSES = (
    'tone-amber',
    'tone-green',
    'tone-blue',
    'tone-violet',
    'tone-rose',
    'tone-teal',
    'tone-coral',
    'tone-slate',
)

# Фиксированные цвета только для заранее определённых категорий.
KNOWN_TONE_MAP = {
    'unset': 'tone-slate',
    'test': 'tone-amber',
    'control': 'tone-green',
    'structural_similar': 'tone-blue',
    'product': 'tone-violet',
    'calibration': 'tone-rose',
    'echo': 'tone-blue',
    'shadow': 'tone-amber',
    'immersion': 'tone-teal',
    'number': 'tone-blue',
    'string': 'tone-green',
    'boolean': 'tone-amber',
    'date': 'tone-rose',
}


def semantic_tone(value: str) -> str:
    key = (value or '').strip().casefold()
    return KNOWN_TONE_MAP.get(key, 'tone-slate')


def category_tone(value: str) -> str:
    """Стабильный цвет для пользовательских категорий (например, тип структуры)."""
    key = (value or '').strip().casefold()
    if key in KNOWN_TONE_MAP:
        return KNOWN_TONE_MAP[key]
    if not key:
        return 'tone-slate'
    index = sum(ord(char) for char in key) % len(TONE_CLASSES)
    return TONE_CLASSES[index]


@register.filter
def ui_tone(value):
    """Семантический тон: только известные категории, иначе нейтральный."""
    return semantic_tone(str(value))


@register.filter
def ui_category_tone(value):
    """Тон категории: известные категории или стабильный цвет на код типа."""
    return category_tone(str(value))


@register.filter
def property_label_with_unit(property_obj):
    """Название свойства с единицей измерения через запятую."""
    return format_property_label_with_unit(property_obj)


@register.filter
def creator_display(obj):
    return get_creator_display(obj)


@register.filter
def decimal_comma(value, decimal_places=None):
    """Отображает число с запятой в качестве десятичного разделителя."""
    if value in (None, ''):
        return '—'
    if decimal_places not in (None, ''):
        try:
            decimal_places = int(decimal_places)
        except (TypeError, ValueError):
            decimal_places = None
    return format_decimal_display(value, decimal_places)


@register.simple_tag
def reference_properties_json_script(properties=None):
    if not isinstance(properties, list):
        properties = []
    return json_script(properties, 'reference-properties-data')


@register.simple_tag
def workspace_users_json_script(users=None):
    if not isinstance(users, list):
        users = []
    return json_script(users, 'workspace-users-data')


@register.simple_tag
def reference_materials_json_script(materials=None):
    if not isinstance(materials, list):
        materials = []
    return json_script(materials, 'reference-materials-data')


@register.simple_tag
def reference_structure_types_json_script(structure_types=None):
    if not isinstance(structure_types, list):
        structure_types = []
    return json_script(structure_types, 'reference-structure-types-data')


@register.simple_tag
def get_structure_color_presets():
    from apps.structures.colors import STRUCTURE_COLOR_PRESETS

    return list(STRUCTURE_COLOR_PRESETS)


@register.filter
def structure_is_hex_color(value):
    from apps.structures.colors import is_hex_display_color, normalize_display_color

    return is_hex_display_color(normalize_display_color(str(value or '')))


@register.simple_tag
def structure_pill_style(color):
    from apps.structures.colors import structure_pill_style as build_style

    result = build_style(color)
    return mark_safe(result) if result else ''


@register.simple_tag
def structure_pill_dot_style(color):
    from apps.structures.colors import structure_pill_dot_style as build_style

    result = build_style(color)
    return mark_safe(result) if result else ''


@register.simple_tag
def entity_code_link_style(color):
    from apps.structures.colors import entity_code_link_style as build_style

    result = build_style(color)
    return mark_safe(result) if result else ''


@register.simple_tag
def entity_code_mark_style(color):
    from apps.structures.colors import entity_code_mark_style as build_style

    result = build_style(color)
    return mark_safe(result) if result else ''
