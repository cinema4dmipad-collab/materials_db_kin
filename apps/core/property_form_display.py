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
    if form.instance.pk and form.instance.property_id:
        return str(form.instance.property_id)
    initial = form.initial.get('property')
    return str(initial) if initial else ''


def enrich_property_form_display(form):
    prop_id = form_property_id(form)
    if prop_id:
        prop = Property.objects.filter(pk=prop_id).first()
        form.property_label = prop.label_with_unit() if prop else EMPTY_LABEL
        form.property_unit = prop.unit if prop else ''
    else:
        form.property_label = EMPTY_LABEL
        form.property_unit = ''
