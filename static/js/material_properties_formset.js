(function () {
    'use strict';

    var PREFIX = 'properties';

    function reindexForms(container, totalFormsInput) {
        var rows = Array.from(container.querySelectorAll('.property-form-row'));
        rows.forEach(function (row, idx) {
            row.querySelectorAll('[name]').forEach(function (input) {
                input.name = input.name.replace(
                    new RegExp('^' + PREFIX + '-\\d+-'),
                    PREFIX + '-' + idx + '-',
                );
                if (input.id) {
                    input.id = input.id.replace(
                        new RegExp('^id_' + PREFIX + '-\\d+-'),
                        'id_' + PREFIX + '-' + idx + '-',
                    );
                }
            });
            row.querySelectorAll('label[for]').forEach(function (label) {
                var htmlFor = label.getAttribute('for');
                if (htmlFor) {
                    label.setAttribute(
                        'for',
                        htmlFor.replace(
                            new RegExp('^id_' + PREFIX + '-\\d+-'),
                            'id_' + PREFIX + '-' + idx + '-',
                        ),
                    );
                }
            });
        });
        totalFormsInput.value = String(rows.length);
    }

    function updateEmptyState(container) {
        var emptyRow = document.getElementById('material-form-properties-empty-row');
        if (!emptyRow) {
            return;
        }
        var hasRows = container.querySelectorAll('.property-form-row:not(.d-none)').length > 0;
        emptyRow.classList.toggle('d-none', hasRows);
    }

    function getUsedPropertyIds(container) {
        var ids = new Set();
        container.querySelectorAll('.property-form-row:not(.d-none) [name$="-property"]').forEach(function (select) {
            if (select.value) {
                ids.add(select.value);
            }
        });
        return ids;
    }

    function formatPropertyName(label, unit) {
        label = (label || '').trim();
        unit = (unit || '').trim();
        if (!label) {
            return '—';
        }
        if (unit && label.endsWith(', ' + unit)) {
            return label.slice(0, -(unit.length + 2)).trim() || label;
        }
        if (unit && label.endsWith(',' + unit)) {
            return label.slice(0, -(unit.length + 1)).trim() || label;
        }
        return label;
    }

    function setRowPropertyMeta(row, label, unit) {
        var labelCell = row.querySelector('.material-props-section__name');
        var unitCell = row.querySelector('.material-props-section__unit');
        if (labelCell) {
            labelCell.textContent = formatPropertyName(label, unit);
        }
        if (unitCell) {
            unitCell.textContent = (unit || '').trim();
        }
    }

    function materialPickerOptions() {
        if (!window.ReferenceMaterialsPicker || !window.ReferenceMaterialsPicker.getMaterials) {
            return [];
        }
        return window.ReferenceMaterialsPicker.getMaterials();
    }

    function ensureMaterialLinkValueField(row, selectedMaterialId) {
        var valueCell = row.querySelector('.material-props-section__value');
        if (!valueCell) {
            return;
        }
        var existing = valueCell.querySelector('[name$="-value"]');
        var fieldName = existing ? existing.name : '';
        var fieldId = existing ? existing.id : '';
        valueCell.innerHTML = '';
        var select = document.createElement('select');
        select.name = fieldName;
        if (fieldId) {
            select.id = fieldId;
        }
        select.className = 'form-select js-material-select material-picker-select';
        select.setAttribute('data-material-picker', 'true');
        var empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '---------';
        select.appendChild(empty);
        materialPickerOptions().forEach(function (item) {
            var option = document.createElement('option');
            option.value = item.material_id;
            option.textContent = item.label || (item.code + ' - ' + item.name);
            select.appendChild(option);
        });
        if (selectedMaterialId) {
            select.value = selectedMaterialId;
        }
        valueCell.appendChild(select);
        if (window.MaterialPickerFields && window.MaterialPickerFields.init) {
            window.MaterialPickerFields.init(valueCell);
        }
    }

    function ensureChoiceValueField(row, choices, selectedValue) {
        var valueCell = row.querySelector('.material-props-section__value');
        if (!valueCell) {
            return;
        }
        var existing = valueCell.querySelector('[name$="-value"]');
        var fieldName = existing ? existing.name : '';
        var fieldId = existing ? existing.id : '';
        valueCell.innerHTML = '';
        var select = document.createElement('select');
        select.name = fieldName;
        if (fieldId) {
            select.id = fieldId;
        }
        select.className = 'form-select';
        select.setAttribute('data-choice-picker', 'true');
        var empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '---------';
        select.appendChild(empty);
        (choices || []).forEach(function (item) {
            var option = document.createElement('option');
            option.value = item.value;
            option.textContent = item.label || item.value;
            select.appendChild(option);
        });
        if (selectedValue) {
            select.value = selectedValue;
        }
        valueCell.appendChild(select);
        if (window.ChoicePickerFields && window.ChoicePickerFields.init) {
            window.ChoicePickerFields.init(valueCell);
        }
    }

    function fillPropertyRow(row, payload) {
        var propertySelect = row.querySelector('[name$="-property"]');
        if (propertySelect) {
            if (
                payload.property_id
                && !propertySelect.querySelector('option[value="' + CSS.escape(payload.property_id) + '"]')
            ) {
                var option = document.createElement('option');
                option.value = payload.property_id;
                option.textContent = payload.label || payload.name || payload.property_id;
                propertySelect.appendChild(option);
            }
            propertySelect.value = payload.property_id;
        }
        setRowPropertyMeta(row, payload.label, payload.unit);
        if (payload.data_type === 'material_link') {
            ensureMaterialLinkValueField(row, payload.value || '');
            setRowPropertyMeta(row, payload.label, '');
        } else if (payload.data_type === 'choice') {
            ensureChoiceValueField(row, payload.choices || [], payload.value || '');
            setRowPropertyMeta(row, payload.label, '');
        } else if (payload.data_type === 'number') {
            if (window.PropertyNumberValue && window.PropertyNumberValue.initRow) {
                window.PropertyNumberValue.initRow(row);
            }
        }
    }

    function appendPropertyFromTemplate(container, template, totalFormsInput) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, formIndex);
        var wrapper = document.createElement('tbody');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = String(formIndex + 1);
        bindDeleteButton(container, row, totalFormsInput);
        updateEmptyState(container);
        if (window.PropertyNumberValue && window.PropertyNumberValue.initRow) {
            window.PropertyNumberValue.initRow(row);
        }
        return row;
    }

    function bindDeleteButton(container, row, totalFormsInput) {
        var deleteBtn = row.querySelector('.delete-property-btn');
        if (!deleteBtn || deleteBtn.dataset.bound === 'true') {
            return;
        }
        deleteBtn.dataset.bound = 'true';

        deleteBtn.addEventListener('click', function () {
            var idInput = row.querySelector('input[name$="-id"]');
            var deleteInput = row.querySelector('input[name$="-DELETE"]');

            if (idInput && idInput.value && deleteInput) {
                deleteInput.checked = true;
                row.classList.add('d-none');
            } else {
                row.remove();
                reindexForms(container, totalFormsInput);
            }
            updateEmptyState(container);
        });
    }

    function findPropertyPayload(propertyId) {
        if (!propertyId || !window.ReferencePropertiesPicker) {
            return null;
        }
        var properties = window.ReferencePropertiesPicker.getReferenceProperties();
        for (var i = 0; i < properties.length; i += 1) {
            if (properties[i].property_id === propertyId) {
                return properties[i];
            }
        }
        return null;
    }

    function getCreatedPropertyIdFromUrl() {
        return new URLSearchParams(window.location.search).get('created_property') || '';
    }

    function cleanupReturnParams() {
        var url = new URL(window.location.href);
        var changed = false;
        ['created_property', 'open_properties'].forEach(function (param) {
            if (url.searchParams.has(param)) {
                url.searchParams.delete(param);
                changed = true;
            }
        });
        if (changed) {
            window.history.replaceState({}, '', url.pathname + url.search + url.hash);
        }
    }

    function focusPropertyValue(row) {
        var valueInput = row.querySelector('[name$="-value"]');
        if (valueInput) {
            valueInput.focus();
        }
    }

    function scrollToPropertiesSection(row) {
        var target = row || document.getElementById('add-property-btn');
        if (target && target.scrollIntoView) {
            target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    function addCreatedPropertyFromUrl(container, template, totalFormsInput) {
        var propertyId = getCreatedPropertyIdFromUrl();
        if (!propertyId) {
            return;
        }
        cleanupReturnParams();

        if (getUsedPropertyIds(container).has(propertyId)) {
            return;
        }

        var payload = findPropertyPayload(propertyId);
        if (!payload) {
            return;
        }

        var row = appendPropertyFromTemplate(container, template, totalFormsInput);
        fillPropertyRow(row, payload);
        scrollToPropertiesSection(row);
        focusPropertyValue(row);
    }

    function entryMapForIndex(entries, index) {
        var prefix = PREFIX + '-' + index + '-';
        var map = {};
        entries.forEach(function (entry) {
            if (!entry || !entry.name || entry.name.indexOf(prefix) !== 0) {
                return;
            }
            map[entry.name.slice(prefix.length)] = entry.value;
        });
        return map;
    }

    function collectDraftIndices(entries) {
        var indices = new Set();
        entries.forEach(function (entry) {
            if (!entry || !entry.name) {
                return;
            }
            var match = entry.name.match(/^properties-(\d+)-/);
            if (match) {
                indices.add(parseInt(match[1], 10));
            }
        });
        return Array.from(indices).sort(function (a, b) {
            return a - b;
        });
    }

    function rebuildFromDraftEntries(entries) {
        var container = document.getElementById('property-forms-container');
        var template = document.getElementById('empty-property-form-template');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');
        if (!container || !template || !totalFormsInput || !Array.isArray(entries)) {
            return false;
        }

        container.querySelectorAll('.property-form-row').forEach(function (row) {
            row.remove();
        });
        totalFormsInput.value = '0';

        var restored = 0;
        var initialCount = 0;
        collectDraftIndices(entries).forEach(function (index) {
            var fields = entryMapForIndex(entries, index);
            var propertyId = fields.property || '';
            var isDeleted = fields.DELETE === 'on'
                || fields.DELETE === 'true'
                || fields.DELETE === '1';
            if (!propertyId && !fields.id) {
                return;
            }
            // Skip brand-new rows that were already deleted in the UI.
            if (isDeleted && !fields.id) {
                return;
            }

            var row = appendPropertyFromTemplate(container, template, totalFormsInput);
            var payload = findPropertyPayload(propertyId) || {
                property_id: propertyId,
                label: fields.property || propertyId,
                unit: '',
                data_type: '',
                choices: [],
            };
            payload = Object.assign({}, payload, {
                property_id: propertyId || payload.property_id,
                value: fields.value || '',
            });
            fillPropertyRow(row, payload);

            var idInput = row.querySelector('input[name$="-id"]');
            if (idInput && fields.id) {
                idInput.value = fields.id;
                initialCount += 1;
            }
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (isDeleted && deleteInput) {
                deleteInput.checked = true;
                row.classList.add('d-none');
            }
            var valueInput = row.querySelector('[name$="-value"]');
            if (valueInput && fields.value != null && !isDeleted) {
                valueInput.value = fields.value;
                if (window.ChoicePickerFields && window.ChoicePickerFields.syncSelect) {
                    window.ChoicePickerFields.syncSelect(valueInput);
                }
                if (window.MaterialPickerFields && window.MaterialPickerFields.syncSelect) {
                    window.MaterialPickerFields.syncSelect(valueInput);
                }
            }
            restored += 1;
        });

        var initialFormsInput = document.getElementById('id_properties-INITIAL_FORMS');
        if (initialFormsInput) {
            initialFormsInput.value = String(initialCount);
        }
        updateEmptyState(container);
        return restored > 0;
    }

    function enhanceExistingPropertyRows(container) {
        container.querySelectorAll('.property-form-row').forEach(function (row) {
            var propertySelect = row.querySelector('[name$="-property"]');
            if (!propertySelect || !propertySelect.value) {
                return;
            }
            var payload = findPropertyPayload(propertySelect.value);
            if (!payload) {
                return;
            }
            setRowPropertyMeta(row, payload.label, payload.unit);
            if (payload.data_type === 'choice') {
                var valueInput = row.querySelector('[name$="-value"]');
                var needsChoiceSelect = !valueInput
                    || valueInput.tagName !== 'SELECT'
                    || valueInput.options.length <= 1;
                if (needsChoiceSelect) {
                    ensureChoiceValueField(
                        row,
                        payload.choices || [],
                        valueInput ? valueInput.value : '',
                    );
                }
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('property-forms-container');
        var template = document.getElementById('empty-property-form-template');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');
        var picker = window.ReferencePropertiesPicker;

        if (!container || !template || !totalFormsInput || !picker) {
            return;
        }

        var form = container.closest('form');
        if (form && window.MaterialFormDraft && window.MaterialFormDraft.restore) {
            window.MaterialFormDraft.restore(form);
        }

        container.querySelectorAll('.property-form-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput);
            if (window.MaterialPickerFields && window.MaterialPickerFields.init) {
                window.MaterialPickerFields.init(row);
            }
            if (window.ChoicePickerFields && window.ChoicePickerFields.init) {
                window.ChoicePickerFields.init(row);
            }
        });

        picker.bind({
            openButtonId: 'add-property-btn',
            getUsedPropertyIds: function () {
                return getUsedPropertyIds(container);
            },
            onConfirm: function (payloads) {
                payloads.forEach(function (payload) {
                    var row = appendPropertyFromTemplate(container, template, totalFormsInput);
                    fillPropertyRow(row, payload);
                });
            },
        });

        if (form) {
            form.addEventListener('submit', function () {
                var rows = container.querySelectorAll('.property-form-row');
                totalFormsInput.value = String(rows.length);
            });
        }

        updateEmptyState(container);
        addCreatedPropertyFromUrl(container, template, totalFormsInput);
        enhanceExistingPropertyRows(container);
    });

    window.MaterialPropertiesFormset = {
        rebuildFromDraftEntries: rebuildFromDraftEntries,
    };
})();
