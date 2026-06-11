(function () {
    'use strict';

    function getDiagramTargets() {
        return {
            diagramTarget: document.getElementById('composite-layer-diagram-live'),
            summaryTarget: document.getElementById('composite-layer-thickness-summary'),
        };
    }

    function refreshDiagram(container) {
        var targets = getDiagramTargets();
        if (!window.CompositeLayerDiagramLive || !targets.diagramTarget) {
            return;
        }
        window.CompositeLayerDiagramLive.update(
            container,
            targets.diagramTarget,
            targets.summaryTarget,
        );
    }

    function isRowVisible(row) {
        if (!row || !row.classList.contains('layer-form-row')) {
            return false;
        }
        if (row.classList.contains('d-none')) {
            return false;
        }
        var deleteInput = row.querySelector('input[name$="-DELETE"]');
        return !(deleteInput && deleteInput.checked);
    }

    function getVisibleRows(container) {
        return Array.from(container.querySelectorAll('.layer-form-row')).filter(isRowVisible);
    }

    function getRowSelectCheckbox(row) {
        return row.querySelector('.layer-row-select');
    }

    function getSelectedRows(container) {
        return getVisibleRows(container).filter(function (row) {
            var checkbox = getRowSelectCheckbox(row);
            return checkbox && checkbox.checked;
        });
    }

    function updateEmptyState(container) {
        var emptyRow = container.querySelector('.layer-empty-row');
        var hasLayers = getVisibleRows(container).length > 0;
        if (emptyRow) {
            emptyRow.classList.toggle('d-none', hasLayers);
        }
    }

    function renumberLayers(container) {
        getVisibleRows(container).forEach(function (row, index) {
            var layerNum = index + 1;
            var layerInput = row.querySelector('input[name$="-layer_number"]');
            if (layerInput) {
                layerInput.value = layerNum;
            }
            var badge = row.querySelector('.layer-index-display');
            if (badge) {
                badge.textContent = String(layerNum);
            }
        });
        updateEmptyState(container);
    }

    function reindexForms(container, totalFormsInput) {
        var rows = Array.from(container.querySelectorAll('.layer-form-row'));
        rows.forEach(function (row, idx) {
            row.querySelectorAll('[name]').forEach(function (input) {
                input.name = input.name.replace(/^layers-\d+-/, 'layers-' + idx + '-');
                if (input.id) {
                    input.id = input.id.replace(/^id_layers-\d+-/, 'id_layers-' + idx + '-');
                }
            });
            row.querySelectorAll('label[for]').forEach(function (label) {
                var htmlFor = label.getAttribute('for');
                if (htmlFor) {
                    label.setAttribute(
                        'for',
                        htmlFor.replace(/^id_layers-\d+-/, 'id_layers-' + idx + '-'),
                    );
                }
            });
        });
        totalFormsInput.value = String(rows.length);
    }

    function copyRowValues(sourceRow, targetRow) {
        sourceRow.querySelectorAll('[name]').forEach(function (sourceInput) {
            var suffix = sourceInput.name.replace(/^layers-\d+-/, '');
            if (suffix === 'DELETE' || suffix === 'id' || suffix === 'layer_number') {
                return;
            }
            var targetInput = targetRow.querySelector('[name$="-' + suffix + '"]');
            if (!targetInput) {
                return;
            }
            if (targetInput.type === 'checkbox') {
                targetInput.checked = sourceInput.checked;
            } else {
                targetInput.value = sourceInput.value;
            }
        });
        if (window.MaterialPickerFields) {
            window.MaterialPickerFields.syncSelect(targetRow.querySelector('[name$="-material"]'));
        }
    }

    function deleteRow(container, row, totalFormsInput) {
        var idInput = row.querySelector('input[name$="-id"]');
        var deleteInput = row.querySelector('input[name$="-DELETE"]');
        var checkbox = getRowSelectCheckbox(row);

        if (idInput && idInput.value && deleteInput) {
            deleteInput.checked = true;
            row.classList.add('d-none');
        } else {
            row.remove();
            reindexForms(container, totalFormsInput);
        }
        if (checkbox) {
            checkbox.checked = false;
        }
        row.classList.remove('layer-form-row--selected');
    }

    function appendLayerFromTemplate(container, template, totalFormsInput) {
        var formIndex = container.querySelectorAll('.layer-form-row').length;
        var html = template.innerHTML.replace(/__prefix__/g, String(formIndex));
        var wrapper = document.createElement('tbody');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = String(formIndex + 1);
        if (window.MaterialPickerFields) {
            window.MaterialPickerFields.init(row);
        }
        renumberLayers(container);
        refreshDiagram(container);
        return row;
    }

    function duplicateRows(container, rows, template, totalFormsInput, ui) {
        rows.forEach(function (sourceRow) {
            var newRow = appendLayerFromTemplate(container, template, totalFormsInput);
            if (newRow) {
                copyRowValues(sourceRow, newRow);
                bindRow(container, newRow, totalFormsInput, ui, state);
            }
        });
        renumberLayers(container);
        refreshDiagram(container);
    }

    function moveRows(container, rows, targetRow, totalFormsInput) {
        if (!rows.length || !targetRow) {
            return;
        }

        var visibleRows = getVisibleRows(container);
        var leadRow = rows[0];
        var dragIndex = visibleRows.indexOf(leadRow);
        var targetIndex = visibleRows.indexOf(targetRow);
        if (dragIndex === -1 || targetIndex === -1 || dragIndex === targetIndex) {
            return;
        }

        var orderedRows = rows.slice().sort(function (a, b) {
            return visibleRows.indexOf(a) - visibleRows.indexOf(b);
        });
        var fragment = document.createDocumentFragment();
        orderedRows.forEach(function (row) {
            fragment.appendChild(row);
        });

        if (dragIndex < targetIndex) {
            container.insertBefore(fragment, targetRow.nextElementSibling);
        } else {
            container.insertBefore(fragment, targetRow);
        }

        reindexForms(container, totalFormsInput);
        renumberLayers(container);
        refreshDiagram(container);
    }

    function moveSelectedRows(container, direction, totalFormsInput) {
        var visibleRows = getVisibleRows(container);
        var selected = getSelectedRows(container);
        if (!selected.length) {
            return;
        }

        var indices = selected.map(function (row) {
            return visibleRows.indexOf(row);
        }).sort(function (a, b) {
            return a - b;
        });

        if (direction < 0) {
            if (indices[0] === 0) {
                return;
            }
            moveRows(container, selected, visibleRows[indices[0] - 1], totalFormsInput);
            return;
        }

        if (indices[indices.length - 1] >= visibleRows.length - 1) {
            return;
        }
        var anchor = visibleRows[indices[indices.length - 1] + 1];
        selected.forEach(function (row) {
            container.insertBefore(row, anchor.nextSibling);
            anchor = row;
        });
        reindexForms(container, totalFormsInput);
        renumberLayers(container);
        refreshDiagram(container);
    }

    function updateRowSelectionState(row) {
        var checkbox = getRowSelectCheckbox(row);
        row.classList.toggle('layer-form-row--selected', Boolean(checkbox && checkbox.checked));
    }

    function clearSelection(container) {
        getVisibleRows(container).forEach(function (row) {
            var checkbox = getRowSelectCheckbox(row);
            if (checkbox) {
                checkbox.checked = false;
            }
            updateRowSelectionState(row);
        });
    }

    function updateToolbarState(container, ui) {
        var visibleRows = getVisibleRows(container);
        var selectedRows = getSelectedRows(container);
        var selectedCount = selectedRows.length;
        var hasSelection = selectedCount > 0;

        if (ui.duplicateBtn) {
            ui.duplicateBtn.disabled = !hasSelection;
        }
        if (ui.deleteBtn) {
            ui.deleteBtn.disabled = !hasSelection;
        }

        if (!hasSelection) {
            if (ui.moveUpBtn) {
                ui.moveUpBtn.disabled = true;
            }
            if (ui.moveDownBtn) {
                ui.moveDownBtn.disabled = true;
            }
        } else {
            var indices = selectedRows.map(function (row) {
                return visibleRows.indexOf(row);
            });
            var minIndex = Math.min.apply(null, indices);
            var maxIndex = Math.max.apply(null, indices);
            if (ui.moveUpBtn) {
                ui.moveUpBtn.disabled = minIndex === 0;
            }
            if (ui.moveDownBtn) {
                ui.moveDownBtn.disabled = maxIndex >= visibleRows.length - 1;
            }
        }

        if (ui.selectionMeta) {
            if (!visibleRows.length) {
                ui.selectionMeta.textContent = '';
            } else if (!selectedCount) {
                ui.selectionMeta.textContent = visibleRows.length + ' сл.';
            } else {
                ui.selectionMeta.textContent = 'Выбрано ' + selectedCount + ' из ' + visibleRows.length;
            }
        }

        if (ui.selectAll) {
            ui.selectAll.indeterminate = selectedCount > 0 && selectedCount < visibleRows.length;
            ui.selectAll.checked = visibleRows.length > 0 && selectedCount === visibleRows.length;
        }
    }

    function bindLiveUpdates(container, row) {
        row.querySelectorAll('input:not(.layer-row-select), select').forEach(function (input) {
            if (input.dataset.layerDiagramBound === 'true') {
                return;
            }
            input.dataset.layerDiagramBound = 'true';
            input.addEventListener('input', function () {
                refreshDiagram(container);
            });
            input.addEventListener('change', function () {
                refreshDiagram(container);
            });
        });
    }

    function handleRowSelection(container, row, event, ui, state) {
        var checkbox = getRowSelectCheckbox(row);
        if (!checkbox) {
            return;
        }

        var visibleRows = getVisibleRows(container);

        if (event.shiftKey && state.lastSelectedRow && visibleRows.indexOf(state.lastSelectedRow) !== -1) {
            var start = visibleRows.indexOf(state.lastSelectedRow);
            var end = visibleRows.indexOf(row);
            if (start > end) {
                var tmp = start;
                start = end;
                end = tmp;
            }
            for (var i = start; i <= end; i += 1) {
                var cb = getRowSelectCheckbox(visibleRows[i]);
                if (cb) {
                    cb.checked = true;
                    updateRowSelectionState(visibleRows[i]);
                }
            }
        } else if (event.ctrlKey || event.metaKey) {
            if (event.target.classList.contains('layer-row-select')) {
                updateRowSelectionState(row);
            } else {
                checkbox.checked = !checkbox.checked;
                updateRowSelectionState(row);
            }
        } else if (event.target.classList.contains('layer-row-select')) {
            updateRowSelectionState(row);
        } else {
            clearSelection(container);
            checkbox.checked = true;
            updateRowSelectionState(row);
        }

        if (checkbox.checked) {
            state.lastSelectedRow = row;
        }
        updateToolbarState(container, ui);
    }

    function bindDragAndDrop(container, totalFormsInput, ui) {
        var dragRow = null;

        container.addEventListener('dragstart', function (event) {
            var handle = event.target.closest('.layer-drag-handle');
            if (!handle) {
                return;
            }
            dragRow = handle.closest('.layer-form-row');
            if (!isRowVisible(dragRow)) {
                dragRow = null;
                return;
            }
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', 'layer');
        });

        container.addEventListener('dragend', function () {
            dragRow = null;
        });

        container.addEventListener('dragover', function (event) {
            if (!dragRow) {
                return;
            }
            event.preventDefault();
        });

        container.addEventListener('drop', function (event) {
            if (!dragRow) {
                return;
            }
            event.preventDefault();
            var targetRow = event.target.closest('.layer-form-row');
            if (!targetRow || targetRow === dragRow || !isRowVisible(targetRow)) {
                return;
            }
            var selected = getSelectedRows(container);
            var rowsToMove = selected.indexOf(dragRow) !== -1 ? selected.slice() : [dragRow];
            moveRows(container, rowsToMove, targetRow, totalFormsInput);
            dragRow = null;
            updateToolbarState(container, ui);
        });
    }

    function bindKeyboardShortcuts(container, template, totalFormsInput, ui, state) {
        document.addEventListener('keydown', function (event) {
            if (!container.closest('.composite-layers-card')) {
                return;
            }
            var active = document.activeElement;
            var inLayers = container.contains(active) || active.closest('.composite-layers-card');
            if (!inLayers) {
                return;
            }
            if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) {
                if (event.key !== 'Delete' && event.key !== 'Backspace') {
                    return;
                }
            }

            if (event.key === 'Insert' || (event.key === 'Enter' && event.altKey)) {
                event.preventDefault();
                ui.addLayer();
                return;
            }

            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') {
                event.preventDefault();
                ui.duplicateSelected();
                return;
            }

            if (event.key === 'Delete' || event.key === 'Backspace') {
                if (getSelectedRows(container).length) {
                    event.preventDefault();
                    ui.deleteSelected();
                }
                return;
            }

            if (event.key === 'ArrowUp' && (event.altKey || getSelectedRows(container).length)) {
                event.preventDefault();
                moveSelectedRows(container, -1, totalFormsInput);
                updateToolbarState(container, ui);
                return;
            }

            if (event.key === 'ArrowDown' && (event.altKey || getSelectedRows(container).length)) {
                event.preventDefault();
                moveSelectedRows(container, 1, totalFormsInput);
                updateToolbarState(container, ui);
            }
        });
    }

    function bindRow(container, row, totalFormsInput, ui, state) {
        bindLiveUpdates(container, row);

        var checkbox = getRowSelectCheckbox(row);
        if (checkbox && checkbox.dataset.bound !== 'true') {
            checkbox.dataset.bound = 'true';
            checkbox.addEventListener('click', function (event) {
                event.stopPropagation();
            });
            checkbox.addEventListener('change', function (event) {
                handleRowSelection(container, row, event, ui, state);
            });
        }

        if (row.dataset.rowBound === 'true') {
            return;
        }
        row.dataset.rowBound = 'true';
        row.addEventListener('click', function (event) {
            if (event.target.closest('.layer-drag-handle, .material-picker-field, button')) {
                return;
            }
            handleRowSelection(container, row, event, ui, state);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('layer-forms-container');
        var template = document.getElementById('empty-layer-form-template');
        var addButton = document.getElementById('add-layer-btn');
        var duplicateBtn = document.getElementById('duplicate-layers-btn');
        var deleteBtn = document.getElementById('delete-layers-btn');
        var moveUpBtn = document.getElementById('move-layers-up-btn');
        var moveDownBtn = document.getElementById('move-layers-down-btn');
        var selectAll = document.getElementById('layer-select-all');
        var selectionMeta = document.getElementById('layers-selection-meta');
        var totalFormsInput = document.getElementById('id_layers-TOTAL_FORMS');
        var form = container ? container.closest('form') : null;

        if (!container || !template || !addButton || !totalFormsInput) {
            return;
        }

        var state = { lastSelectedRow: null };
        var ui = {
            duplicateBtn: duplicateBtn,
            deleteBtn: deleteBtn,
            moveUpBtn: moveUpBtn,
            moveDownBtn: moveDownBtn,
            selectAll: selectAll,
            selectionMeta: selectionMeta,
            addLayer: function () {},
            duplicateSelected: function () {},
            deleteSelected: function () {},
        };

        ui.addLayer = function () {
            var visible = getVisibleRows(container);
            var lastRow = visible[visible.length - 1];
            var row = appendLayerFromTemplate(container, template, totalFormsInput);
            bindRow(container, row, totalFormsInput, ui, state);
            if (lastRow) {
                copyRowValues(lastRow, row);
            }
            clearSelection(container);
            var checkbox = getRowSelectCheckbox(row);
            if (checkbox) {
                checkbox.checked = true;
                updateRowSelectionState(row);
                state.lastSelectedRow = row;
            }
            updateToolbarState(container, ui);
            row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        };

        ui.duplicateSelected = function () {
            var selected = getSelectedRows(container).slice();
            if (!selected.length) {
                return;
            }
            duplicateRows(container, selected, template, totalFormsInput, ui);
            updateToolbarState(container, ui);
        };

        ui.deleteSelected = function () {
            getSelectedRows(container).slice().forEach(function (row) {
                deleteRow(container, row, totalFormsInput);
            });
            state.lastSelectedRow = null;
            updateToolbarState(container, ui);
            refreshDiagram(container);
        };

        container.querySelectorAll('.layer-form-row').forEach(function (row) {
            bindRow(container, row, totalFormsInput, ui, state);
        });

        if (window.MaterialPickerFields) {
            window.MaterialPickerFields.init(container);
        }

        addButton.addEventListener('click', ui.addLayer);
        if (duplicateBtn) {
            duplicateBtn.addEventListener('click', ui.duplicateSelected);
        }
        if (deleteBtn) {
            deleteBtn.addEventListener('click', ui.deleteSelected);
        }
        if (moveUpBtn) {
            moveUpBtn.addEventListener('click', function () {
                moveSelectedRows(container, -1, totalFormsInput);
                updateToolbarState(container, ui);
            });
        }
        if (moveDownBtn) {
            moveDownBtn.addEventListener('click', function () {
                moveSelectedRows(container, 1, totalFormsInput);
                updateToolbarState(container, ui);
            });
        }
        if (selectAll) {
            selectAll.addEventListener('change', function () {
                var checked = selectAll.checked;
                getVisibleRows(container).forEach(function (row) {
                    var checkbox = getRowSelectCheckbox(row);
                    if (checkbox) {
                        checkbox.checked = checked;
                        updateRowSelectionState(row);
                    }
                });
                updateToolbarState(container, ui);
            });
        }

        bindDragAndDrop(container, totalFormsInput, ui);
        bindKeyboardShortcuts(container, template, totalFormsInput, ui, state);

        if (form) {
            form.addEventListener('submit', function () {
                reindexForms(container, totalFormsInput);
                renumberLayers(container);
            });
        }

        renumberLayers(container);
        refreshDiagram(container);
        updateToolbarState(container, ui);
    });
})();
