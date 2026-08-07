(function () {
    'use strict';

    var DRAFT_STORAGE_KEY = 'material-form-draft';

    function shouldAllowEnterSubmit(event) {
        var target = event.target;
        if (!target) {
            return false;
        }
        if (target.tagName === 'TEXTAREA') {
            return true;
        }
        if (target.type === 'submit') {
            return true;
        }
        return target.tagName === 'BUTTON' && target.type === 'submit';
    }

    function bindEnterGuard(form) {
        form.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' || event.defaultPrevented) {
                return;
            }
            if (shouldAllowEnterSubmit(event)) {
                return;
            }
            event.preventDefault();
        });
    }

    function bindStructureTypeApply(form) {
        var structureSelect = document.getElementById('id_struct_type');
        var flag = document.getElementById('apply-struct-type-flag');
        if (!structureSelect || !flag) {
            return;
        }

        structureSelect.addEventListener('change', function () {
            flag.value = '1';
            form.requestSubmit();
        });
    }

    function bindVisibilityFields(form) {
        var modeSelect = document.getElementById('id_visibility_mode');
        var publishedGroup = document.getElementById('published-workspaces-group');
        if (!modeSelect || !publishedGroup) {
            return;
        }

        function syncPublishedVisibility() {
            publishedGroup.hidden = modeSelect.value !== 'selected_workspaces';
        }

        modeSelect.addEventListener('change', syncPublishedVisibility);
        syncPublishedVisibility();
    }

    function isTemplateField(element) {
        return Boolean(
            element.closest('#empty-property-form-template')
            || element.closest('#empty-layer-form-template')
            || element.closest('template')
        );
    }

    function collectFormEntries(form) {
        var entries = [];
        form.querySelectorAll('input, select, textarea').forEach(function (element) {
            if (!element.name || element.type === 'submit' || element.type === 'button') {
                return;
            }
            if (isTemplateField(element)) {
                return;
            }
            if (element.type === 'checkbox') {
                if (element.checked) {
                    entries.push({ name: element.name, value: element.value || 'on' });
                }
            } else if (element.type === 'radio') {
                if (element.checked) {
                    entries.push({ name: element.name, value: element.value });
                }
            } else if (element.tagName === 'SELECT' && element.multiple) {
                Array.from(element.selectedOptions || []).forEach(function (option) {
                    entries.push({ name: element.name, value: option.value });
                });
            } else {
                entries.push({ name: element.name, value: element.value });
            }
        });
        return entries;
    }

    function applyEntryToForm(form, name, value) {
        var elements = form.querySelectorAll('[name="' + CSS.escape(name) + '"]');
        if (!elements.length) {
            return;
        }
        var first = elements[0];
        if (first.type === 'checkbox') {
            first.checked = value === 'on' || value === 'true' || value === '1';
            return;
        }
        if (first.type === 'radio') {
            elements.forEach(function (radio) {
                radio.checked = radio.value === value;
            });
            return;
        }
        if (first.multiple && first.tagName === 'SELECT') {
            var selected = Array.isArray(value) ? value : [value];
            Array.from(first.options).forEach(function (option) {
                option.selected = selected.indexOf(option.value) !== -1;
            });
            return;
        }
        first.value = value;
    }

    function clearFormDraft() {
        sessionStorage.removeItem(DRAFT_STORAGE_KEY);
    }

    function saveFormDraft(form) {
        if (!form) {
            return;
        }
        sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({
            path: window.location.pathname,
            entries: collectFormEntries(form),
        }));
    }

    function readFormDraft() {
        var raw = sessionStorage.getItem(DRAFT_STORAGE_KEY);
        if (!raw) {
            return null;
        }
        try {
            var draft = JSON.parse(raw);
            if (!draft || !Array.isArray(draft.entries)) {
                clearFormDraft();
                return null;
            }
            if (draft.path && draft.path !== window.location.pathname) {
                return null;
            }
            return draft;
        } catch (error) {
            clearFormDraft();
            return null;
        }
    }

    function isPropertiesEntry(name) {
        return /^properties-\d+-/.test(name) || name.indexOf('properties-') === 0;
    }

    function isLayersEntry(name) {
        return /^layers-\d+-/.test(name) || name.indexOf('layers-') === 0;
    }

    function applyMainDraftEntries(form, entries) {
        var byName = {};
        entries.forEach(function (entry) {
            if (!entry || !entry.name) {
                return;
            }
            if (isPropertiesEntry(entry.name) || isLayersEntry(entry.name)) {
                return;
            }
            if (Object.prototype.hasOwnProperty.call(byName, entry.name)) {
                if (!Array.isArray(byName[entry.name])) {
                    byName[entry.name] = [byName[entry.name]];
                }
                byName[entry.name].push(entry.value);
            } else {
                byName[entry.name] = entry.value;
            }
        });
        Object.keys(byName).forEach(function (name) {
            applyEntryToForm(form, name, byName[name]);
        });
    }

    function restoreFormDraft(form) {
        var draft = readFormDraft();
        if (!draft || !form) {
            return false;
        }
        applyMainDraftEntries(form, draft.entries);
        if (window.MaterialPropertiesFormset && window.MaterialPropertiesFormset.rebuildFromDraftEntries) {
            window.MaterialPropertiesFormset.rebuildFromDraftEntries(draft.entries);
        }
        clearFormDraft();
        return true;
    }

    function bindCreatePropertyLink(form) {
        var link = document.getElementById('create-reference-property-btn');
        if (!link || link.dataset.boundDraft === 'true') {
            return;
        }
        link.dataset.boundDraft = 'true';
        link.addEventListener('click', function () {
            saveFormDraft(form);
            var createUrl = new URL(link.href, window.location.origin);
            var returnUrl = new URL(window.location.href);
            returnUrl.searchParams.delete('open_properties');
            returnUrl.searchParams.delete('created_property');
            createUrl.searchParams.set('next', returnUrl.pathname + returnUrl.search);
            link.href = createUrl.toString();
        });
    }

    function bindFormSubmitClearDraft(form) {
        if (form.dataset.boundDraftClear === 'true') {
            return;
        }
        form.dataset.boundDraftClear = 'true';
        form.addEventListener('submit', clearFormDraft);
    }

    window.MaterialFormDraft = {
        save: saveFormDraft,
        restore: restoreFormDraft,
        clear: clearFormDraft,
        read: readFormDraft,
    };

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('material-form');
        if (!form) {
            return;
        }
        bindEnterGuard(form);
        bindStructureTypeApply(form);
        bindVisibilityFields(form);
        bindCreatePropertyLink(form);
        bindFormSubmitClearDraft(form);
    });
})();
