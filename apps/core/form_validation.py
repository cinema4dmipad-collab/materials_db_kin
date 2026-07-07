from django.utils.html import format_html
from django.utils.safestring import SafeString


def _field_label(form, field_name):
    field = form.fields.get(field_name)
    if field and field.label:
        return str(field.label)
    return field_name


def collect_form_errors(form, *, default_section, field_sections=None):
    field_sections = field_sections or {}
    items = []
    for field_name, errors in form.errors.items():
        if field_name == '__all__':
            section = default_section
            for error in errors:
                items.append({'section': section, 'message': error})
            continue

        section = field_sections.get(field_name, default_section)
        label = _field_label(form, field_name)
        for error in errors:
            if isinstance(error, SafeString):
                message = format_html('{}: {}', label, error)
            else:
                message = f'{label}: {error}'
            items.append({'section': section, 'message': message})
    return items


def collect_inline_formset_errors(formset, *, section_label, row_label='строка'):
    if formset is None:
        return []

    items = []
    for error in formset.non_form_errors():
        items.append({'section': section_label, 'message': str(error)})

    for index, inline_form in enumerate(formset.forms, start=1):
        if not inline_form.errors:
            continue
        for field_name, errors in inline_form.errors.items():
            label = _field_label(inline_form, field_name)
            for error in errors:
                if field_name == '__all__':
                    message = f'{row_label.capitalize()} {index} — {error}'
                else:
                    message = f'{row_label.capitalize()} {index} — {label}: {error}'
                items.append({
                    'section': section_label,
                    'message': message,
                })
    return items


def validation_sections(summary):
    sections = []
    seen = set()
    for item in summary:
        section = item['section']
        if section not in seen:
            sections.append(section)
            seen.add(section)
    return sections


def validation_flash_message(summary):
    sections = validation_sections(summary)
    if not sections:
        return None
    if len(sections) == 1:
        return f'Не удалось сохранить материал. Исправьте ошибки в разделе «{sections[0]}».'
    joined = ', '.join(f'«{section}»' for section in sections)
    return f'Не удалось сохранить материал. Исправьте ошибки в разделах: {joined}.'
