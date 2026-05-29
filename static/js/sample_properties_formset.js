(function () {
    'use strict';

    var PREFIX = 'properties';
    var materialPropertyIds = new Set();

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

    function propertyLabelFromSelect(select) {
        if (!select || !select.value) {
            return '';
        }
        var option = select.options[select.selectedIndex];
        return option ? option.text.trim() : '';
    }

    function isExtraProperty(propertyId) {
        return Boolean(propertyId) && !materialPropertyIds.has(propertyId);
    }

    function updateRowWarning(row) {
        var warning = row.querySelector('.property-extra-warning');
        var select = row.querySelector('[name$="-property"]');
        if (!warning || !select) {
            return;
        }
        if (row.classList.contains('d-none')) {
            warning.classList.add('d-none');
            return;
        }
        var extra = isExtraProperty(select.value);
        warning.classList.toggle('d-none', !extra);
        select.classList.toggle('border-warning', extra);
    }

    function updateGlobalWarning(container, globalWarning) {
        if (!globalWarning) {
            return;
        }
        var extraLabels = [];
        container.querySelectorAll('.property-form-row').forEach(function (row) {
            if (row.classList.contains('d-none')) {
                return;
            }
            var select = row.querySelector('[name$="-property"]');
            if (select && isExtraProperty(select.value)) {
                var label = propertyLabelFromSelect(select);
                if (label && extraLabels.indexOf(label) === -1) {
                    extraLabels.push(label);
                }
            }
        });

        if (!extraLabels.length) {
            globalWarning.classList.add('d-none');
            globalWarning.textContent = '';
            return;
        }

        globalWarning.classList.remove('d-none');
        globalWarning.textContent =
            'Следующие свойства образца отсутствуют у выбранного материала: '
            + extraLabels.join(', ')
            + '.';
    }

    function updateAllWarnings(container, globalWarning) {
        container.querySelectorAll('.property-form-row').forEach(function (row) {
            updateRowWarning(row);
        });
        updateGlobalWarning(container, globalWarning);
    }

    function bindPropertySelect(row, container, globalWarning) {
        var select = row.querySelector('[name$="-property"]');
        if (!select || select.dataset.boundExtraWarning === 'true') {
            return;
        }
        select.dataset.boundExtraWarning = 'true';
        select.addEventListener('change', function () {
            updateRowWarning(row);
            updateGlobalWarning(container, globalWarning);
        });
    }

    function bindDeleteButton(container, row, totalFormsInput, globalWarning) {
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
            updateAllWarnings(container, globalWarning);
        });
    }

    function appendPropertyFromTemplate(container, template, totalFormsInput, globalWarning) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, formIndex);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = String(formIndex + 1);
        bindDeleteButton(container, row, totalFormsInput, globalWarning);
        bindPropertySelect(row, container, globalWarning);
        updateRowWarning(row);
        updateGlobalWarning(container, globalWarning);
        return row;
    }

    function clearPropertyRows(container, totalFormsInput) {
        container.querySelectorAll('.property-form-row').forEach(function (row) {
            row.remove();
        });
        totalFormsInput.value = '0';
    }

    function fillPropertyRow(row, propertyId, value) {
        var propertySelect = row.querySelector('[name$="-property"]');
        var valueInput = row.querySelector('[name$="-value"]');
        if (propertySelect) {
            propertySelect.value = propertyId;
        }
        if (valueInput) {
            valueInput.value = value;
        }
    }

    function fetchMaterialProperties(materialId, propertiesUrlTemplate) {
        if (!materialId) {
            materialPropertyIds = new Set();
            return Promise.resolve([]);
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
                return properties;
            })
            .catch(function () {
                materialPropertyIds = new Set();
                return [];
            });
    }

    function loadPropertiesFromMaterial(materialId, container, template, totalFormsInput, propertiesUrlTemplate, globalWarning) {
        return fetchMaterialProperties(materialId, propertiesUrlTemplate).then(function (properties) {
            if (!materialId) {
                clearPropertyRows(container, totalFormsInput);
                updateGlobalWarning(container, globalWarning);
                return;
            }
            clearPropertyRows(container, totalFormsInput);
            properties.forEach(function (item) {
                var row = appendPropertyFromTemplate(container, template, totalFormsInput, globalWarning);
                fillPropertyRow(row, item.property_id, item.value);
                updateRowWarning(row);
            });
            updateGlobalWarning(container, globalWarning);
        });
    }

    function refreshMaterialPropertyIds(materialId, propertiesUrlTemplate, container, globalWarning) {
        return fetchMaterialProperties(materialId, propertiesUrlTemplate).then(function () {
            updateAllWarnings(container, globalWarning);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('property-forms-container');
        var template = document.getElementById('empty-property-form-template');
        var addButton = document.getElementById('add-property-btn');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');
        var materialSelect = document.querySelector('[data-sample-material-select]');
        var globalWarning = document.getElementById('sample-extra-properties-warning');
        var form = container ? container.closest('form') : null;

        if (!container || !template || !addButton || !totalFormsInput || !materialSelect || !form) {
            return;
        }

        var propertiesUrlTemplate = form.getAttribute('data-material-properties-url');
        var skipInitialAutoload = form.getAttribute('data-properties-prefilled') === 'true';
        var initialMaterialId = materialSelect.value;

        container.querySelectorAll('.property-form-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput, globalWarning);
            bindPropertySelect(row, container, globalWarning);
        });

        addButton.addEventListener('click', function () {
            appendPropertyFromTemplate(container, template, totalFormsInput, globalWarning);
        });

        form.addEventListener('submit', function () {
            var rows = container.querySelectorAll('.property-form-row');
            totalFormsInput.value = String(rows.length);
        });

        materialSelect.addEventListener('change', function () {
            loadPropertiesFromMaterial(
                materialSelect.value,
                container,
                template,
                totalFormsInput,
                propertiesUrlTemplate,
                globalWarning,
            );
        });

        if (skipInitialAutoload) {
            refreshMaterialPropertyIds(
                initialMaterialId,
                propertiesUrlTemplate,
                container,
                globalWarning,
            );
        } else if (initialMaterialId) {
            loadPropertiesFromMaterial(
                initialMaterialId,
                container,
                template,
                totalFormsInput,
                propertiesUrlTemplate,
                globalWarning,
            );
        }
    });
})();
