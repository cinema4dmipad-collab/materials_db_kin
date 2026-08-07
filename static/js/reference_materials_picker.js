(function () {
    'use strict';

    var activeSelect = null;
    var activeOnSelect = null;
    var activeScope = 'workspace';

    var SCOPE_HINTS = {
        workspace: 'Материалы, созданные в текущем рабочем пространстве.',
        shared: 'Опубликованные материалы, доступные в этом пространстве — с общей видимостью или из других пространств.',
    };

    var SCOPE_EMPTY_MESSAGES = {
        workspace: 'В этом пространстве пока нет материалов. Создайте материал кнопкой «Создать».',
        shared: 'Нет опубликованных материалов, доступных в этом пространстве.',
    };

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function normalizeMaterials(parsed) {
        if (Array.isArray(parsed)) {
            return parsed;
        }
        if (typeof parsed === 'string') {
            if (!parsed.trim()) {
                return [];
            }
            try {
                return normalizeMaterials(JSON.parse(parsed));
            } catch (error) {
                return [];
            }
        }
        if (parsed && typeof parsed === 'object') {
            return Object.values(parsed);
        }
        return [];
    }

    function getMaterials() {
        var node = document.getElementById('reference-materials-data');
        if (!node) {
            return [];
        }
        try {
            return normalizeMaterials(JSON.parse(node.textContent));
        } catch (error) {
            return [];
        }
    }

    function getModal() {
        var modalEl = document.getElementById('reference-materials-modal');
        if (!modalEl || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return window.bootstrap.Modal.getOrCreateInstance(modalEl);
    }

    function materialScopes(item) {
        if (Array.isArray(item.scopes) && item.scopes.length) {
            return item.scopes;
        }
        return ['workspace', 'shared'];
    }

    function filterByScope(materials, scope) {
        return materials.filter(function (item) {
            return materialScopes(item).indexOf(scope) !== -1;
        });
    }

    function getActiveScope() {
        var activeTab = document.querySelector('#reference-materials-scope-tabs .nav-link.active');
        return activeTab ? activeTab.dataset.scope : activeScope;
    }

    function setActiveScope(scope) {
        activeScope = scope || 'workspace';
        var tabs = document.querySelectorAll('#reference-materials-scope-tabs .nav-link');
        tabs.forEach(function (tab) {
            var isActive = tab.dataset.scope === activeScope;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        var hintNode = document.getElementById('reference-materials-scope-hint');
        if (hintNode) {
            hintNode.textContent = SCOPE_HINTS[activeScope] || '';
        }

        var createBtn = document.querySelector('.reference-materials-create-btn');
        if (createBtn) {
            createBtn.classList.toggle('d-none', activeScope !== 'workspace');
        }
    }

    function guessScopeForMaterial(materialId) {
        var item = getMaterials().find(function (entry) {
            return entry.material_id === materialId;
        });
        if (!item) {
            return 'workspace';
        }
        var scopes = materialScopes(item);
        if (scopes.indexOf('workspace') !== -1) {
            return 'workspace';
        }
        return scopes[0] || 'workspace';
    }

    function renderList(filterText) {
        var listNode = document.getElementById('reference-materials-list');
        var emptyNode = document.getElementById('reference-materials-empty');
        var scopeEmptyNode = document.getElementById('reference-materials-scope-empty');
        var selectBtn = document.getElementById('reference-materials-select-btn');
        if (!listNode || !emptyNode || !selectBtn) {
            return;
        }

        var query = (filterText || '').trim().toLowerCase();
        var allMaterials = getMaterials();
        var scope = getActiveScope();
        var scopedMaterials = filterByScope(allMaterials, scope);
        var materials = scopedMaterials.filter(function (item) {
            if (!query) {
                return true;
            }
            var haystack = [
                item.label,
                item.code,
                item.name,
                item.struct_type_name,
            ].join(' ').toLowerCase();
            return haystack.indexOf(query) !== -1;
        });

        listNode.innerHTML = '';
        emptyNode.classList.add('d-none');
        if (scopeEmptyNode) {
            scopeEmptyNode.classList.add('d-none');
        }

        if (!allMaterials.length) {
            emptyNode.classList.remove('d-none');
            selectBtn.disabled = true;
            return;
        }

        if (!scopedMaterials.length) {
            if (scopeEmptyNode) {
                scopeEmptyNode.textContent = SCOPE_EMPTY_MESSAGES[scope] || 'Материалы не найдены.';
                scopeEmptyNode.classList.remove('d-none');
            }
            selectBtn.disabled = true;
            return;
        }

        if (!materials.length) {
            listNode.innerHTML = '<p class="text-muted small mb-0">Ничего не найдено.</p>';
            selectBtn.disabled = true;
            return;
        }

        var groups = new Map();
        materials.forEach(function (item) {
            var groupName = item.struct_type_name || 'Без типа';
            if (!groups.has(groupName)) {
                groups.set(groupName, []);
            }
            groups.get(groupName).push(item);
        });

        var selectedValue = activeSelect ? activeSelect.value : '';

        groups.forEach(function (items, groupName) {
            var groupEl = document.createElement('div');
            groupEl.className = 'reference-properties-group';
            groupEl.innerHTML = '<div class="reference-properties-group__title">' + escapeHtml(groupName) + '</div>';

            items.forEach(function (item) {
                var itemEl = document.createElement('label');
                itemEl.className = 'reference-property-item';
                var checked = selectedValue && selectedValue === item.material_id ? ' checked' : '';
                itemEl.innerHTML = ''
                    + '<input type="radio" class="form-check-input mt-1 reference-material-radio" name="reference-material-radio"'
                    + ' value="' + escapeHtml(item.material_id) + '"' + checked + '>'
                    + '<span class="flex-grow-1">'
                    + '<span class="fw-semibold">' + escapeHtml(item.label) + '</span>'
                    + '<div class="reference-property-item__meta">'
                    + '<code>' + escapeHtml(item.code) + '</code>'
                    + '</div>'
                    + '</span>';
                groupEl.appendChild(itemEl);
            });

            listNode.appendChild(groupEl);
        });

        selectBtn.disabled = !listNode.querySelector('.reference-material-radio:checked');
        listNode.querySelectorAll('.reference-material-radio').forEach(function (radio) {
            radio.addEventListener('change', function () {
                selectBtn.disabled = false;
            });
        });
    }

    function bindModalControls() {
        var modalEl = document.getElementById('reference-materials-modal');
        var searchInput = document.getElementById('reference-materials-search');
        var selectBtn = document.getElementById('reference-materials-select-btn');
        if (!modalEl || !searchInput || !selectBtn || modalEl.dataset.materialPickerBound === 'true') {
            return;
        }
        modalEl.dataset.materialPickerBound = 'true';

        document.querySelectorAll('#reference-materials-scope-tabs .nav-link').forEach(function (tab) {
            tab.addEventListener('click', function () {
                setActiveScope(tab.dataset.scope);
                renderList(searchInput.value);
            });
        });

        searchInput.addEventListener('input', function () {
            renderList(searchInput.value);
        });

        selectBtn.addEventListener('click', function () {
            var selected = modalEl.querySelector('.reference-material-radio:checked');
            if (activeOnSelect && selected) {
                activeOnSelect(selected.value);
                activeOnSelect = null;
                activeSelect = null;
                var modal = getModal();
                if (modal) {
                    modal.hide();
                }
                return;
            }
            if (activeSelect && selected) {
                activeSelect.value = selected.value;
                activeSelect.dispatchEvent(new Event('change', { bubbles: true }));
                if (window.MaterialPickerFields) {
                    window.MaterialPickerFields.syncSelect(activeSelect);
                }
            }
            var modal = getModal();
            if (modal) {
                modal.hide();
            }
        });
    }

    function openFor(select) {
        openWithOptions({ select: select });
    }

    function openWithOptions(options) {
        options = options || {};
        activeSelect = options.select || null;
        activeOnSelect = options.onSelect || null;
        var searchInput = document.getElementById('reference-materials-search');
        if (searchInput) {
            searchInput.value = '';
        }
        var scope = options.scope;
        if (!scope) {
            scope = activeSelect && activeSelect.value
                ? guessScopeForMaterial(activeSelect.value)
                : 'workspace';
        }
        setActiveScope(scope);
        renderList('');
        var modal = getModal();
        if (modal) {
            modal.show();
        }
    }

    window.ReferenceMaterialsPicker = {
        escapeHtml: escapeHtml,
        getMaterials: getMaterials,
        renderList: renderList,
        openFor: openFor,
        openWithOptions: openWithOptions,
        init: bindModalControls,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindModalControls);
    } else {
        bindModalControls();
    }
})();
