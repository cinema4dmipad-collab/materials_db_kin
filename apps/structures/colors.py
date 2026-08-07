import re

from django.core.exceptions import ValidationError

from apps.core.tag_utils import validate_tag_color

DEFAULT_STRUCTURE_DISPLAY_COLOR = '#007679'

TONE_TO_HEX = {
    'tone-coral': '#E76F51',
    'tone-amber': '#F59E0B',
    'tone-green': '#10B981',
    'tone-blue': '#6A8FC0',
    'tone-violet': '#8B5CF6',
    'tone-rose': '#F43F5E',
    'tone-teal': '#007679',
    'tone-slate': '#999999',
}

STRUCTURE_COLOR_PRESETS = (
    ('#E76F51', 'Коралловый'),
    ('#F59E0B', 'Янтарный'),
    ('#10B981', 'Зелёный'),
    ('#6A8FC0', 'Синий'),
    ('#8B5CF6', 'Фиолетовый'),
    ('#F43F5E', 'Розовый'),
    ('#007679', 'Бирюзовый'),
    ('#999999', 'Серый'),
)

HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def is_hex_display_color(value: str) -> bool:
    return bool(value and HEX_COLOR_RE.fullmatch(str(value).strip()))


def normalize_display_color(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return DEFAULT_STRUCTURE_DISPLAY_COLOR
    if raw in TONE_TO_HEX:
        return TONE_TO_HEX[raw]
    normalized = raw.upper()
    if HEX_COLOR_RE.fullmatch(normalized):
        return normalized
    return DEFAULT_STRUCTURE_DISPLAY_COLOR


def validate_display_color(value: str) -> None:
    validate_tag_color(value)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    raw = hex_color.lstrip('#')
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def lighten_hex(hex_color: str, amount: float = 0.88) -> str:
    red, green, blue = _hex_to_rgb(hex_color)

    def mix(channel: int) -> int:
        return int(channel + (255 - channel) * amount)

    return f'#{mix(red):02X}{mix(green):02X}{mix(blue):02X}'


def structure_pill_style(color: str) -> str:
    hex_color = normalize_display_color(color)
    if not is_hex_display_color(hex_color):
        return ''
    red, green, blue = _hex_to_rgb(hex_color)
    background = lighten_hex(hex_color)
    return (
        f'style="background-color:{background};color:{hex_color};'
        f'border-color:rgba({red},{green},{blue},0.25);"'
    )


def structure_pill_dot_style(color: str) -> str:
    hex_color = normalize_display_color(color)
    if not is_hex_display_color(hex_color):
        return ''
    return f'style="background-color:{hex_color};"'


def entity_code_link_style(color: str) -> str:
    hex_color = normalize_display_color(color)
    if not is_hex_display_color(hex_color):
        return ''
    return f'style="color:{hex_color};"'


def entity_code_mark_style(color: str) -> str:
    return structure_pill_dot_style(color)
