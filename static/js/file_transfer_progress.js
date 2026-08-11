(function () {
    'use strict';

    var overlay;
    var titleEl;
    var barEl;
    var metaEl;
    var progressRoot;

    function initOverlay() {
        overlay = document.getElementById('file-transfer-progress');
        if (!overlay) {
            return false;
        }
        titleEl = overlay.querySelector('.file-transfer-progress__title');
        barEl = overlay.querySelector('.progress-bar');
        metaEl = overlay.querySelector('.file-transfer-progress__meta');
        progressRoot = overlay.querySelector('.progress');
        return Boolean(titleEl && barEl && metaEl && progressRoot);
    }

    function formatBytes(bytes) {
        if (!bytes && bytes !== 0) {
            return '';
        }
        var units = ['Б', 'КБ', 'МБ', 'ГБ'];
        var index = 0;
        var value = bytes;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index += 1;
        }
        return (index === 0 ? value : value.toFixed(1)) + ' ' + units[index];
    }

    function setBusy(isBusy) {
        overlay.classList.toggle('d-none', !isBusy);
        overlay.setAttribute('aria-busy', isBusy ? 'true' : 'false');
    }

    function setTitle(text) {
        titleEl.textContent = text || '';
        titleEl.setAttribute('title', text || '');
    }

    function showProgress(mode, label) {
        var title = mode === 'download' ? 'Скачивание файла' : 'Загрузка файла';
        if (label) {
            title += ': ' + label;
        }
        setTitle(title);
        barEl.style.width = '0%';
        barEl.classList.remove('progress-bar-animated');
        progressRoot.setAttribute('aria-valuenow', '0');
        metaEl.textContent = '0%';
        setBusy(true);
    }

    function updateProgress(loaded, total) {
        if (total > 0) {
            var percent = Math.min(100, Math.round((loaded / total) * 100));
            barEl.style.width = percent + '%';
            progressRoot.setAttribute('aria-valuenow', String(percent));
            metaEl.textContent = formatBytes(loaded) + ' / ' + formatBytes(total) + ' (' + percent + '%)';
            barEl.classList.remove('progress-bar-animated');
            return;
        }

        barEl.style.width = '100%';
        barEl.classList.add('progress-bar-animated');
        progressRoot.setAttribute('aria-valuenow', '0');
        metaEl.textContent = formatBytes(loaded) + ' · размер неизвестен';
    }

    function finishProgress() {
        barEl.style.width = '100%';
        barEl.classList.remove('progress-bar-animated');
        progressRoot.setAttribute('aria-valuenow', '100');
        window.setTimeout(function () {
            setBusy(false);
        }, 350);
    }

    /** Indeterminate / staged busy UI for non-XHR flows (e.g. Open in KeenetiX). */
    function showBusy(title, meta) {
        if (!overlay && !initOverlay()) {
            return;
        }
        setTitle(title || 'Передача');
        barEl.style.width = '35%';
        barEl.classList.add('progress-bar-animated', 'progress-bar-striped');
        progressRoot.setAttribute('aria-valuenow', '0');
        metaEl.textContent = meta || 'Подождите…';
        setBusy(true);
    }

    function setBusyMeta(meta) {
        if (!metaEl) {
            return;
        }
        metaEl.textContent = meta || '';
    }

    function setBusyPercent(percent, meta) {
        if (!barEl) {
            return;
        }
        var value = Math.max(0, Math.min(100, Math.round(percent)));
        barEl.style.width = value + '%';
        if (value >= 100) {
            barEl.classList.remove('progress-bar-animated');
        } else {
            barEl.classList.add('progress-bar-animated', 'progress-bar-striped');
        }
        progressRoot.setAttribute('aria-valuenow', String(value));
        if (meta != null) {
            metaEl.textContent = meta;
        }
    }

    function hideBusy() {
        if (!overlay) {
            return;
        }
        setBusy(false);
    }

    window.FileTransferProgress = {
        showBusy: showBusy,
        setBusyMeta: setBusyMeta,
        setBusyPercent: setBusyPercent,
        finish: finishProgress,
        hide: hideBusy,
    };

    function formHasNewFile(form) {
        var fileInput = form.querySelector('input[type="file"]');
        return Boolean(fileInput && fileInput.files && fileInput.files.length > 0);
    }

    function replaceDocument(html) {
        document.open();
        document.write(html);
        document.close();
    }

    function sameDocumentUrl(a, b) {
        try {
            return new URL(a, window.location.href).href.split('#')[0]
                === new URL(b, window.location.href).href.split('#')[0];
        } catch (err) {
            return a.split('#')[0] === b.split('#')[0];
        }
    }

    function submitFormNatively(form) {
        form.dataset.fileUploadNativeFallback = '1';
        if (typeof form.requestSubmit === 'function') {
            form.requestSubmit();
        } else {
            HTMLFormElement.prototype.submit.call(form);
        }
    }

    function uploadForm(form) {
        var submitButton = form.querySelector('[type="submit"]');
        var fileInput = form.querySelector('input[type="file"]');
        var fileName = fileInput && fileInput.files[0] ? fileInput.files[0].name : '';
        var formData = new FormData(form);
        var xhr = new XMLHttpRequest();
        var startUrl = form.getAttribute('action') || window.location.href;

        showProgress('upload', fileName);
        if (submitButton) {
            submitButton.disabled = true;
        }

        xhr.open(form.getAttribute('method') || 'POST', startUrl);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

        xhr.upload.addEventListener('progress', function (event) {
            updateProgress(event.loaded, event.total);
        });

        xhr.addEventListener('load', function () {
            if (submitButton) {
                submitButton.disabled = false;
            }

            if (xhr.status >= 200 && xhr.status < 400) {
                var finalUrl = xhr.responseURL || startUrl;
                if (!sameDocumentUrl(finalUrl, startUrl)) {
                    finishProgress();
                    window.location.href = finalUrl;
                    return;
                }
            }

            finishProgress();
            replaceDocument(xhr.responseText);
        });

        xhr.addEventListener('error', function () {
            if (submitButton) {
                submitButton.disabled = false;
            }
            setBusy(false);
            // Chrome: ERR_UPLOAD_FILE_CHANGED when the file was edited after pick (Excel/OneDrive).
            // Fall back to a normal form POST so the wizard still works when XHR is blocked.
            if (form.dataset.fileUploadNativeFallback !== '1') {
                submitFormNatively(form);
                return;
            }
            window.alert(
                'Не удалось загрузить файл. Если файл открыт в Excel — закройте его, '
                + 'заново выберите файл и повторите.'
            );
        });

        xhr.send(formData);
    }

    function downloadFile(link) {
        var url = link.getAttribute('href');
        var fileName = link.getAttribute('data-download-name') || '';
        var xhr = new XMLHttpRequest();

        showProgress('download', fileName || url.split('/').pop());
        xhr.open('GET', url);
        xhr.responseType = 'blob';

        xhr.addEventListener('progress', function (event) {
            updateProgress(event.loaded, event.total);
        });

        xhr.addEventListener('load', function () {
            if (xhr.status === 200) {
                var objectUrl = window.URL.createObjectURL(xhr.response);
                var anchor = document.createElement('a');
                anchor.href = objectUrl;
                anchor.download = fileName || 'download';
                document.body.appendChild(anchor);
                anchor.click();
                anchor.remove();
                window.setTimeout(function () {
                    window.URL.revokeObjectURL(objectUrl);
                }, 1000);
                finishProgress();
                return;
            }

            setBusy(false);
            window.open(url, '_blank', 'noopener');
        });

        xhr.addEventListener('error', function () {
            setBusy(false);
            window.open(url, '_blank', 'noopener');
        });

        xhr.send();
    }

    function bindUploadForms() {
        document.querySelectorAll('form[enctype="multipart/form-data"]').forEach(function (form) {
            if (form.dataset.fileUploadBound === 'true') {
                return;
            }
            if (form.dataset.nativeFileUpload === '1') {
                return;
            }
            if (!form.querySelector('input[type="file"]')) {
                return;
            }
            form.dataset.fileUploadBound = 'true';
            form.addEventListener('submit', function (event) {
                if (form.dataset.fileUploadNativeFallback === '1') {
                    form.dataset.fileUploadNativeFallback = '';
                    return;
                }
                if (!formHasNewFile(form)) {
                    return;
                }
                event.preventDefault();
                uploadForm(form);
            });
        });
    }

    function bindDownloadLinks() {
        document.querySelectorAll('a.file-download-link[href]').forEach(function (link) {
            if (link.dataset.fileDownloadBound === 'true') {
                return;
            }
            link.dataset.fileDownloadBound = 'true';
            link.addEventListener('click', function (event) {
                event.preventDefault();
                downloadFile(link);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!initOverlay()) {
            return;
        }
        bindUploadForms();
        bindDownloadLinks();
    });
})();
