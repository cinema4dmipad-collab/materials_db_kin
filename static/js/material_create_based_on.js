(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var button = document.getElementById('create-based-on-btn');
        if (!button || !window.ReferenceMaterialsPicker) {
            return;
        }

        button.addEventListener('click', function () {
            var createUrl = button.dataset.createUrl;
            if (!createUrl) {
                return;
            }

            window.ReferenceMaterialsPicker.openWithOptions({
                scope: 'shared',
                onSelect: function (materialId) {
                    var url = new URL(createUrl, window.location.origin);
                    url.searchParams.set('based_on', materialId);
                    window.location.assign(url.toString());
                },
            });
        });
    });
})();
