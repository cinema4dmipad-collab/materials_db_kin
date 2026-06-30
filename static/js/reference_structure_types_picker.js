(function () {
    'use strict';

    var activeSelect = null;
    var EMPTY_VALUE = '__none__';

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function normalizeStructureTypes(parsed) {
        if (Array.isArray(parsed)) {
            return parsed;
        }
        if (typeof parsed === 'string') {
            if (!parsed.trim()) {
                return [];
            }
            try {
                return normalizeStructureTypes(JSON.parse(parsed));
            } catch (error) {
                return [];
            }
        }
        if (parsed && typeof parsed === 'object') {
            return Object.values(parsed);
        }
        return [];
    }

    function getStructureTypes() {
        var node = document.getElementById('reference-structure-types-data');
        if (!node) {
            return [];
        }
        try {
            return normalizeStructureTypes(JSON.parse(node.textContent));
        } catch (error) {
            return [];
        }
    }

    function getModal() {
        var modalEl = document.getElementById('reference-structure-types-modal');
        if (!modalEl || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return window.bootstrap.Modal.getOrCreateInstance(modalEl);
    }

    function selectedRadioValue() {
        if (!activeSelect) {
            return EMPTY_VALUE;
        }
        return activeSelect.value || EMPTY_VALUE;
    }

    function metaLine(item) {
        var status = item.is_created ? 'БД готова' : 'Таблица не создана';
        var fieldsPart = item.field_count ? item.field_count + ' пол.' : '0 пол.';
        var codePart = item.code ? '<code>' + escapeHtml(item.code) + '</code> · ' : '';
        return codePart + escapeHtml(fieldsPart) + ' · ' + escapeHtml(status);
    }

    function renderEmptyOption(selectedValue) {
        var emptyItem = document.createElement('label');
        emptyItem.className = 'reference-property-item';
        var emptyChecked = selectedValue === EMPTY_VALUE ? ' checked' : '';
        emptyItem.innerHTML = ''
            + '<input type="radio" class="form-check-input mt-1 reference-structure-type-radio" name="reference-structure-type-radio"'
            + ' value="' + EMPTY_VALUE + '"' + emptyChecked + '>'
            + '<span class="flex-grow-1">'
            + '<span class="fw-semibold">Без типа структуры</span>'
            + '<div class="reference-property-item__meta">Параметры структуры не задаются</div>'
            + '</span>';
        return emptyItem;
    }

    function renderList(filterText) {
        var listNode = document.getElementById('reference-structure-types-list');
        var emptyNode = document.getElementById('reference-structure-types-empty');
        var selectBtn = document.getElementById('reference-structure-types-select-btn');
        if (!listNode || !emptyNode || !selectBtn) {
            return;
        }

        var query = (filterText || '').trim().toLowerCase();
        var allTypes = getStructureTypes();
        var structureTypes = allTypes.filter(function (item) {
            if (!query) {
                return true;
            }
            var haystack = [
                item.label,
                item.name,
                item.code,
                item.description,
            ].join(' ').toLowerCase();
            return haystack.indexOf(query) !== -1;
        });

        listNode.innerHTML = '';
        emptyNode.classList.toggle('d-none', allTypes.length > 0);

        var selectedValue = selectedRadioValue();
        var groupEl = document.createElement('div');
        groupEl.className = 'reference-properties-group';
        groupEl.appendChild(renderEmptyOption(selectedValue));

        structureTypes.forEach(function (item) {
            var itemEl = document.createElement('label');
            itemEl.className = 'reference-property-item' + (item.is_created ? '' : ' is-used');
            var checked = selectedValue === item.structure_type_id ? ' checked' : '';
            var description = item.description
                ? '<div class="reference-property-item__meta">' + escapeHtml(item.description) + '</div>'
                : '';
            itemEl.innerHTML = ''
                + '<input type="radio" class="form-check-input mt-1 reference-structure-type-radio" name="reference-structure-type-radio"'
                + ' value="' + escapeHtml(item.structure_type_id) + '"' + checked + '>'
                + '<span class="flex-grow-1">'
                + '<span class="fw-semibold">' + escapeHtml(item.label) + '</span>'
                + '<div class="reference-property-item__meta">' + metaLine(item) + '</div>'
                + description
                + '</span>';
            groupEl.appendChild(itemEl);
        });

        listNode.appendChild(groupEl);

        if (allTypes.length && !structureTypes.length) {
            var notFound = document.createElement('p');
            notFound.className = 'text-muted small mb-0 mt-2';
            notFound.textContent = 'Ничего не найдено.';
            listNode.appendChild(notFound);
        }

        selectBtn.disabled = false;
    }

    function bindModalControls() {
        var modalEl = document.getElementById('reference-structure-types-modal');
        var searchInput = document.getElementById('reference-structure-types-search');
        var selectBtn = document.getElementById('reference-structure-types-select-btn');
        if (!modalEl || !searchInput || !selectBtn || modalEl.dataset.structureTypePickerBound === 'true') {
            return;
        }
        modalEl.dataset.structureTypePickerBound = 'true';

        searchInput.addEventListener('input', function () {
            renderList(searchInput.value);
        });

        selectBtn.addEventListener('click', function () {
            var selected = modalEl.querySelector('.reference-structure-type-radio:checked');
            if (activeSelect && selected) {
                activeSelect.value = selected.value === EMPTY_VALUE ? '' : selected.value;
                activeSelect.dispatchEvent(new Event('change', { bubbles: true }));
                if (window.StructureTypePickerFields) {
                    window.StructureTypePickerFields.syncSelect(activeSelect);
                }
            }
            var modal = getModal();
            if (modal) {
                modal.hide();
            }
        });
    }

    function openFor(select) {
        if (!select) {
            return;
        }
        activeSelect = select;
        var searchInput = document.getElementById('reference-structure-types-search');
        if (searchInput) {
            searchInput.value = '';
        }
        renderList('');
        var modal = getModal();
        if (modal) {
            modal.show();
        }
    }

    window.ReferenceStructureTypesPicker = {
        openFor: openFor,
        init: bindModalControls,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindModalControls);
    } else {
        bindModalControls();
    }
})();
