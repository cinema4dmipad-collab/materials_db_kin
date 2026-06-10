(function () {
    'use strict';

    function renumberLayers(container) {
        var layerNum = 1;
        container.querySelectorAll('.layer-form-row').forEach(function (row) {
            if (row.classList.contains('d-none')) {
                return;
            }
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) {
                return;
            }
            var layerInput = row.querySelector('input[name$="-layer_number"]');
            if (layerInput) {
                layerInput.value = layerNum;
                layerNum += 1;
            }
        });
    }

    function reindexForms(container, totalFormsInput) {
        var rows = Array.from(container.querySelectorAll('.layer-form-row'));
        rows.forEach(function (row, idx) {
            row.querySelectorAll('[name]').forEach(function (input) {
                input.name = input.name.replace(/^layers-\d+-/, 'layers-' + idx + '-');
                if (input.id) {
                    input.id = input.id.replace(/^id_layers-\d+-/, 'id_layers-' + idx + '-');
                }
            });
            row.querySelectorAll('label[for]').forEach(function (label) {
                var htmlFor = label.getAttribute('for');
                if (htmlFor) {
                    label.setAttribute(
                        'for',
                        htmlFor.replace(/^id_layers-\d+-/, 'id_layers-' + idx + '-'),
                    );
                }
            });
        });
        totalFormsInput.value = String(rows.length);
    }

    function appendLayerFromTemplate(container, template, totalFormsInput) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, formIndex);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = String(formIndex + 1);
        bindRowActions(container, row, template, totalFormsInput);
        if (window.initMaterialSelectLinks) {
            window.initMaterialSelectLinks(row);
        }
        renumberLayers(container);
        return row;
    }

    function copyRowValues(sourceRow, targetRow) {
        sourceRow.querySelectorAll('[name]').forEach(function (sourceInput) {
            var suffix = sourceInput.name.replace(/^layers-\d+-/, '');
            if (suffix === 'DELETE' || suffix === 'id' || suffix === 'layer_number') {
                return;
            }
            var targetInput = targetRow.querySelector('[name$="-' + suffix + '"]');
            if (!targetInput) {
                return;
            }
            if (targetInput.type === 'checkbox') {
                targetInput.checked = sourceInput.checked;
            } else {
                targetInput.value = sourceInput.value;
            }
        });
    }

    function bindDeleteButton(container, row, template, totalFormsInput) {
        var deleteBtn = row.querySelector('.delete-layer-btn');
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
            renumberLayers(container);
        });
    }

    function bindDuplicateButton(container, row, template, totalFormsInput) {
        var dupBtn = row.querySelector('.duplicate-layer-btn');
        if (!dupBtn || dupBtn.dataset.bound === 'true') {
            return;
        }
        dupBtn.dataset.bound = 'true';

        dupBtn.addEventListener('click', function () {
            var newRow = appendLayerFromTemplate(container, template, totalFormsInput);
            if (newRow) {
                copyRowValues(row, newRow);
                if (window.initMaterialSelectLinks) {
                    window.initMaterialSelectLinks(newRow);
                }
                renumberLayers(container);
            }
        });
    }

    function bindRowActions(container, row, template, totalFormsInput) {
        bindDeleteButton(container, row, template, totalFormsInput);
        bindDuplicateButton(container, row, template, totalFormsInput);
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('layer-forms-container');
        var template = document.getElementById('empty-layer-form-template');
        var addButton = document.getElementById('add-layer-btn');
        var totalFormsInput = document.getElementById('id_layers-TOTAL_FORMS');

        if (!container || !template || !addButton || !totalFormsInput) {
            return;
        }

        container.querySelectorAll('.layer-form-row').forEach(function (row) {
            bindRowActions(container, row, template, totalFormsInput);
        });

        addButton.addEventListener('click', function () {
            appendLayerFromTemplate(container, template, totalFormsInput);
        });

        renumberLayers(container);
    });
})();
