from apps.references.models import Property


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
        form.property_label = prop.display_name if prop else '—'
        form.property_unit = prop.unit if prop else ''
    else:
        form.property_label = '—'
        form.property_unit = ''
