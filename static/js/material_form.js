(function () {
    'use strict';

    function shouldAllowEnterSubmit(event) {
        var target = event.target;
        if (!target) {
            return false;
        }
        if (target.tagName === 'TEXTAREA') {
            return true;
        }
        if (target.type === 'submit') {
            return true;
        }
        return target.tagName === 'BUTTON' && target.type === 'submit';
    }

    function bindEnterGuard(form) {
        form.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' || event.defaultPrevented) {
                return;
            }
            if (shouldAllowEnterSubmit(event)) {
                return;
            }
            event.preventDefault();
        });
    }

    function bindStructureTypeApply(form) {
        var structureSelect = document.getElementById('id_struct_type');
        var flag = document.getElementById('apply-struct-type-flag');
        if (!structureSelect || !flag) {
            return;
        }

        structureSelect.addEventListener('change', function () {
            flag.value = '1';
            form.requestSubmit();
        });
    }

    function bindVisibilityFields(form) {
        var modeSelect = document.getElementById('id_visibility_mode');
        var publishedGroup = document.getElementById('published-workspaces-group');
        if (!modeSelect || !publishedGroup) {
            return;
        }

        function syncPublishedVisibility() {
            publishedGroup.hidden = modeSelect.value !== 'selected_workspaces';
        }

        modeSelect.addEventListener('change', syncPublishedVisibility);
        syncPublishedVisibility();
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('material-form');
        if (!form) {
            return;
        }
        bindEnterGuard(form);
        bindStructureTypeApply(form);
        bindVisibilityFields(form);
    });
})();
