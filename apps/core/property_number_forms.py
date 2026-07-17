from django import forms
from django.core.exceptions import ValidationError

from apps.core.fields import (
    LocalizedPropertyValueField,
    apply_property_decimal_places_to_value_field,
    localized_range_bound_field,
)
from apps.core.property_number_value import (
    VALUE_KIND_RANGE,
    VALUE_KIND_SCALAR,
    VALUE_KIND_TOLERANCE,
    clean_number_property_fields,
    form_state_from_value_slots,
)


def resolve_number_property_kind(*, is_range, is_tolerance, hidden_kind):
    if is_range:
        return VALUE_KIND_RANGE
    if is_tolerance:
        return VALUE_KIND_TOLERANCE
    kind = (hidden_kind or VALUE_KIND_SCALAR).strip()
    if kind in {VALUE_KIND_SCALAR, VALUE_KIND_RANGE, VALUE_KIND_TOLERANCE}:
        return kind
    return VALUE_KIND_SCALAR


class NumberPropertyValueFormMixin:
    def _init_number_property_fields(self, prop):
        if 'value_kind' in self.fields:
            self.fields['value_kind'].widget = forms.HiddenInput()
        if 'value_b' in self.fields:
            self.fields['value_b'].widget = forms.HiddenInput()
            self.fields['value_b'].required = False
        if prop is not None and getattr(prop, 'data_type', None) != 'number':
            for name in (
                'value_kind',
                'value_b',
                'value_min',
                'value_max',
                'value_tolerance',
                'is_range',
                'is_tolerance',
            ):
                self.fields.pop(name, None)
            return
        instance_kind = getattr(self.instance, 'value_kind', None)
        self.fields['is_range'] = forms.BooleanField(
            required=False,
            label='Диапазон',
            widget=forms.CheckboxInput(
                attrs={'class': 'form-check-input property-number-value__range-toggle'},
            ),
            initial=instance_kind == VALUE_KIND_RANGE,
        )
        self.fields['is_tolerance'] = forms.BooleanField(
            required=False,
            label='±',
            widget=forms.CheckboxInput(
                attrs={'class': 'form-check-input property-number-value__tolerance-toggle'},
            ),
            initial=instance_kind == VALUE_KIND_TOLERANCE,
        )
        if 'value_tolerance' not in self.fields:
            self.fields['value_tolerance'] = localized_range_bound_field(bound_label='±')
        for name in ('value', 'value_min', 'value_max', 'value_tolerance'):
            if name in self.fields and isinstance(self.fields[name], LocalizedPropertyValueField):
                apply_property_decimal_places_to_value_field(self.fields[name], prop)
        self._init_number_property_from_instance()

    def _init_number_property_from_instance(self):
        instance = getattr(self, 'instance', None)
        if instance is None or not getattr(instance, 'pk', None):
            return
        if not hasattr(instance, 'value_b'):
            return
        state = form_state_from_value_slots(
            value_kind=getattr(instance, 'value_kind', VALUE_KIND_SCALAR),
            value=getattr(instance, 'value', None),
            value_b=getattr(instance, 'value_b', None),
        )
        for key, field_value in state.items():
            if key in self.fields:
                self.fields[key].initial = field_value

    def _clean_number_property(self, cleaned_data, prop):
        if not prop or prop.data_type != 'number':
            cleaned_data.pop('is_range', None)
            cleaned_data.pop('is_tolerance', None)
            return cleaned_data
        is_range = cleaned_data.pop('is_range', False)
        is_tolerance = cleaned_data.pop('is_tolerance', False)
        if is_range and is_tolerance:
            is_tolerance = False
        kind = resolve_number_property_kind(
            is_range=is_range,
            is_tolerance=is_tolerance,
            hidden_kind=cleaned_data.get('value_kind'),
        )
        try:
            normalized = clean_number_property_fields(
                value_kind=kind,
                value=cleaned_data.get('value'),
                value_min=cleaned_data.get('value_min'),
                value_max=cleaned_data.get('value_max'),
                value_tolerance=cleaned_data.get('value_tolerance'),
                decimal_places=prop.effective_decimal_places(),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
            if kind == VALUE_KIND_RANGE:
                self.add_error('value_min', message)
            elif kind == VALUE_KIND_TOLERANCE:
                if 'погрешность' in message.lower():
                    self.add_error('value_tolerance', message)
                else:
                    self.add_error('value', message)
            else:
                self.add_error('value', message)
            return cleaned_data
        cleaned_data.update(normalized)
        return cleaned_data
