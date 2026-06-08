(function () {
    'use strict';

    const CYRILLIC = {
        а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
        и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
        с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch',
        ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
    };

    function transliterate(text) {
        return (text || '')
            .trim()
            .toLowerCase()
            .split('')
            .map((char) => CYRILLIC[char] ?? char)
            .join('');
    }

    function normalizeIdentifier(text, maxLength) {
        let slug = transliterate(text)
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_+|_+$/g, '');
        if (!slug) {
            return '';
        }
        if (/^[0-9]/.test(slug)) {
            slug = `f_${slug}`;
        }
        if (maxLength && slug.length > maxLength) {
            slug = slug.slice(0, maxLength).replace(/_+$/, '');
        }
        return slug;
    }

    function bindTypePreview() {
        const nameInput = document.querySelector('[data-structure-code-source]');
        const codePreview = document.getElementById('structure-code-preview');
        const tablePreview = document.getElementById('structure-table-preview');
        if (!nameInput || !codePreview || !tablePreview) {
            return;
        }

        const update = () => {
            const code = normalizeIdentifier(nameInput.value, 50);
            codePreview.textContent = code || '—';
            tablePreview.textContent = code ? `structures_${code}` : '—';
        };

        nameInput.addEventListener('input', update);
        update();
    }

    function bindFieldNameAutofill(row) {
        const labelInput = row.querySelector('[data-structure-field-label]');
        const nameInput = row.querySelector('[data-structure-field-name]');
        if (!labelInput || !nameInput) {
            return;
        }

        let manual = Boolean(nameInput.value.trim());

        nameInput.addEventListener('input', () => {
            manual = Boolean(nameInput.value.trim());
        });

        labelInput.addEventListener('input', () => {
            if (manual) {
                return;
            }
            nameInput.value = normalizeIdentifier(labelInput.value, 63);
        });
    }

    function getTotalFormsInput() {
        return document.querySelector('input[name="fields-TOTAL_FORMS"]');
    }

    function getNextIndex() {
        const totalInput = getTotalFormsInput();
        if (!totalInput) {
            return 0;
        }
        return parseInt(totalInput.value, 10);
    }

    function incrementTotalForms(nextIdx) {
        const totalInput = getTotalFormsInput();
        if (totalInput) {
            totalInput.value = String(nextIdx + 1);
        }
    }

    function appendRowFromTemplate() {
        const template = document.getElementById('field-row-template');
        const tbody = document.getElementById('structure-field-rows');
        if (!template || !tbody) {
            return null;
        }

        const nextIdx = getNextIndex();
        const html = template.innerHTML.replace(/__idx__/g, String(nextIdx));
        tbody.insertAdjacentHTML('beforeend', html);
        const newRow = tbody.lastElementChild;
        incrementTotalForms(nextIdx);

        if (newRow) {
            bindFieldNameAutofill(newRow);
            bindDeleteButtons(newRow);
            bindDuplicateButton(newRow);
        }
        return newRow;
    }

    function copyRowValues(sourceRow, targetRow) {
        sourceRow.querySelectorAll('[name]').forEach((sourceInput) => {
            const suffix = sourceInput.name.replace(/^fields-\d+-/, '');
            const targetInput = targetRow.querySelector(`[name$="-${suffix}"]`);
            if (!targetInput) {
                return;
            }
            if (targetInput.type === 'checkbox') {
                targetInput.checked = sourceInput.checked;
            } else {
                targetInput.value = sourceInput.value;
            }
        });
    }

    function reindexForms() {
        const tbody = document.getElementById('structure-field-rows');
        const totalInput = getTotalFormsInput();
        if (!tbody || !totalInput) {
            return;
        }

        const rows = Array.from(tbody.querySelectorAll('[data-structure-field-row]'));
        rows.forEach((row, idx) => {
            row.querySelectorAll('[name]').forEach((input) => {
                input.name = input.name.replace(/^fields-\d+-/, `fields-${idx}-`);
                if (input.id) {
                    input.id = input.id.replace(/^id_fields-\d+-/, `id_fields-${idx}-`);
                }
            });
        });
        totalInput.value = String(rows.length);
    }

    function bindDeleteButtons(row) {
        const deleteBtn = row.querySelector('.delete-row-btn');
        if (!deleteBtn || deleteBtn.dataset.bound === 'true') {
            return;
        }
        deleteBtn.dataset.bound = 'true';

        deleteBtn.addEventListener('click', () => {
            const idInput = row.querySelector('input[name$="-id"]');
            const deleteInput = row.querySelector('input[name$="-DELETE"]');

            if (idInput && idInput.value && deleteInput) {
                deleteInput.checked = true;
                row.classList.add('d-none');
                return;
            }

            row.remove();
            reindexForms();
        });
    }

    function bindDuplicateButton(row) {
        const dupBtn = row.querySelector('.duplicate-row-btn');
        if (!dupBtn || dupBtn.dataset.bound === 'true') {
            return;
        }
        dupBtn.dataset.bound = 'true';

        dupBtn.addEventListener('click', () => {
            const newRow = appendRowFromTemplate();
            if (newRow) {
                copyRowValues(row, newRow);
            }
        });
    }

    function bindAddFieldButton() {
        const addBtn = document.getElementById('add-field-btn');
        if (!addBtn || addBtn.dataset.bound === 'true') {
            return;
        }
        addBtn.dataset.bound = 'true';
        addBtn.addEventListener('click', () => {
            appendRowFromTemplate();
        });
    }

    function bindFieldRows() {
        document.querySelectorAll('[data-structure-field-row]').forEach((row) => {
            bindFieldNameAutofill(row);
            bindDeleteButtons(row);
            bindDuplicateButton(row);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindTypePreview();
        bindFieldRows();
        bindAddFieldButton();
    });
})();
