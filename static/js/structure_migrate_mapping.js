(function () {
    'use strict';

    var form = document.querySelector('.migrate-map-constructor-form');
    if (!form) {
        return;
    }

    var DRAG_MIME = 'application/x-migrate-map-source';
    var catalogSearch = document.getElementById('migrate-map-catalog-search');
    var clearRowBtn = document.getElementById('migrate-map-clear-row');
    var resetAllBtn = document.getElementById('migrate-map-reset-all');
    var catalogPanel = document.getElementById('migrate-map-catalog');
    var selectedRow = null;
    var dragPayload = null;
    var suppressNextClick = false;

    function rows() {
        return Array.prototype.slice.call(form.querySelectorAll('[data-migrate-map-row]'));
    }

    function catalogItems() {
        return Array.prototype.slice.call(
            form.querySelectorAll('.import-map-catalog-item[data-source-name]')
        );
    }

    function sourceInput(row) {
        return row ? row.querySelector('.migrate-map-source-value') : null;
    }

    function dropSlot(row) {
        return row ? row.querySelector('[data-drop-slot]') : null;
    }

    function clearBtn(row) {
        return row ? row.querySelector('[data-migrate-clear-row]') : null;
    }

    function setSelected(row) {
        rows().forEach(function (item) {
            item.classList.toggle('is-selected', item === row);
            item.setAttribute('aria-selected', item === row ? 'true' : 'false');
        });
        selectedRow = row;
    }

    function claimedSources() {
        var claimed = {};
        rows().forEach(function (row) {
            var input = sourceInput(row);
            if (input && input.value) {
                claimed[input.value] = row.getAttribute('data-target-field') || '';
            }
        });
        return claimed;
    }

    function syncCatalogUsed() {
        var claimed = claimedSources();
        catalogItems().forEach(function (btn) {
            var name = btn.getAttribute('data-source-name') || '';
            var used = Boolean(claimed[name]);
            btn.classList.toggle('is-used', used);
            btn.setAttribute('aria-disabled', used ? 'true' : 'false');
            var item = btn.closest('.import-map-catalog__item');
            if (item) {
                item.classList.toggle('is-used', used);
            }
        });
    }

    function setRowSource(row, sourceName, sourceLabel) {
        if (!row) {
            return;
        }
        var input = sourceInput(row);
        var slot = dropSlot(row);
        var labelEl = slot ? slot.querySelector('.import-map-expr-label') : null;
        var btn = clearBtn(row);
        if (!input || !slot || !labelEl) {
            return;
        }
        if (sourceName) {
            // Free this source from other rows.
            rows().forEach(function (other) {
                if (other === row) {
                    return;
                }
                var otherInput = sourceInput(other);
                if (otherInput && otherInput.value === sourceName) {
                    setRowSource(other, '', '');
                }
            });
            input.value = sourceName;
            input.setAttribute('data-label', sourceLabel || sourceName);
            labelEl.textContent = sourceLabel || sourceName;
            slot.classList.remove('is-empty');
            slot.setAttribute('draggable', 'true');
            row.classList.remove('is-unmapped');
            if (btn) {
                btn.classList.remove('d-none');
            }
        } else {
            input.value = '';
            input.setAttribute('data-label', '');
            labelEl.textContent = '';
            slot.classList.add('is-empty');
            slot.removeAttribute('draggable');
            row.classList.add('is-unmapped');
            if (btn) {
                btn.classList.add('d-none');
            }
        }
        syncCatalogUsed();
        updateSectionCount();
    }

    function updateSectionCount() {
        var countEl = form.querySelector('[data-map-section-count]');
        if (!countEl) {
            return;
        }
        var mapped = rows().filter(function (row) {
            var input = sourceInput(row);
            return input && input.value;
        }).length;
        countEl.textContent = String(mapped) + ' / ' + String(rows().length);
    }

    function assignFromCatalog(btn) {
        if (!btn || btn.classList.contains('is-used')) {
            return;
        }
        var row = selectedRow || rows().find(function (item) {
            var input = sourceInput(item);
            return input && !input.value;
        });
        if (!row) {
            return;
        }
        setSelected(row);
        setRowSource(
            row,
            btn.getAttribute('data-source-name') || '',
            btn.getAttribute('data-label') || ''
        );
    }

    function bindRow(row) {
        row.addEventListener('click', function (event) {
            if (event.target.closest('[data-migrate-clear-row]')) {
                return;
            }
            if (suppressNextClick) {
                suppressNextClick = false;
                return;
            }
            setSelected(row);
        });
        row.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                setSelected(row);
            }
        });

        var btn = clearBtn(row);
        if (btn) {
            btn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                setRowSource(row, '', '');
                setSelected(row);
            });
        }

        var slot = dropSlot(row);
        if (!slot) {
            return;
        }

        slot.addEventListener('dragstart', function (event) {
            var input = sourceInput(row);
            if (!input || !input.value) {
                event.preventDefault();
                return;
            }
            dragPayload = {
                sourceName: input.value,
                sourceLabel: input.getAttribute('data-label') || input.value,
                fromTarget: row.getAttribute('data-target-field') || '',
            };
            try {
                event.dataTransfer.setData(DRAG_MIME, JSON.stringify(dragPayload));
                event.dataTransfer.effectAllowed = 'move';
            } catch (err) {
                /* ignore */
            }
            slot.classList.add('is-dragging');
        });

        slot.addEventListener('dragend', function () {
            slot.classList.remove('is-dragging');
            dragPayload = null;
            suppressNextClick = true;
            window.setTimeout(function () {
                suppressNextClick = false;
            }, 0);
        });

        slot.addEventListener('dragover', function (event) {
            event.preventDefault();
            slot.classList.add('is-drop-target');
        });

        slot.addEventListener('dragleave', function () {
            slot.classList.remove('is-drop-target');
        });

        slot.addEventListener('drop', function (event) {
            event.preventDefault();
            slot.classList.remove('is-drop-target');
            var payload = dragPayload;
            if (!payload) {
                try {
                    payload = JSON.parse(event.dataTransfer.getData(DRAG_MIME) || '{}');
                } catch (err) {
                    payload = null;
                }
            }
            if (!payload || !payload.sourceName) {
                return;
            }
            var previous = sourceInput(row);
            var prevName = previous ? previous.value : '';
            var prevLabel = previous ? previous.getAttribute('data-label') || '' : '';
            setRowSource(row, payload.sourceName, payload.sourceLabel || payload.sourceName);
            if (payload.fromTarget && payload.fromTarget !== row.getAttribute('data-target-field')) {
                var fromRow = form.querySelector(
                    '[data-migrate-map-row][data-target-field="' +
                        (window.CSS && CSS.escape ? CSS.escape(payload.fromTarget) : payload.fromTarget) +
                        '"]'
                );
                if (fromRow) {
                    // Swap if target already had a value.
                    if (prevName) {
                        setRowSource(fromRow, prevName, prevLabel);
                    } else {
                        setRowSource(fromRow, '', '');
                    }
                }
            }
            setSelected(row);
            dragPayload = null;
        });
    }

    function bindCatalog() {
        catalogItems().forEach(function (btn) {
            btn.addEventListener('dragstart', function (event) {
                if (btn.classList.contains('is-used')) {
                    event.preventDefault();
                    return;
                }
                dragPayload = {
                    sourceName: btn.getAttribute('data-source-name') || '',
                    sourceLabel: btn.getAttribute('data-label') || '',
                    fromTarget: '',
                };
                try {
                    event.dataTransfer.setData(DRAG_MIME, JSON.stringify(dragPayload));
                    event.dataTransfer.effectAllowed = 'copyMove';
                } catch (err) {
                    /* ignore */
                }
                btn.classList.add('is-dragging');
            });
            btn.addEventListener('dragend', function () {
                btn.classList.remove('is-dragging');
                dragPayload = null;
            });
            btn.addEventListener('click', function () {
                assignFromCatalog(btn);
            });
        });

        if (catalogPanel) {
            catalogPanel.addEventListener('dragover', function (event) {
                if (!dragPayload || !dragPayload.fromTarget) {
                    return;
                }
                event.preventDefault();
            });
            catalogPanel.addEventListener('drop', function (event) {
                if (!dragPayload || !dragPayload.fromTarget) {
                    return;
                }
                event.preventDefault();
                var fromRow = form.querySelector(
                    '[data-migrate-map-row][data-target-field="' +
                        (window.CSS && CSS.escape ? CSS.escape(dragPayload.fromTarget) : dragPayload.fromTarget) +
                        '"]'
                );
                if (fromRow) {
                    setRowSource(fromRow, '', '');
                }
                dragPayload = null;
            });
        }
    }

    if (catalogSearch) {
        catalogSearch.addEventListener('input', function () {
            var q = (catalogSearch.value || '').trim().toLowerCase();
            form.querySelectorAll('.import-map-catalog__item').forEach(function (item) {
                var label = item.getAttribute('data-catalog-label') || '';
                item.classList.toggle('d-none', Boolean(q) && label.indexOf(q) === -1);
            });
        });
    }

    if (clearRowBtn) {
        clearRowBtn.addEventListener('click', function () {
            if (selectedRow) {
                setRowSource(selectedRow, '', '');
            }
        });
    }

    if (resetAllBtn) {
        resetAllBtn.addEventListener('click', function () {
            rows().forEach(function (row) {
                setRowSource(row, '', '');
            });
        });
    }

    form.querySelectorAll('[data-map-section-toggle]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var section = btn.closest('.import-map-section');
            if (!section) {
                return;
            }
            var collapsed = section.classList.toggle('is-collapsed');
            btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        });
    });

    rows().forEach(bindRow);
    bindCatalog();
    syncCatalogUsed();
    updateSectionCount();
})();
