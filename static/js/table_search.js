(function () {
    'use strict';

    function filterTableRows(input) {
        var tableId = input.getAttribute('data-table-search');
        var table = document.getElementById(tableId);
        if (!table) {
            return;
        }

        var query = input.value.trim().toLowerCase();
        table.querySelectorAll('tbody tr').forEach(function (row) {
            if (row.classList.contains('table-search-ignore')) {
                return;
            }
            var visible = !query || row.textContent.toLowerCase().includes(query);
            row.classList.toggle('d-none', !visible);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-table-search]').forEach(function (input) {
            input.addEventListener('input', function () {
                filterTableRows(input);
            });
        });

        document.querySelectorAll('[data-card-search]').forEach(function (input) {
            input.addEventListener('input', function () {
                var query = input.value.trim().toLowerCase();
                var container = document.querySelector(input.getAttribute('data-card-search'));
                if (!container) {
                    return;
                }
                container.querySelectorAll('[data-card-search-item]').forEach(function (item) {
                    var visible = !query || item.textContent.toLowerCase().includes(query);
                    item.classList.toggle('d-none', !visible);
                });
            });
        });
    });
})();
