(function () {
    'use strict';

    function normalizeIdentifier(text, maxLength) {
        if (window.PropertyNameAutofill && typeof window.PropertyNameAutofill.normalizeIdentifier === 'function') {
            return window.PropertyNameAutofill.normalizeIdentifier(text, maxLength);
        }
        var CYRILLIC = {
            а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
            и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
            с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch',
            ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
        };
        var slug = (text || '')
            .trim()
            .toLowerCase()
            .split('')
            .map(function (char) {
                return Object.prototype.hasOwnProperty.call(CYRILLIC, char) ? CYRILLIC[char] : char;
            })
            .join('')
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_+|_+$/g, '');
        if (!slug) {
            return '';
        }
        if (/^[0-9]/.test(slug)) {
            slug = 'f_' + slug;
        }
        if (maxLength && slug.length > maxLength) {
            slug = slug.slice(0, maxLength).replace(/_+$/, '');
        }
        return slug;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var sourceInput = document.querySelector('[data-dictionary-name-source]');
        var targetInput = document.querySelector('[data-dictionary-code-target]');
        if (!sourceInput || !targetInput) {
            return;
        }
        var form = sourceInput.form;
        var isCreate = form && form.getAttribute('data-dictionary-form-mode') === 'create';
        var codeEditedManually = !isCreate;

        targetInput.addEventListener('input', function () {
            codeEditedManually = true;
        });

        sourceInput.addEventListener('input', function () {
            if (codeEditedManually) {
                return;
            }
            targetInput.value = normalizeIdentifier(sourceInput.value, 64);
        });
    });
})();
