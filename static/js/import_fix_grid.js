(function () {
    'use strict';

    var form = document.getElementById('import-unrecognized-form');
    var grid = document.getElementById('import-fix-grid');
    var editor = document.getElementById('import-fix-editor');
    if (!form || !grid || !editor) {
        return;
    }

    var editorMeta = document.getElementById('import-fix-editor-meta');
    var editorRaw = document.getElementById('import-fix-editor-raw');
    var editorInput = document.getElementById('import-fix-editor-input');
    var editorSkip = document.getElementById('import-fix-editor-skip');
    var editorClose = document.getElementById('import-fix-editor-close');
    var jumpBtn = document.getElementById('import-unrecognized-jump');
    var gridWrap = document.getElementById('import-fix-grid-wrap');
    var selectedCell = null;
    var jumpIndex = -1;

    function problemCells() {
        return Array.prototype.slice.call(
            grid.querySelectorAll('[data-fix-cell].is-unrecognized')
        );
    }

    function setCellDisplay(cell, text) {
        var value = (text || '').trim();
        if (value) {
            cell.textContent = value;
            return;
        }
        cell.textContent = '';
        var empty = document.createElement('span');
        empty.className = 'import-fix-cell__empty';
        empty.innerHTML = '&nbsp;';
        cell.appendChild(empty);
    }

    function updateAttentionCount() {
        var remaining = problemCells().length;
        var countEl = document.getElementById('import-fix-attention-count');
        if (countEl) {
            countEl.textContent = String(remaining);
        }
        updatePanelResolvedState(remaining);
    }

    function updatePanelResolvedState(remaining) {
        var panel = document.getElementById('import-unrecognized-fields');
        var titleText = document.getElementById('import-unrecognized-title-text');
        var hint = document.getElementById('import-unrecognized-hint');
        var label = document.getElementById('import-fix-attention-label');
        var resolved = remaining === 0;

        if (panel) {
            panel.classList.toggle('is-resolved', resolved);
        }
        if (jumpBtn) {
            jumpBtn.classList.toggle('text-bg-warning', !resolved);
            jumpBtn.classList.toggle('text-bg-success', resolved);
            jumpBtn.textContent = resolved ? 'Исправлено' : 'Предупреждение';
            jumpBtn.title = resolved
                ? 'Все проблемные значения обработаны'
                : 'Перейти к следующей проблемной ячейке';
            jumpBtn.setAttribute(
                'aria-label',
                resolved
                    ? 'Все ошибки исправлены'
                    : 'Перейти к следующей проблемной ячейке'
            );
            jumpBtn.disabled = resolved;
        }
        if (titleText) {
            titleText.textContent = resolved
                ? 'Ошибки исправлены'
                : 'Нераспознанные значения';
        }
        if (label) {
            label.textContent = resolved ? 'осталось проблем' : 'требуют внимания';
        }
        if (hint) {
            hint.textContent = resolved
                ? 'Все жёлтые ячейки обработаны. Можно нажимать «Записать».'
                : (
                    'В таблице — все значения, которые будут записаны в базу. '
                    + 'Подсвеченные ячейки система не разобрала: кликните ячейку или бейдж «Предупреждение», '
                    + 'чтобы переходить по ним по кругу и править значение ниже. '
                    + 'Исправленные ячейки подсвечиваются зелёным.'
                );
        }
    }

    function applyCellResolution(cell) {
        if (!cell) {
            return;
        }
        var inputName = cell.getAttribute('data-input-name') || '';
        var raw = cell.getAttribute('data-raw') || '';
        var valueInput = hiddenValue(inputName);
        var skipInput = hiddenSkip(inputName);
        var skipped = !!(skipInput && skipInput.checked);
        var value = valueInput ? valueInput.value : '';

        cell.classList.remove('is-skipped', 'is-fixed', 'is-unrecognized');
        if (skipped) {
            cell.classList.add('is-skipped');
            cell.title = 'Игнорируется при записи: ' + (raw || '—');
            setCellDisplay(cell, raw);
        } else if (String(value).trim() !== '') {
            cell.classList.add('is-fixed');
            cell.title = 'Исправлено: ' + String(value).trim();
            setCellDisplay(cell, value);
        } else {
            cell.classList.add('is-unrecognized');
            cell.title = 'Клик — исправить: ' + (raw || '');
            setCellDisplay(cell, raw);
        }
        updateAttentionCount();
    }

    function hiddenValue(inputName) {
        return form.querySelector('[data-fix-input="' + CSS.escape(inputName) + '"]');
    }

    function hiddenSkip(inputName) {
        return form.querySelector('[data-fix-skip="' + CSS.escape(inputName) + '"]');
    }

    function clearHeaderHighlights() {
        grid.querySelectorAll('.is-active-col').forEach(function (el) {
            el.classList.remove('is-active-col');
        });
    }

    function highlightHeaders(cell) {
        clearHeaderHighlights();
        var colIndex = cell.getAttribute('data-col-index');
        if (colIndex == null) {
            return;
        }
        grid.querySelectorAll('thead [data-col-index="' + colIndex + '"]').forEach(function (el) {
            el.classList.add('is-active-col');
        });
    }

    function scrollCellInGridOnly(cell) {
        if (!cell || !gridWrap) {
            return;
        }
        var wrapRect = gridWrap.getBoundingClientRect();
        var cellRect = cell.getBoundingClientRect();
        var nameCell = grid.querySelector('.import-fix-grid__name');
        var nameWidth = nameCell ? (nameCell.offsetWidth || 0) : 0;
        var pad = 8;

        var deltaTop = 0;
        if (cellRect.top < wrapRect.top + pad) {
            deltaTop = cellRect.top - wrapRect.top - pad;
        } else if (cellRect.bottom > wrapRect.bottom - pad) {
            deltaTop = cellRect.bottom - wrapRect.bottom + pad;
        }

        var deltaLeft = 0;
        var leftLimit = wrapRect.left + nameWidth + pad;
        if (cellRect.left < leftLimit) {
            deltaLeft = cellRect.left - leftLimit;
        } else if (cellRect.right > wrapRect.right - pad) {
            deltaLeft = cellRect.right - wrapRect.right + pad;
        }

        if (deltaTop) {
            gridWrap.scrollTop += deltaTop;
        }
        if (deltaLeft) {
            gridWrap.scrollLeft += deltaLeft;
        }
    }

    function focusWithoutPageScroll(el) {
        if (!el) {
            return;
        }
        try {
            el.focus({ preventScroll: true });
        } catch (err) {
            el.focus();
        }
    }

    function clearSelection() {
        if (selectedCell) {
            selectedCell.classList.remove('is-selected');
            selectedCell = null;
        }
        clearHeaderHighlights();
        editor.classList.add('d-none');
        editor.hidden = true;
        editor.removeAttribute('data-active-input');
        if (editorInput) {
            editorInput.value = '';
            editorInput.disabled = false;
        }
    }

    function selectCell(cell, options) {
        if (!cell || !cell.hasAttribute('data-fix-cell')) {
            return;
        }
        options = options || {};
        if (selectedCell) {
            selectedCell.classList.remove('is-selected');
        }
        selectedCell = cell;
        selectedCell.classList.add('is-selected');
        highlightHeaders(cell);
        jumpIndex = problemCells().indexOf(cell);

        var inputName = cell.getAttribute('data-input-name') || '';
        var material = cell.getAttribute('data-material-label') || '';
        var sourceRow = cell.getAttribute('data-source-row') || '';
        var target = cell.getAttribute('data-target-label') || '';
        var column = cell.getAttribute('data-column-label') || '';
        var raw = cell.getAttribute('data-raw') || '';

        if (editorMeta) {
            editorMeta.textContent = 'строка ' + sourceRow
                + ' · ' + material
                + ' · ' + target
                + (column ? ' ← «' + column + '»' : '');
        }
        if (editorRaw) {
            editorRaw.textContent = raw || '—';
        }

        var valueInput = hiddenValue(inputName);
        var skipInput = hiddenSkip(inputName);
        editor.setAttribute('data-active-input', inputName);
        if (editorInput) {
            editorInput.value = valueInput ? valueInput.value : raw;
            editorInput.disabled = !!(skipInput && skipInput.checked);
        }
        if (editorSkip) {
            editorSkip.checked = !!(skipInput && skipInput.checked);
        }

        editor.classList.remove('d-none');
        editor.hidden = false;
        scrollCellInGridOnly(cell);
        if (options.focusInput !== false && editorInput && !editorInput.disabled) {
            focusWithoutPageScroll(editorInput);
            editorInput.select();
        } else {
            focusWithoutPageScroll(cell);
        }
    }

    function jumpToNextProblem() {
        var cells = problemCells();
        if (!cells.length) {
            return;
        }
        jumpIndex = (jumpIndex + 1) % cells.length;
        // Не фокусируем поле ввода — иначе страница прыгает к редактору под таблицей.
        selectCell(cells[jumpIndex], { focusInput: false });
    }

    function syncFromEditor() {
        var inputName = editor.getAttribute('data-active-input') || '';
        if (!inputName) {
            return;
        }
        var valueInput = hiddenValue(inputName);
        var skipInput = hiddenSkip(inputName);
        if (valueInput && editorInput) {
            valueInput.value = editorInput.value;
        }
        if (skipInput && editorSkip) {
            skipInput.checked = editorSkip.checked;
        }
        if (editorInput) {
            editorInput.disabled = !!(editorSkip && editorSkip.checked);
        }
        applyCellResolution(selectedCell);
    }

    grid.addEventListener('click', function (event) {
        var cell = event.target.closest('[data-fix-cell]');
        if (!cell || !grid.contains(cell)) {
            return;
        }
        selectCell(cell);
    });

    grid.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        var cell = event.target.closest('[data-fix-cell]');
        if (!cell || !grid.contains(cell)) {
            return;
        }
        event.preventDefault();
        selectCell(cell);
    });

    if (jumpBtn) {
        jumpBtn.addEventListener('click', function (event) {
            event.preventDefault();
            jumpToNextProblem();
        });
    }

    if (editorInput) {
        editorInput.addEventListener('input', syncFromEditor);
        editorInput.addEventListener('change', syncFromEditor);
        editorInput.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter') {
                return;
            }
            // Enter в поле правки не должен жать «Записать».
            event.preventDefault();
            syncFromEditor();
            jumpToNextProblem();
        });
    }
    if (editorSkip) {
        editorSkip.addEventListener('change', syncFromEditor);
    }
    if (editorClose) {
        editorClose.addEventListener('click', clearSelection);
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !editor.hidden) {
            clearSelection();
        }
    });

    form.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || event.defaultPrevented) {
            return;
        }
        var target = event.target;
        if (!target) {
            return;
        }
        // Явный клик/фокус на submit — оставляем.
        if (target.type === 'submit') {
            return;
        }
        if (target.tagName === 'BUTTON' && target.type === 'submit') {
            return;
        }
        if (target.tagName === 'TEXTAREA') {
            return;
        }
        event.preventDefault();
    });

    form.addEventListener('submit', function () {
        syncFromEditor();
    });

    updateAttentionCount();
})();
