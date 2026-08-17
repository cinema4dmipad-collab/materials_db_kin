from __future__ import annotations

from apps.composites.layer_symmetry import (
    format_layer_count_label,
    format_mirror_note,
    mirrored_layer_count,
)
from apps.composites.reinforcement_formula import build_reinforcement_formula

LEGEND_MODE_MATERIAL = 'material'
LEGEND_MODE_THICKNESS = 'thickness'
LEGEND_MODE_ANGLE = 'angle'
LEGEND_MODES = (
    LEGEND_MODE_MATERIAL,
    LEGEND_MODE_THICKNESS,
    LEGEND_MODE_ANGLE,
)

LAYER_COLORS = (
    '#0066FF',
    '#FF5500',
    '#00B050',
    '#9933FF',
    '#00BFBF',
    '#FFB300',
    '#E60026',
    '#3355FF',
    '#009973',
    '#E600E6',
)

GRADIENT_BLUE = (0, 102, 255)
GRADIENT_WHITE = (255, 255, 255)
GRADIENT_RED = (230, 0, 38)

ANGLE_SCALE_MIN = -90.0
ANGLE_SCALE_MAX = 90.0

LEGEND_MODE_LABELS = {
    LEGEND_MODE_MATERIAL: 'Материал',
    LEGEND_MODE_THICKNESS: 'Толщина',
    LEGEND_MODE_ANGLE: 'Угол армирования',
}

LEGEND_CAPTIONS = {
    LEGEND_MODE_MATERIAL: 'Один материал — один цвет',
    LEGEND_MODE_THICKNESS: 'Цвет по толщине: синий → белый → красный',
    LEGEND_MODE_ANGLE: 'Цвет по углу: −90° синий → 0° белый → +90° красный',
}


def _layer_color(color_index: int) -> str:
    return LAYER_COLORS[color_index % len(LAYER_COLORS)]


def _hex_color(rgb: tuple[int, int, int]) -> str:
    return '#{:02X}{:02X}{:02X}'.format(*rgb)


def _lerp_channel(start: int, end: int, t: float) -> int:
    return int(round(start + (end - start) * t))


def _lerp_rgb(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        _lerp_channel(start[0], end[0], t),
        _lerp_channel(start[1], end[1], t),
        _lerp_channel(start[2], end[2], t),
    )


def diverging_blue_white_red(t: float) -> str:
    """Map t∈[0,1] onto blue → white → red."""
    t = max(0.0, min(1.0, float(t)))
    if t <= 0.5:
        rgb = _lerp_rgb(GRADIENT_BLUE, GRADIENT_WHITE, t * 2.0)
    else:
        rgb = _lerp_rgb(GRADIENT_WHITE, GRADIENT_RED, (t - 0.5) * 2.0)
    return _hex_color(rgb)


def signed_fiber_angle(angle) -> float:
    """Wrap reinforcement angle to [-90, 90]."""
    value = ((float(angle) + 180.0) % 360.0) - 180.0
    if value > ANGLE_SCALE_MAX:
        value -= 180.0
    elif value < ANGLE_SCALE_MIN:
        value += 180.0
    return value


def _format_signed_angle_label(value: float) -> str:
    number = float(value)
    if number > 0:
        abs_text = str(int(number) if number == int(number) else number)
        return f'+{abs_text} °'
    if number < 0:
        abs_number = abs(number)
        abs_text = str(int(abs_number) if abs_number == int(abs_number) else abs_number)
        return f'−{abs_text} °'
    return '0 °'


def _normalize_angle(angle) -> str:
    value = round(signed_fiber_angle(angle), 2)
    if value == int(value):
        return str(int(value))
    return str(value).replace(',', '.')


def _angle_value(angle) -> float:
    return signed_fiber_angle(angle)


def _material_color_map(layer_list) -> dict:
    colors: dict = {}
    color_index = 0
    for layer in layer_list:
        if layer.material_id not in colors:
            colors[layer.material_id] = _layer_color(color_index)
            color_index += 1
    return colors


def _scale_color(value: float, min_value: float, max_value: float) -> str:
    if max_value <= min_value:
        return diverging_blue_white_red(0.5)
    t = (value - min_value) / (max_value - min_value)
    return diverging_blue_white_red(t)


