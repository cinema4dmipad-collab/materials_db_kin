(function () {
    'use strict';

    var PREFIX = 'properties';
    var materialPropertyIds = new Set();

    function getMaterialContainer() {
        return document.getElementById('material-property-forms-container');
    }

    function getExtraContainer() {
        return document.getElementById('extra-property-forms-container');
    }

    function getDeletedContainer() {
        return document.getElementById('deleted-property-forms-container');
    }

    function getAllRows() {
        var rows = [];
        var materialContainer = getMaterialContainer();
        var extraContainer = getExtraContainer();
        var deletedContainer = getDeletedContainer();
        if (materialContainer) {
            rows = rows.concat(Array.from(materialContainer.querySelectorAll('.property-form-row')));
        }
        if (extraContainer) {
            rows = rows.concat(Array.from(extraContainer.querySelectorAll('.property-form-row')));
        }
        if (deletedContainer) {
            rows = rows.concat(Array.from(deletedContainer.querySelectorAll('.property-form-row')));
        }
        return rows;
    }

    function reindexForms(totalFormsInput) {
        getAllRows().forEach(function (row, idx) {
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
        totalFormsInput.value = String(getAllRows().length);
    }

    function getUsedPropertyIds() {
        var ids = new Set();
        getAllRows().forEach(function (row) {
            if (row.classList.contains('d-none')) {
                return;
            }
            var select = row.querySelector('[name$="-property"]');
            if (select && select.value) {
                ids.add(select.value);
            }
        });
        materialPropertyIds.forEach(function (propertyId) {
            ids.add(propertyId);
        });
        return ids;
    }

    function collectExistingValues() {
        var values = {};
        getAllRows().forEach(function (row) {
            if (row.classList.contains('d-none')) {
                return;
            }
            var select = row.querySelector('[name$="-property"]');
            var valueInput = row.querySelector('[name$="-value"]');
            if (select && select.value && valueInput) {
                values[select.value] = valueInput.value;
            }
        });
        return values;
    }

    function updateMaterialEmptyState() {
        var emptyRow = document.getElementById('material-properties-empty-row');
        var materialContainer = getMaterialContainer();
        if (!emptyRow || !materialContainer) {
            return;
        }
        var hasRows = materialContainer.querySelectorAll('.property-form-row:not(.d-none)').length > 0;
        emptyRow.classList.toggle('d-none', hasRows);
    }

    function updateExtraEmptyState() {
        var emptyRow = document.getElementById('extra-properties-empty-row');
        var extraContainer = getExtraContainer();
        if (!emptyRow || !extraContainer) {
            return;
        }
        var hasRows = extraContainer.querySelectorAll('.property-form-row:not(.d-none)').length > 0;
        emptyRow.classList.toggle('d-none', hasRows);
    }

    function bindDeleteButton(row, totalFormsInput) {
        var deleteBtn = row.querySelector('.delete-property-btn');
        if (!deleteBtn || deleteBtn.dataset.bound === 'true') {
            return;
        }
        deleteBtn.dataset.bound = 'true';

        deleteBtn.addEventListener('click', function () {
            removeRowOrMarkDeleted(row);
            reindexForms(totalFormsInput);
            updateExtraEmptyState();
        });
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

    function fillPropertyRow(row, propertyId, value, label, unit) {
        var propertySelect = row.querySelector('[name$="-property"]');
        var valueInput = row.querySelector('[name$="-value"]');
        if (propertySelect) {
            propertySelect.value = propertyId;
        }
        if (valueInput) {
            valueInput.value = value || '';
        }
        setRowPropertyMeta(row, label, unit);
    }

    function appendRowFromTemplate(container, template, totalFormsInput) {
        var formIndex = getAllRows().length;
        var html = template.innerHTML.replace(/__prefix__/g, String(formIndex));
        var wrapper = document.createElement('tbody');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        reindexForms(totalFormsInput);
        return row;
    }

    function removeRowOrMarkDeleted(row) {
        var deletedContainer = getDeletedContainer();
        var idInput = row.querySelector('input[name$="-id"]');
        var deleteInput = row.querySelector('input[name$="-DELETE"]');
        if (idInput && idInput.value && deleteInput && deletedContainer) {
            deleteInput.checked = true;
            row.classList.add('d-none');
            deletedContainer.appendChild(row);
            return;
        }
        row.remove();
    }

    function clearContainer(container) {
        container.querySelectorAll('.property-form-row').forEach(function (row) {
            removeRowOrMarkDeleted(row);
        });
    }

    function removeExtraDuplicates() {
        var extraContainer = getExtraContainer();
        if (!extraContainer) {
            return;
        }
        extraContainer.querySelectorAll('.property-form-row').forEach(function (row) {
            var select = row.querySelector('[name$="-property"]');
            if (select && materialPropertyIds.has(select.value)) {
                removeRowOrMarkDeleted(row);
            }
        });
    }

    function fetchMaterialProperties(materialId, propertiesUrlTemplate) {
        if (!materialId) {
            materialPropertyIds = new Set();
            return Promise.resolve({
                properties: [],
                structure_properties: [],
                structure_message: '',
                structure_type: null,
            });
        }

        var url = propertiesUrlTemplate.replace('00000000-0000-0000-0000-000000000000', materialId);
        return fetch(url, {
            headers: {
                Accept: 'application/json',
            },
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Failed to load material properties');
                }
                return response.json();
            })
            .then(function (data) {
                var properties = data.properties || [];
                materialPropertyIds = new Set(properties.map(function (item) {
                    return item.property_id;
                }));
                return data;
            })
            .catch(function () {
                materialPropertyIds = new Set();
                return {
                    properties: [],
                    structure_properties: [],
                    structure_message: '',
                    structure_type: null,
                };
            });
    }

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function buildStructurePropertyValueCell(prop, materialDetailUrlTemplate) {
        if (prop.field_type === 'MaterialLink' && prop.value && materialDetailUrlTemplate) {
            var detailUrl = materialDetailUrlTemplate.replace(
                '00000000-0000-0000-0000-000000000000',
                prop.value,
            );
            return '<a href="' + escapeHtml(detailUrl) + '">' + escapeHtml(prop.display_value || prop.value) + '</a>';
        }
        return escapeHtml(prop.display_value || '—');
    }

    function renderStructurePropertiesSection(data, materialDetailUrlTemplate) {
        var section = document.getElementById('sample-structure-properties-section');
        if (section) {
            section.remove();
        }

        var properties = data.structure_properties || [];
        var message = data.structure_message || '';
        if (!properties.length && !message) {
            return;
        }

        var materialContainer = getMaterialContainer();
        if (!materialContainer) {
            return;
        }

        var table = materialContainer.closest('table');
        if (!table) {
            return;
        }

        var tbody = document.createElement('tbody');
        tbody.className = 'material-props-section';
        tbody.id = 'sample-structure-properties-section';

        var rowsHtml = '<tr class="material-props-section__header">'
            + '<th scope="colgroup" colspan="3">Из параметров структуры</th>'
            + '</tr>';

        if (properties.length) {
            properties.forEach(function (prop) {
                rowsHtml += '<tr class="structure-property-row">'
                    + '<th scope="row" class="material-props-section__name">' + escapeHtml(prop.label || prop.name || '—') + '</th>'
                    + '<td class="material-props-section__value">' + buildStructurePropertyValueCell(prop, materialDetailUrlTemplate) + '</td>'
                    + '<td class="material-props-section__unit">' + escapeHtml(prop.unit || '') + '</td>'
                    + '</tr>';
            });
        } else {
            rowsHtml += '<tr class="material-props-section__empty structure-properties-empty-row">'
                + '<td colspan="3">' + escapeHtml(message) + '</td>'
                + '</tr>';
        }

        tbody.innerHTML = rowsHtml;
        table.insertBefore(tbody, table.querySelector('tbody'));
    }

    function loadMaterialProperties(materialId, materialTemplate, totalFormsInput, propertiesUrlTemplate, materialDetailUrlTemplate) {
        var materialContainer = getMaterialContainer();
        if (!materialContainer || !materialTemplate) {
            return Promise.resolve();
        }

        var existingValues = collectExistingValues();

        return fetchMaterialProperties(materialId, propertiesUrlTemplate).then(function (data) {
            renderStructurePropertiesSection(data, materialDetailUrlTemplate);
            var properties = data.properties || [];
            clearContainer(materialContainer);

            if (!materialId) {
                reindexForms(totalFormsInput);
                removeExtraDuplicates();
                reindexForms(totalFormsInput);
                updateMaterialEmptyState();
                updateExtraEmptyState();
                return;
            }

            properties.forEach(function (item) {
                var row = appendRowFromTemplate(materialContainer, materialTemplate, totalFormsInput);
                var sampleValue = existingValues[item.property_id];
                fillPropertyRow(
                    row,
                    item.property_id,
                    sampleValue !== undefined ? sampleValue : item.value,
                    item.display_name,
                    item.unit,
                );
            });

            removeExtraDuplicates();
            reindexForms(totalFormsInput);
            updateMaterialEmptyState();
            updateExtraEmptyState();
        });
    }

    function initSamplePropertiesFormset() {
        var materialContainer = getMaterialContainer();
        var extraContainer = getExtraContainer();
        var materialTemplate = document.getElementById('empty-material-property-form-template');
        var extraTemplate = document.getElementById('empty-extra-property-form-template');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');
        var materialSelect = document.getElementById('id_material')
            || document.querySelector('[data-sample-material-select]');
        var form = materialContainer ? materialContainer.closest('form') : null;
        var picker = window.ReferencePropertiesPicker;

        if (!materialContainer || !extraContainer || !materialTemplate || !extraTemplate
            || !totalFormsInput || !form || !picker) {
            return;
        }

        var propertiesUrlTemplate = form.getAttribute('data-material-properties-url');
        var materialDetailUrlTemplate = form.getAttribute('data-material-detail-url');

        getAllRows().forEach(function (row) {
            if (row.classList.contains('property-form-row--extra')) {
                bindDeleteButton(row, totalFormsInput);
            }
        });

        picker.bind({
            openButtonId: 'add-extra-property-btn',
            getUsedPropertyIds: getUsedPropertyIds,
            onConfirm: function (payloads) {
                payloads.forEach(function (payload) {
                    if (materialPropertyIds.has(payload.property_id)) {
                        return;
                    }
                    var row = appendRowFromTemplate(extraContainer, extraTemplate, totalFormsInput);
                    fillPropertyRow(
                        row,
                        payload.property_id,
                        '',
                        payload.label,
                        payload.unit,
                    );
                    bindDeleteButton(row, totalFormsInput);
                });
                reindexForms(totalFormsInput);
                updateExtraEmptyState();
            },
        });

        form.addEventListener('submit', function () {
            reindexForms(totalFormsInput);
        });

        updateMaterialEmptyState();
        updateExtraEmptyState();
        reindexForms(totalFormsInput);

        if (!materialSelect) {
            return;
        }

        var initialMaterialId = materialSelect.value;
        var hasMaterialRows = materialContainer.querySelector('.property-form-row') !== null;

        materialSelect.addEventListener('change', function () {
            loadMaterialProperties(
                materialSelect.value,
                materialTemplate,
                totalFormsInput,
                propertiesUrlTemplate,
                materialDetailUrlTemplate,
            );
        });

        fetchMaterialProperties(initialMaterialId, propertiesUrlTemplate).then(function (data) {
            if (!hasMaterialRows && initialMaterialId) {
                return loadMaterialProperties(
                    initialMaterialId,
                    materialTemplate,
                    totalFormsInput,
                    propertiesUrlTemplate,
                    materialDetailUrlTemplate,
                );
            }
            renderStructurePropertiesSection(data, materialDetailUrlTemplate);
            removeExtraDuplicates();
            reindexForms(totalFormsInput);
            updateMaterialEmptyState();
            updateExtraEmptyState();
            return null;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSamplePropertiesFormset);
    } else {
        initSamplePropertiesFormset();
    }
})();
