(function () {
    'use strict';

    function currentPath() {
        // No hash — otherwise the same page can be saved twice (#section).
        var path = window.location.pathname || '/';
        if (path.length > 1 && path.endsWith('/')) {
            path = path.replace(/\/+$/, '');
        }
        return path + (window.location.search || '');
    }

    function defaultLabel() {
        var title = (document.title || '').trim();
        if (!title) {
            return currentPath();
        }
        // Drop trailing site suffix: "Help — Keenetica Lab" → "Help"
        var parts = title.split(/\s+[—–|-]\s+/);
        if (parts.length > 1 && parts[0].trim()) {
            return parts[0].trim();
        }
        return title;
    }

    function normalizeHex(value) {
        var text = (value || '').trim();
        if (!text) {
            return '';
        }
        if (text.charAt(0) !== '#') {
            text = '#' + text;
        }
        if (!/^#[0-9A-Fa-f]{6}$/.test(text)) {
            return null;
        }
        return text.toUpperCase();
    }

    function syncColorPicker(modal) {
        var root = modal.querySelector('[data-bookmark-color-picker]');
        if (!root) {
            return;
        }
        var textInput = root.querySelector('.bookmark-color-picker__text');
        var nativeInput = root.querySelector('.bookmark-color-picker__native');
        var iconPicker = modal.querySelector('.bookmark-icon-picker');
        var color = normalizeHex(textInput ? textInput.value : '') || '';

        if (nativeInput && color) {
            nativeInput.value = color;
        }
        if (iconPicker) {
            if (color) {
                iconPicker.style.setProperty('--bookmark-icon-color', color);
            } else {
                iconPicker.style.removeProperty('--bookmark-icon-color');
            }
        }
        root.querySelectorAll('.bookmark-color-picker__preset').forEach(function (button) {
            var preset = (button.getAttribute('data-color') || '').toUpperCase();
            var isDefault = preset === '';
            var active = isDefault ? !color : preset === color;
            button.classList.toggle('bookmark-color-picker__preset--active', active);
        });
    }

    function bindColorPicker(modal) {
        var root = modal.querySelector('[data-bookmark-color-picker]');
        if (!root || root.dataset.bound === '1') {
            return;
        }
        root.dataset.bound = '1';
        var textInput = root.querySelector('.bookmark-color-picker__text');
        var nativeInput = root.querySelector('.bookmark-color-picker__native');

        root.querySelectorAll('.bookmark-color-picker__preset').forEach(function (button) {
            button.addEventListener('click', function () {
                var preset = button.getAttribute('data-color') || '';
                if (textInput) {
                    textInput.value = preset ? preset.toUpperCase() : '';
                }
                syncColorPicker(modal);
            });
        });

        if (nativeInput) {
            nativeInput.addEventListener('input', function () {
                if (textInput) {
                    textInput.value = (nativeInput.value || '').toUpperCase();
                }
                syncColorPicker(modal);
            });
        }

        if (textInput) {
            textInput.addEventListener('input', function () {
                var normalized = normalizeHex(textInput.value);
                if (normalized) {
                    textInput.value = normalized;
                }
                syncColorPicker(modal);
            });
            textInput.addEventListener('blur', function () {
                var normalized = normalizeHex(textInput.value);
                if (normalized === null && textInput.value.trim()) {
                    textInput.value = '';
                } else if (normalized) {
                    textInput.value = normalized;
                }
                syncColorPicker(modal);
            });
        }
    }

    function fillForm(modal) {
        var labelInput = document.getElementById('bookmark-page-label');
        var urlInput = document.getElementById('bookmark-page-url');
        var nextInput = document.getElementById('bookmark-page-next');
        var colorInput = document.getElementById('bookmark-page-icon-color');
        var path = currentPath();
        var bookmarked = modal && modal.getAttribute('data-bookmarked') === '1';
        var existingLabel = (modal && modal.getAttribute('data-bookmark-label')) || '';
        var existingIcon = (modal && modal.getAttribute('data-bookmark-icon')) || '';
        var existingColor = (modal && modal.getAttribute('data-bookmark-icon-color')) || '';

        if (urlInput) {
            urlInput.value = path;
        }
        if (nextInput) {
            nextInput.value = path;
        }
        if (labelInput) {
            labelInput.value = bookmarked && existingLabel ? existingLabel : defaultLabel();
        }

        var iconValue = bookmarked && existingIcon ? existingIcon : 'bi-bookmark';
        var iconInput = modal.querySelector('input[name="icon"][value="' + iconValue + '"]')
            || modal.querySelector('input[name="icon"]');
        if (iconInput) {
            iconInput.checked = true;
        }

        if (colorInput) {
            colorInput.value = bookmarked ? (normalizeHex(existingColor) || '') : '';
        }
        syncColorPicker(modal);
    }

    function init() {
        var modal = document.getElementById('bookmarkPageModal');
        if (!modal) {
            return;
        }
        bindColorPicker(modal);
        modal.addEventListener('show.bs.modal', function () {
            fillForm(modal);
            var labelInput = document.getElementById('bookmark-page-label');
            window.setTimeout(function () {
                if (labelInput) {
                    labelInput.focus();
                    labelInput.select();
                }
            }, 150);
        });
        syncColorPicker(modal);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
