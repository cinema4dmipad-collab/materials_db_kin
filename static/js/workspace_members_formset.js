(function () {
    'use strict';

    var PREFIX = 'members';

    function reindexForms(container, totalFormsInput) {
        var rows = Array.from(container.querySelectorAll('.member-add-row'));
        rows.forEach(function (row, idx) {
            row.querySelectorAll('[name]').forEach(function (input) {
                input.name = input.name.replace(
                    new RegExp('^' + PREFIX + '-\\d+-'),
                    PREFIX + '-' + idx + '-',
                );
                if (input.id) {
                    input.id = input.id.replace(
                        new RegExp('^id_' + PREFIX + '-\\d+-'),
                        'id_' + PREFIX + '-' + idx + '-',
                    );
                }
            });
            row.querySelectorAll('label[for]').forEach(function (label) {
                var htmlFor = label.getAttribute('for');
                if (htmlFor) {
                    label.setAttribute(
                        'for',
                        htmlFor.replace(
                            new RegExp('^id_' + PREFIX + '-\\d+-'),
                            'id_' + PREFIX + '-' + idx + '-',
                        ),
                    );
                }
            });
        });
        totalFormsInput.value = String(rows.length);
    }

    function updateEmptyState(container) {
        var emptyRow = document.getElementById('members-add-empty-row');
        if (!emptyRow) {
            return;
        }
        var hasRows = container.querySelectorAll('.member-add-row').length > 0;
        emptyRow.classList.toggle('d-none', hasRows);
    }

    function getUsedUserIds(container) {
        var ids = new Set();
        container.querySelectorAll('.member-add-row [name$="-user"]').forEach(function (input) {
            if (input.value) {
                ids.add(String(input.value));
            }
        });
        return ids;
    }

    function buildUserCardHtml(payload) {
        var picker = window.WorkspaceUsersPicker;
        var escapeHtml = picker ? picker.escapeHtml : function (value) { return value; };
        var initials = escapeHtml((payload.username || '?').slice(0, 2).toUpperCase());
        var metaParts = [];
        if (payload.full_name) {
            metaParts.push(escapeHtml(payload.full_name));
        }
        if (payload.email) {
            metaParts.push(escapeHtml(payload.email));
        }
        var metaHtml = metaParts.length
            ? '<span class="user-picker__meta">' + metaParts.join(' · ') + '</span>'
            : '';

        return ''
            + '<div class="user-picker__option is-selected member-add-row__user-card-inner">'
            + '<span class="user-picker__badge" aria-hidden="true">' + initials + '</span>'
            + '<span class="user-picker__text">'
            + '<span class="user-picker__username">' + escapeHtml(payload.username || '—') + '</span>'
            + metaHtml
            + '</span>'
            + '</div>';
    }

    function fillMemberRow(row, payload) {
        var userInput = row.querySelector('[name$="-user"]');
        if (userInput) {
            userInput.value = String(payload.user_id);
        }
        var userCell = row.querySelector('.member-add-row__user-card');
        if (userCell) {
            userCell.innerHTML = buildUserCardHtml(payload);
            userCell.classList.remove('text-muted');
        }
    }

    function appendMemberFromTemplate(container, template, totalFormsInput) {
        var formIndex = parseInt(totalFormsInput.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, String(formIndex));
        container.insertAdjacentHTML('beforeend', html);
        totalFormsInput.value = String(formIndex + 1);
        var row = container.lastElementChild;
        bindDeleteButton(container, row, totalFormsInput);
        if (window.GroupPicker) {
            window.GroupPicker.initWithin(row);
        }
        updateEmptyState(container);
        return row;
    }

    function bindDeleteButton(container, row, totalFormsInput) {
        var deleteBtn = row.querySelector('.delete-member-row-btn');
        if (!deleteBtn || deleteBtn.dataset.bound === 'true') {
            return;
        }
        deleteBtn.dataset.bound = 'true';

        deleteBtn.addEventListener('click', function () {
            row.remove();
            reindexForms(container, totalFormsInput);
            updateEmptyState(container);
        });
    }

    function showClientError(container, message) {
        var alertEl = document.getElementById('members-add-client-error');
        var emptyRow = document.getElementById('members-add-empty-row');
        if (alertEl) {
            alertEl.textContent = message;
            alertEl.classList.remove('d-none');
        }
        if (emptyRow && !container.querySelectorAll('.member-add-row').length) {
            emptyRow.classList.add('members-add-empty-row--invalid');
        }
    }

    function hideClientError() {
        var alertEl = document.getElementById('members-add-client-error');
        var emptyRow = document.getElementById('members-add-empty-row');
        if (alertEl) {
            alertEl.textContent = '';
            alertEl.classList.add('d-none');
        }
        if (emptyRow) {
            emptyRow.classList.remove('members-add-empty-row--invalid');
        }
    }

    function validateBeforeSubmit(container) {
        var rows = container.querySelectorAll('.member-add-row');
        if (!rows.length) {
            return 'Добавьте хотя бы одного участника — нажмите «Добавить» и выберите пользователей.';
        }
        for (var i = 0; i < rows.length; i += 1) {
            var row = rows[i];
            var userInput = row.querySelector('[name$="-user"]');
            if (!userInput || !userInput.value) {
                return 'В каждой строке должен быть выбран пользователь.';
            }
            if (!row.querySelector('.group-picker-checkboxes input:checked')) {
                return 'Выберите хотя бы одну группу для каждого участника.';
            }
        }
        return null;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('member-add-forms-container');
        var template = document.getElementById('empty-member-form-template');
        var totalFormsInput = document.getElementById('id_members-TOTAL_FORMS');
        var picker = window.WorkspaceUsersPicker;
        var addForm = document.getElementById('members-add-form');
        var submitBtn = document.getElementById('members-add-submit-btn');

        if (!container || !template || !totalFormsInput || !picker) {
            return;
        }

        container.querySelectorAll('.member-add-row').forEach(function (row) {
            bindDeleteButton(container, row, totalFormsInput);
            if (window.GroupPicker) {
                window.GroupPicker.initWithin(row);
            }
            var userInput = row.querySelector('[name$="-user"]');
            if (userInput && userInput.value) {
                var users = picker.getWorkspaceUsers();
                for (var i = 0; i < users.length; i += 1) {
                    if (String(users[i].user_id) === String(userInput.value)) {
                        fillMemberRow(row, users[i]);
                        break;
                    }
                }
            }
        });

        picker.bind({
            openButtonId: 'add-members-btn',
            getUsedUserIds: function () {
                return getUsedUserIds(container);
            },
            onConfirm: function (payloads) {
                hideClientError();
                payloads.forEach(function (payload) {
                    var row = appendMemberFromTemplate(container, template, totalFormsInput);
                    fillMemberRow(row, payload);
                });
            },
        });

        if (addForm) {
            addForm.addEventListener('submit', function (event) {
                var errorMessage = validateBeforeSubmit(container);
                if (errorMessage) {
                    event.preventDefault();
                    showClientError(container, errorMessage);
                    updateEmptyState(container);
                    if (submitBtn) {
                        submitBtn.blur();
                    }
                    var target = document.getElementById('members-add-client-error')
                        || document.getElementById('members-add-empty-row');
                    if (target && target.scrollIntoView) {
                        target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                    return;
                }
                hideClientError();
                totalFormsInput.value = String(container.querySelectorAll('.member-add-row').length);
            });
        }

        updateEmptyState(container);
    });
})();
