/**
 * Export selected materials via a native form POST (target=_blank).
 *
 * Blob/fetch downloads are unreliable in Chrome (failed items named like
 * "<uuid>.xlsx", "Ошибка" / "Проверьте подключение к интернету"). The browser
 * handles Content-Disposition: attachment from a real navigation instead —
 * same pattern as scan/attachment downloads.
 */
(function () {
    'use strict';

    var exporting = false;

    function selectedItems(root) {
        return Array.prototype.slice.call(
            root.querySelectorAll('[data-list-bulk-item]:checked:not(:disabled)')
        );
    }

    function enableSelectMode(root) {
        if (root.classList.contains('list-bulk--active')) {
            return;
        }
        var toggle = root.querySelector('[data-list-bulk-toggle]');
        if (toggle) {
            toggle.click();
        }
    }

    function showModal(id) {
        var modalEl = document.getElementById(id);
        if (modalEl && window.bootstrap && window.bootstrap.Modal) {
            window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
            return true;
        }
        return false;
    }

    function showNeedSelectModal() {
        if (showModal('materials-export-need-select-modal')) {
            return;
        }
        window.alert(
            'Сначала выберите материалы в списке (кнопка «Выбрать»), затем снова нажмите «Выгрузить в Excel».'
        );
    }

    function showStructureModal(message) {
        var body = document.querySelector('[data-materials-export-structure-body]');
        if (body && message) {
            body.textContent = message;
        }
        if (showModal('materials-export-structure-modal')) {
            return;
        }
        window.alert(
            message ||
                'В одном файле можно выгрузить только материалы одного типа структуры.'
        );
    }

    function showErrorModal(message) {
        var body = document.querySelector('[data-materials-export-error-body]');
        if (body) {
            body.textContent =
                message || 'Не удалось выгрузить файл. Попробуйте ещё раз.';
        }
        if (showModal('materials-export-error-modal')) {
            return;
        }
        window.alert(message || 'Не удалось выгрузить файл. Попробуйте ещё раз.');
    }

    function structureKey(item) {
        return (item.getAttribute('data-struct-type-id') || '').trim();
    }

    function validateSingleStructure(items) {
        var keys = {};
        var missing = 0;
        items.forEach(function (el) {
            var key = structureKey(el);
            if (!key) {
                missing += 1;
                return;
            }
            keys[key] = true;
        });
        var distinct = Object.keys(keys);
        if (missing > 0) {
            return {
                ok: false,
                message:
                    'Выгрузка возможна только для материалов с типом структуры. Уберите из выбора материалы без типа.',
            };
        }
        if (distinct.length > 1) {
            return {
                ok: false,
                message:
                    'В одном файле можно выгрузить только один тип структуры. Отметьте материалы одного типа и повторите выгрузку.',
            };
        }
        return { ok: true };
    }

    function csrfFromCookie() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function setBusy(button, busy) {
        exporting = busy;
        if (!button) {
            return;
        }
        button.disabled = busy;
        button.classList.toggle('disabled', busy);
        if (busy) {
            button.setAttribute('aria-busy', 'true');
        } else {
            button.removeAttribute('aria-busy');
        }
    }

    function startNativeDownload(url, ids, csrfToken, scope) {
        var form = document.createElement('form');
        form.method = 'post';
        form.action = url;
        // Real navigation download — Chrome applies Content-Disposition reliably.
        form.target = '_blank';
        form.style.display = 'none';
        form.setAttribute('accept-charset', 'utf-8');

        var csrf = document.createElement('input');
        csrf.type = 'hidden';
        csrf.name = 'csrfmiddlewaretoken';
        csrf.value = csrfToken || csrfFromCookie() || '';
        form.appendChild(csrf);

        if (scope) {
            var scopeInput = document.createElement('input');
            scopeInput.type = 'hidden';
            scopeInput.name = 'scope';
            scopeInput.value = scope;
            form.appendChild(scopeInput);
        }

        ids.forEach(function (id) {
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'ids';
            input.value = id;
            form.appendChild(input);
        });

        document.body.appendChild(form);
        form.submit();
        window.setTimeout(function () {
            if (form.parentNode) {
                form.parentNode.removeChild(form);
            }
        }, 0);
    }

    function onExportClick(event) {
        event.preventDefault();
        if (exporting) {
            return;
        }
        var button = event.currentTarget;
        var root = document.querySelector('[data-list-bulk]');
        if (!root) {
            showNeedSelectModal();
            return;
        }
        var items = selectedItems(root);
        if (!items.length) {
            enableSelectMode(root);
            showNeedSelectModal();
            return;
        }
        var check = validateSingleStructure(items);
        if (!check.ok) {
            showStructureModal(check.message);
            return;
        }
        var url = button.getAttribute('data-export-url');
        if (!url) {
            showErrorModal('Не задан адрес выгрузки.');
            return;
        }
        var csrf = button.getAttribute('data-csrf') || csrfFromCookie() || '';
        var scope = button.getAttribute('data-export-scope') || '';
        setBusy(button, true);
        try {
            startNativeDownload(
                url,
                items.map(function (el) {
                    return el.value;
                }),
                csrf,
                scope
            );
        } catch (err) {
            showErrorModal('Не удалось начать выгрузку. Обновите страницу и повторите.');
        } finally {
            // Keep button free after the browser has taken the navigation.
            window.setTimeout(function () {
                setBusy(button, false);
            }, 1500);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        Array.prototype.forEach.call(
            document.querySelectorAll('[data-materials-export]'),
            function (btn) {
                btn.addEventListener('click', onExportClick);
            }
        );
    });
})();
