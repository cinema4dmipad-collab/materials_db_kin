(function () {
    'use strict';

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function urlForTemplate(template, materialId) {
        if (!template || !materialId) {
            return '';
        }
        return template.replace('00000000-0000-0000-0000-000000000000', materialId);
    }

    function rootConfig(root) {
        return {
            propertiesUrlTemplate: root.getAttribute('data-material-properties-url') || '',
            materialDetailUrlTemplate: root.getAttribute('data-material-detail-url') || '',
        };
    }

    function buildStructureValueCell(prop, materialDetailUrlTemplate) {
        if (prop.field_type === 'MaterialLink' && prop.value && materialDetailUrlTemplate) {
            var detailUrl = urlForTemplate(materialDetailUrlTemplate, prop.value);
            return '<a href="' + escapeHtml(detailUrl) + '">'
                + escapeHtml(prop.display_value || prop.value)
                + '</a>';
        }
        return escapeHtml(prop.display_value || '—');
    }

    function buildMaterialPropertyValueCell(item, materialDetailUrlTemplate) {
        if (item.data_type === 'material_link' && item.material_id && materialDetailUrlTemplate) {
            var detailUrl = urlForTemplate(materialDetailUrlTemplate, item.material_id);
            return '<a href="' + escapeHtml(detailUrl) + '">' + escapeHtml(item.value || '—') + '</a>';
        }
        return escapeHtml(item.value || '—');
    }

    function buildSectionTable(title, rowsHtml) {
        return ''
            + '<div class="structure-material-preview__section">'
            + '<div class="structure-material-preview__section-title">' + escapeHtml(title) + '</div>'
            + '<div class="table-responsive">'
            + '<table class="table table-sm align-middle mb-0 structure-material-preview__table">'
            + '<thead><tr>'
            + '<th scope="col">Свойство</th>'
            + '<th scope="col">Значение</th>'
            + '<th scope="col" class="structure-material-preview__unit-col">Ед.</th>'
            + '</tr></thead>'
            + '<tbody>' + rowsHtml + '</tbody>'
            + '</table>'
            + '</div>'
            + '</div>';
    }

    function renderPreview(container, data, materialDetailUrlTemplate) {
        var sections = [];
        var structureProps = data.structure_properties || [];
        var properties = data.properties || [];
        var structureMessage = data.structure_message || '';

        if (structureProps.length) {
            var structRows = structureProps.map(function (prop) {
                return ''
                    + '<tr>'
                    + '<th scope="row" class="structure-material-preview__name">'
                    + escapeHtml(prop.label || prop.name || '—')
                    + '</th>'
                    + '<td class="structure-material-preview__value">'
                    + buildStructureValueCell(prop, materialDetailUrlTemplate)
                    + '</td>'
                    + '<td class="structure-material-preview__unit">' + escapeHtml(prop.unit || '') + '</td>'
                    + '</tr>';
            }).join('');
            sections.push(buildSectionTable('Из параметров структуры', structRows));
        } else if (structureMessage) {
            sections.push(
                '<p class="structure-material-preview__message text-muted small mb-0">'
                + escapeHtml(structureMessage)
                + '</p>'
            );
        }

        if (properties.length) {
            var propRows = properties.map(function (item) {
                return ''
                    + '<tr>'
                    + '<th scope="row" class="structure-material-preview__name">'
                    + escapeHtml(item.display_name || '—')
                    + '</th>'
                    + '<td class="structure-material-preview__value">'
                    + buildMaterialPropertyValueCell(item, materialDetailUrlTemplate)
                    + '</td>'
                    + '<td class="structure-material-preview__unit">' + escapeHtml(item.unit || '') + '</td>'
                    + '</tr>';
            }).join('');
            sections.push(buildSectionTable('Дополнительные свойства', propRows));
        }

        if (!sections.length) {
            container.innerHTML = '<p class="text-muted small mb-0">Свойства не заданы.</p>';
            return;
        }

        container.innerHTML = sections.join('');
    }

    function setButtonState(button, expanded) {
        button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        button.textContent = expanded ? 'Свернуть' : 'Развернуть';
        button.classList.toggle('is-expanded', expanded);
    }

    function setPreviewVisible(preview, visible) {
        preview.hidden = !visible;
        preview.classList.toggle('d-none', !visible);
        var previewRow = preview.closest('tr.structure-material-preview-row');
        if (previewRow) {
            previewRow.hidden = !visible;
            previewRow.classList.toggle('d-none', !visible);
        }
    }

    function fetchMaterialProperties(materialId, propertiesUrlTemplate) {
        var url = urlForTemplate(propertiesUrlTemplate, materialId);
        if (!url) {
            return Promise.reject(new Error('missing url'));
        }
        return fetch(url, {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('load failed');
            }
            return response.json();
        });
    }

    document.addEventListener('click', function (event) {
        var button = event.target.closest('.structure-material-expand');
        if (!button) {
            return;
        }

        var root = button.closest('[data-structure-material-expand-root]');
        if (!root) {
            return;
        }

        var materialId = button.getAttribute('data-material-id');
        var previewId = button.getAttribute('aria-controls');
        var preview = previewId ? document.getElementById(previewId) : null;
        if (!materialId || !preview) {
            return;
        }

        var config = rootConfig(root);
        var expanded = button.getAttribute('aria-expanded') === 'true';
        if (expanded) {
            setPreviewVisible(preview, false);
            setButtonState(button, false);
            return;
        }

        setPreviewVisible(preview, true);
        setButtonState(button, true);

        if (preview.getAttribute('data-loaded') === '1') {
            return;
        }

        preview.innerHTML = '<p class="text-muted small mb-0">Загрузка…</p>';
        fetchMaterialProperties(materialId, config.propertiesUrlTemplate)
            .then(function (data) {
                renderPreview(preview, data, config.materialDetailUrlTemplate);
                preview.setAttribute('data-loaded', '1');
            })
            .catch(function () {
                preview.innerHTML = '<p class="text-danger small mb-0">Не удалось загрузить свойства материала.</p>';
            });
    });
})();
