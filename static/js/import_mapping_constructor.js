(function () {
    'use strict';

    var form = document.querySelector('.import-map-constructor-form');
    if (!form) {
        return;
    }

    var SKIP = 'skip';
    var MULTI_OK = {
        'material.description': true,
        'material.tags': true,
        skip: true,
    };

    var required = (form.getAttribute('data-required-targets') || '')
        .split(',')
        .map(function (item) { return item.trim(); })
        .filter(Boolean);
    var dupBox = document.getElementById('import-duplicate-targets');
    var dupList = document.getElementById('import-duplicate-list');
    var missingBox = document.getElementById('import-missing-required');
    var missingList = document.getElementById('import-missing-required-list');
    var catalogSearch = document.getElementById('import-map-catalog-search');
    var clearRowBtn = document.getElementById('import-map-clear-row');
    var resetAllBtn = document.getElementById('import-map-reset-all');
    var catalogPanel = document.getElementById('import-map-catalog');

    var DRAG_MIME = 'application/x-import-map-target';
    var rows = Array.prototype.slice.call(form.querySelectorAll('[data-import-map-row]'));
    var catalogItems = Array.prototype.slice.call(form.querySelectorAll('.import-map-catalog-item'));
    var selectedRow = null;
    var dragPayload = null;
    var suppressNextClick = false;
    var targetLabels = {};
    catalogItems.forEach(function (btn) {
        var target = btn.getAttribute('data-target');
        if (target) {
            targetLabels[target] = btn.getAttribute('data-label') || target;
        }
    });
    var requiredLabels = {};
    required.forEach(function (target) {
        requiredLabels[target] = targetLabels[target] || (target === 'material.name' ? 'Название' : target);
    });

    function rowTargetInput(row) {
        return row ? row.querySelector('.import-map-target') : null;
    }

    function rowLabelEl(row) {
        return row ? row.querySelector('.import-map-expr-label') : null;
    }

    function rowSlotEl(row) {
        return row ? row.querySelector('.import-map-expr-slot') : null;
    }

    function optionLabel(value) {
        if (!value || value === SKIP) {
            return '';
        }
        if (targetLabels[value]) {
            return targetLabels[value];
        }
        var match = catalogItems.find(function (btn) {
            return btn.getAttribute('data-target') === value;
        });
        return match ? (match.getAttribute('data-label') || value) : value;
    }

    function skipLabelFor() {
        return '';
    }

    function findRowByColumnIndex(index) {
        var needle = String(index);
        return rows.find(function (row) {
            return row.getAttribute('data-column-index') === needle;
        }) || null;
    }

    function syncRowExpressionUi(row) {
        var input = rowTargetInput(row);
        if (!input) {
            return;
        }
        var isSkip = !input.value || input.value === SKIP;
        row.classList.toggle('is-unmapped', isSkip);
        var slot = rowSlotEl(row);
        if (slot) {
            slot.classList.toggle('is-empty', isSkip);
            slot.setAttribute('draggable', isSkip ? 'false' : 'true');
            slot.title = isSkip
                ? 'Перетащите поле сюда или выберите строку и кликните поле справа'
                : 'Перетащите обратно в каталог, чтобы очистить';
        }
        var labelEl = rowLabelEl(row);
        if (labelEl) {
            var text = isSkip ? '' : (input.getAttribute('data-label') || optionLabel(input.value));
            labelEl.textContent = text;
        }
    }

    function selectRow(row) {
        if (selectedRow) {
            selectedRow.classList.remove('is-selected');
        }
        selectedRow = row || null;
        if (selectedRow) {
            selectedRow.classList.add('is-selected');
        }
        if (catalogPanel) {
            catalogPanel.classList.toggle('is-armed', !!selectedRow);
        }
    }

    function assignTarget(row, target, label) {
        var input = rowTargetInput(row);
        if (!input) {
            return;
        }
        var resolvedLabel = label || optionLabel(target);
        input.value = target;
        if (target === SKIP) {
            input.removeAttribute('data-label');
        } else {
            input.setAttribute('data-label', resolvedLabel);
        }
        syncRowExpressionUi(row);
        refreshState();
    }

    function clearRowExpression(row) {
        assignTarget(row, SKIP, skipLabelFor());
    }

    function targetUsage() {
        var counts = {};
        var columns = {};
        rows.forEach(function (row) {
            var input = rowTargetInput(row);
            if (!input) {
                return;
            }
            var value = input.value;
            if (!value || MULTI_OK[value]) {
                return;
            }
            counts[value] = (counts[value] || 0) + 1;
            if (!columns[value]) {
                columns[value] = [];
            }
            columns[value].push(row.getAttribute('data-column-label') || '');
        });
        return { counts: counts, columns: columns };
    }

    function canAssignTarget(row, target) {
        if (!target || MULTI_OK[target]) {
            return true;
        }
        var input = rowTargetInput(row);
        if (input && input.value === target) {
            return true;
        }
        var usage = targetUsage();
        return !usage.counts[target];
    }

    function refreshCatalogState() {
        var usage = targetUsage();
        catalogItems.forEach(function (btn) {
            var target = btn.getAttribute('data-target');
            var used = !!usage.counts[target];
            var disabled = used && !MULTI_OK[target];
            btn.classList.toggle('is-used', used);
            btn.classList.toggle('is-disabled', disabled);
            btn.disabled = disabled;
            btn.setAttribute('draggable', disabled ? 'false' : 'true');
        });
    }

    function clearDropHover() {
        form.querySelectorAll('.import-map-expr-slot.is-drop-hover, .import-map-expr-slot.is-drop-blocked')
            .forEach(function (slot) {
                slot.classList.remove('is-drop-hover', 'is-drop-blocked');
            });
        rows.forEach(function (row) {
            row.classList.remove('is-drop-over');
        });
        if (catalogPanel) {
            catalogPanel.classList.remove('is-drop-clear');
        }
    }

    function readDragPayload(event) {
        if (dragPayload) {
            return dragPayload;
        }
        if (!event.dataTransfer) {
            return null;
        }
        var raw = '';
        try {
            raw = event.dataTransfer.getData(DRAG_MIME) || event.dataTransfer.getData('text/plain');
        } catch (err) {
            return null;
        }
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (err) {
            return { target: raw, label: '', source: 'catalog' };
        }
    }

    function writeDragPayload(event, payload) {
        dragPayload = payload;
        var raw = JSON.stringify(payload);
        try {
            event.dataTransfer.setData(DRAG_MIME, raw);
        } catch (err) {
            /* older browsers */
        }
        event.dataTransfer.setData('text/plain', raw);
        event.dataTransfer.effectAllowed = payload.source === 'row' ? 'move' : 'copy';
        form.classList.add('is-dragging');
        form.classList.toggle('is-dragging-from-row', payload.source === 'row');
    }

    function endDrag(element) {
        if (element) {
            element.classList.remove('is-dragging');
        }
        form.classList.remove('is-dragging', 'is-dragging-from-row');
        clearDropHover();
        dragPayload = null;
        suppressNextClick = true;
        window.setTimeout(function () {
            suppressNextClick = false;
        }, 0);
    }

    function setSlotDropState(row, payload) {
        var slot = rowSlotEl(row);
        if (!slot || !payload || !payload.target) {
            return;
        }
        if (payload.source === 'row' && String(payload.columnIndex) === row.getAttribute('data-column-index')) {
            return;
        }
        var allowed = canAssignTarget(row, payload.target);
        slot.classList.toggle('is-drop-hover', allowed);
        slot.classList.toggle('is-drop-blocked', !allowed);
        row.classList.toggle('is-drop-over', true);
    }

    function applyTargetToRow(row, target, label, options) {
        options = options || {};
        if (!row || !target) {
            return;
        }
        selectRow(row);
        var input = rowTargetInput(row);
        if (!options.fromDrag && input && input.value === target && target !== SKIP) {
            clearRowExpression(row);
            return;
        }
        if (!canAssignTarget(row, target)) {
            return;
        }
        assignTarget(row, target, label);
        if (options.clearSourceRow && options.clearSourceRow !== row) {
            clearRowExpression(options.clearSourceRow);
        }
    }

    function dropPayloadOnRow(row, payload) {
        if (!row || !payload || !payload.target) {
            return;
        }
        var sourceRow = payload.source === 'row'
            ? findRowByColumnIndex(payload.columnIndex)
            : null;
        if (sourceRow === row) {
            return;
        }
        applyTargetToRow(row, payload.target, payload.label, {
            fromDrag: true,
            clearSourceRow: sourceRow,
        });
    }

    function dropPayloadOnCatalog(payload) {
        if (!payload || payload.source !== 'row') {
            return;
        }
        var sourceRow = findRowByColumnIndex(payload.columnIndex);
        if (sourceRow) {
            clearRowExpression(sourceRow);
            selectRow(sourceRow);
        }
    }

    function refreshRequiredHighlight() {
        var targetCounts = {};
        var targetColumns = {};
        rows.forEach(function (row) {
            var input = rowTargetInput(row);
            if (!input) {
                return;
            }
            var value = input.value;
            var isRequired = required.indexOf(value) !== -1;
            var colLabel = row.getAttribute('data-column-label') || '';
            row.classList.toggle('is-required-row', isRequired);
            row.classList.toggle('table-success', isRequired);
            var badge = row.querySelector('.import-required-badge');
            if (isRequired) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'import-required-badge';
                    badge.textContent = '★';
                    badge.title = 'Обязательное поле';
                    var titleEl = row.querySelector('.import-map-row__title');
                    if (titleEl && titleEl.parentNode) {
                        titleEl.parentNode.insertBefore(badge, titleEl.nextSibling);
                    }
                }
            } else if (badge) {
                badge.remove();
            }
            if (value && !MULTI_OK[value]) {
                targetCounts[value] = (targetCounts[value] || 0) + 1;
                if (!targetColumns[value]) {
                    targetColumns[value] = [];
                }
                targetColumns[value].push(colLabel || value);
            }
        });

        var duplicateTargets = Object.keys(targetCounts).filter(function (target) {
            return targetCounts[target] > 1;
        });

        rows.forEach(function (row) {
            var input = rowTargetInput(row);
            if (!input) {
                return;
            }
            var isDup = duplicateTargets.indexOf(input.value) !== -1;
            row.classList.toggle('is-duplicate', isDup);
            row.classList.toggle('table-warning', isDup && !row.classList.contains('is-required-row'));
        });

        if (dupBox && dupList) {
            dupBox.classList.toggle('d-none', duplicateTargets.length === 0);
            dupList.innerHTML = duplicateTargets.map(function (target) {
                var cols = (targetColumns[target] || []).map(function (col) {
                    return '«' + col + '»';
                }).join(', ');
                return '<li data-target="' + target + '"><code>' + target + '</code>: ' + cols + '</li>';
            }).join('');
        }

        var mappedTargets = {};
        rows.forEach(function (row) {
            var input = rowTargetInput(row);
            if (input && input.value) {
                mappedTargets[input.value] = true;
            }
        });
        var missingRequired = required.filter(function (target) {
            return !mappedTargets[target];
        });
        if (missingBox && missingList) {
            missingBox.classList.toggle('d-none', missingRequired.length === 0);
            missingList.innerHTML = missingRequired.map(function (target) {
                return '<li data-target="' + target + '">' + (requiredLabels[target] || target) + '</li>';
            }).join('');
        }

        form.querySelectorAll('.import-map-continue').forEach(function (button) {
            button.disabled = duplicateTargets.length > 0 || missingRequired.length > 0;
        });

        refreshCatalogState();
    }

    function refreshState() {
        refreshRequiredHighlight();
    }

    function filterCatalog(query) {
        var needle = (query || '').trim().toLowerCase();
        form.querySelectorAll('.import-map-catalog__item').forEach(function (item) {
            var label = item.getAttribute('data-catalog-label') || '';
            item.classList.toggle('d-none', needle && label.indexOf(needle) === -1);
        });
        form.querySelectorAll('.import-map-catalog__group').forEach(function (group) {
            var visible = group.querySelectorAll('.import-map-catalog__item:not(.d-none)').length > 0;
            group.classList.toggle('d-none', !visible && !!needle);
        });
    }

    rows.forEach(function (row) {
        row.addEventListener('click', function (event) {
            if (event.target.closest('select, button, a, input, label')) {
                return;
            }
            selectRow(row);
        });
        row.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                selectRow(row);
            }
        });
    });

    catalogItems.forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (suppressNextClick) {
                suppressNextClick = false;
                return;
            }
            if (!selectedRow && rows.length) {
                selectRow(rows[0]);
            }
            if (!selectedRow) {
                return;
            }
            applyTargetToRow(
                selectedRow,
                btn.getAttribute('data-target'),
                btn.getAttribute('data-label')
            );
        });

        btn.addEventListener('dragstart', function (event) {
            if (btn.disabled) {
                event.preventDefault();
                return;
            }
            writeDragPayload(event, {
                source: 'catalog',
                target: btn.getAttribute('data-target'),
                label: btn.getAttribute('data-label') || '',
            });
            btn.classList.add('is-dragging');
        });

        btn.addEventListener('dragend', function () {
            endDrag(btn);
        });
    });

    rows.forEach(function (row) {
        var slot = rowSlotEl(row);
        if (slot) {
            slot.addEventListener('dragstart', function (event) {
                var input = rowTargetInput(row);
                if (!input || !input.value || input.value === SKIP) {
                    event.preventDefault();
                    return;
                }
                event.stopPropagation();
                writeDragPayload(event, {
                    source: 'row',
                    columnIndex: row.getAttribute('data-column-index'),
                    target: input.value,
                    label: input.getAttribute('data-label') || optionLabel(input.value),
                });
                slot.classList.add('is-dragging');
                selectRow(row);
            });
            slot.addEventListener('dragend', function () {
                endDrag(slot);
            });
        }

        var dropZones = [row, slot].filter(Boolean);
        dropZones.forEach(function (zone) {
            zone.addEventListener('dragenter', function (event) {
                if (!readDragPayload(event) && !dragPayload) {
                    return;
                }
                event.preventDefault();
            });
            zone.addEventListener('dragover', function (event) {
                var payload = readDragPayload(event);
                if (!payload || !payload.target) {
                    return;
                }
                if (
                    payload.source === 'row'
                    && String(payload.columnIndex) === row.getAttribute('data-column-index')
                ) {
                    return;
                }
                event.preventDefault();
                event.dataTransfer.dropEffect = canAssignTarget(row, payload.target)
                    ? (payload.source === 'row' ? 'move' : 'copy')
                    : 'none';
                clearDropHover();
                setSlotDropState(row, payload);
            });
            zone.addEventListener('dragleave', function (event) {
                if (!row.contains(event.relatedTarget)) {
                    var currentSlot = rowSlotEl(row);
                    if (currentSlot) {
                        currentSlot.classList.remove('is-drop-hover', 'is-drop-blocked');
                    }
                    row.classList.remove('is-drop-over');
                }
            });
            zone.addEventListener('drop', function (event) {
                var payload = readDragPayload(event);
                if (!payload || !payload.target) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                clearDropHover();
                dropPayloadOnRow(row, payload);
            });
        });
    });

    if (catalogPanel) {
        catalogPanel.addEventListener('dragenter', function (event) {
            var payload = readDragPayload(event);
            if (!payload || payload.source !== 'row') {
                return;
            }
            event.preventDefault();
        });
        catalogPanel.addEventListener('dragover', function (event) {
            var payload = readDragPayload(event);
            if (!payload || payload.source !== 'row') {
                return;
            }
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            clearDropHover();
            catalogPanel.classList.add('is-drop-clear');
        });
        catalogPanel.addEventListener('dragleave', function (event) {
            if (!catalogPanel.contains(event.relatedTarget)) {
                catalogPanel.classList.remove('is-drop-clear');
            }
        });
        catalogPanel.addEventListener('drop', function (event) {
            var payload = readDragPayload(event);
            if (!payload || payload.source !== 'row') {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            clearDropHover();
            dropPayloadOnCatalog(payload);
        });
    }

    if (clearRowBtn) {
        clearRowBtn.addEventListener('click', function () {
            if (!selectedRow && rows.length) {
                selectRow(rows[0]);
            }
            if (selectedRow) {
                clearRowExpression(selectedRow);
            }
        });
    }

    if (resetAllBtn) {
        resetAllBtn.addEventListener('click', function () {
            if (!window.confirm('Сбросить все выражения? Все колонки будут помечены как «пропустить».')) {
                return;
            }
            rows.forEach(function (row) {
                clearRowExpression(row);
            });
        });
    }

    if (catalogSearch) {
        catalogSearch.addEventListener('input', function () {
            filterCatalog(catalogSearch.value);
        });
    }

    var policy = document.getElementById('map-match-policy');
    if (policy) {
        policy.addEventListener('change', refreshState);
    }

    rows.forEach(function (row) {
        syncRowExpressionUi(row);
    });

    if (rows.length) {
        selectRow(rows[0]);
    }
    refreshState();
})();
