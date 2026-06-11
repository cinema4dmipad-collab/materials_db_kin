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

    function setRowPropertyMeta(row, label, unit) {
        var labelCell = row.querySelector('.material-props-section__name');
        var unitCell = row.querySelector('.material-props-section__unit');
        if (labelCell) {
            labelCell.textContent = label || '—';
        }
        if (unitCell) {
            unitCell.textContent = unit || '—';
        }
    }

    function fillPropertyRow(row, payload) {
        var propertySelect = row.querySelector('[name$="-property"]');
        if (propertySelect) {
            propertySelect.value = payload.property_id;
        }
        setRowPropertyMeta(row, payload.label, payload.unit);
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

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('property-forms-container');
        var template = document.getElementById('empty-property-form-template');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');
        var picker = window.ReferencePropertiesPicker;

        if (!container || !template || !totalFormsInput || !picker) {
            return;
        }

        container.querySelectorAll('.property-form-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput);
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

        var form = container.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                var rows = container.querySelectorAll('.property-form-row');
                totalFormsInput.value = String(rows.length);
            });
        }

        updateEmptyState(container);
    });
})();
