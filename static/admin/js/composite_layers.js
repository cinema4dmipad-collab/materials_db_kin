(function ($) {
    'use strict';

    function renumberCompositeLayers() {
        var $group = $('#compositelayer_set-group');
        if (!$group.length) {
            return;
        }

        var layerNum = 1;
        $group.find('tbody tr.form-row:not(.empty-form)').each(function () {
            var $row = $(this);
            if ($row.hasClass('deleted') || $row.find('input[name$="-DELETE"]').prop('checked')) {
                return;
            }
            $row.find('input[name$="-layer_number"]').val(layerNum);
            layerNum += 1;
        });
    }

    function customizeAddLayerLink() {
        var $addRow = $('#compositelayer_set-group .add-row a');
        if ($addRow.length) {
            $addRow.text('Добавить');
        }
    }

    $(document).on('formset:added formset:removed', function (event, $row, formsetName) {
        if (formsetName === 'compositelayer_set') {
            renumberCompositeLayers();
        }
    });

    $(document).on('change', '#compositelayer_set-group input[name$="-DELETE"]', function () {
        renumberCompositeLayers();
    });

    $(function () {
        renumberCompositeLayers();
        customizeAddLayerLink();
    });
})(django.jQuery);
