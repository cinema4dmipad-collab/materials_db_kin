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

    function appendPropertyFromTemplate(container, template, totalFormsInput) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, formIndex);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = String(formIndex + 1);
        bindDeleteButton(container, row, totalFormsInput);
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
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('property-forms-container');
        var template = document.getElementById('empty-property-form-template');
        var addButton = document.getElementById('add-property-btn');
        var totalFormsInput = document.getElementById('id_properties-TOTAL_FORMS');

        if (!container || !template || !addButton || !totalFormsInput) {
            return;
        }

        container.querySelectorAll('.property-form-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput);
        });

        addButton.addEventListener('click', function () {
            appendPropertyFromTemplate(container, template, totalFormsInput);
        });

        var form = container.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                var rows = container.querySelectorAll('.property-form-row');
                totalFormsInput.value = String(rows.length);
            });
        }
    });
})();
