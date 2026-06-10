(function () {
    'use strict';

    var PLACEHOLDER = '00000000-0000-0000-0000-000000000000';

    function buildUrl(template, materialId) {
        return template.replace(PLACEHOLDER, materialId);
    }

    function getSelectedLabel(select) {
        var option = select.options[select.selectedIndex];
        return option && option.value ? option.text.trim() : '';
    }

    function ensureLinkWrap(select) {
        var wrap = select.closest('.material-select-field');
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.className = 'material-select-field';
            select.parentNode.insertBefore(wrap, select);
            wrap.appendChild(select);
        }

        var link = wrap.querySelector('.material-select-link');
        if (!link) {
            link = document.createElement('a');
            link.className = 'material-select-link';
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            wrap.appendChild(link);
        }
        return link;
    }

    function syncLink(select) {
        var template = select.getAttribute('data-material-detail-url');
        if (!template) {
            return;
        }

        var link = ensureLinkWrap(select);
        var value = select.value;
        if (!value) {
            link.hidden = true;
            link.removeAttribute('href');
            link.textContent = '';
            return;
        }

        link.href = buildUrl(template, value);
        link.textContent = getSelectedLabel(select) || 'Открыть материал';
        link.title = 'Открыть карточку материала';
        link.hidden = false;
    }

    function bindSelect(select) {
        if (select.dataset.materialSelectLinkBound === 'true') {
            syncLink(select);
            return;
        }
        select.dataset.materialSelectLinkBound = 'true';
        syncLink(select);
        select.addEventListener('change', function () {
            syncLink(select);
        });
    }

    function initMaterialSelectLinks(root) {
        var scope = root || document;
        scope.querySelectorAll('select[data-material-detail-url]').forEach(bindSelect);
    }

    document.addEventListener('DOMContentLoaded', function () {
        initMaterialSelectLinks();
    });

    window.initMaterialSelectLinks = initMaterialSelectLinks;
})();
