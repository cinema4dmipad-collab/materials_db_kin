(function () {
    'use strict';

    function rowHasValue(row) {
        var select = row.querySelector('select');
        return Boolean(select && String(select.value || '').trim());
    }

    function syncDictionaryFields(root) {
        var card = root || document.querySelector('[data-dictionary-fields]');
        if (!card) {
            return;
        }
        var emptyNode = card.querySelector('[data-dictionary-empty]');
        var addBtn = card.querySelector('#add-dictionary-field-btn');
        var rows = Array.from(card.querySelectorAll('[data-dictionary-row]'));
        var activeCount = 0;

        rows.forEach(function (row) {
            var name = row.getAttribute('data-dictionary-row');
            var addItem = card.querySelector('[data-dictionary-add="' + name + '"]');
            var isActive = row.getAttribute('data-dictionary-active') === '1' || rowHasValue(row);
            if (isActive) {
                row.classList.remove('d-none');
                row.setAttribute('data-dictionary-active', '1');
                activeCount += 1;
            } else {
                row.classList.add('d-none');
                row.removeAttribute('data-dictionary-active');
            }
            if (addItem) {
                addItem.classList.toggle('d-none', isActive);
                var listItem = addItem.closest('li');
                if (listItem) {
                    listItem.classList.toggle('d-none', isActive);
                }
            }
        });

        if (emptyNode) {
            emptyNode.hidden = activeCount > 0;
        }
        if (addBtn) {
            addBtn.disabled = activeCount >= rows.length;
            addBtn.classList.toggle('disabled', activeCount >= rows.length);
            addBtn.setAttribute('aria-disabled', activeCount >= rows.length ? 'true' : 'false');
        }
    }

    function showRow(card, name) {
        var row = card.querySelector('[data-dictionary-row="' + name + '"]');
        if (!row) {
            return;
        }
        row.classList.remove('d-none');
        row.setAttribute('data-dictionary-active', '1');
        if (window.ChoicePickerFields) {
            window.ChoicePickerFields.init(row);
        }
        var select = row.querySelector('select');
        var trigger = row.querySelector('.choice-picker__trigger');
        window.setTimeout(function () {
            if (trigger) {
                trigger.focus();
            } else if (select) {
                select.focus();
            }
        }, 0);
        syncDictionaryFields(card);
    }

    function hideRow(card, name) {
        var row = card.querySelector('[data-dictionary-row="' + name + '"]');
        if (!row) {
            return;
        }
        var select = row.querySelector('select');
        if (select) {
            select.value = '';
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        row.classList.add('d-none');
        row.removeAttribute('data-dictionary-active');
        syncDictionaryFields(card);
    }

    function initDictionaryFields(root) {
        var card = (root || document).querySelector('[data-dictionary-fields]');
        if (!card || card.dataset.dictionaryFieldsReady === '1') {
            return;
        }
        card.dataset.dictionaryFieldsReady = '1';

        card.querySelectorAll('[data-dictionary-add]').forEach(function (button) {
            button.addEventListener('click', function () {
                showRow(card, button.getAttribute('data-dictionary-add'));
            });
        });

        card.querySelectorAll('[data-dictionary-remove]').forEach(function (button) {
            button.addEventListener('click', function () {
                hideRow(card, button.getAttribute('data-dictionary-remove'));
            });
        });

        card.querySelectorAll('[data-dictionary-row] select').forEach(function (select) {
            select.addEventListener('change', function () {
                syncDictionaryFields(card);
            });
        });

        syncDictionaryFields(card);
    }

    window.MaterialDictionaryFields = {
        init: initDictionaryFields,
        sync: syncDictionaryFields,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initDictionaryFields();
        });
    } else {
        initDictionaryFields();
    }
})();
