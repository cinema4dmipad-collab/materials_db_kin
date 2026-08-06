/**
 * KeenetiX desktop channel via Lab API (same user / PAT owner).
 * Last KeenetiX that connected with the token receives open_scan commands.
 * No keenetix:// protocol / console launcher.
 */
(function () {
    'use strict';

    var POLL_MS = 5000;
    var lastOnline = false;

    function csrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (match) {
            return decodeURIComponent(match[1]);
        }
        var input = document.querySelector('input[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function apiFetch(path, options) {
        options = options || {};
        var headers = options.headers || {};
        headers['Accept'] = 'application/json';
        if (options.method && options.method !== 'GET') {
            headers['Content-Type'] = 'application/json';
            var csrf = csrfToken();
            if (csrf) {
                headers['X-CSRFToken'] = csrf;
            }
        }
        return fetch(path, {
            method: options.method || 'GET',
            headers: headers,
            body: options.body ? JSON.stringify(options.body) : undefined,
            credentials: 'same-origin',
            cache: 'no-store',
        }).then(function (resp) {
            return resp.json().catch(function () { return {}; }).then(function (data) {
                return { ok: resp.ok, status: resp.status, data: data };
            });
        });
    }

    function flash(message, kind) {
        if (window.AppFlash && typeof window.AppFlash.show === 'function') {
            window.AppFlash.show(message, kind);
            return;
        }
        window.alert(message);
    }

    function progressApi() {
        return window.FileTransferProgress || null;
    }

    function setPresence(online, detail) {
        lastOnline = !!online;
        var el = document.getElementById('keenetix-bridge-presence');
        if (!el) {
            return;
        }
        el.dataset.state = online ? 'online' : 'offline';
        el.classList.remove(
            'keenetix-bridge-presence--offline',
            'keenetix-bridge-presence--online',
            'keenetix-bridge-presence--paired'
        );
        if (online) {
            el.classList.add('keenetix-bridge-presence--paired');
            el.title = detail || 'KeenetiX подключён — сканы откроются в текущем окне';
        } else {
            el.classList.add('keenetix-bridge-presence--offline');
            el.title = detail || 'KeenetiX не подключён. Запустите приложение с токеном этого пользователя';
        }
        el.textContent = 'KeenetiX';
    }

    function refreshStatus() {
        return apiFetch('/api/v1/desktop/status/').then(function (res) {
            if (res && res.ok && res.data && res.data.online) {
                setPresence(true);
            } else {
                setPresence(false);
            }
            return res;
        }).catch(function () {
            setPresence(false);
            return null;
        });
    }

    function openScan(scanId, workspaceId) {
        return apiFetch('/api/v1/desktop/open-scan/', {
            method: 'POST',
            body: {
                scan_id: scanId,
                workspace_id: workspaceId || '',
            },
        }).then(function (res) {
            if (res.status === 503 || (res.data && res.data.error === 'desktop_offline')) {
                throw new Error('desktop_offline');
            }
            if (!res.ok) {
                throw new Error((res.data && (res.data.detail || res.data.error)) || ('HTTP ' + res.status));
            }
            return res.data;
        });
    }

    function openViaDesktop(a) {
        var scanId = a.getAttribute('data-scan-id') || '';
        var workspaceId = a.getAttribute('data-workspace-id') || '';
        var progress = progressApi();
        if (a.dataset.keenetixBusy === '1') {
            return Promise.resolve();
        }
        a.dataset.keenetixBusy = '1';
        if (progress) {
            progress.showBusy('Открытие в KeenetiX', 'Проверка подключения…');
            progress.setBusyPercent(20, 'Проверка подключения…');
        }
        return refreshStatus().then(function () {
            if (!lastOnline) {
                if (progress) {
                    progress.hide();
                }
                flash('KeenetiX не подключён. Запустите KeenetiX Pro с токеном этого пользователя.', 'warning');
                return;
            }
            if (progress) {
                progress.setBusyPercent(55, 'Отправка команды в KeenetiX…');
            }
            return openScan(scanId, workspaceId).then(function () {
                if (progress) {
                    progress.setBusyPercent(100, 'Команда отправлена — скачивание в KeenetiX');
                    progress.finish();
                }
                flash('Скан отправлен в KeenetiX', 'success');
                a.classList.add('keenetix-bridge-open--ok');
            }).catch(function (err) {
                if (progress) {
                    progress.hide();
                }
                if (String(err && err.message) === 'desktop_offline') {
                    flash('KeenetiX отключился. Запустите приложение снова.', 'warning');
                    setPresence(false);
                    return;
                }
                flash('Не удалось открыть скан в KeenetiX', 'danger');
            });
        }).catch(function () {
            if (progress) {
                progress.hide();
            }
            flash('Не удалось открыть скан в KeenetiX', 'danger');
        }).finally(function () {
            delete a.dataset.keenetixBusy;
        });
    }

    function bindOpenButtons() {
        document.addEventListener('click', function (ev) {
            var a = ev.target.closest('a[data-keenetix-open-scan], button[data-keenetix-open-scan]');
            if (!a || !a.getAttribute('data-scan-id')) {
                return;
            }
            ev.preventDefault();
            openViaDesktop(a);
        });
    }

    function bindPresenceClick() {
        var el = document.getElementById('keenetix-bridge-presence');
        if (!el) {
            return;
        }
        el.style.cursor = 'default';
        el.addEventListener('click', function () {
            refreshStatus().then(function () {
                if (lastOnline) {
                    flash('KeenetiX онлайн', 'success');
                } else {
                    flash('Запустите KeenetiX Pro с токеном этого пользователя', 'warning');
                }
            });
        });
    }

    function init() {
        bindOpenButtons();
        bindPresenceClick();
        refreshStatus();
        setInterval(refreshStatus, POLL_MS);
    }

    window.KeenetixBridge = {
        refreshStatus: refreshStatus,
        openScan: openScan,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
