(function () {
    'use strict';

    function parseScopeOptions(raw) {
        if (!raw) {
            return [{ value: '', label: 'Везде' }];
        }
        return raw.split(';').map(function (part) {
            var commaIndex = part.indexOf(',');
            if (commaIndex === -1) {
                return { value: part.trim(), label: part.trim() || 'Везде' };
            }
            return {
                value: part.slice(0, commaIndex).trim(),
                label: part.slice(commaIndex + 1).trim(),
            };
        }).filter(function (item) {
            return item.label;
        });
    }

    function populateScopeSelect(select, scopesRaw) {
        var scopes = parseScopeOptions(scopesRaw);
        select.innerHTML = '';
        scopes.forEach(function (scope) {
            var option = document.createElement('option');
            option.value = scope.value;
            option.textContent = scope.label;
            select.appendChild(option);
        });
    }

    function rowMatchesQuery(row, query, scope) {
        if (!query) {
            return true;
        }
        if (!scope) {
            return row.textContent.toLowerCase().includes(query);
        }
        var cells = row.querySelectorAll('td');
        var cellIndex = parseInt(scope, 10);
        if (Number.isNaN(cellIndex) || !cells[cellIndex]) {
            return row.textContent.toLowerCase().includes(query);
        }
        return cells[cellIndex].textContent.toLowerCase().includes(query);
    }

    function filterTable(panel) {
        var tableId = panel.getAttribute('data-client-filter-table');
        var table = document.getElementById(tableId);
        var input = panel.querySelector('[data-client-filter-input]');
        var scopeSelect = panel.querySelector('[data-client-filter-scope]');
        if (!table || !input) {
            return;
        }

        var query = input.value.trim().toLowerCase();
        var scope = scopeSelect ? scopeSelect.value : '';
        table.querySelectorAll('tbody tr').forEach(function (row) {
            if (row.classList.contains('table-search-ignore')) {
                return;
            }
            row.classList.toggle('d-none', !rowMatchesQuery(row, query, scope));
        });
    }

    function filterCards(panel) {
        var targetSelector = panel.getAttribute('data-client-filter-target');
        var container = document.querySelector(targetSelector);
        var input = panel.querySelector('[data-client-filter-input]');
        var scopeSelect = panel.querySelector('[data-client-filter-scope]');
        if (!container || !input) {
            return;
        }

        var query = input.value.trim().toLowerCase();
        var scope = scopeSelect ? scopeSelect.value : '';
        container.querySelectorAll('[data-client-search-item]').forEach(function (item) {
            var haystack = '';
            if (!scope) {
                haystack = item.textContent;
            } else {
                haystack = item.getAttribute('data-search-' + scope) || item.textContent;
            }
            item.classList.toggle('d-none', query && !haystack.toLowerCase().includes(query));
        });
    }

    function bindClientFilterPanel(panel) {
        if (panel.dataset.bound === 'true') {
            return;
        }
        panel.dataset.bound = 'true';

        var scopeSelect = panel.querySelector('[data-client-filter-scope]');
        if (scopeSelect) {
            populateScopeSelect(scopeSelect, panel.getAttribute('data-client-filter-scopes'));
        }

        var applyFilter = function () {
            var mode = panel.getAttribute('data-client-filter-mode') || 'table';
            if (mode === 'cards') {
                filterCards(panel);
            } else {
                filterTable(panel);
            }
        };

        var input = panel.querySelector('[data-client-filter-input]');
        if (input) {
            input.addEventListener('input', applyFilter);
        }
        if (scopeSelect) {
            scopeSelect.addEventListener('change', applyFilter);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-client-filter-mode]').forEach(bindClientFilterPanel);
    });
})();
