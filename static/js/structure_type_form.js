(function () {
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

    function bindFieldRows() {
        document.querySelectorAll('[data-structure-field-row]').forEach(bindFieldNameAutofill);
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindTypePreview();
        bindFieldRows();
    });
})();
