(function () {
    'use strict';

    function isHexColor(value) {
        return /^#[0-9A-Fa-f]{6}$/.test(value || '');
    }

    function syncPicker(root) {
        var nativeInput = root.querySelector('.structure-color-picker__native');
        var textInput = root.querySelector('.structure-color-picker__text');
        if (!nativeInput || !textInput) {
            return;
        }
        if (isHexColor(textInput.value)) {
            nativeInput.value = textInput.value;
        }
        root.querySelectorAll('.structure-color-picker__preset').forEach(function (button) {
            var presetColor = (button.dataset.color || '').toUpperCase();
            button.classList.toggle(
                'structure-color-picker__preset--active',
                presetColor === textInput.value.toUpperCase(),
            );
        });
    }

    function setColor(root, color) {
        var nativeInput = root.querySelector('.structure-color-picker__native');
        var textInput = root.querySelector('.structure-color-picker__text');
        if (!nativeInput || !textInput || !isHexColor(color)) {
            return;
        }
        var normalized = color.toUpperCase();
        nativeInput.value = normalized;
        textInput.value = normalized;
        textInput.dispatchEvent(new Event('input', { bubbles: true }));
        textInput.dispatchEvent(new Event('change', { bubbles: true }));
        syncPicker(root);
    }

    function initPicker(root) {
        var nativeInput = root.querySelector('.structure-color-picker__native');
        var textInput = root.querySelector('.structure-color-picker__text');
        if (!nativeInput || !textInput) {
            return;
        }

        syncPicker(root);

        nativeInput.addEventListener('input', function () {
            textInput.value = nativeInput.value.toUpperCase();
            syncPicker(root);
        });

        textInput.addEventListener('input', function () {
            if (isHexColor(textInput.value)) {
                nativeInput.value = textInput.value;
            }
            syncPicker(root);
        });

        root.querySelectorAll('.structure-color-picker__preset').forEach(function (button) {
            button.addEventListener('click', function () {
                setColor(root, button.dataset.color || '');
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-structure-color-picker]').forEach(initPicker);
    });
})();
