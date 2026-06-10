(function($) {
    'use strict';

    function option(value, text) {
        return $('<option></option>').attr('value', value).text(text);
    }

    $(function() {
        var $structureType = $('#id_struct_type');
        var $propsSelect = $('#id_struct_props_id');

        if (!$structureType.length || !$propsSelect.length) {
            return;
        }

        var loadUrl = $propsSelect.data('load-url');
        if (!loadUrl) {
            return;
        }

        $structureType.on('change', function() {
            var structureTypeId = $(this).val();

            $propsSelect.empty();
            if (!structureTypeId) {
                $propsSelect.append(option('', 'Сначала выберите тип структуры'));
                return;
            }

            $propsSelect.append(option('', 'Загрузка...'));
            $.get(loadUrl, {structure_type_id: structureTypeId})
                .done(function(data) {
                    $propsSelect.empty();
                    $propsSelect.append(option('', '---------'));

                    if (data.instances && data.instances.length) {
                        $.each(data.instances, function(index, instance) {
                            $propsSelect.append(option(instance.id, instance.name));
                        });
                    } else {
                        $propsSelect.append(option('', 'Нет доступных структур'));
                    }
                })
                .fail(function() {
                    $propsSelect.empty();
                    $propsSelect.append(option('', 'Не удалось загрузить структуры'));
                });
        });
    });
})(django.jQuery);
