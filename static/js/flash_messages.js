(function () {
    'use strict';

    var DEFAULT_DELAY_MS = 6000;
    var DELAYS_MS = {
        success: 5000,
        info: 5000,
        warning: 7000,
    };

    function alertKind(el) {
        var match = el.className.match(/\balert-(success|info|warning|danger|error|primary|secondary)\b/);
        return match ? match[1] : 'info';
    }

    function dismissDelay(el) {
        var kind = alertKind(el);
        if (kind === 'danger' || kind === 'error') {
            return null;
        }
        return DELAYS_MS[kind] || DEFAULT_DELAY_MS;
    }

    function dismissAlert(el) {
        if (!el || !el.isConnected) {
            return;
        }
        if (window.bootstrap && window.bootstrap.Alert) {
            window.bootstrap.Alert.getOrCreateInstance(el).close();
            return;
        }
        el.classList.remove('show');
        window.setTimeout(function () {
            if (el.parentNode) {
                el.parentNode.removeChild(el);
            }
        }, 300);
    }

    function scheduleDismiss(el) {
        var delay = dismissDelay(el);
        if (delay === null) {
            return;
        }
        window.setTimeout(function () {
            dismissAlert(el);
        }, delay);
    }

    function ensureContainer() {
        var container = document.getElementById('app-flash-messages');
        if (container) {
            return container;
        }
        container = document.createElement('div');
        container.id = 'app-flash-messages';
        container.className = 'app-flash-messages';
        var main = document.querySelector('.app-shell__content, .app-main--guest main, main');
        if (main) {
            main.insertBefore(container, main.firstChild);
        } else {
            document.body.insertBefore(container, document.body.firstChild);
        }
        return container;
    }

    function normalizeKind(kind) {
        var map = {
            ok: 'success',
            success: 'success',
            info: 'info',
            warn: 'warning',
            warning: 'warning',
            error: 'danger',
            danger: 'danger',
        };
        return map[kind] || 'info';
    }

    /** Show a Bootstrap flash alert at the top of the page (same as Django messages). */
    function showFlash(message, kind) {
        var text = String(message || '').trim();
        if (!text) {
            return null;
        }
        var tag = normalizeKind(kind);
        var container = ensureContainer();
        var el = document.createElement('div');
        el.className = 'alert alert-' + tag + ' alert-dismissible fade show app-flash-alert';
        el.setAttribute('role', 'alert');
        el.appendChild(document.createTextNode(text + ' '));
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'alert');
        closeBtn.setAttribute('aria-label', 'Закрыть');
        el.appendChild(closeBtn);
        container.appendChild(el);
        scheduleDismiss(el);
        try {
            el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (err) {
            /* ignore */
        }
        return el;
    }

    function initFlashMessages() {
        var container = document.getElementById('app-flash-messages');
        if (!container) {
            return;
        }
        container.querySelectorAll('.app-flash-alert').forEach(scheduleDismiss);
    }

    window.AppFlash = {
        show: showFlash,
    };

    document.addEventListener('DOMContentLoaded', initFlashMessages);
})();
