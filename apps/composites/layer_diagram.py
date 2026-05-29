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


def _layer_color(color_index: int) -> str:
    return LAYER_COLORS[color_index % len(LAYER_COLORS)]


def _material_color_map(layer_list) -> dict:
    colors: dict = {}
    color_index = 0
    for layer in layer_list:
        if layer.material_id not in colors:
            colors[layer.material_id] = _layer_color(color_index)
            color_index += 1
    return colors


def _normalize_angle(angle) -> str:
    value = round(float(angle) % 180, 2)
    if value == int(value):
        return str(int(value))
    return str(value).replace(',', '.')


def build_layer_diagram(layers):
    layer_list = list(layers)
    if not layer_list:
        return None

    total_thickness = sum(float(layer.thickness) for layer in layer_list)
    if total_thickness <= 0:
        total_thickness = float(len(layer_list))

    material_colors = _material_color_map(layer_list)
    diagram_layers = []
    material_legend = []

    for layer in layer_list:
        color = material_colors[layer.material_id]

        if not any(entry['material_id'] == layer.material_id for entry in material_legend):
            material_legend.append(
                {
                    'material_id': layer.material_id,
                    'material_label': str(layer.material),
                    'color': color,
                }
            )

        thickness = float(layer.thickness)
        diagram_layers.append(
            {
                'layer_number': layer.layer_number,
                'material_id': layer.material_id,
                'material_label': str(layer.material),
                'material_code': layer.material.code,
                'angle': _normalize_angle(layer.angle),
                'thickness': layer.thickness,
                'thickness_percent': round(thickness / total_thickness * 100, 1),
                'flex_grow': max(int(thickness * 1000), 1),
                'color': color,
            }
        )

    return {
        'layers': diagram_layers,
        'material_legend': material_legend,
        'total_thickness': round(total_thickness, 4),
        'layer_count': len(diagram_layers),
    }
