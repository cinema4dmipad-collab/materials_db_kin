from datetime import datetime, timedelta

from django import forms
from django.utils import timezone


class ApiTokenCreateForm(forms.Form):
    name = forms.CharField(
        label='Название',
        max_length=256,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Например: KeenetiX — рабочий ПК',
    )
    expires_in_days = forms.IntegerField(
        label='Срок жизни, дней',
        required=False,
        min_value=1,
        max_value=3650,
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        help_text='Пусто и «Без срока» — токен бессрочный. По умолчанию 30 дней.',
    )
    never_expires = forms.BooleanField(
        label='Без срока',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def cleaned_expires_at(self):
        if self.cleaned_data.get('never_expires'):
            return None
        days = self.cleaned_data.get('expires_in_days')
        if days is None:
            days = 30
        return timezone.now() + timedelta(days=int(days))


class ApiTokenUpdateForm(forms.Form):
    name = forms.CharField(
        label='Название',
        max_length=256,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    expires_at = forms.DateTimeField(
        label='Действует до',
        required=False,
        widget=forms.DateTimeInput(
            attrs={'class': 'form-control', 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        help_text='Оставьте пустым для бессрочного токена.',
    )
    never_expires = forms.BooleanField(
        label='Без срока',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance is not None:
            self.fields['name'].initial = instance.name
            if instance.expires_at:
                local = timezone.localtime(instance.expires_at)
                self.fields['expires_at'].initial = local.strftime('%Y-%m-%dT%H:%M')
            else:
                self.fields['never_expires'].initial = True

    def cleaned_expires_at_value(self) -> datetime | None:
        if self.cleaned_data.get('never_expires'):
            return None
        return self.cleaned_data.get('expires_at')
