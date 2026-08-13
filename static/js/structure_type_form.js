(function () {
    'use strict';

    function getDraftStorageKey() {
        const form = document.getElementById('structure-type-form');
        const scope = form?.dataset?.structureDraftKey || 'new';
        return `structure-type-form-draft:${scope}`;
    }

    const CYRILLIC = {
        а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
        и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
        с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch',
        ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
    };

    function fieldTypeLabel(fieldType) {
        const labels = window.ReferencePropertiesPicker?.FIELD_TYPE_LABELS || {};
        return labels[fieldType] || fieldType || '—';
    }

    const FIELD_TYPE_DEFAULTS = {
        CharField: { max_length: '255', max_digits: '', decimal_places: '', default_value: '' },
        ChoiceField: { max_length: '255', max_digits: '', decimal_places: '', default_value: '' },
        DecimalField: { max_length: '', max_digits: '10', decimal_places: '2', default_value: '' },
        MaterialLink: { max_length: '', max_digits: '', decimal_places: '', default_value: '' },
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

    function getStructureForm() {
        return document.getElementById('structure-type-form');
    }

    function getFieldList() {
        return document.getElementById('structure-field-list');
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

    function getVisibleFieldRows() {
        return Array.from(document.querySelectorAll('[data-structure-field-row]')).filter(
            (row) => !row.classList.contains('d-none'),
        );
    }

    function updateEmptyState() {
        const emptyNode = document.getElementById('structure-field-empty');
        if (!emptyNode) {
            return;
        }
        emptyNode.classList.toggle('d-none', getVisibleFieldRows().length > 0);
    }

    function syncRowSummary(row) {
        const label = row.querySelector('[name$="-label"]')?.value?.trim() || '—';
        const name = row.querySelector('[name$="-name"]')?.value?.trim() || '—';
        const fieldType = row.querySelector('[name$="-field_type"]')?.value || '';

        const labelNode = row.querySelector('[data-field-summary="label"]');
        const nameNode = row.querySelector('[data-field-summary="name"]');
        const typeNode = row.querySelector('[data-field-summary="type"]');

        if (labelNode) {
            labelNode.textContent = label;
        }
        if (nameNode) {
            nameNode.textContent = name;
        }
        if (typeNode) {
            let typeLabel = fieldTypeLabel(fieldType);
            if (fieldType === 'DecimalField') {
                const places = row.querySelector('[name$="-decimal_places"]')?.value || '2';
                typeLabel = `${typeLabel} · ${places} зн.`;
            }
            typeNode.textContent = typeLabel;
            typeNode.dataset.fieldTypeValue = fieldType;
        }
    }

    function setRowInputValue(row, suffix, value) {
        const input = row.querySelector(`[name$="-${suffix}"]`);
        if (!input) {
            return;
        }
        if (input.type === 'checkbox') {
            input.checked = Boolean(value);
            return;
        }
        input.value = value ?? '';
    }

    function applyHiddenFieldDefaults(row, fieldType) {
        const defaults = FIELD_TYPE_DEFAULTS[fieldType] || {
            max_length: '',
            max_digits: '',
            decimal_places: '',
            default_value: '',
        };

        setRowInputValue(row, 'max_length', defaults.max_length ?? '');
        setRowInputValue(row, 'max_digits', defaults.max_digits ?? '');
        setRowInputValue(row, 'decimal_places', defaults.decimal_places ?? '');
        setRowInputValue(row, 'default_value', defaults.default_value ?? '');
    }

    function getUsedColumnNames() {
        const names = new Set();
        getVisibleFieldRows().forEach((row) => {
            const value = row.querySelector('[name$="-name"]')?.value?.trim().toLowerCase();
            if (value) {
                names.add(value);
            }
        });
        return names;
    }

    function getUsedPropertyIds() {
        const ids = new Set();
        getVisibleFieldRows().forEach((row) => {
            if (row.dataset.referencePropertyId) {
                ids.add(row.dataset.referencePropertyId);
            }
        });
        return ids;
    }

    function getUsedLabels() {
        const labels = new Set();
        getVisibleFieldRows().forEach((row) => {
            const value = row.querySelector('[name$="-label"]')?.value?.trim().toLowerCase();
            if (value) {
                labels.add(value);
            }
        });
        return labels;
    }

    function annotateReferencePropertyIds() {
        const picker = window.ReferencePropertiesPicker;
        if (!picker?.getReferenceProperties) {
            return;
        }
        const byName = new Map();
        picker.getReferenceProperties().forEach((item) => {
            if (item?.name && item.property_id) {
                byName.set(String(item.name).toLowerCase(), String(item.property_id));
            }
        });
        getVisibleFieldRows().forEach((row) => {
            if (row.dataset.referencePropertyId) {
                return;
            }
            const name = row.querySelector('[name$="-name"]')?.value?.trim().toLowerCase();
            if (name && byName.has(name)) {
                row.dataset.referencePropertyId = byName.get(name);
            }
        });
    }

    function markRowAsExisting(row) {
        if (!row) {
            return;
        }
        row.dataset.existingField = 'true';
        const requiredWrap = row.querySelector('.structure-field-item__required');
        const isRequired = Boolean(row.querySelector('input[name$="-is_required"]')?.checked);
        if (requiredWrap) {
            requiredWrap.remove();
        }
        const meta = row.querySelector('.structure-field-item__meta');
        if (isRequired && meta && !meta.querySelector('.badge.text-bg-secondary')) {
            const badge = document.createElement('span');
            badge.className = 'badge text-bg-secondary';
            badge.textContent = 'Обязательное';
            meta.appendChild(badge);
        }
        const list = getFieldList();
        if (list?.dataset.canDeleteExisting === 'false') {
            row.querySelector('.delete-row-btn')?.remove();
        }
    }

    function getNextSortOrder() {
        let maxOrder = 0;
        getVisibleFieldRows().forEach((row) => {
            const value = parseInt(row.querySelector('[name$="-sort_order"]')?.value || '0', 10);
            if (!Number.isNaN(value)) {
                maxOrder = Math.max(maxOrder, value);
            }
        });
        return maxOrder + 1;
    }

    function appendRowFromTemplate() {
        const template = document.getElementById('field-row-template');
        const list = getFieldList();
        if (!template || !list) {
            return null;
        }

        const nextIdx = getNextIndex();
        const html = template.innerHTML.replace(/__idx__/g, String(nextIdx));
        list.insertAdjacentHTML('beforeend', html);
        const newRow = list.lastElementChild;
        incrementTotalForms(nextIdx);

        if (newRow) {
            bindDeleteButtons(newRow);
            bindRequiredMirror(newRow);
            updateEmptyState();
        }
        return newRow;
    }

    function reindexForms() {
        const list = getFieldList();
        const totalInput = getTotalFormsInput();
        const form = getStructureForm();
        const initialInput = form?.querySelector('input[name="fields-INITIAL_FORMS"]');
        if (!list || !totalInput) {
            return;
        }

        const rows = Array.from(list.querySelectorAll('[data-structure-field-row]'));
        // Existing instances (with id) must come first for Django formset INITIAL_FORMS.
        rows.sort((a, b) => {
            const aId = (a.querySelector('input[name$="-id"]')?.value || '').trim();
            const bId = (b.querySelector('input[name$="-id"]')?.value || '').trim();
            if (Boolean(aId) === Boolean(bId)) {
                return 0;
            }
            return aId ? -1 : 1;
        });
        rows.forEach((row) => list.appendChild(row));

        rows.forEach((row, idx) => {
            row.querySelectorAll('[name]').forEach((input) => {
                input.name = input.name.replace(/^fields-\d+-/, `fields-${idx}-`);
                if (input.id) {
                    input.id = input.id.replace(/^id_fields-\d+-/, `id_fields-${idx}-`);
                }
            });
        });
        totalInput.value = String(rows.length);
        if (initialInput) {
            const withId = rows.filter((row) => {
                const value = (row.querySelector('input[name$="-id"]')?.value || '').trim();
                return Boolean(value);
            }).length;
            initialInput.value = String(withId);
        }
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
            } else {
                row.remove();
                reindexForms();
            }
            updateEmptyState();
        });
    }

    function bindRequiredMirror(row) {
        if (!row || row.dataset.requiredMirrorBound === 'true') {
            return;
        }
        const mirror = row.querySelector('[data-structure-field-required-mirror]');
        const hidden = row.querySelector('input[name$="-is_required"]');
        if (!mirror || !hidden) {
            return;
        }
        row.dataset.requiredMirrorBound = 'true';
        mirror.checked = hidden.checked;
        mirror.addEventListener('change', () => {
            hidden.checked = mirror.checked;
        });
    }

    function fillRowFromPropertyData(row, data) {
        row.dataset.referencePropertyId = data.property_id;
        setRowInputValue(row, 'label', data.label);
        setRowInputValue(row, 'name', data.name);
        setRowInputValue(row, 'field_type', data.field_type);
        setRowInputValue(row, 'sort_order', String(getNextSortOrder()));
        applyHiddenFieldDefaults(row, data.field_type);
        if (data.decimal_places != null && data.decimal_places !== '') {
            setRowInputValue(row, 'decimal_places', String(data.decimal_places));
        }
        if (data.max_digits != null && data.max_digits !== '') {
            setRowInputValue(row, 'max_digits', String(data.max_digits));
        }
        const choices = data.choice_options || data.choices || [];
        setRowInputValue(row, 'choice_options', JSON.stringify(choices));
        const requiredInput = row.querySelector('input[name$="-is_required"]');
        if (requiredInput) {
            requiredInput.checked = true;
        }
        bindRequiredMirror(row);
        const mirror = row.querySelector('[data-structure-field-required-mirror]');
        if (mirror) {
            mirror.checked = true;
        }
        syncRowSummary(row);
    }

    function propertyMetaLine(item) {
        const picker = window.ReferencePropertiesPicker;
        const escapeHtml = picker.escapeHtml;
        const typeLabel = item.data_type === 'choice'
            ? (picker.DATA_TYPE_LABELS.choice || 'Выбор из списка')
            : fieldTypeLabel(item.field_type);
        return `<code>${escapeHtml(item.name)}</code> · ${escapeHtml(typeLabel)}`;
    }

    function renderReferencePropertiesList(filterText = '') {
        const picker = window.ReferencePropertiesPicker;
        if (!picker) {
            return;
        }
        picker.renderList({
            filterText,
            getUsedPropertyIds,
            getUsedColumnNames,
            getUsedLabels,
            metaLine: propertyMetaLine,
        });
    }

    function applyEntryToForm(form, name, value) {
        const elements = form.querySelectorAll(`[name="${CSS.escape(name)}"]`);
        if (!elements.length) {
            return;
        }
        const first = elements[0];
        if (first.type === 'checkbox') {
            first.checked = value === 'on' || value === 'true' || value === '1';
        } else if (first.type === 'radio') {
            elements.forEach((radio) => {
                radio.checked = radio.value === value;
            });
        } else {
            first.value = value;
        }
    }

    function saveFormDraft() {
        const form = getStructureForm();
        if (!form) {
            return;
        }

        const entries = [];
        form.querySelectorAll('input, select, textarea').forEach((element) => {
            if (!element.name || element.type === 'submit' || element.type === 'button') {
                return;
            }
            if (element.closest('#field-row-template')) {
                return;
            }
            if (element.type === 'checkbox') {
                if (element.checked) {
                    entries.push({ name: element.name, value: element.value || 'on' });
                }
            } else if (element.type === 'radio') {
                if (element.checked) {
                    entries.push({ name: element.name, value: element.value });
                }
            } else {
                entries.push({ name: element.name, value: element.value });
            }
        });

        const referenceIds = {};
        document.querySelectorAll('[data-structure-field-row]').forEach((row) => {
            const match = row.querySelector('[name]')?.name?.match(/^fields-(\d+)-/);
            if (match && row.dataset.referencePropertyId) {
                referenceIds[match[1]] = row.dataset.referencePropertyId;
            }
        });

        sessionStorage.setItem(getDraftStorageKey(), JSON.stringify({ entries, referenceIds }));
    }

    function clearFormDraft() {
        sessionStorage.removeItem(getDraftStorageKey());
    }

    function restoreFormDraft() {
        const raw = sessionStorage.getItem(getDraftStorageKey());
        if (!raw) {
            return false;
        }

        let draft;
        try {
            draft = JSON.parse(raw);
        } catch (error) {
            clearFormDraft();
            return false;
        }

        const form = getStructureForm();
        if (!form || !Array.isArray(draft.entries)) {
            clearFormDraft();
            return false;
        }

        const formsetEntries = draft.entries.filter((entry) => /^fields-\d+-/.test(entry.name));
        const mainEntries = draft.entries.filter((entry) => !/^fields-\d+-/.test(entry.name));

        mainEntries.forEach(({ name, value }) => {
            applyEntryToForm(form, name, value);
        });

        const list = getFieldList();
        if (list) {
            list.querySelectorAll('[data-structure-field-row]').forEach((row) => row.remove());
        }
        if (getTotalFormsInput()) {
            getTotalFormsInput().value = '0';
        }

        const indices = new Set();
        formsetEntries.forEach(({ name }) => {
            const match = name.match(/^fields-(\d+)-/);
            if (match) {
                indices.add(parseInt(match[1], 10));
            }
        });

        Array.from(indices).sort((a, b) => a - b).forEach((origIdx) => {
            const rowEntries = formsetEntries.filter((entry) => {
                const match = entry.name.match(/^fields-(\d+)-/);
                return match && parseInt(match[1], 10) === origIdx;
            });

            const labelEntry = rowEntries.find((entry) => entry.name.endsWith('-label'));
            const nameEntry = rowEntries.find((entry) => entry.name.endsWith('-name'));
            const idEntry = rowEntries.find((entry) => entry.name.endsWith('-id'));
            const isDeleted = rowEntries.some(
                (entry) => entry.name.endsWith('-DELETE')
                    && (entry.value === 'on' || entry.value === 'true'),
            );

            if (!labelEntry?.value && !nameEntry?.value && !idEntry?.value) {
                return;
            }

            const row = appendRowFromTemplate();
            if (!row) {
                return;
            }

            rowEntries.forEach(({ name, value }) => {
                const suffix = name.replace(/^fields-\d+-/, '');
                const element = row.querySelector(`[name$="-${suffix}"]`);
                if (!element) {
                    return;
                }
                if (element.type === 'checkbox') {
                    element.checked = value === 'on' || value === 'true' || value === '1';
                } else {
                    element.value = value;
                }
            });

            const refId = draft.referenceIds?.[String(origIdx)];
            if (refId) {
                row.dataset.referencePropertyId = refId;
            } else {
                delete row.dataset.referencePropertyId;
            }

            if (isDeleted) {
                row.classList.add('d-none');
            }

            if (idEntry?.value) {
                markRowAsExisting(row);
            }

            bindDeleteButtons(row);
            bindRequiredMirror(row);
            syncRowSummary(row);
        });

        reindexForms();
        annotateReferencePropertyIds();
        updateEmptyState();
        clearFormDraft();
        return true;
    }

    function getCreatedPropertyIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const values = params.getAll('created_property');
        return values.length ? values[values.length - 1] : '';
    }

    function cleanupCreatedPropertyParam() {
        const url = new URL(window.location.href);
        if (!url.searchParams.has('created_property')) {
            return;
        }
        url.searchParams.delete('created_property');
        window.history.replaceState({}, '', url.pathname + url.search + url.hash);
    }

    function findPropertyPayload(propertyId) {
        const picker = window.ReferencePropertiesPicker;
        if (!picker?.getReferenceProperties || !propertyId) {
            return null;
        }
        return picker.getReferenceProperties().find((item) => item.property_id === propertyId) || null;
    }

    function addCreatedPropertyFromUrl() {
        const propertyId = getCreatedPropertyIdFromUrl();
        cleanupCreatedPropertyParam();
        if (!propertyId) {
            return;
        }
        if (getUsedPropertyIds().has(propertyId)) {
            return;
        }
        const payload = findPropertyPayload(propertyId);
        if (!payload) {
            return;
        }
        const name = (payload.name || '').toLowerCase();
        const label = (payload.label || '').toLowerCase();
        if (getUsedColumnNames().has(name) || getUsedLabels().has(label)) {
            return;
        }
        const row = appendRowFromTemplate();
        if (row) {
            fillRowFromPropertyData(row, payload);
            updateEmptyState();
        }
    }

    function shouldOpenPropertiesModal() {
        const params = new URLSearchParams(window.location.search);
        return params.get('open_properties') === '1';
    }

    function cleanupOpenPropertiesParam() {
        const url = new URL(window.location.href);
        if (!url.searchParams.has('open_properties')) {
            return;
        }
        url.searchParams.delete('open_properties');
        window.history.replaceState({}, '', url.pathname + url.search + url.hash);
    }

    function bindPropertiesModal() {
        const picker = window.ReferencePropertiesPicker;
        if (!picker) {
            return null;
        }
        return picker.bind({
            openButtonId: 'add-from-properties-btn',
            getUsedPropertyIds,
            getUsedColumnNames,
            getUsedLabels,
            metaLine: propertyMetaLine,
            onConfirm(payloads) {
                const usedIds = getUsedPropertyIds();
                const usedNames = getUsedColumnNames();
                const usedLabels = getUsedLabels();
                payloads.forEach((payload) => {
                    const propertyId = payload.property_id;
                    const name = (payload.name || '').toLowerCase();
                    const label = (payload.label || '').toLowerCase();
                    if (
                        (propertyId && usedIds.has(propertyId))
                        || (name && usedNames.has(name))
                        || (label && usedLabels.has(label))
                    ) {
                        return;
                    }
                    const row = appendRowFromTemplate();
                    if (row) {
                        fillRowFromPropertyData(row, payload);
                        if (propertyId) {
                            usedIds.add(propertyId);
                        }
                        if (name) {
                            usedNames.add(name);
                        }
                        if (label) {
                            usedLabels.add(label);
                        }
                    }
                });
                updateEmptyState();
            },
        });
    }

    function bindCreatePropertyLink() {
        const link = document.getElementById('create-reference-property-btn');
        if (!link || link.dataset.bound === 'true') {
            return;
        }
        link.dataset.bound = 'true';

        link.addEventListener('click', () => {
            saveFormDraft();
            const createUrl = new URL(link.href, window.location.origin);
            const returnUrl = new URL(window.location.href);
            returnUrl.searchParams.delete('open_properties');
            returnUrl.searchParams.delete('created_property');
            createUrl.searchParams.set('next', returnUrl.pathname + returnUrl.search);
            link.href = createUrl.toString();
        });
    }

    function bindFormSubmitClearDraft() {
        const form = getStructureForm();
        if (!form || form.dataset.boundDraftClear === 'true') {
            return;
        }
        form.dataset.boundDraftClear = 'true';
        form.addEventListener('submit', clearFormDraft);
    }

    function bindFieldRows() {
        document.querySelectorAll('[data-structure-field-row]').forEach((row) => {
            bindDeleteButtons(row);
            bindRequiredMirror(row);
            syncRowSummary(row);
        });
        annotateReferencePropertyIds();
        updateEmptyState();
    }

    document.addEventListener('DOMContentLoaded', () => {
        const restored = restoreFormDraft();
        if (!restored) {
            bindFieldRows();
        } else {
            document.querySelectorAll('[data-structure-field-row]').forEach((row) => {
                bindDeleteButtons(row);
                bindRequiredMirror(row);
                syncRowSummary(row);
            });
            annotateReferencePropertyIds();
        }

        const modal = bindPropertiesModal();
        bindCreatePropertyLink();
        bindFormSubmitClearDraft();
        addCreatedPropertyFromUrl();

        if (shouldOpenPropertiesModal()) {
            cleanupOpenPropertiesParam();
            renderReferencePropertiesList();
            modal?.show();
        }
    });
})();
