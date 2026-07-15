(function () {
    'use strict';

    var CYRILLIC = {
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
            .map(function (char) {
                return Object.prototype.hasOwnProperty.call(CYRILLIC, char) ? CYRILLIC[char] : char;
            })
            .join('');
    }

    function normalizeIdentifier(text, maxLength) {
        var slug = transliterate(text)
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

    function syncPropertyTypeUi(form) {
        if (!form) {
            return;
        }
        var dataType = form.querySelector('[data-property-data-type]') || form.querySelector('#id_data_type');
        var unitInput = form.querySelector('#id_unit');
        var unitGroup = form.querySelector('[data-property-unit-group]')
            || (unitInput ? unitInput.closest('.mb-3') : null);
        var choicesSection = form.querySelector('[data-property-choices-section]');
        if (!dataType) {
            return;
        }
        var hideUnit = dataType.value === 'material_link' || dataType.value === 'choice';
        var showChoices = dataType.value === 'choice';
        if (unitGroup) {
            unitGroup.classList.toggle('d-none', hideUnit);
        }
        if (hideUnit && unitInput) {
            unitInput.value = '';
        }
        if (choicesSection) {
            choicesSection.classList.toggle('d-none', !showChoices);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var sourceInput = document.querySelector('[data-property-name-source]');
        var targetInput = document.querySelector('[data-property-name-target]');
        var form = sourceInput ? sourceInput.form : document.querySelector('form[data-property-form-mode]');

        if (form) {
            var dataType = form.querySelector('[data-property-data-type]') || form.querySelector('#id_data_type');
            syncPropertyTypeUi(form);
            if (dataType) {
                dataType.addEventListener('change', function () {
                    syncPropertyTypeUi(form);
                });
            }
        }

        if (!sourceInput || !targetInput) {
            return;
        }

        var isCreate = form && form.getAttribute('data-property-form-mode') === 'create';
        var nameEditedManually = !isCreate;

        targetInput.addEventListener('input', function () {
            nameEditedManually = true;
        });

        sourceInput.addEventListener('input', function () {
            if (nameEditedManually) {
                return;
            }
            targetInput.value = normalizeIdentifier(sourceInput.value, 100);
        });
    });

    window.PropertyNameAutofill = {
        normalizeIdentifier: normalizeIdentifier,
    };
})();
