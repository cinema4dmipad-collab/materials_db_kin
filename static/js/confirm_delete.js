/**
 * In-page delete confirmation (Bootstrap modal) instead of a separate page.
 *
 * Triggers:
 * - click [data-confirm-delete] — POST to href or data-confirm-url
 * - submit [data-confirm-delete-form] — confirm, then submit the same form
 * - window.AppConfirmDelete.ask({...}) — used by list bulk-select
 */
(function (window, document) {
    'use strict';

    var DEFAULT_TITLE = 'Удаление';
    var DEFAULT_MESSAGE = 'Удалить эту запись? Действие нельзя отменить.';
    var DEFAULT_SUBMIT = 'Удалить';

    var modalEl = null;
    var modal = null;
    var titleEl = null;
    var bodyEl = null;
    var submitBtn = null;
    var postForm = null;
    var pending = null;

    function ensureUi() {
        if (modalEl) {
            return Boolean(modal);
        }
        modalEl = document.getElementById('app-confirm-delete-modal');
        postForm = document.getElementById('app-confirm-delete-form');
        if (!modalEl || !postForm || !window.bootstrap || !window.bootstrap.Modal) {
            return false;
        }
        titleEl = modalEl.querySelector('[data-confirm-delete-title]');
        bodyEl = modalEl.querySelector('[data-confirm-delete-body]');
        submitBtn = modalEl.querySelector('[data-confirm-delete-submit]');
        modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
        if (submitBtn) {
            submitBtn.addEventListener('click', onConfirm);
        }
        modalEl.addEventListener('hidden.bs.modal', function () {
            pending = null;
        });
        return true;
    }

    function setBody(message, messageHtml) {
        if (!bodyEl) {
            return;
        }
        if (messageHtml) {
            bodyEl.innerHTML = messageHtml;
        } else {
            bodyEl.textContent = message || DEFAULT_MESSAGE;
        }
    }

    function ask(options) {
        options = options || {};
        if (!ensureUi()) {
            if (typeof options.onFallback === 'function') {
                options.onFallback();
                return;
            }
            if (options.type === 'form' && options.form) {
                options.form.dataset.confirmDeleteBypass = '1';
                if (typeof options.form.requestSubmit === 'function') {
                    options.form.requestSubmit();
                } else {
                    options.form.submit();
                }
                return;
            }
            if (options.type === 'post-url' && options.url && window.confirm(options.message || DEFAULT_MESSAGE)) {
                postViaTempForm(options.url);
            }
            return;
        }
        if (titleEl) {
            titleEl.textContent = options.title || DEFAULT_TITLE;
        }
        setBody(options.message, options.messageHtml);
        if (submitBtn) {
            submitBtn.textContent = options.submitLabel || DEFAULT_SUBMIT;
        }
        pending = options;
        modal.show();
    }

    function clearExtraFields(form) {
        Array.prototype.slice.call(form.querySelectorAll('input')).forEach(function (input) {
            if (input.name === 'csrfmiddlewaretoken') {
                return;
            }
            input.parentNode.removeChild(input);
        });
    }

    function postViaTempForm(url, extraFields) {
        if (!postForm) {
            return;
        }
        postForm.action = url;
        clearExtraFields(postForm);
        if (extraFields) {
            Object.keys(extraFields).forEach(function (name) {
                var values = extraFields[name];
                if (!Array.isArray(values)) {
                    values = [values];
                }
                values.forEach(function (value) {
                    var input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = name;
                    input.value = value;
                    postForm.appendChild(input);
                });
            });
        }
        postForm.submit();
    }

    function ensureConfirmField(form) {
        var conf = form.querySelector('input[name="confirm"]');
        if (!conf) {
            conf = document.createElement('input');
            conf.type = 'hidden';
            conf.name = 'confirm';
            form.appendChild(conf);
        }
        conf.value = '1';
    }

    function onConfirm() {
        if (!pending) {
            return;
        }
        var current = pending;
        pending = null;
        if (modal) {
            modal.hide();
        }
        if (current.type === 'form' && current.form) {
            if (current.requireConfirmField) {
                ensureConfirmField(current.form);
            }
            current.form.dataset.confirmDeleteBypass = '1';
            if (typeof current.form.requestSubmit === 'function') {
                current.form.requestSubmit();
            } else {
                current.form.submit();
            }
            return;
        }
        if (current.type === 'post-url' && current.url) {
            postViaTempForm(current.url, current.fields || null);
        }
    }

    function messageFromEl(el) {
        return el.getAttribute('data-confirm-message') || DEFAULT_MESSAGE;
    }

    function titleFromEl(el) {
        return el.getAttribute('data-confirm-title') || DEFAULT_TITLE;
    }

    function submitLabelFromEl(el) {
        return el.getAttribute('data-confirm-submit') || DEFAULT_SUBMIT;
    }

    document.addEventListener('click', function (event) {
        var el = event.target.closest('[data-confirm-delete]');
        if (!el) {
            return;
        }
        var url = el.getAttribute('data-confirm-url') || el.getAttribute('href');
        if (!url || url === '#') {
            return;
        }
        event.preventDefault();
        ask({
            type: 'post-url',
            url: url,
            title: titleFromEl(el),
            message: messageFromEl(el),
            submitLabel: submitLabelFromEl(el),
        });
    });

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches('[data-confirm-delete-form]')) {
            return;
        }
        if (form.dataset.confirmDeleteBypass === '1') {
            delete form.dataset.confirmDeleteBypass;
            return;
        }
        event.preventDefault();
        ask({
            type: 'form',
            form: form,
            title: titleFromEl(form),
            message: messageFromEl(form),
            submitLabel: submitLabelFromEl(form),
            requireConfirmField: form.hasAttribute('data-confirm-require-flag'),
        });
    });

    window.AppConfirmDelete = {
        ask: ask,
        DEFAULT_MESSAGE: DEFAULT_MESSAGE,
    };
})(window, document);
