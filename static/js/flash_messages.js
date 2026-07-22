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

    function initFlashMessages() {
        var container = document.getElementById('app-flash-messages');
        if (!container) {
            return;
        }
        var alerts = container.querySelectorAll('.app-flash-alert');
        alerts.forEach(function (el) {
            var delay = dismissDelay(el);
            if (delay === null) {
                return;
            }
            window.setTimeout(function () {
                dismissAlert(el);
            }, delay);
        });
    }

    document.addEventListener('DOMContentLoaded', initFlashMessages);
})();
