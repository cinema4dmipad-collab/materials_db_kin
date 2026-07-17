from apps.core.form_validation import (
    collect_form_errors,
    collect_inline_formset_errors,
    validation_flash_message,
    validation_sections,
)
from apps.structures.constants import STRUCTURE_FIELD_PREFIX


def build_material_form_validation_summary(form, properties_formset=None, layers_formset=None):
    field_sections = {
        field_name: 'Параметры структуры'
        for field_name in form.errors
        if field_name.startswith(STRUCTURE_FIELD_PREFIX)
    }
    field_sections.update({
        'visibility_mode': 'Видимость',
        'published_workspaces': 'Видимость',
    })
    summary = collect_form_errors(
        form,
        default_section='Материал',
        field_sections=field_sections,
    )
    summary.extend(
        collect_inline_formset_errors(
            properties_formset,
            section_label='Свойства',
            row_label='строка',
        )
    )
    summary.extend(
        collect_inline_formset_errors(
            layers_formset,
            section_label='Слои композита',
            row_label='слой',
        )
    )
    return summary


__all__ = [
    'build_material_form_validation_summary',
    'validation_flash_message',
    'validation_sections',
]
