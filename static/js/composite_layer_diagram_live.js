(function () {
    'use strict';

    var STORAGE_KEY = 'composite-layer-legend-mode';
    var LEGEND_MODE_MATERIAL = 'material';
    var LEGEND_MODE_THICKNESS = 'thickness';
    var LEGEND_MODE_ANGLE = 'angle';

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

    var GRADIENT_BLUE = [0, 102, 255];
    var GRADIENT_WHITE = [255, 255, 255];
    var GRADIENT_RED = [230, 0, 38];

    var LEGEND_MODE_LABELS = {
        material: 'Материал',
        thickness: 'Толщина',
        angle: 'Угол армирования',
    };

    var LEGEND_CAPTIONS = {
        material: 'Один материал — один цвет',
        thickness: 'Цвет по толщине: синий → белый → красный',
        angle: 'Цвет по углу: синий → белый → красный',
    };

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

    function formatDecimalDisplay(value, decimals) {
        var number = Number(value);
        if (Number.isNaN(number)) {
            return String(value).replace('.', ',');
        }
        if (decimals == null) {
            return String(number).replace('.', ',');
        }
        var text = number.toFixed(decimals).replace(/\.?0+$/, '');
        return (text || '0').replace('.', ',');
    }

    function lerpChannel(start, end, t) {
        return Math.round(start + (end - start) * t);
    }

    function lerpRgb(start, end, t) {
        var clamped = Math.max(0, Math.min(1, t));
        return [
            lerpChannel(start[0], end[0], clamped),
            lerpChannel(start[1], end[1], clamped),
            lerpChannel(start[2], end[2], clamped),
        ];
    }

    function rgbToHex(rgb) {
        return '#' + rgb.map(function (channel) {
            return channel.toString(16).padStart(2, '0');
        }).join('').toUpperCase();
    }

    function divergingBlueWhiteRed(t) {
        var clamped = Math.max(0, Math.min(1, t));
        if (clamped <= 0.5) {
            return rgbToHex(lerpRgb(GRADIENT_BLUE, GRADIENT_WHITE, clamped * 2));
        }
        return rgbToHex(lerpRgb(GRADIENT_WHITE, GRADIENT_RED, (clamped - 0.5) * 2));
    }

    function scaleColor(value, minValue, maxValue) {
        if (!(maxValue > minValue)) {
            return divergingBlueWhiteRed(0.5);
        }
        return divergingBlueWhiteRed((value - minValue) / (maxValue - minValue));
    }

    function resolveLegendMode(mode) {
        if (mode === LEGEND_MODE_THICKNESS || mode === LEGEND_MODE_ANGLE) {
            return mode;
        }
        return LEGEND_MODE_MATERIAL;
    }

    function getStoredLegendMode() {
        try {
            return resolveLegendMode(sessionStorage.getItem(STORAGE_KEY));
        } catch (error) {
            return LEGEND_MODE_MATERIAL;
        }
    }

    function setStoredLegendMode(mode) {
        try {
            sessionStorage.setItem(STORAGE_KEY, resolveLegendMode(mode));
        } catch (error) {
            // ignore
        }
    }

    function isSymmetricEnabled() {
        var checkbox = document.getElementById('id_layers_symmetric');
        return Boolean(checkbox && checkbox.checked);
    }

    function expandSymmetricLayers(layers) {
        if (!layers.length) {
            return layers;
        }
        var expanded;
        if (layers.length % 2 === 0) {
            expanded = layers.concat(layers.slice().reverse());
        } else {
            var side = layers.slice(0, -1);
            var center = layers[layers.length - 1];
            expanded = side.concat([center], side.slice().reverse());
        }
        return expanded.map(function (layer, index) {
            return Object.assign({}, layer, { layer_number: index + 1 });
        });
    }

    function parseAngleValue(raw) {
        var value = parseFloat(String(raw == null ? '' : raw).replace(',', '.'));
        if (Number.isNaN(value)) {
            return 0;
        }
        value = value % 180;
        if (value < 0) {
            value += 180;
        }
        return value;
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
            var lockedInput = row.querySelector('input[name$="-thickness_locked"]');
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
                angle_value: parseAngleValue(angleInput && angleInput.value),
                thickness: thickness,
                thickness_locked: Boolean(lockedInput && lockedInput.checked),
            });
        });
        if (isSymmetricEnabled()) {
            return expandSymmetricLayers(layers);
        }
        return layers;
    }

    function buildLayerDiagram(layers, colorBy) {
        if (!layers.length) {
            return null;
        }

        var legendMode = resolveLegendMode(colorBy);
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

        var thicknessValues = layers.map(function (layer) {
            return layer.thickness > 0 ? layer.thickness : 0;
        });
        var angleValues = layers.map(function (layer) {
            return layer.angle_value != null ? layer.angle_value : parseAngleValue(layer.angle);
        });
        var thicknessMin = Math.min.apply(null, thicknessValues);
        var thicknessMax = Math.max.apply(null, thicknessValues);
        var angleMin = Math.min.apply(null, angleValues);
        var angleMax = Math.max.apply(null, angleValues);

        var materialLegend = [];
        var diagramLayers = layers.map(function (layer, index) {
            var materialColor = materialColors[layer.material_id];
            if (!materialLegend.some(function (entry) {
                return entry.material_id === layer.material_id;
            })) {
                materialLegend.push({
                    material_id: layer.material_id,
                    material_label: layer.material_label,
                    color: materialColor,
                });
            }

            var thickness = layer.thickness > 0 ? layer.thickness : 0;
            var angleValue = layer.angle_value != null ? layer.angle_value : parseAngleValue(layer.angle);
            var color = materialColor;
            if (legendMode === LEGEND_MODE_THICKNESS) {
                color = scaleColor(thickness, thicknessMin, thicknessMax);
            } else if (legendMode === LEGEND_MODE_ANGLE) {
                color = scaleColor(angleValue, angleMin, angleMax);
            }

            var effectiveThickness = thickness > 0 ? thickness : 1;
            return {
                layer_number: layer.layer_number || index + 1,
                material_id: layer.material_id,
                material_label: layer.material_label,
                material_code: layer.material_code,
                angle: layer.angle,
                angle_value: angleValue,
                thickness: thickness,
                thickness_percent: thickness > 0
                    ? Math.round(thickness / totalThickness * 1000) / 10
                    : 0,
                flex_grow: Math.max(Math.round(effectiveThickness * 1000), 1),
                color: color,
                material_color: materialColor,
            };
        });

        var scale = null;
        if (legendMode === LEGEND_MODE_THICKNESS) {
            scale = {
                min: thicknessMin,
                max: thicknessMax,
                unit: 'мм',
            };
        } else if (legendMode === LEGEND_MODE_ANGLE) {
            scale = {
                min: angleMin,
                max: angleMax,
                unit: '°',
            };
        }

        return {
            layers: diagramLayers,
            material_legend: materialLegend,
            legend_mode: legendMode,
            scale: scale,
            legend_caption: LEGEND_CAPTIONS[legendMode],
            total_thickness: Math.round(totalThickness * 10000) / 10000,
            layer_count: diagramLayers.length,
        };
    }

    function renderModeSelect(selectedMode) {
        return ''
            + '<div class="layer-legend-mode">'
            + '<label class="layer-legend-mode__label" for="layer-legend-mode-select">Режим легенды</label>'
            + '<select id="layer-legend-mode-select" class="form-select form-select-sm layer-legend-mode__select">'
            + Object.keys(LEGEND_MODE_LABELS).map(function (mode) {
                return '<option value="' + mode + '"'
                    + (mode === selectedMode ? ' selected' : '')
                    + '>' + escapeHtml(LEGEND_MODE_LABELS[mode]) + '</option>';
            }).join('')
            + '</select>'
            + '</div>';
    }

    function renderScaleLegend(scale, mode) {
        if (!scale) {
            return '';
        }
        var decimals = mode === LEGEND_MODE_THICKNESS ? 4 : 2;
        return ''
            + '<div class="layer-scale-legend mb-3" aria-label="Цветовая шкала">'
            + '<div class="layer-scale-legend__bar"></div>'
            + '<div class="layer-scale-legend__labels">'
            + '<span>' + escapeHtml(formatDecimalDisplay(scale.min, decimals))
            + ' ' + escapeHtml(scale.unit) + '</span>'
            + '<span>среднее</span>'
            + '<span>' + escapeHtml(formatDecimalDisplay(scale.max, decimals))
            + ' ' + escapeHtml(scale.unit) + '</span>'
            + '</div>'
            + '</div>';
    }

    function renderMaterialLegend(entries) {
        if (!entries || !entries.length) {
            return '';
        }
        return ''
            + '<div class="layer-material-legend mb-3">'
            + entries.map(function (entry) {
                return ''
                    + '<span class="layer-material-chip">'
                    + '<span class="layer-material-chip-swatch" style="background-color: '
                    + escapeHtml(entry.color) + ';"></span>'
                    + escapeHtml(entry.material_label)
                    + '</span>';
            }).join('')
            + '</div>';
    }

    function renderDiagram(target, diagram, options) {
        if (!target) {
            return;
        }
        var opts = options || {};
        var showModeSelect = opts.showModeSelect !== false;

        if (!diagram) {
            target.innerHTML = ''
                + '<div class="composite-layer-diagram composite-layer-diagram--empty p-3 p-lg-4 h-100">'
                + '<div class="d-flex justify-content-between align-items-start gap-2 mb-2">'
                + '<h3 class="composite-layer-diagram__title mb-0">Схема укладки</h3>'
                + (showModeSelect ? renderModeSelect(getStoredLegendMode()) : '')
                + '</div>'
                + '<p class="text-muted mb-0">Добавьте слои слева — схема появится здесь.</p>'
                + '</div>';
            return;
        }

        var legendHtml = diagram.legend_mode === LEGEND_MODE_MATERIAL
            ? renderMaterialLegend(diagram.material_legend)
            : renderScaleLegend(diagram.scale, diagram.legend_mode);

        var stackHtml = diagram.layers.map(function (item) {
            return ''
                + '<div class="layer-stack-segment"'
                + ' style="flex: ' + item.flex_grow + ' 1 0%; background-color: ' + escapeHtml(item.color) + ';"'
                + ' data-material-id="' + escapeHtml(String(item.material_id)) + '"'
                + ' data-thickness="' + escapeHtml(String(item.thickness)) + '"'
                + ' data-angle="' + escapeHtml(String(item.angle_value != null ? item.angle_value : item.angle)) + '"'
                + ' title="Слой ' + item.layer_number + ': ' + escapeHtml(item.material_label)
                + ' · ' + escapeHtml(formatDecimalDisplay(item.thickness)) + ' мм'
                + ' · ' + escapeHtml(String(item.angle)) + '°">'
                + '<span class="layer-stack-segment-index">#' + item.layer_number + '</span>'
                + '<span class="layer-stack-material-code">' + escapeHtml(item.material_code) + '</span>'
                + '</div>';
        }).join('');

        target.innerHTML = ''
            + '<div class="composite-layer-diagram p-3 p-lg-4">'
            + '<div class="d-flex justify-content-between align-items-start gap-2 mb-2 flex-wrap">'
            + '<h3 class="composite-layer-diagram__title mb-0">Схема укладки</h3>'
            + (showModeSelect ? renderModeSelect(diagram.legend_mode) : '')
            + '</div>'
            + legendHtml
            + '<div class="layer-stack-panel">'
            + '<div class="layer-stack-title">Сверху ↓ вниз</div>'
            + '<div class="layer-stack-column" style="--layer-stack-count: ' + diagram.layer_count + ';">'
            + stackHtml
            + '</div>'
            + '<div class="layer-stack-caption">' + escapeHtml(diagram.legend_caption) + '</div>'
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

    function bindModeSelect(diagramTarget, onChange) {
        if (!diagramTarget || diagramTarget.dataset.legendModeBound === 'true') {
            return;
        }
        diagramTarget.dataset.legendModeBound = 'true';
        diagramTarget.addEventListener('change', function (event) {
            var select = event.target.closest('#layer-legend-mode-select');
            if (!select) {
                return;
            }
            var mode = resolveLegendMode(select.value);
            setStoredLegendMode(mode);
            if (typeof onChange === 'function') {
                onChange(mode);
            }
        });
    }

    function update(layerContainer, diagramTarget, summaryTarget) {
        var mode = getStoredLegendMode();
        var diagram = buildLayerDiagram(parseLayerRows(layerContainer), mode);
        renderDiagram(diagramTarget, diagram);
        renderSummary(summaryTarget, diagram);
        bindModeSelect(diagramTarget, function () {
            update(layerContainer, diagramTarget, summaryTarget);
        });
    }

    function renderStatic(diagramTarget, layers, options) {
        var opts = options || {};
        var mode = resolveLegendMode(opts.colorBy || getStoredLegendMode());
        setStoredLegendMode(mode);
        var normalized = (layers || []).map(function (layer) {
            return Object.assign({}, layer, {
                angle_value: layer.angle_value != null
                    ? Number(layer.angle_value)
                    : parseAngleValue(layer.angle),
                thickness: Number(layer.thickness_value != null ? layer.thickness_value : layer.thickness) || 0,
            });
        });
        var diagram = buildLayerDiagram(normalized, mode);
        renderDiagram(diagramTarget, diagram, { showModeSelect: true });
        bindModeSelect(diagramTarget, function (nextMode) {
            renderStatic(diagramTarget, layers, { colorBy: nextMode });
        });
        return diagram;
    }

    window.CompositeLayerDiagramLive = {
        update: update,
        renderStatic: renderStatic,
        buildLayerDiagram: buildLayerDiagram,
        expandSymmetricLayers: expandSymmetricLayers,
        isSymmetricEnabled: isSymmetricEnabled,
        divergingBlueWhiteRed: divergingBlueWhiteRed,
        getStoredLegendMode: getStoredLegendMode,
    };
})();
