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

    function addLayer(container, template, totalFormsInput) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, formIndex);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        var row = wrapper.firstElementChild;
        container.appendChild(row);
        totalFormsInput.value = formIndex + 1;
        renumberLayers(container);
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('layer-forms-container');
        var template = document.getElementById('empty-layer-form-template');
        var addButton = document.getElementById('add-layer-btn');
        var totalFormsInput = document.getElementById('id_layers-TOTAL_FORMS');

        if (!container || !template || !addButton || !totalFormsInput) {
            return;
        }

        addButton.addEventListener('click', function () {
            addLayer(container, template, totalFormsInput);
        });

        container.addEventListener('change', function (event) {
            if (event.target.matches('input[name$="-DELETE"]')) {
                renumberLayers(container);
            }
        });

        renumberLayers(container);
    });
})();
