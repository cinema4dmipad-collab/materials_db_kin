MATERIAL_DETAIL_PK_PLACEHOLDER = '00000000-0000-0000-0000-000000000000'
MATERIAL_DETAIL_URL_TEMPLATE = f'/materials/{MATERIAL_DETAIL_PK_PLACEHOLDER}/'


def material_select_widget_attrs(**extra):
    attrs = {
        'class': 'form-select js-material-select material-picker-select',
        'data-material-picker': 'true',
    }
    attrs.update(extra)
    return attrs


def structure_type_select_widget_attrs(**extra):
    attrs = {
        'class': 'form-select structure-type-picker-select',
        'data-structure-type-picker': 'true',
    }
    attrs.update(extra)
    return attrs
