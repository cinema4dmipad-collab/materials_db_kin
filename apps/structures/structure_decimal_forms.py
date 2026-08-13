from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.core.fields import LocalizedPropertyValueField, apply_property_decimal_places_to_value_field, localized_range_bound_field
from apps.core.property_number_forms import resolve_number_property_kind
from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
    form_state_from_value_slots,
)
from apps.structures.constants import (
    STRUCTURE_FIELD_PREFIX,
    resolve_structure_field_decimal_places,
)
from apps.structures.decimal_range import (
    decimal_storage_columns,
    pack_decimal_field_data,
    read_decimal_field_state,
)

_DECIMAL_FIELD_SUFFIXES = ('__kind', '__b', '__min', '__max', '__tolerance', '__is_range', '__is_tolerance')


def structure_decimal_base_name(structure_field_pk) -> str:
    return f'{STRUCTURE_FIELD_PREFIX}{structure_field_pk}'


def structure_decimal_field_names(structure_field_pk) -> dict[str, str]:
    base = structure_decimal_base_name(structure_field_pk)
    return {
        'value': base,
        'kind': f'{base}__kind',
        'min': f'{base}__min',
        'max': f'{base}__max',
        'tolerance': f'{base}__tolerance',
        'is_range': f'{base}__is_range',
        'is_tolerance': f'{base}__is_tolerance',
    }


def is_structure_decimal_subfield(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _DECIMAL_FIELD_SUFFIXES)


def add_structure_decimal_fields(form, structure_field) -> dict[str, str]:
    names = structure_decimal_field_names(structure_field.pk)
    places = resolve_structure_field_decimal_places(structure_field)
    form.fields[names['value']] = LocalizedPropertyValueField(
        label=structure_field.label,
        required=False,
        help_text=structure_field.help_text or None,
        decimal_places=places,
    )
    form.fields[names['min']] = localized_range_bound_field(
        bound_label='От',
        decimal_places=places,
    )
    form.fields[names['max']] = localized_range_bound_field(
        bound_label='До',
        decimal_places=places,
    )
    form.fields[names['tolerance']] = localized_range_bound_field(
        bound_label='±',
        decimal_places=places,
    )
    form.fields[names['kind']] = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        initial=VALUE_KIND_SCALAR,
    )
    form.fields[names['is_range']] = forms.BooleanField(
        required=False,
        label='Диапазон',
        widget=forms.CheckboxInput(
            attrs={'class': 'form-check-input property-number-value__range-toggle'},
        ),
    )
    form.fields[names['is_tolerance']] = forms.BooleanField(
        required=False,
        label='±',
        widget=forms.CheckboxInput(
            attrs={'class': 'form-check-input property-number-value__tolerance-toggle'},
        ),
    )
    apply_property_decimal_places_to_value_field(form.fields[names['value']], _decimal_property(structure_field))
    apply_property_decimal_places_to_value_field(form.fields[names['min']], _decimal_property(structure_field))
    apply_property_decimal_places_to_value_field(form.fields[names['max']], _decimal_property(structure_field))
    apply_property_decimal_places_to_value_field(form.fields[names['tolerance']], _decimal_property(structure_field))
    return names


def apply_structure_decimal_initial(form, structure_field, record: dict) -> None:
    if not record:
        return
    names = structure_decimal_field_names(structure_field.pk)
    state = read_decimal_field_state(record, structure_field.name)
    form.fields[names['value']].initial = state['value']
    form.fields[names['min']].initial = state['value_min']
    form.fields[names['max']].initial = state['value_max']
    form.fields[names['tolerance']].initial = state['value_tolerance']
    form.fields[names['kind']].initial = state['value_kind']
    if state['value_kind'] == VALUE_KIND_RANGE:
        form.fields[names['is_range']].initial = True
    if state['value_kind'] == VALUE_KIND_TOLERANCE:
        form.fields[names['is_tolerance']].initial = True


def clean_structure_decimal_fields(form, structure_field, cleaned_data: dict) -> dict:
    names = structure_decimal_field_names(structure_field.pk)
    is_range = cleaned_data.pop(names['is_range'], False)
    is_tolerance = cleaned_data.pop(names['is_tolerance'], False)
    kind = cleaned_data.pop(names['kind'], VALUE_KIND_SCALAR)
    if is_range and is_tolerance:
        is_tolerance = False
    resolved_kind = resolve_number_property_kind(
        is_range=is_range,
        is_tolerance=is_tolerance,
        hidden_kind=kind,
    )
    places = resolve_structure_field_decimal_places(structure_field)
    try:
        normalized = clean_number_property_fields(
            value_kind=resolved_kind,
            value=cleaned_data.pop(names['value'], ''),
            value_min=cleaned_data.pop(names['min'], ''),
            value_max=cleaned_data.pop(names['max'], ''),
            value_tolerance=cleaned_data.pop(names['tolerance'], ''),
            decimal_places=places,
        )
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
        if resolved_kind == VALUE_KIND_RANGE:
            form.add_error(names['min'], message)
        elif resolved_kind == VALUE_KIND_TOLERANCE:
            if 'погрешность' in message.lower():
                form.add_error(names['tolerance'], message)
            else:
                form.add_error(names['value'], message)
        else:
            form.add_error(names['value'], message)
        return cleaned_data
    form_state = form_state_from_value_slots(
        value_kind=normalized['value_kind'],
        value=normalized['value'],
        value_b=normalized['value_b'],
    )
    cleaned_data[names['value']] = form_state['value']
    cleaned_data[names['min']] = form_state['value_min']
    cleaned_data[names['max']] = form_state['value_max']
    cleaned_data[names['tolerance']] = form_state['value_tolerance']
    cleaned_data[names['kind']] = normalized['value_kind']
    packed = pack_decimal_field_data(
        structure_field.name,
        value_kind=normalized['value_kind'],
        value=normalized['value'],
        value_b=normalized['value_b'],
    )
    cleaned_data.update(packed)
    return cleaned_data


def collect_structure_decimal_sql_data(structure_field, cleaned_data: dict) -> dict:
    value_col, kind_col, b_col = decimal_storage_columns(structure_field.name)
    return {
        key: cleaned_data[key]
        for key in (value_col, kind_col, b_col)
        if key in cleaned_data
    }


def structure_decimal_bound_group(form, structure_field):
    names = structure_decimal_field_names(structure_field.pk)
    return {
        'structure_field': structure_field,
        'value': form[names['value']],
        'value_min': form[names['min']],
        'value_max': form[names['max']],
        'value_tolerance': form[names['tolerance']],
        'value_kind': form[names['kind']],
        'is_range': form[names['is_range']],
        'is_tolerance': form[names['is_tolerance']],
    }


def _decimal_property(structure_field):
    class _Prop:
        data_type = 'number'

        def effective_decimal_places(self):
            return resolve_structure_field_decimal_places(structure_field)

    return _Prop()
