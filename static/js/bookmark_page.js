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

    function fillForm() {
        var labelInput = document.getElementById('bookmark-page-label');
        var urlInput = document.getElementById('bookmark-page-url');
        var nextInput = document.getElementById('bookmark-page-next');
        var path = currentPath();
        if (urlInput) {
            urlInput.value = path;
        }
        if (nextInput) {
            nextInput.value = path;
        }
        if (labelInput && !labelInput.value.trim()) {
            labelInput.value = defaultLabel();
        }
    }

    function init() {
        var modal = document.getElementById('bookmarkPageModal');
        if (!modal) {
            return;
        }
        modal.addEventListener('show.bs.modal', function () {
            var labelInput = document.getElementById('bookmark-page-label');
            if (labelInput) {
                labelInput.value = '';
            }
            var defaultIcon = modal.querySelector('input[name="icon"][value="bi-bookmark"]')
                || modal.querySelector('input[name="icon"]');
            if (defaultIcon) {
                defaultIcon.checked = true;
            }
            fillForm();
            window.setTimeout(function () {
                if (labelInput) {
                    labelInput.focus();
                    labelInput.select();
                }
            }, 150);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
