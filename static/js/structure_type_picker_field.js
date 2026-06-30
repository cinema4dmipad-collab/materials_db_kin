(function () {
    'use strict';

    function selectedLabel(select) {
        if (!select || !select.value) {
            return '';
        }
        var option = select.options[select.selectedIndex];
        return option ? option.text.trim() : '';
    }

    function syncSelect(select) {
        var wrap = select.closest('.structure-type-picker-field');
        if (!wrap) {
            return;
        }
        var labelNode = wrap.querySelector('.structure-type-picker-field__label');
        if (!labelNode) {
            return;
        }
        var label = selectedLabel(select);
        labelNode.textContent = label || '— не выбран —';
        labelNode.classList.toggle('text-muted', !label);
    }

    function enhanceSelect(select) {
        if (!select || select.dataset.structureTypePickerBound === 'true') {
            syncSelect(select);
            return;
        }
        select.dataset.structureTypePickerBound = 'true';

        var wrap = document.createElement('div');
        wrap.className = 'structure-type-picker-field material-picker-field material-picker-field--compact d-flex align-items-stretch';
        select.parentNode.insertBefore(wrap, select);

        var labelNode = document.createElement('button');
        labelNode.type = 'button';
        labelNode.className = 'structure-type-picker-field__label material-picker-field__label form-control text-start flex-grow-1';
        labelNode.setAttribute('aria-label', 'Выбранный тип структуры — нажмите, чтобы изменить');
        labelNode.title = 'Нажмите, чтобы выбрать тип структуры';

        wrap.appendChild(labelNode);
        wrap.appendChild(select);

        select.classList.add('material-picker-select--hidden');

        function openPicker() {
            if (window.ReferenceStructureTypesPicker) {
                window.ReferenceStructureTypesPicker.openFor(select);
            }
        }

        labelNode.addEventListener('click', openPicker);
        select.addEventListener('change', function () {
            syncSelect(select);
        });

        syncSelect(select);
    }

    function initStructureTypePickerFields(root) {
        var scope = root || document;
        scope.querySelectorAll('select[data-structure-type-picker]').forEach(enhanceSelect);
    }

    window.StructureTypePickerFields = {
        init: initStructureTypePickerFields,
        syncSelect: syncSelect,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initStructureTypePickerFields();
        });
    } else {
        initStructureTypePickerFields();
    }
})();
