(function () {
    'use strict';

    var PREFIX = 'choices';

    function reindexForms(container, totalFormsInput) {
        var rows = Array.from(container.querySelectorAll('.choice-form-row'));
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
        });
        totalFormsInput.value = String(rows.length);
    }

    function bindChoiceValueAutofill(row) {
        var labelInput = row.querySelector('[data-choice-label]');
        var valueInput = row.querySelector('[data-choice-value]');
        if (!labelInput || !valueInput || labelInput.dataset.boundAutofill === 'true') {
            return;
        }
        labelInput.dataset.boundAutofill = 'true';
        var valueEditedManually = Boolean(valueInput.value);
        valueInput.addEventListener('input', function () {
            valueEditedManually = true;
        });
        labelInput.addEventListener('input', function () {
            if (valueEditedManually) {
                return;
            }
            if (window.PropertyNameAutofill && window.PropertyNameAutofill.normalizeIdentifier) {
                valueInput.value = window.PropertyNameAutofill.normalizeIdentifier(labelInput.value, 100);
            }
        });
    }

    function bindDeleteButton(container, row, totalFormsInput) {
        var deleteBtn = row.querySelector('.delete-choice-btn');
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
        var container = document.getElementById('choice-forms-container');
        var template = document.getElementById('empty-choice-form-template');
        var totalFormsInput = document.getElementById('id_choices-TOTAL_FORMS');
        var addButton = document.getElementById('add-choice-btn');
        if (!container || !template || !totalFormsInput) {
            return;
        }

        container.querySelectorAll('.choice-form-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput);
            bindChoiceValueAutofill(row);
        });

        if (addButton) {
            addButton.addEventListener('click', function () {
                var formIndex = parseInt(totalFormsInput.value, 10);
                var html = template.innerHTML.replace(/__prefix__/g, String(formIndex));
                var wrapper = document.createElement('tbody');
                wrapper.innerHTML = html.trim();
                var row = wrapper.firstElementChild;
                container.appendChild(row);
                totalFormsInput.value = String(formIndex + 1);
                bindDeleteButton(container, row, totalFormsInput);
                bindChoiceValueAutofill(row);
                var labelInput = row.querySelector('[data-choice-label]');
                if (labelInput) {
                    labelInput.focus();
                }
            });
        }
    });
})();
