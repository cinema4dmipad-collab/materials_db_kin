from django import template

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
