(function () {
    'use strict';

    var LAYER_COLORS = [
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
    ];

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function layerColor(colorIndex) {
        return LAYER_COLORS[colorIndex % LAYER_COLORS.length];
    }

    function materialCodeFromLabel(label) {
        if (!label) {
            return '—';
        }
        var parts = label.split(' - ');
        return parts[0].trim() || label;
    }

    function formatDecimalDisplay(value) {
        return String(value).replace('.', ',');
    }

    function parseLayerRows(layerContainer) {
        var layers = [];
        layerContainer.querySelectorAll('.layer-form-row').forEach(function (row) {
            if (row.classList.contains('d-none')) {
                return;
            }
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) {
                return;
            }

            var materialSelect = row.querySelector('[name$="-material"]');
            var angleInput = row.querySelector('[name$="-angle"]');
            var thicknessInput = row.querySelector('[name$="-thickness"]');
            var layerNumberInput = row.querySelector('[name$="-layer_number"]');
            if (!materialSelect || !materialSelect.value) {
                return;
            }

            var thickness = parseFloat(String(thicknessInput && thicknessInput.value).replace(',', '.'));
            if (Number.isNaN(thickness) || thickness <= 0) {
                thickness = 0;
            }

            var materialLabel = '';
            if (materialSelect.selectedIndex >= 0) {
                materialLabel = materialSelect.options[materialSelect.selectedIndex].text.trim();
            }

            layers.push({
                layer_number: parseInt(layerNumberInput && layerNumberInput.value, 10) || layers.length + 1,
                material_id: materialSelect.value,
                material_label: materialLabel,
                material_code: materialCodeFromLabel(materialLabel),
                angle: angleInput ? angleInput.value : '',
                thickness: thickness,
            });
        });
        return layers;
    }

    function buildLayerDiagram(layers) {
        if (!layers.length) {
            return null;
        }

        var totalThickness = layers.reduce(function (sum, layer) {
            return sum + (layer.thickness > 0 ? layer.thickness : 0);
        }, 0);
        if (totalThickness <= 0) {
            totalThickness = layers.length;
        }

        var materialColors = {};
        var colorIndex = 0;
        layers.forEach(function (layer) {
            if (!materialColors[layer.material_id]) {
                materialColors[layer.material_id] = layerColor(colorIndex);
                colorIndex += 1;
            }
        });

        var materialLegend = [];
        var diagramLayers = layers.map(function (layer, index) {
            var color = materialColors[layer.material_id];
            if (!materialLegend.some(function (entry) {
                return entry.material_id === layer.material_id;
            })) {
                materialLegend.push({
                    material_id: layer.material_id,
                    material_label: layer.material_label,
                    color: color,
                });
            }

            var thickness = layer.thickness > 0 ? layer.thickness : 0;
            var effectiveThickness = thickness > 0 ? thickness : 1;
            return {
                layer_number: layer.layer_number || index + 1,
                material_id: layer.material_id,
                material_label: layer.material_label,
                material_code: layer.material_code,
                angle: layer.angle,
                thickness: thickness,
                thickness_percent: thickness > 0
                    ? Math.round(thickness / totalThickness * 1000) / 10
                    : 0,
                flex_grow: Math.max(Math.round(effectiveThickness * 1000), 1),
                color: color,
            };
        });

        return {
            layers: diagramLayers,
            material_legend: materialLegend,
            total_thickness: Math.round(totalThickness * 10000) / 10000,
            layer_count: diagramLayers.length,
        };
    }

    function renderDiagram(target, diagram) {
        if (!target) {
            return;
        }

        if (!diagram) {
            target.innerHTML = ''
                + '<div class="composite-layer-diagram composite-layer-diagram--empty p-3 p-lg-4 h-100">'
                + '<h3 class="composite-layer-diagram__title">Схема укладки</h3>'
                + '<p class="text-muted mb-0">Добавьте слои слева — схема появится здесь.</p>'
                + '</div>';
            return;
        }

        var legendHtml = diagram.material_legend.map(function (entry) {
            return ''
                + '<span class="layer-material-chip">'
                + '<span class="layer-material-chip-swatch" style="background-color: '
                + escapeHtml(entry.color) + ';"></span>'
                + escapeHtml(entry.material_label)
                + '</span>';
        }).join('');

        var stackHtml = diagram.layers.map(function (item) {
            return ''
                + '<div class="layer-stack-segment"'
                + ' style="flex: ' + item.flex_grow + ' 1 0%; background-color: ' + escapeHtml(item.color) + ';"'
                + ' title="Слой ' + item.layer_number + ': ' + escapeHtml(item.material_label)
                + ' · ' + escapeHtml(formatDecimalDisplay(item.thickness)) + ' мм">'
                + '<span class="layer-stack-segment-index">#' + item.layer_number + '</span>'
                + '<span class="layer-stack-material-code">' + escapeHtml(item.material_code) + '</span>'
                + '</div>';
        }).join('');

        target.innerHTML = ''
            + '<div class="composite-layer-diagram p-3 p-lg-4">'
            + '<h3 class="composite-layer-diagram__title">Схема укладки</h3>'
            + (legendHtml ? '<div class="layer-material-legend mb-3">' + legendHtml + '</div>' : '')
            + '<div class="layer-stack-panel">'
            + '<div class="layer-stack-title">Сверху ↓ вниз</div>'
            + '<div class="layer-stack-column" style="--layer-stack-count: ' + diagram.layer_count + ';">'
            + stackHtml
            + '</div>'
            + '<div class="layer-stack-caption">Один материал — один цвет</div>'
            + '</div>'
            + '</div>';
    }

    function renderSummary(summaryTarget, diagram) {
        if (!summaryTarget) {
            return;
        }
        if (!diagram) {
            summaryTarget.classList.add('d-none');
            summaryTarget.innerHTML = '';
            return;
        }

        summaryTarget.classList.remove('d-none');
        summaryTarget.innerHTML = ''
            + '<span class="composite-thickness-summary__label">Общая толщина</span>'
            + '<span class="composite-thickness-summary__value">Σt = '
            + escapeHtml(formatDecimalDisplay(diagram.total_thickness)) + ' мм</span>'
            + '<span class="composite-thickness-summary__meta">' + diagram.layer_count + ' сл.</span>';
    }

    function update(layerContainer, diagramTarget, summaryTarget) {
        var diagram = buildLayerDiagram(parseLayerRows(layerContainer));
        renderDiagram(diagramTarget, diagram);
        renderSummary(summaryTarget, diagram);
    }

    window.CompositeLayerDiagramLive = {
        update: update,
    };
})();