def resolve_legend_mode(color_by: str | None) -> str:
    mode = (color_by or LEGEND_MODE_MATERIAL).strip().lower()
    if mode not in LEGEND_MODES:
        return LEGEND_MODE_MATERIAL
    return mode


def build_layer_diagram(
    layers,
    *,
    color_by: str | None = None,
    symmetric: bool = False,
    defining_count: int | None = None,
):
    layer_list = list(layers)
    if not layer_list:
        return None

    legend_mode = resolve_legend_mode(color_by)
    total_thickness = sum(float(layer.thickness) for layer in layer_list)
    if total_thickness <= 0:
        total_thickness = float(len(layer_list))

    material_colors = _material_color_map(layer_list)
    thickness_values = [float(layer.thickness) for layer in layer_list]
    thickness_min = min(thickness_values) if thickness_values else 0.0
    thickness_max = max(thickness_values) if thickness_values else 0.0

    diagram_layers = []
    material_legend = []

    for layer in layer_list:
        material_color = material_colors[layer.material_id]
        if not any(entry['material_id'] == layer.material_id for entry in material_legend):
            material_legend.append(
                {
                    'material_id': layer.material_id,
                    'material_label': str(layer.material),
                    'color': material_color,
                }
            )

        thickness = float(layer.thickness)
        angle_raw = _angle_value(layer.angle)
        if legend_mode == LEGEND_MODE_THICKNESS:
            color = _scale_color(thickness, thickness_min, thickness_max)
        elif legend_mode == LEGEND_MODE_ANGLE:
            color = _scale_color(angle_raw, ANGLE_SCALE_MIN, ANGLE_SCALE_MAX)
        else:
            color = material_color

        diagram_layers.append(
            {
                'layer_number': layer.layer_number,
                'material_id': str(layer.material_id),
                'material_label': str(layer.material),
                'material_code': layer.material.code,
                'angle': _normalize_angle(layer.angle),
                'angle_value': angle_raw,
                'thickness': layer.thickness,
                'thickness_value': thickness,
                'thickness_percent': round(thickness / total_thickness * 100, 1),
                'flex_grow': max(int(thickness * 1000), 1),
                'color': color,
                'material_color': material_color,
            }
        )

    scale = None
    if legend_mode == LEGEND_MODE_THICKNESS:
        scale = {
            'min': thickness_min,
            'max': thickness_max,
            'unit': 'мм',
            'mid_label': 'среднее',
            'min_color': diverging_blue_white_red(0.0),
            'mid_color': diverging_blue_white_red(0.5),
            'max_color': diverging_blue_white_red(1.0),
        }
    elif legend_mode == LEGEND_MODE_ANGLE:
        scale = {
            'min': ANGLE_SCALE_MIN,
            'max': ANGLE_SCALE_MAX,
            'unit': '°',
            'min_label': _format_signed_angle_label(ANGLE_SCALE_MIN),
            'mid_label': _format_signed_angle_label(0),
            'max_label': _format_signed_angle_label(ANGLE_SCALE_MAX),
            'min_color': diverging_blue_white_red(0.0),
            'mid_color': diverging_blue_white_red(0.5),
            'max_color': diverging_blue_white_red(1.0),
        }

    layer_count = len(diagram_layers)
    stored_count = defining_count if defining_count is not None else layer_count
    is_symmetric = bool(symmetric)
    mirror_count = mirrored_layer_count(stored_count) if is_symmetric else 0
    return {
        'layers': diagram_layers,
        'material_legend': material_legend,
        'legend_mode': legend_mode,
        'legend_modes': [
            {'value': mode, 'label': LEGEND_MODE_LABELS[mode]}
            for mode in LEGEND_MODES
        ],
        'legend_caption': LEGEND_CAPTIONS[legend_mode],
        'scale': scale,
        'total_thickness': round(total_thickness, 4),
        'layer_count': layer_count,
        'defining_count': stored_count,
        'mirror_count': mirror_count,
        'symmetric': is_symmetric,
        'layer_count_label': format_layer_count_label(
            stored_count,
            symmetric=is_symmetric,
        ),
        'mirror_note': format_mirror_note(stored_count) if is_symmetric else '',
        'reinforcement_formula': build_reinforcement_formula(
            item['angle_value'] for item in diagram_layers
        ),
    }
