/**
 * Export selected materials via fetch (blob download).
 * Avoids form.submit() navigating to HTML error/redirect pages that get saved as broken "xlsx".
 */
(function () {
    'use strict';

    var XLSX_MIME =
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
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

    function parseFilename(contentDisposition, fallback) {
        if (!contentDisposition) {
            return fallback;
        }
        var utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
        if (utfMatch && utfMatch[1]) {
            try {
                return decodeURIComponent(utfMatch[1].trim().replace(/"/g, ''));
            } catch (err) {
                /* ignore */
            }
        }
        var match = /filename="?([^";]+)"?/i.exec(contentDisposition);
        if (match && match[1]) {
            return match[1].trim();
        }
        return fallback;
    }

    function looksLikeZipXlsx(buffer) {
        if (!buffer || buffer.byteLength < 4) {
            return false;
        }
        var bytes = new Uint8Array(buffer, 0, 4);
        // XLSX is a ZIP: PK\x03\x04
        return bytes[0] === 0x50 && bytes[1] === 0x4b;
    }

    function triggerBlobDownload(blob, filename) {
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename || 'materials.xlsx';
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        window.setTimeout(function () {
            window.URL.revokeObjectURL(url);
            if (link.parentNode) {
                link.parentNode.removeChild(link);
            }
        }, 1000);
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

    async function exportViaFetch(button, ids, scope) {
        var url = button.getAttribute('data-export-url');
        var csrf = button.getAttribute('data-csrf') || '';
        if (!url) {
            showErrorModal('Не задан адрес выгрузки.');
            return;
        }

        var body = new FormData();
        ids.forEach(function (id) {
            body.append('ids', id);
        });
        if (scope) {
            body.append('scope', scope);
        }

        setBusy(button, true);
        try {
            var response = await fetch(url, {
                method: 'POST',
                body: body,
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': csrf,
                    'X-Requested-With': 'XMLHttpRequest',
                    Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/json',
                },
            });

            var contentType = (response.headers.get('Content-Type') || '').toLowerCase();

            if (!response.ok) {
                var errorMessage = 'Не удалось выгрузить файл (код ' + response.status + ').';
                if (contentType.indexOf('application/json') !== -1) {
                    try {
                        var payload = await response.json();
                        if (payload && payload.error) {
                            errorMessage = payload.error;
                        }
                    } catch (err) {
                        /* ignore */
                    }
                }
                showErrorModal(errorMessage);
                return;
            }

            if (contentType.indexOf('application/json') !== -1) {
                try {
                    var jsonPayload = await response.json();
                    showErrorModal(
                        (jsonPayload && jsonPayload.error) ||
                            'Сервер вернул ошибку вместо файла Excel.'
                    );
                } catch (err) {
                    showErrorModal('Сервер вернул ошибку вместо файла Excel.');
                }
                return;
            }

            if (
                contentType.indexOf('text/html') !== -1 ||
                contentType.indexOf('text/plain') !== -1
            ) {
                showErrorModal(
                    'Сервер вернул страницу вместо файла Excel. Обновите страницу и попробуйте снова.'
                );
                return;
            }

            var buffer = await response.arrayBuffer();
            if (!looksLikeZipXlsx(buffer)) {
                showErrorModal(
                    'Получен повреждённый ответ вместо Excel. Обновите страницу и попробуйте снова.'
                );
                return;
            }

            var filename = parseFilename(
                response.headers.get('Content-Disposition'),
                'materials.xlsx'
            );
            if (!/\.xlsx$/i.test(filename)) {
                filename += '.xlsx';
            }
            var blob = new Blob([buffer], { type: XLSX_MIME });
            triggerBlobDownload(blob, filename);
        } catch (err) {
            showErrorModal(
                'Сеть или браузер прервали выгрузку. Проверьте соединение и попробуйте снова.'
            );
        } finally {
            setBusy(button, false);
        }
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
        var scope = button.getAttribute('data-export-scope') || '';
        exportViaFetch(
            button,
            items.map(function (el) {
                return el.value;
            }),
            scope
        );
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
