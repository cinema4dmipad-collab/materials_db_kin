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
        var wrap = select.closest('.material-picker-field');
        if (!wrap) {
            return;
        }
        var labelNode = wrap.querySelector('.material-picker-field__label');
        if (!labelNode) {
            return;
        }
        var label = selectedLabel(select);
        labelNode.textContent = label || '— не выбран —';
        labelNode.classList.toggle('text-muted', !label);
    }

    function enhanceSelect(select) {
        if (!select || select.dataset.materialPickerBound === 'true') {
            syncSelect(select);
            return;
        }
        select.dataset.materialPickerBound = 'true';

        var compact = select.dataset.materialPickerCompact === 'true';

        var wrap = document.createElement('div');
        wrap.className = 'material-picker-field d-flex gap-2 align-items-stretch'
            + (compact ? ' material-picker-field--compact' : '');
        select.parentNode.insertBefore(wrap, select);

        var labelNode = document.createElement('button');
        labelNode.type = 'button';
        labelNode.className = 'material-picker-field__label form-control form-control-sm text-start flex-grow-1';
        labelNode.setAttribute('aria-label', 'Выбранный материал — нажмите, чтобы изменить');
        labelNode.title = 'Нажмите, чтобы выбрать материал';

        wrap.appendChild(labelNode);
        if (!compact) {
            var openBtn = document.createElement('button');
            openBtn.type = 'button';
            openBtn.className = 'btn btn-sm btn-outline-primary material-picker-open-btn text-nowrap';
            openBtn.textContent = 'Выбрать';
            openBtn.addEventListener('click', openPicker);
            wrap.appendChild(openBtn);
        }
        wrap.appendChild(select);

        select.classList.add('material-picker-select--hidden');

        function openPicker() {
            if (window.ReferenceMaterialsPicker) {
                window.ReferenceMaterialsPicker.openFor(select);
            }
        }

        labelNode.addEventListener('click', openPicker);
        select.addEventListener('change', function () {
            syncSelect(select);
        });

        syncSelect(select);
    }

    function initMaterialPickerFields(root) {
        var scope = root || document;
        scope.querySelectorAll('select[data-material-picker]').forEach(enhanceSelect);
    }

    window.MaterialPickerFields = {
        init: initMaterialPickerFields,
        syncSelect: syncSelect,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initMaterialPickerFields();
        });
    } else {
        initMaterialPickerFields();
    }
})();
