(function () {
    'use strict';

    var DATA_TYPE_LABELS = {
        number: 'Число',
        string: 'Строка',
        boolean: 'Да/Нет',
        date: 'Дата',
        material_link: 'Материал',
        choice: 'Выбор из списка',
    };

    var FIELD_TYPE_LABELS = {
        CharField: 'Строка',
        TextField: 'Текст',
        IntegerField: 'Целое число',
        DecimalField: 'Число',
        FloatField: 'Число',
        BooleanField: 'Да/Нет',
        DateField: 'Дата',
        DateTimeField: 'Дата и время',
        MaterialLink: 'Материал',
    };

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function normalizeReferenceProperties(parsed) {
        if (Array.isArray(parsed)) {
            return parsed;
        }
        if (typeof parsed === 'string') {
            if (!parsed.trim()) {
                return [];
            }
            try {
                var nested = JSON.parse(parsed);
                return normalizeReferenceProperties(nested);
            } catch (error) {
                return [];
            }
        }
        if (parsed && typeof parsed === 'object') {
            return Object.values(parsed);
        }
        return [];
    }

    function getReferenceProperties() {
        var node = document.getElementById('reference-properties-data');
        if (!node) {
            return [];
        }
        try {
            return normalizeReferenceProperties(JSON.parse(node.textContent));
        } catch (error) {
            return [];
        }
    }

    function defaultMetaLine(item) {
        var typeLabel = DATA_TYPE_LABELS[item.data_type] || item.data_type || '—';
        var unitPart = item.unit ? ' · ' + escapeHtml(item.unit) : '';
        return '<code>' + escapeHtml(item.name) + '</code> · ' + escapeHtml(typeLabel) + unitPart;
    }

    function renderList(options) {
        options = options || {};
        var filterText = options.filterText || '';
        var getUsedPropertyIds = options.getUsedPropertyIds || function () { return new Set(); };
        var getUsedColumnNames = options.getUsedColumnNames || function () { return new Set(); };
        var metaLine = options.metaLine || defaultMetaLine;

        var listNode = document.getElementById('reference-properties-list');
        var emptyNode = document.getElementById('reference-properties-empty');
        var addBtn = document.getElementById('reference-properties-add-btn');
        if (!listNode || !emptyNode || !addBtn) {
            return;
        }

        var query = filterText.trim().toLowerCase();
        var usedPropertyIds = getUsedPropertyIds();
        var usedColumnNames = getUsedColumnNames();
        var allProperties = getReferenceProperties();
        var properties = allProperties.filter(function (item) {
            if (!query) {
                return true;
            }
            var haystack = [
                item.label,
                item.name,
                item.group_name,
                item.unit,
                item.data_type,
            ].join(' ').toLowerCase();
            return haystack.indexOf(query) !== -1;
        });

        listNode.innerHTML = '';
        if (!allProperties.length) {
            emptyNode.classList.remove('d-none');
            addBtn.disabled = true;
            return;
        }
        emptyNode.classList.add('d-none');

        if (!properties.length) {
            listNode.innerHTML = '<p class="text-muted small mb-0">Ничего не найдено.</p>';
            addBtn.disabled = true;
            return;
        }

        var groups = new Map();
        properties.forEach(function (item) {
            var groupName = item.group_name || 'Без группы';
            if (!groups.has(groupName)) {
                groups.set(groupName, []);
            }
            groups.get(groupName).push(item);
        });

        groups.forEach(function (items, groupName) {
            var groupEl = document.createElement('div');
            groupEl.className = 'reference-properties-group';
            groupEl.innerHTML = '<div class="reference-properties-group__title">' + escapeHtml(groupName) + '</div>';

            items.forEach(function (item) {
                var isUsed = usedPropertyIds.has(item.property_id)
                    || usedColumnNames.has((item.name || '').toLowerCase());
                var itemEl = document.createElement('label');
                itemEl.className = 'reference-property-item' + (isUsed ? ' is-used' : '');
                itemEl.innerHTML = ''
                    + '<input type="checkbox" class="form-check-input mt-1 reference-property-checkbox"'
                    + ' value="' + escapeHtml(item.property_id) + '"' + (isUsed ? ' disabled' : '') + '>'
                    + '<span class="flex-grow-1">'
                    + '<span class="fw-semibold">' + escapeHtml(item.label) + '</span>'
                    + '<div class="reference-property-item__meta">'
                    + metaLine(item)
                    + (isUsed ? ' · уже добавлено' : '')
                    + '</div>'
                    + '</span>';
                groupEl.appendChild(itemEl);
            });

            listNode.appendChild(groupEl);
        });

        addBtn.disabled = true;
        listNode.querySelectorAll('.reference-property-checkbox').forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                var selected = listNode.querySelectorAll('.reference-property-checkbox:checked:not(:disabled)');
                addBtn.disabled = selected.length === 0;
            });
        });
    }

    function bind(options) {
        options = options || {};
        var openButtonId = options.openButtonId;
        var getUsedPropertyIds = options.getUsedPropertyIds;
        var getUsedColumnNames = options.getUsedColumnNames;
        var metaLine = options.metaLine;
        var onConfirm = options.onConfirm;

        if (!openButtonId || !getUsedPropertyIds || !onConfirm) {
            return null;
        }

        var openBtn = document.getElementById(openButtonId);
        var modalEl = document.getElementById('reference-properties-modal');
        var searchInput = document.getElementById('reference-properties-search');
        var addBtn = document.getElementById('reference-properties-add-btn');
        if (!openBtn || !modalEl || !searchInput || !addBtn || openBtn.dataset.referencePickerBound === 'true') {
            return null;
        }
        openBtn.dataset.referencePickerBound = 'true';

        function getModal() {
            if (!window.bootstrap || !window.bootstrap.Modal) {
                return null;
            }
            return window.bootstrap.Modal.getOrCreateInstance(modalEl);
        }

        function renderCurrentList(filterText) {
            renderList({
                filterText: filterText,
                getUsedPropertyIds: getUsedPropertyIds,
                getUsedColumnNames: getUsedColumnNames,
                metaLine: metaLine,
            });
        }

        openBtn.addEventListener('click', function () {
            searchInput.value = '';
            renderCurrentList('');
            var modal = getModal();
            if (modal) {
                modal.show();
            }
        });

        searchInput.addEventListener('input', function () {
            renderCurrentList(searchInput.value);
        });

        addBtn.addEventListener('click', function () {
            var selected = modalEl.querySelectorAll('.reference-property-checkbox:checked:not(:disabled)');
            var allProperties = getReferenceProperties();
            var byId = {};
            allProperties.forEach(function (item) {
                if (item && item.property_id) {
                    byId[item.property_id] = item;
                }
            });
            var payloads = [];
            selected.forEach(function (checkbox) {
                var item = byId[checkbox.value];
                if (item) {
                    payloads.push(item);
                }
            });
            if (payloads.length) {
                onConfirm(payloads);
            }
            var modal = getModal();
            if (modal) {
                modal.hide();
            }
        });

        return getModal();
    }

    window.ReferencePropertiesPicker = {
        DATA_TYPE_LABELS: DATA_TYPE_LABELS,
        FIELD_TYPE_LABELS: FIELD_TYPE_LABELS,
        escapeHtml: escapeHtml,
        getReferenceProperties: getReferenceProperties,
        renderList: renderList,
        bind: bind,
    };
})();
