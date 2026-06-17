from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import Tag
from apps.core.tag_utils import normalize_tag_name, tag_slug_from_name, validate_tag_names

_BOOTSTRAP_INPUT = {'class': 'form-control'}


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs=_BOOTSTRAP_INPUT),
        }
        labels = {
            'name': 'Название',
        }
        help_texts = {
            'name': 'Название должно быть уникальным.',
        }

    def clean_name(self):
        name = normalize_tag_name(self.cleaned_data.get('name', ''))
        if not name:
            raise ValidationError('Укажите название тега.')
        validate_tag_names([name])
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        if not name:
            return cleaned_data

        slug = tag_slug_from_name(name)
        queryset = Tag.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            existing = queryset.first()
            self.add_error('name', f'Тег «{existing.name}» уже существует.')
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = tag_slug_from_name(instance.name)
        if commit:
            instance.save()
        return instance
