(function () {
    'use strict';

    var form = document.querySelector('.import-map-constructor-form');
    if (!form) {
        return;
    }

    var SKIP = 'skip';
    var TARGET_CODE = 'material.code';
    var TARGET_TAGS = 'material.tags';
    var TARGET_TAG_PREFIX = 'tag:';
    var TARGET_PROPERTY_PREFIX = 'property:';
    var DRAG_MIME = 'application/x-import-map-column';

    var required = (form.getAttribute('data-required-targets') || '')
        .split(',')
        .map(function (item) { return item.trim(); })
        .filter(Boolean);
    var fileColumns = [];
    var fileColumnsEl = document.getElementById('import-file-columns');
    if (fileColumnsEl) {
        try {
            fileColumns = JSON.parse(fileColumnsEl.textContent || '[]') || [];
        } catch (err) {
            fileColumns = [];
        }
    }
    var columnMeta = {};
    fileColumns.forEach(function (col) {
        columnMeta[String(col.index)] = {
            label: col.label || ('Колонка ' + col.index),
            sample: col.sample || '—',
        };
    });

    var missingBox = document.getElementById('import-missing-required');
    var missingList = document.getElementById('import-missing-required-list');
    var catalogSearch = document.getElementById('import-map-catalog-search');
    var clearRowBtn = document.getElementById('import-map-clear-row');
    var resetAllBtn = document.getElementById('import-map-reset-all');
    var catalogPanel = document.getElementById('import-map-catalog');
    var tbodyPrimary = document.querySelector('#import-map-section-primary');
    var tbodyMaterial = document.querySelector('#import-map-section-material');
    var tbodyAddon = document.querySelector('#import-map-section-addon');
    var tbodyTag = document.querySelector('#import-map-section-tag');
    var hiddenBox = document.getElementById('import-map-hidden-inputs');
    var addonDropdownEl = document.getElementById('import-map-addon-dropdown');
    var addonSearch = document.getElementById('import-map-addon-search');
    var addonMenu = document.getElementById('import-map-addon-menu');
    var addFieldBtn = document.getElementById('import-map-add-field');

    var selectedRow = null;
    var dragPayload = null;
    var suppressNextClick = false;
    var parseModes = [];
    var requiredLabels = {};

    function rows() {
        return Array.prototype.slice.call(form.querySelectorAll('[data-import-map-row]'));
    }

    function catalogItems() {
        return Array.prototype.slice.call(form.querySelectorAll('.import-map-catalog-item[data-column-index]'));
    }

    function fallbackRequiredLabel(target) {
        if (target === 'material.name') {
            return 'Название';
        }
        if (target === TARGET_CODE) {
            return 'Код материала';
        }
        return target;
    }

    function syncRequiredFromPolicy() {
        // Name is always required for duplicate detection; overwrite on import is forbidden.
        required = (form.getAttribute('data-required-targets') || '')
            .split(',')
            .map(function (item) { return item.trim(); })
            .filter(Boolean);
        if (required.indexOf('material.name') < 0) {
            required.push('material.name');
        }
        required = required.filter(function (target) {
            return target !== TARGET_CODE;
        });
        form.setAttribute('data-required-targets', required.join(','));
        requiredLabels = {};
        required.forEach(function (target) {
            var row = findRowByTarget(target);
            requiredLabels[target] = (row && row.getAttribute('data-field-label'))
                || fallbackRequiredLabel(target);
        });
    }

    function isTagRow(row) {
        return row && row.getAttribute('data-map-section-kind') === 'tag';
    }

    function mappingTargetForRow(row) {
        if (!row) {
            return '';
        }
        var explicit = row.getAttribute('data-mapping-target');
        if (explicit) {
            return explicit;
        }
        var target = row.getAttribute('data-field-target') || '';
        if (target.indexOf(TARGET_TAG_PREFIX) === 0) {
            return TARGET_TAGS;
        }
        return target;
    }

    function tagScopeFromLabel(label) {
        var text = String(label || '').replace(/\s*[\(,].*$/, '').trim().toLowerCase();
        return text || 'тег';
    }

    function tagPreviewForColumn(index, sample) {
        var label = columnLabel(index);
        var scope = tagScopeFromLabel(label);
        var value = String(sample || '').trim();
        if (!value || value === '—') {
            return scope + '::…';
        }
        return scope + '::' + value;
    }

    function findRowByTarget(target) {
        return rows().find(function (row) {
            return row.getAttribute('data-field-target') === target;
        }) || null;
    }

    function findRowByColumnIndex(index, options) {
        options = options || {};
        var needle = String(index);
        var matches = rows().filter(function (row) {
            return row.getAttribute('data-column-index') === needle;
        });
        if (options.tagOnly) {
            return matches.find(function (row) { return isTagRow(row); }) || null;
        }
        if (options.preferNonTag) {
            return matches.find(function (row) { return !isTagRow(row); }) || matches[0] || null;
        }
        return matches[0] || null;
    }

    function canAssignTagColumn(columnIndex, options) {
        options = options || {};
        if (columnIndex == null || columnIndex === '') {
            return true;
        }
        var needle = String(columnIndex);
        if (options.ignoreTagRow) {
            var ignoreInput = columnInput(options.ignoreTagRow);
            if (ignoreInput && String(ignoreInput.value) === needle) {
                return true;
            }
        }
        return !rows().some(function (other) {
            if (!isTagRow(other)) {
                return false;
            }
            if (options.ignoreTagRow && other === options.ignoreTagRow) {
                return false;
            }
            return other.getAttribute('data-column-index') === needle;
        });
    }

    function columnInput(row) {
        return row ? row.querySelector('.import-map-column-value') : null;
    }

    function rowLabelEl(row) {
        return row ? row.querySelector('.import-map-expr-label') : null;
    }

    function rowSlotEl(row) {
        return row ? row.querySelector('.import-map-expr-slot') : null;
    }

    function parseSelect(row) {
        return row ? row.querySelector('.import-map-parse') : null;
    }

    function columnLabel(index) {
        var meta = columnMeta[String(index)];
        return meta ? meta.label : ('Колонка ' + index);
    }

    function columnSample(index) {
        var meta = columnMeta[String(index)];
        return meta ? meta.sample : '—';
    }

    function selectRow(row) {
        if (selectedRow) {
            selectedRow.classList.remove('is-selected');
            selectedRow.setAttribute('aria-selected', 'false');
        }
        selectedRow = row || null;
        if (selectedRow) {
            selectedRow.classList.add('is-selected');
            selectedRow.setAttribute('aria-selected', 'true');
        }
        if (catalogPanel) {
            catalogPanel.classList.toggle('is-armed', !!selectedRow);
        }
    }

    function syncRowExpressionUi(row) {
        var input = columnInput(row);
        if (!input) {
            return;
        }
        var index = (input.value || '').trim();
        var isEmpty = !index;
        row.classList.toggle('is-unmapped', isEmpty);
        if (isEmpty) {
            row.removeAttribute('data-column-index');
        } else {
            row.setAttribute('data-column-index', index);
        }
        var slot = rowSlotEl(row);
        if (slot) {
            slot.classList.toggle('is-empty', isEmpty);
            slot.setAttribute('draggable', isEmpty ? 'false' : 'true');
            slot.title = isEmpty
                ? 'Перетащите колонку сюда или выберите строку и кликните колонку справа'
                : (isTagRow(row)
                    ? 'Перетащите в другое поле, в «Теги» или обратно в каталог'
                    : 'Перетащите в другое поле, в «Теги» или обратно в каталог');
        }
        var labelEl = rowLabelEl(row);
        if (labelEl) {
            labelEl.textContent = isEmpty ? '' : (input.getAttribute('data-label') || columnLabel(index));
        }
        var sampleEl = row.querySelector('.import-map-row__sample-live');
        if (sampleEl) {
            var sample;
            if (isEmpty) {
                sample = '—';
            } else if (isTagRow(row)) {
                sample = tagPreviewForColumn(
                    index,
                    input.getAttribute('data-sample') || columnSample(index)
                );
            } else {
                sample = input.getAttribute('data-sample') || columnSample(index);
            }
            sampleEl.textContent = sample;
            sampleEl.title = sample;
        }
        var sampleDrag = row.querySelector('.import-map-row__sample');
        if (sampleDrag) {
            sampleDrag.classList.toggle('is-draggable-source', !isEmpty);
            sampleDrag.setAttribute('draggable', isEmpty ? 'false' : 'true');
            sampleDrag.title = isEmpty
                ? ''
                : 'Перетащите значение в «Теги» или в другое поле';
        }
        var titleEl = row.querySelector('.import-map-row__title');
        if (titleEl && isTagRow(row)) {
            titleEl.textContent = isEmpty
                ? 'Тег'
                : (row.getAttribute('data-field-label') || columnLabel(index));
        }
        var parse = parseSelect(row);
        if (parse && !parse.classList.contains('import-map-parse--tag')) {
            parse.disabled = isEmpty;
        }
    }

    function assignColumn(row, columnIndex, label, sample) {
        var input = columnInput(row);
        if (!input) {
            return;
        }
        var index = columnIndex == null || columnIndex === '' ? '' : String(columnIndex);
        input.value = index;
        if (!index) {
            input.removeAttribute('data-label');
            input.removeAttribute('data-sample');
        } else {
            input.setAttribute('data-label', label || columnLabel(index));
            input.setAttribute('data-sample', sample || columnSample(index));
        }
        if (isTagRow(row)) {
            if (index) {
                row.setAttribute('data-field-target', TARGET_TAG_PREFIX + index);
                row.setAttribute('data-field-label', label || columnLabel(index));
            }
        }
        syncRowExpressionUi(row);
        refreshState();
    }

    function clearRowExpression(row) {
        assignColumn(row, '', '', '—');
    }

    function canAssignColumn(row, columnIndex, options) {
        options = options || {};
        if (columnIndex == null || columnIndex === '') {
            return true;
        }
        var needle = String(columnIndex);
        var input = columnInput(row);
        if (input && String(input.value) === needle) {
            return true;
        }
        var ignoreField = options.ignoreFieldTarget;
        return !rows().some(function (other) {
            if (other === row) {
                return false;
            }
            if (isTagRow(other)) {
                return false;
            }
            if (ignoreField && other.getAttribute('data-field-target') === ignoreField) {
                return false;
            }
            return other.getAttribute('data-column-index') === needle;
        });
    }

    function syncHiddenInputs() {
        if (!hiddenBox) {
            return;
        }
        var byIndex = {};
        fileColumns.forEach(function (col) {
            byIndex[String(col.index)] = { target: SKIP, parse: 'auto' };
        });
        rows().forEach(function (row) {
            if (isTagRow(row)) {
                return;
            }
            var target = mappingTargetForRow(row);
            var input = columnInput(row);
            var parse = parseSelect(row);
            if (!target || !input || !input.value) {
                return;
            }
            byIndex[String(input.value)] = {
                target: target,
                parse: (parse && parse.value) || 'auto',
            };
        });
        Object.keys(byIndex).forEach(function (index) {
            var mapInput = hiddenBox.querySelector('[data-map-index="' + index + '"]');
            var parseInput = hiddenBox.querySelector('[data-parse-index="' + index + '"]');
            if (mapInput) {
                mapInput.value = byIndex[index].target;
            }
            if (parseInput) {
                parseInput.value = byIndex[index].parse;
            }
        });

        var tagBox = document.getElementById('import-map-tag-columns');
        if (tagBox) {
            tagBox.innerHTML = '';
            rows().forEach(function (row) {
                if (!isTagRow(row)) {
                    return;
                }
                var input = columnInput(row);
                if (!input || !input.value) {
                    return;
                }
                var hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = 'tag_col';
                hidden.value = input.value;
                tagBox.appendChild(hidden);
            });
        }
    }

    function refreshCatalogState() {
        var used = {};
        rows().forEach(function (row) {
            var index = row.getAttribute('data-column-index');
            if (index) {
                used[String(index)] = row;
            }
        });
        catalogItems().forEach(function (btn) {
            var index = btn.getAttribute('data-column-index');
            var owner = used[String(index)];
            var isUsed = !!owner;
            btn.classList.toggle('is-used', isUsed);
            btn.classList.toggle('is-locate-only', isUsed);
            btn.classList.remove('is-disabled');
            btn.disabled = false;
            btn.setAttribute('draggable', isUsed ? 'false' : 'true');
            btn.title = isUsed
                ? 'Уже в поле — клик выделит; можно также перетащить в «Теги»'
                : 'Клик или перетащите в «Колонка файла»';
        });
    }

    function clearDropHover() {
        form.querySelectorAll('.import-map-expr-slot.is-drop-hover, .import-map-expr-slot.is-drop-blocked')
            .forEach(function (slot) {
                slot.classList.remove('is-drop-hover', 'is-drop-blocked');
            });
        rows().forEach(function (row) {
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
            return { columnIndex: raw, label: '', source: 'catalog' };
        }
    }

    function rowAllowsDrop(row, payload) {
        if (!row || !payload || payload.columnIndex == null || payload.columnIndex === '') {
            return false;
        }
        if (isTagRow(row)) {
            return canAssignTagColumn(payload.columnIndex, { ignoreTagRow: row });
        }
        return canAssignColumn(row, payload.columnIndex, {
            ignoreFieldTarget: payload.source === 'row' ? payload.fieldTarget : null,
        });
    }

    function dropEffectFor(row, payload, allowed) {
        if (!allowed) {
            return 'none';
        }
        if (isTagRow(row)) {
            return 'copy';
        }
        return payload.source === 'row' ? 'move' : 'copy';
    }

    function writeRowDragPayload(event, row) {
        var input = columnInput(row);
        if (!input || !input.value) {
            event.preventDefault();
            return false;
        }
        event.stopPropagation();
        writeDragPayload(event, {
            source: 'row',
            fieldTarget: row.getAttribute('data-field-target'),
            columnIndex: input.value,
            label: input.getAttribute('data-label') || columnLabel(input.value),
            sample: input.getAttribute('data-sample') || columnSample(input.value),
        });
        selectRow(row);
        return true;
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
        event.dataTransfer.effectAllowed = payload.source === 'row' ? 'copyMove' : 'copy';
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
        if (!slot || !payload || payload.columnIndex == null || payload.columnIndex === '') {
            return;
        }
        if (
            payload.source === 'row'
            && payload.fieldTarget
            && payload.fieldTarget === row.getAttribute('data-field-target')
        ) {
            return;
        }
        var allowed = isTagRow(row)
            ? canAssignTagColumn(payload.columnIndex, { ignoreTagRow: row })
            : canAssignColumn(row, payload.columnIndex, {
                ignoreFieldTarget: payload.source === 'row' ? payload.fieldTarget : null,
            });
        slot.classList.toggle('is-drop-hover', allowed);
        slot.classList.toggle('is-drop-blocked', !allowed);
        row.classList.toggle('is-drop-over', true);
    }

    function applyColumnToRow(row, columnIndex, label, sample, options) {
        options = options || {};
        if (!row || columnIndex == null || columnIndex === '') {
            return;
        }
        selectRow(row);
        var input = columnInput(row);
        if (!options.fromDrag && input && String(input.value) === String(columnIndex)) {
            if (isTagRow(row)) {
                removeFieldRow(row);
            } else {
                clearRowExpression(row);
            }
            return;
        }
        if (isTagRow(row)) {
            if (!canAssignTagColumn(columnIndex, { ignoreTagRow: row })) {
                return;
            }
            var existingTagRow = findRowByColumnIndex(columnIndex, { tagOnly: true });
            if (existingTagRow && existingTagRow !== row) {
                removeFieldRow(existingTagRow);
            }
            assignColumn(row, columnIndex, label, sample);
            return;
        }
        if (!canAssignColumn(row, columnIndex, {
            ignoreFieldTarget: options.clearSourceRow
                ? options.clearSourceRow.getAttribute('data-field-target')
                : null,
        })) {
            return;
        }
        var owner = findRowByColumnIndex(columnIndex);
        if (owner && owner !== row) {
            if (isTagRow(owner)) {
                removeFieldRow(owner);
            } else {
                clearRowExpression(owner);
            }
        }
        assignColumn(row, columnIndex, label, sample);
    }

    function dropPayloadOnRow(row, payload) {
        if (!row || !payload || payload.columnIndex == null || payload.columnIndex === '') {
            return;
        }
        var sourceRow = payload.source === 'row' && payload.fieldTarget
            ? findRowByTarget(payload.fieldTarget)
            : null;
        if (sourceRow === row) {
            return;
        }
        if (isTagRow(row)) {
            if (!canAssignTagColumn(payload.columnIndex, { ignoreTagRow: row })) {
                return;
            }
            assignColumn(row, payload.columnIndex, payload.label, payload.sample);
            if (sourceRow && isTagRow(sourceRow) && sourceRow !== row) {
                removeFieldRow(sourceRow);
            }
            selectRow(row);
            return;
        }
        if (sourceRow) {
            if (!canAssignColumn(row, payload.columnIndex, {
                ignoreFieldTarget: payload.fieldTarget,
            })) {
                return;
            }
            var destInput = columnInput(row);
            var destIndex = destInput ? destInput.value : '';
            var destLabel = destInput ? (destInput.getAttribute('data-label') || '') : '';
            var destSample = destInput ? (destInput.getAttribute('data-sample') || '') : '';
            assignColumn(row, payload.columnIndex, payload.label, payload.sample);
            if (destIndex) {
                assignColumn(sourceRow, destIndex, destLabel, destSample);
            } else if (isTagRow(sourceRow)) {
                removeFieldRow(sourceRow);
            } else {
                clearRowExpression(sourceRow);
            }
            selectRow(row);
            return;
        }
        applyColumnToRow(row, payload.columnIndex, payload.label, payload.sample, {
            fromDrag: true,
        });
    }

    function dropPayloadOnCatalog(payload) {
        if (!payload || payload.source !== 'row' || !payload.fieldTarget) {
            return;
        }
        var sourceRow = findRowByTarget(payload.fieldTarget);
        if (sourceRow) {
            clearRowExpression(sourceRow);
            selectRow(sourceRow);
        }
    }

    function refreshRequiredHighlight() {
        var missingRequired = required.filter(function (target) {
            var row = findRowByTarget(target);
            if (!row) {
                return true;
            }
            var input = columnInput(row);
            return !(input && input.value);
        });

        rows().forEach(function (row) {
            var target = row.getAttribute('data-field-target');
            var isRequired = required.indexOf(target) !== -1;
            row.classList.toggle('is-required-row', isRequired);
            row.setAttribute('data-is-required', isRequired ? '1' : '0');
            var badge = row.querySelector('.import-required-badge');
            if (isRequired && !badge) {
                badge = document.createElement('span');
                badge.className = 'import-required-badge';
                badge.textContent = '★ обязательно';
                var headEl = row.querySelector('.import-map-row__head');
                if (headEl) {
                    headEl.appendChild(badge);
                } else {
                    var titleEl = row.querySelector('.import-map-row__title');
                    if (titleEl && titleEl.parentNode) {
                        titleEl.parentNode.insertBefore(badge, titleEl.nextSibling);
                    }
                }
            } else if (!isRequired && badge) {
                badge.remove();
            }
        });

        var colOwners = {};
        var duplicates = [];
        rows().forEach(function (row) {
            row.classList.remove('is-duplicate');
            var input = columnInput(row);
            if (!input || !input.value) {
                return;
            }
            var idx = String(input.value);
            if (colOwners[idx]) {
                var ownerRow = colOwners[idx];
                var fieldAndTagPair = isTagRow(ownerRow) !== isTagRow(row);
                if (!fieldAndTagPair) {
                    duplicates.push({
                        column: input.getAttribute('data-label') || columnLabel(idx),
                        targets: [
                            ownerRow.getAttribute('data-field-label') || '',
                            row.getAttribute('data-field-label') || '',
                        ],
                    });
                    row.classList.add('is-duplicate');
                    ownerRow.classList.add('is-duplicate');
                }
            } else {
                colOwners[idx] = row;
            }
        });

        if (missingBox && missingList) {
            missingBox.classList.toggle('d-none', missingRequired.length === 0);
            missingList.innerHTML = missingRequired.map(function (target) {
                return '<li data-target="' + target + '">'
                    + escapeHtml(requiredLabels[target] || fallbackRequiredLabel(target))
                    + '</li>';
            }).join('');
        }

        form.querySelectorAll('.import-map-continue').forEach(function (button) {
            button.disabled = duplicates.length > 0 || missingRequired.length > 0;
        });

        refreshCatalogState();
        syncHiddenInputs();
        refreshSectionMeta();
    }

    function refreshState() {
        rows().forEach(syncRowExpressionUi);
        refreshRequiredHighlight();
    }

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function escapeAttr(text) {
        return escapeHtml(text).replace(/'/g, '&#39;');
    }

    function collectParseModes() {
        var first = form.querySelector('.import-map-parse');
        parseModes = [];
        if (!first) {
            return;
        }
        Array.prototype.forEach.call(first.options, function (opt) {
            parseModes.push({ value: opt.value, label: opt.textContent });
        });
    }

    function parseOptionsHtml(selected) {
        return parseModes.map(function (mode) {
            var sel = mode.value === selected ? ' selected' : '';
            return '<option value="' + mode.value + '"' + sel + '>' + escapeHtml(mode.label) + '</option>';
        }).join('');
    }

    function ensureCodeRowIfNeeded() {
        if (required.indexOf(TARGET_CODE) === -1) {
            return;
        }
        if (findRowByTarget(TARGET_CODE)) {
            return;
        }
        addFieldRow(TARGET_CODE, 'Код материала', { primary: true });
    }

    function refreshSectionMeta() {
        document.querySelectorAll('.import-map-section').forEach(function (section) {
            var count = section.querySelectorAll('[data-import-map-row]').length;
            var countEl = section.querySelector('[data-map-section-count]');
            if (countEl) {
                countEl.textContent = String(count);
            }
            var emptyEl = section.querySelector('[data-map-section-empty]');
            if (emptyEl) {
                emptyEl.classList.toggle('d-none', count > 0);
            }
        });
    }

    function bindSectionToggles() {
        document.querySelectorAll('[data-map-section-toggle]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var section = btn.closest('.import-map-section');
                if (!section) {
                    return;
                }
                var collapsed = section.classList.toggle('is-collapsed');
                btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            });
        });
    }

    function hideAddonItem(target) {
        var btn = document.querySelector('.import-map-addon-item[data-target="' + CSS.escape(target) + '"]');
        if (btn) {
            btn.setAttribute('data-addon-hidden', '1');
            btn.classList.add('d-none');
        }
        syncMaterialAddButton();
    }

    function showAddonItem(target) {
        var btn = document.querySelector('.import-map-addon-item[data-target="' + CSS.escape(target) + '"]');
        if (btn) {
            btn.removeAttribute('data-addon-hidden');
            btn.classList.remove('d-none');
        }
        filterAddonCatalog();
        syncMaterialAddButton();
    }

    function filterAddonCatalog() {
        var needle = addonSearch ? (addonSearch.value || '').trim().toLowerCase() : '';
        document.querySelectorAll('#import-map-addon-catalog .import-map-addon-item').forEach(function (item) {
            if (item.getAttribute('data-addon-hidden') === '1') {
                item.classList.add('d-none');
                return;
            }
            var label = item.getAttribute('data-catalog-label') || '';
            item.classList.toggle('d-none', !!(needle && label.indexOf(needle) === -1));
        });
        document.querySelectorAll('#import-map-addon-catalog .import-map-addon-menu__group').forEach(function (group) {
            var visible = group.querySelectorAll('.import-map-addon-item:not(.d-none)').length > 0;
            group.classList.toggle('d-none', !visible && !!needle);
        });
        syncMaterialAddButton();
    }

    function closeAddonMenu() {
        if (!window.bootstrap || !bootstrap.Dropdown) {
            return;
        }
        var toggle = document.getElementById('import-map-add-field');
        if (!toggle) {
            return;
        }
        var dropdown = bootstrap.Dropdown.getInstance(toggle);
        if (dropdown) {
            dropdown.hide();
        }
    }

    function sectionBody(section) {
        if (section === 'primary') {
            return tbodyPrimary;
        }
        if (section === 'material') {
            return tbodyMaterial;
        }
        if (section === 'tag') {
            return tbodyTag;
        }
        return tbodyAddon;
    }

    function sectionForTarget(target, options) {
        options = options || {};
        if (options.primary || options.section === 'primary') {
            return 'primary';
        }
        if (options.section === 'tag' || (target || '').indexOf(TARGET_TAG_PREFIX) === 0 || target === TARGET_TAGS) {
            return 'tag';
        }
        if (options.section === 'material' || options.section === 'property') {
            return options.section;
        }
        if ((target || '').indexOf(TARGET_PROPERTY_PREFIX) === 0) {
            return 'property';
        }
        return 'material';
    }

    function syncMaterialAddButton() {
        if (!addFieldBtn) {
            return;
        }
        var visible = document.querySelectorAll(
            '#import-map-addon-catalog .import-map-addon-item:not(.d-none)'
        ).length;
        addFieldBtn.disabled = visible === 0;
    }

    function addFieldRow(target, label, options) {
        options = options || {};
        if (findRowByTarget(target)) {
            return findRowByTarget(target);
        }
        var section = sectionForTarget(target, options);
        var isPrimary = section === 'primary';
        var targetBody = sectionBody(section);
        if (!targetBody) {
            return null;
        }
        collectParseModes();
        var tr = document.createElement('tr');
        tr.className = 'import-map-row is-unmapped';
        tr.setAttribute('data-import-map-row', '');
        tr.setAttribute('data-field-target', target);
        tr.setAttribute('data-field-label', label);
        tr.setAttribute('data-is-primary', isPrimary ? '1' : '0');
        tr.setAttribute('data-map-section-kind', section);
        tr.setAttribute('data-is-required', required.indexOf(target) !== -1 ? '1' : '0');
        tr.tabIndex = 0;
        tr.setAttribute('role', 'option');
        tr.setAttribute('aria-selected', 'false');
        tr.setAttribute('aria-label', 'Поле ' + label);
        tr.innerHTML = ''
            + '<td class="import-map-row__file">'
            + '<div class="import-map-row__head">'
            + '<div class="import-map-row__title">' + escapeHtml(label) + '</div>'
            + '</div>'
            + '<div class="import-map-row__sample import-map-row__sample-live">—</div>'
            + '</td>'
            + '<td class="import-map-row__expr">'
            + '<span class="import-map-expr-slot is-empty" data-drop-slot draggable="false"'
            + ' title="Перетащите колонку сюда или выберите строку и кликните колонку справа">'
            + '<span class="import-map-expr-label"></span></span>'
            + '<input type="hidden" class="import-map-column-value" value="">'
            + '</td>'
            + '<td class="import-map-row__parse">'
            + '<select class="form-select form-select-sm import-map-parse" disabled aria-label="Тип поля для '
            + escapeAttr(label) + '">' + parseOptionsHtml('auto') + '</select>'
            + '</td>'
            + '<td class="import-map-row__actions">'
            + (isPrimary
                ? ''
                : '<button type="button" class="btn btn-link btn-sm text-danger import-map-remove-field p-0" title="Убрать поле">×</button>')
            + '</td>';
        var emptyEl = targetBody.querySelector('[data-map-section-empty]');
        if (emptyEl) {
            targetBody.insertBefore(tr, emptyEl);
        } else {
            targetBody.appendChild(tr);
        }
        if (targetBody.classList.contains('is-collapsed')) {
            targetBody.classList.remove('is-collapsed');
            var toggle = targetBody.querySelector('[data-map-section-toggle]');
            if (toggle) {
                toggle.setAttribute('aria-expanded', 'true');
            }
        }
        bindRow(tr);
        hideAddonItem(target);
        selectRow(tr);
        refreshState();
        return tr;
    }

    function addTagRow(columnIndex, label, sample) {
        var index = columnIndex == null || columnIndex === '' ? '' : String(columnIndex);
        if (!index) {
            return null;
        }
        var existing = rows().find(function (row) {
            return isTagRow(row) && row.getAttribute('data-column-index') === index;
        });
        if (existing) {
            selectRow(existing);
            return existing;
        }
        var targetBody = sectionBody('tag');
        if (!targetBody) {
            return null;
        }
        var tr = document.createElement('tr');
        tr.className = 'import-map-row is-unmapped';
        tr.setAttribute('data-import-map-row', '');
        tr.setAttribute('data-field-target', TARGET_TAG_PREFIX + index);
        tr.setAttribute('data-mapping-target', TARGET_TAGS);
        tr.setAttribute('data-field-label', label || columnLabel(index));
        tr.setAttribute('data-map-section-kind', 'tag');
        tr.setAttribute('data-is-primary', '0');
        tr.setAttribute('data-is-required', '0');
        tr.tabIndex = 0;
        tr.setAttribute('role', 'option');
        tr.setAttribute('aria-selected', 'false');
        tr.innerHTML = ''
            + '<td class="import-map-row__file">'
            + '<div class="import-map-row__head">'
            + '<div class="import-map-row__title">' + escapeHtml(label || columnLabel(index)) + '</div>'
            + '</div>'
            + '<div class="import-map-row__sample import-map-row__sample-live">—</div>'
            + '</td>'
            + '<td class="import-map-row__expr">'
            + '<span class="import-map-expr-slot is-empty" data-drop-slot draggable="false"'
            + ' title="Перетащите колонку сюда или выберите строку и кликните колонку справа">'
            + '<span class="import-map-expr-label"></span></span>'
            + '<input type="hidden" class="import-map-column-value" value="">'
            + '</td>'
            + '<td class="import-map-row__parse import-map-row__parse--tag">'
            + '<span class="text-muted" aria-hidden="true">—</span>'
            + '</td>'
            + '<td class="import-map-row__actions">'
            + '<button type="button" class="btn btn-link btn-sm text-danger import-map-remove-field p-0" title="Убрать тег">×</button>'
            + '</td>';
        var emptyEl = targetBody.querySelector('[data-map-section-empty]');
        if (emptyEl) {
            targetBody.insertBefore(tr, emptyEl);
        } else {
            targetBody.appendChild(tr);
        }
        if (targetBody.classList.contains('is-collapsed')) {
            targetBody.classList.remove('is-collapsed');
            var toggle = targetBody.querySelector('[data-map-section-toggle]');
            if (toggle) {
                toggle.setAttribute('aria-expanded', 'true');
            }
        }
        bindRow(tr);
        assignColumn(tr, index, label || columnLabel(index), sample || columnSample(index));
        selectRow(tr);
        refreshState();
        return tr;
    }

    function removeFieldRow(row) {
        if (!row || row.getAttribute('data-is-primary') === '1') {
            return;
        }
        var target = row.getAttribute('data-field-target');
        if (selectedRow === row) {
            selectedRow = null;
        }
        row.remove();
        if (target) {
            showAddonItem(target);
        }
        refreshState();
    }

    function bindCatalogItem(btn) {
        btn.addEventListener('click', function () {
            if (suppressNextClick) {
                suppressNextClick = false;
                return;
            }
            var index = btn.getAttribute('data-column-index');
            var owner = findRowByColumnIndex(index, { preferNonTag: true });
            if (owner && btn.classList.contains('is-locate-only')) {
                selectRow(owner);
                owner.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                return;
            }
            if (!selectedRow && rows().length) {
                selectRow(rows()[0]);
            }
            if (!selectedRow) {
                return;
            }
            if (isTagRow(selectedRow) && btn.classList.contains('is-used')) {
                if (!canAssignTagColumn(index, { ignoreTagRow: selectedRow })) {
                    return;
                }
                applyColumnToRow(
                    selectedRow,
                    index,
                    btn.getAttribute('data-label'),
                    btn.getAttribute('data-sample')
                );
                return;
            }
            applyColumnToRow(
                selectedRow,
                index,
                btn.getAttribute('data-label'),
                btn.getAttribute('data-sample')
            );
        });

        btn.addEventListener('dragstart', function (event) {
            if (btn.classList.contains('is-used')) {
                event.preventDefault();
                return;
            }
            writeDragPayload(event, {
                source: 'catalog',
                columnIndex: btn.getAttribute('data-column-index'),
                label: btn.getAttribute('data-label') || '',
                sample: btn.getAttribute('data-sample') || '—',
            });
            btn.classList.add('is-dragging');
        });

        btn.addEventListener('dragend', function () {
            endDrag(btn);
        });
    }

    function bindRow(row) {
        row.addEventListener('click', function (event) {
            if (event.target.closest('select, button, a, input, label')) {
                return;
            }
            selectRow(row);
        });
        row.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') {
                if (event.target.closest('select, input, button, a')) {
                    return;
                }
                event.preventDefault();
                selectRow(row);
            }
        });

        var parse = parseSelect(row);
        if (parse) {
            parse.addEventListener('change', function () {
                refreshState();
            });
            parse.addEventListener('focus', function () {
                selectRow(row);
            });
        }

        var removeBtn = row.querySelector('.import-map-remove-field');
        if (removeBtn) {
            removeBtn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                removeFieldRow(row);
            });
        }

        var slot = rowSlotEl(row);
        if (slot) {
            slot.addEventListener('dragstart', function (event) {
                if (!writeRowDragPayload(event, row)) {
                    return;
                }
                slot.classList.add('is-dragging');
            });
            slot.addEventListener('dragend', function () {
                endDrag(slot);
            });
        }

        var sampleDrag = row.querySelector('.import-map-row__sample');
        if (sampleDrag) {
            sampleDrag.addEventListener('dragstart', function (event) {
                if (!writeRowDragPayload(event, row)) {
                    return;
                }
                sampleDrag.classList.add('is-dragging');
            });
            sampleDrag.addEventListener('dragend', function () {
                endDrag(sampleDrag);
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
                if (!payload || payload.columnIndex == null || payload.columnIndex === '') {
                    return;
                }
                if (
                    payload.source === 'row'
                    && payload.fieldTarget === row.getAttribute('data-field-target')
                ) {
                    return;
                }
                event.preventDefault();
                var allowed = rowAllowsDrop(row, payload);
                event.dataTransfer.dropEffect = dropEffectFor(row, payload, allowed);
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
                if (!payload || payload.columnIndex == null || payload.columnIndex === '') {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                clearDropHover();
                dropPayloadOnRow(row, payload);
            });
        });
    }

    function bindTagSectionDrop() {
        if (!tbodyTag) {
            return;
        }
        tbodyTag.addEventListener('dragenter', function (event) {
            if (!readDragPayload(event) && !dragPayload) {
                return;
            }
            event.preventDefault();
        });
        tbodyTag.addEventListener('dragover', function (event) {
            var payload = readDragPayload(event);
            if (!payload || payload.columnIndex == null || payload.columnIndex === '') {
                return;
            }
            event.preventDefault();
            var allowed = canAssignTagColumn(payload.columnIndex, {
                ignoreTagRow: payload.source === 'row' && payload.fieldTarget
                    ? (function () {
                        var sourceRow = findRowByTarget(payload.fieldTarget);
                        return sourceRow && isTagRow(sourceRow) ? sourceRow : null;
                    })()
                    : null,
            });
            event.dataTransfer.dropEffect = allowed
                ? 'copy'
                : 'none';
            tbodyTag.classList.toggle('is-drop-hover', allowed);
            tbodyTag.classList.toggle('is-drop-blocked', !allowed);
        });
        tbodyTag.addEventListener('dragleave', function (event) {
            if (!tbodyTag.contains(event.relatedTarget)) {
                tbodyTag.classList.remove('is-drop-hover', 'is-drop-blocked');
            }
        });
        tbodyTag.addEventListener('drop', function (event) {
            var payload = readDragPayload(event);
            if (!payload || payload.columnIndex == null || payload.columnIndex === '') {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            clearDropHover();
            tbodyTag.classList.remove('is-drop-hover', 'is-drop-blocked');
            if (!canAssignTagColumn(payload.columnIndex)) {
                return;
            }
            var sourceRow = payload.source === 'row' && payload.fieldTarget
                ? findRowByTarget(payload.fieldTarget)
                : null;
            addTagRow(payload.columnIndex, payload.label, payload.sample);
            if (sourceRow && isTagRow(sourceRow) && sourceRow !== findRowByColumnIndex(payload.columnIndex, { tagOnly: true })) {
                removeFieldRow(sourceRow);
            }
        });
    }

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
            if (!selectedRow && rows().length) {
                selectRow(rows()[0]);
            }
            if (selectedRow) {
                clearRowExpression(selectedRow);
            }
        });
    }

    function isTypingTarget(target) {
        if (!target || target === document.body) {
            return false;
        }
        var tag = (target.tagName || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
            return true;
        }
        if (target.isContentEditable) {
            return true;
        }
        return false;
    }

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Delete' && event.key !== 'Backspace') {
            return;
        }
        if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) {
            return;
        }
        if (isTypingTarget(event.target)) {
            return;
        }
        if (!selectedRow || !form.contains(selectedRow)) {
            return;
        }
        event.preventDefault();
        clearRowExpression(selectedRow);
    });

    if (resetAllBtn) {
        resetAllBtn.addEventListener('click', function () {
            if (!window.confirm('Сбросить все сопоставления? Колонки будут сняты со всех полей.')) {
                return;
            }
            rows().slice().forEach(function (row) {
                if (isTagRow(row)) {
                    removeFieldRow(row);
                } else {
                    clearRowExpression(row);
                }
            });
        });
    }

    if (catalogSearch) {
        catalogSearch.addEventListener('input', function () {
            var needle = (catalogSearch.value || '').trim().toLowerCase();
            form.querySelectorAll('.import-map-catalog__item').forEach(function (item) {
                var label = item.getAttribute('data-catalog-label') || '';
                item.classList.toggle('d-none', !!(needle && label.indexOf(needle) === -1));
            });
            form.querySelectorAll('.import-map-catalog__group').forEach(function (group) {
                var visible = group.querySelectorAll('.import-map-catalog__item:not(.d-none)').length > 0;
                group.classList.toggle('d-none', !visible && !!needle);
            });
        });
    }

    document.querySelectorAll('.import-map-addon-item').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var target = btn.getAttribute('data-target');
            var label = btn.getAttribute('data-label') || target;
            addFieldRow(target, label, { section: 'material' });
            closeAddonMenu();
        });
    });

    if (addonSearch) {
        addonSearch.addEventListener('input', filterAddonCatalog);
        addonSearch.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeAddonMenu();
            }
        });
    }

    if (window.ReferencePropertiesPicker && window.ReferencePropertiesPicker.bind) {
        window.ReferencePropertiesPicker.bind({
            openButtonId: 'import-map-add-property',
            getUsedPropertyIds: function () {
                var used = new Set();
                rows().forEach(function (row) {
                    var target = row.getAttribute('data-field-target') || '';
                    if (target.indexOf(TARGET_PROPERTY_PREFIX) === 0) {
                        used.add(target.slice(TARGET_PROPERTY_PREFIX.length));
                    }
                });
                return used;
            },
            onConfirm: function (payloads) {
                payloads.forEach(function (payload) {
                    if (!payload || !payload.property_id) {
                        return;
                    }
                    var label = payload.label || payload.name || String(payload.property_id);
                    addFieldRow(
                        TARGET_PROPERTY_PREFIX + payload.property_id,
                        label,
                        { section: 'property' }
                    );
                });
            },
        });
    }

    form.addEventListener('submit', function () {
        syncHiddenInputs();
    });

    collectParseModes();
    bindSectionToggles();
    bindTagSectionDrop();
    catalogItems().forEach(bindCatalogItem);
    rows().forEach(bindRow);
    rows().forEach(function (row) {
        if (!isTagRow(row)) {
            hideAddonItem(row.getAttribute('data-field-target'));
        }
    });
    syncRequiredFromPolicy();
    if (rows().length) {
        selectRow(rows()[0]);
    }
    refreshState();
})();
