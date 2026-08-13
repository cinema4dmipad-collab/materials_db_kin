(function () {
    'use strict';

    function bindCreateBasedOn(button) {
        if (!button || button.dataset.boundCreateBasedOn === 'true') {
            return;
        }
        button.dataset.boundCreateBasedOn = 'true';

        button.addEventListener('click', function () {
            if (!window.ReferenceMaterialsPicker) {
                return;
            }
            var createUrl = button.dataset.createUrl;
            if (!createUrl) {
                return;
            }

            window.ReferenceMaterialsPicker.openWithOptions({
                scope: 'workspace',
                onSelect: function (materialId) {
                    var url = new URL(createUrl, window.location.origin);
                    url.searchParams.set('based_on', materialId);
                    window.location.assign(url.toString());
                },
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-create-based-on]').forEach(bindCreateBasedOn);
        var legacy = document.getElementById('create-based-on-btn');
        if (legacy) {
            bindCreateBasedOn(legacy);
        }
    });
})();
