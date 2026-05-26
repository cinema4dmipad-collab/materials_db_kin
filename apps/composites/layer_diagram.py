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


def _layer_color(layer_index: int) -> str:
    return LAYER_COLORS[layer_index % len(LAYER_COLORS)]


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

    diagram_layers = []
    material_legend = []

    for index, layer in enumerate(layer_list):
        color = _layer_color(index)

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
