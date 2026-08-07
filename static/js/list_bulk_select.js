(function () {
    'use strict';

    function initBulkRoot(root) {
        var toggle = root.querySelector('[data-list-bulk-toggle]');
        var toolbar = root.querySelector('[data-list-bulk-toolbar]');
        var form = root.querySelector('[data-list-bulk-form]');
        var selectPage = root.querySelector('[data-list-bulk-select-page]');
        var countEl = root.querySelector('[data-list-bulk-count]');
        var submitBtn = root.querySelector('[data-list-bulk-submit]');
        var cancelBtn = root.querySelector('[data-list-bulk-cancel]');
        if (!toggle || !form) {
            return;
        }

        function items() {
            return Array.prototype.slice.call(root.querySelectorAll('[data-list-bulk-item]'));
        }

        function selectedCount() {
            return items().filter(function (el) {
                return el.checked && !el.disabled;
            }).length;
        }

        function sync() {
            var n = selectedCount();
            if (countEl) {
                countEl.textContent = 'Выбрано: ' + n;
            }
            if (submitBtn) {
                submitBtn.disabled = n === 0;
            }
            if (selectPage) {
                var enabled = items().filter(function (el) {
                    return !el.disabled;
                });
                var checked = enabled.filter(function (el) {
                    return el.checked;
                });
                selectPage.checked = enabled.length > 0 && checked.length === enabled.length;
                selectPage.indeterminate = checked.length > 0 && checked.length < enabled.length;
            }
        }

        function setMode(on) {
            root.classList.toggle('list-bulk--active', on);
            toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
            toggle.textContent = on ? 'Готово' : 'Выбрать';
            if (toolbar) {
                toolbar.hidden = !on;
            }
            items().forEach(function (el) {
                el.disabled = !on;
                if (!on) {
                    el.checked = false;
                }
            });
            if (selectPage) {
                selectPage.checked = false;
                selectPage.indeterminate = false;
            }
            sync();
        }

        toggle.addEventListener('click', function () {
            setMode(!root.classList.contains('list-bulk--active'));
        });

        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                setMode(false);
            });
        }

        if (selectPage) {
            selectPage.addEventListener('change', function () {
                var on = selectPage.checked;
                items().forEach(function (el) {
                    if (!el.disabled) {
                        el.checked = on;
                    }
                });
                sync();
            });
        }

        form.addEventListener('change', function (event) {
            if (event.target && event.target.matches('[data-list-bulk-item]')) {
                sync();
            }
        });

        form.addEventListener('submit', function (event) {
            if (form.dataset.confirmDeleteBypass === '1') {
                delete form.dataset.confirmDeleteBypass;
                items().forEach(function (el) {
                    if (!el.checked) {
                        el.disabled = true;
                    }
                });
                return;
            }
            if (!root.classList.contains('list-bulk--active') || selectedCount() === 0) {
                event.preventDefault();
                return;
            }
            event.preventDefault();
            var n = selectedCount();
            var message =
                form.getAttribute('data-confirm-message') ||
                ('Удалить выбранные записи (' + n + ')? Действие нельзя отменить.');
            if (window.AppConfirmDelete && typeof window.AppConfirmDelete.ask === 'function') {
                window.AppConfirmDelete.ask({
                    type: 'form',
                    form: form,
                    title: form.getAttribute('data-confirm-title') || 'Удаление выбранных',
                    message: message.replace('{count}', String(n)),
                    submitLabel: form.getAttribute('data-confirm-submit') || 'Удалить выбранные',
                    requireConfirmField: true,
                });
                return;
            }
            if (!window.confirm(message.replace('{count}', String(n)))) {
                return;
            }
            var conf = form.querySelector('input[name="confirm"]');
            if (!conf) {
                conf = document.createElement('input');
                conf.type = 'hidden';
                conf.name = 'confirm';
                form.appendChild(conf);
            }
            conf.value = '1';
            form.dataset.confirmDeleteBypass = '1';
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.submit();
            }
        });

        setMode(false);
    }

    document.addEventListener('DOMContentLoaded', function () {
        Array.prototype.forEach.call(document.querySelectorAll('[data-list-bulk]'), initBulkRoot);
    });
})();
