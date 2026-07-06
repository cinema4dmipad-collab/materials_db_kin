(function () {
    'use strict';

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getWorkspaceUsers() {
        var node = document.getElementById('workspace-users-data');
        if (!node) {
            return [];
        }
        try {
            var parsed = JSON.parse(node.textContent);
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    function userMetaLine(item) {
        var parts = [];
        if (item.full_name) {
            parts.push(escapeHtml(item.full_name));
        }
        if (item.email) {
            parts.push(escapeHtml(item.email));
        }
        return parts.join(' · ') || '—';
    }

    function renderList(options) {
        options = options || {};
        var filterText = options.filterText || '';
        var getUsedUserIds = options.getUsedUserIds || function () { return new Set(); };

        var listNode = document.getElementById('workspace-users-list');
        var emptyNode = document.getElementById('workspace-users-empty');
        var addBtn = document.getElementById('workspace-users-add-btn');
        if (!listNode || !emptyNode || !addBtn) {
            return;
        }

        var query = filterText.trim().toLowerCase();
        var usedUserIds = getUsedUserIds();
        var allUsers = getWorkspaceUsers();
        var users = allUsers.filter(function (item) {
            if (!query) {
                return true;
            }
            var haystack = [
                item.username,
                item.full_name,
                item.email,
            ].join(' ').toLowerCase();
            return haystack.indexOf(query) !== -1;
        });

        listNode.innerHTML = '';
        if (!allUsers.length) {
            emptyNode.classList.remove('d-none');
            addBtn.disabled = true;
            return;
        }
        emptyNode.classList.add('d-none');

        if (!users.length) {
            listNode.innerHTML = '<p class="text-muted small mb-0">Ничего не найдено.</p>';
            addBtn.disabled = true;
            return;
        }

        users.forEach(function (item) {
            var userId = String(item.user_id);
            var isUsed = usedUserIds.has(userId);
            var initials = escapeHtml((item.username || '?').slice(0, 2).toUpperCase());
            var itemEl = document.createElement('label');
            itemEl.className = 'reference-property-item workspace-user-item' + (isUsed ? ' is-used' : '');
            itemEl.innerHTML = ''
                + '<input type="checkbox" class="form-check-input mt-1 workspace-user-checkbox"'
                + ' value="' + escapeHtml(userId) + '"' + (isUsed ? ' disabled' : '') + '>'
                + '<span class="user-picker__badge" aria-hidden="true">' + initials + '</span>'
                + '<span class="flex-grow-1">'
                + '<span class="fw-semibold">' + escapeHtml(item.username || '—') + '</span>'
                + '<div class="reference-property-item__meta">'
                + userMetaLine(item)
                + (isUsed ? ' · уже в списке' : '')
                + '</div>'
                + '</span>';
            itemEl.querySelector('input').dataset.userPayload = JSON.stringify(item);
            listNode.appendChild(itemEl);
        });

        addBtn.disabled = true;
        listNode.querySelectorAll('.workspace-user-checkbox').forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                var selected = listNode.querySelectorAll('.workspace-user-checkbox:checked:not(:disabled)');
                addBtn.disabled = selected.length === 0;
            });
        });
    }

    function bind(options) {
        options = options || {};
        var openButtonId = options.openButtonId;
        var getUsedUserIds = options.getUsedUserIds;
        var onConfirm = options.onConfirm;

        if (!openButtonId || !getUsedUserIds || !onConfirm) {
            return null;
        }

        var openBtn = document.getElementById(openButtonId);
        var modalEl = document.getElementById('workspace-users-modal');
        var searchInput = document.getElementById('workspace-users-search');
        var addBtn = document.getElementById('workspace-users-add-btn');
        if (!openBtn || !modalEl || !searchInput || !addBtn || openBtn.dataset.workspaceUsersPickerBound === 'true') {
            return null;
        }
        openBtn.dataset.workspaceUsersPickerBound = 'true';

        function getModal() {
            if (!window.bootstrap || !window.bootstrap.Modal) {
                return null;
            }
            return window.bootstrap.Modal.getOrCreateInstance(modalEl);
        }

        function renderCurrentList(filterText) {
            renderList({
                filterText: filterText,
                getUsedUserIds: getUsedUserIds,
            });
        }

        openBtn.addEventListener('click', function () {
            searchInput.value = '';
            renderCurrentList('');
            var modal = getModal();
            if (modal) {
                modal.show();
            }
        });

        searchInput.addEventListener('input', function () {
            renderCurrentList(searchInput.value);
        });

        addBtn.addEventListener('click', function () {
            var selected = modalEl.querySelectorAll('.workspace-user-checkbox:checked:not(:disabled)');
            var payloads = [];
            selected.forEach(function (checkbox) {
                try {
                    payloads.push(JSON.parse(checkbox.dataset.userPayload || '{}'));
                } catch (error) {
                    /* skip invalid payload */
                }
            });
            if (payloads.length) {
                onConfirm(payloads);
            }
            var modal = getModal();
            if (modal) {
                modal.hide();
            }
        });

        return getModal();
    }

    window.WorkspaceUsersPicker = {
        escapeHtml: escapeHtml,
        getWorkspaceUsers: getWorkspaceUsers,
        renderList: renderList,
        bind: bind,
    };
})();
