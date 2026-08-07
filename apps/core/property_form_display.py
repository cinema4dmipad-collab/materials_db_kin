from apps.references.models import Property

EMPTY_LABEL = '\u2014'


def property_label_with_unit(prop: Property) -> str:
    if prop is None:
        return EMPTY_LABEL
    return prop.label_with_unit()


def form_property_id(form):
    value = form['property'].value()
    if value:
        return str(value)
    property_id = getattr(form.instance, 'property_id', None)
    if property_id:
        return str(property_id)
    initial = form.initial.get('property')
    if initial:
        return str(getattr(initial, 'pk', initial))
    return ''


def enrich_property_form_display(form):
    prop_id = form_property_id(form)
    if prop_id:
        prop = Property.objects.filter(pk=prop_id).first()
        form.property_label = prop.base_display_name() if prop else EMPTY_LABEL
        form.property_unit = prop.effective_unit() if prop else ''
    else:
        form.property_label = EMPTY_LABEL
        form.property_unit = ''
