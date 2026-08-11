(function () {
    'use strict';

    var VALUE_KIND_SCALAR = 'scalar';
    var VALUE_KIND_RANGE = 'range';
    var VALUE_KIND_TOLERANCE = 'tolerance';

    function setInputsDisabled(container, disabled) {
        if (!container) {
            return;
        }
        container.querySelectorAll('input, select, textarea').forEach(function (input) {
            if (input.type === 'hidden' && /value_kind|__kind/.test(input.name || '')) {
                return;
            }
            input.disabled = Boolean(disabled);
        });
    }

    function syncValueBetweenModes(block, isRange, isTolerance) {
        var scalarInput = block.querySelector(
            '[data-property-number-scalar] input[name$="-value"], [data-property-number-scalar] input[name$="-__value"]'
        );
        var toleranceValueInput = block.querySelector(
            '[data-property-number-tolerance] input[name$="-value"], [data-property-number-tolerance] input[name$="-__value"]'
        );
        if (!scalarInput || !toleranceValueInput) {
            return;
        }
        if (isTolerance && !isRange) {
            if (!toleranceValueInput.value && scalarInput.value) {
                toleranceValueInput.value = scalarInput.value;
            }
        } else if (!isRange && !isTolerance) {
            if (!scalarInput.value && toleranceValueInput.value) {
                scalarInput.value = toleranceValueInput.value;
            }
        }
    }

    function syncBlockMode(block) {
        if (!block) {
            return;
        }
        var rangeToggle = block.querySelector('.property-number-value__range-toggle');
        var toleranceToggle = block.querySelector('.property-number-value__tolerance-toggle');
        var scalarBlock = block.querySelector('[data-property-number-scalar]');
        var rangeBlock = block.querySelector('[data-property-number-range]');
        var toleranceBlock = block.querySelector('[data-property-number-tolerance]');
        var kindInput = block.querySelector('[name$="-value_kind"], [name$="-__kind"]');
        var isRange = Boolean(rangeToggle && rangeToggle.checked);
        var isTolerance = Boolean(toleranceToggle && toleranceToggle.checked);

        if (isRange && isTolerance && toleranceToggle) {
            toleranceToggle.checked = false;
            isTolerance = false;
        }

        syncValueBetweenModes(block, isRange, isTolerance);

        block.classList.remove(
            'property-number-value--range',
            'property-number-value--tolerance'
        );
        if (isRange) {
            block.classList.add('property-number-value--range');
        } else if (isTolerance) {
            block.classList.add('property-number-value--tolerance');
        }

        if (scalarBlock) {
            scalarBlock.classList.toggle('d-none', isRange || isTolerance);
            setInputsDisabled(scalarBlock, isRange || isTolerance);
        }
        if (rangeBlock) {
            rangeBlock.classList.toggle('d-none', !isRange);
            setInputsDisabled(rangeBlock, !isRange);
        }
        if (toleranceBlock) {
            toleranceBlock.classList.toggle('d-none', !isTolerance);
            setInputsDisabled(toleranceBlock, !isTolerance);
        }
        if (kindInput) {
            if (isRange) {
                kindInput.value = VALUE_KIND_RANGE;
            } else if (isTolerance) {
                kindInput.value = VALUE_KIND_TOLERANCE;
            } else {
                kindInput.value = VALUE_KIND_SCALAR;
            }
        }
    }

    function bindToggle(block, toggle, otherToggle) {
        if (!toggle) {
            return;
        }
        toggle.addEventListener('change', function () {
            if (toggle.checked && otherToggle) {
                otherToggle.checked = false;
            }
            syncBlockMode(block);
        });
    }

    function initBlock(block) {
        if (!block || block.dataset.propertyNumberBound === 'true') {
            return;
        }
        block.dataset.propertyNumberBound = 'true';
        var rangeToggle = block.querySelector('.property-number-value__range-toggle');
        var toleranceToggle = block.querySelector('.property-number-value__tolerance-toggle');
        bindToggle(block, rangeToggle, toleranceToggle);
        bindToggle(block, toleranceToggle, rangeToggle);
        syncBlockMode(block);
    }

    function initRow(row) {
        if (!row) {
            return;
        }
        row.querySelectorAll('[data-property-number-value]').forEach(initBlock);
    }

    function initContainer(container) {
        if (!container) {
            return;
        }
        container.querySelectorAll('[data-property-number-value]').forEach(initBlock);
        container.querySelectorAll('.property-form-row').forEach(initRow);
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-property-number-value]').forEach(initBlock);
        initContainer(document.getElementById('property-forms-container'));
        initContainer(document.getElementById('material-property-forms-container'));
        initContainer(document.getElementById('extra-property-forms-container'));
    });

    window.PropertyNumberValue = {
        initBlock: initBlock,
        initRow: initRow,
        initContainer: initContainer,
        syncBlockMode: syncBlockMode,
    };
})();
