from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from apps.core.number_utils import (
    format_decimal_display,
    normalize_decimal_input,
)

LOCALIZED_DECIMAL_WIDGET_ATTRS = {
    'class': 'form-control localized-number-input',
    'inputmode': 'decimal',
    'autocomplete': 'off',
}


class LocalizedDecimalWidget(forms.TextInput):
    def __init__(self, attrs=None):
        merged = {**LOCALIZED_DECIMAL_WIDGET_ATTRS, **(attrs or {})}
        super().__init__(attrs=merged)


class LocalizedDecimalField(forms.DecimalField):
    widget = LocalizedDecimalWidget

    def prepare_value(self, value):
        if value in (None, ''):
            return ''
        return format_decimal_display(value, self.decimal_places)

    def to_python(self, value):
        if value in (None, ''):
            return None
        if not isinstance(value, str):
            return super().to_python(value)
        normalized = normalize_decimal_input(value)
        if not normalized:
            return None
        return super().to_python(normalized)


class LocalizedFloatField(forms.FloatField):
    widget = LocalizedDecimalWidget

    def prepare_value(self, value):
        if value in (None, ''):
            return ''
        return format_decimal_display(value)

    def to_python(self, value):
        if value in (None, ''):
            return None
        if isinstance(value, str):
            normalized = normalize_decimal_input(value)
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError as exc:
                raise ValidationError('Введите корректное число.') from exc
        return super().to_python(value)


class LocalizedPropertyValueField(forms.CharField):
    widget = LocalizedDecimalWidget

    def prepare_value(self, value):
        if value in (None, ''):
            return ''
        return format_decimal_display(value)

    def to_python(self, value):
        value = super().to_python(value)
        if value in (None, ''):
            return ''
        return value.strip()


def clean_localized_number_value(form, *, property_field_name='property', value_field_name='value'):
    value = (form.cleaned_data.get(value_field_name) or '').strip()
    prop = form.cleaned_data.get(property_field_name)
    if not value or not prop or prop.data_type != 'number':
        form.cleaned_data[value_field_name] = value
        return

    normalized = normalize_decimal_input(value)
    if not normalized:
        form.cleaned_data[value_field_name] = ''
        return

    try:
        Decimal(normalized)
    except InvalidOperation:
        form.add_error(value_field_name, 'Введите корректное число.')
        return

    form.cleaned_data[value_field_name] = normalized
