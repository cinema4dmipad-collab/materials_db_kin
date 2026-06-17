import json

from django import forms
from django.forms.utils import flatatt
from django.template.loader import render_to_string
from django.utils.html import escape

from apps.core.models import Tag


class TagNamesWidget(forms.TextInput):
    template_name = 'widgets/tag_names_input.html'

    def __init__(self, attrs=None, tag_suggestions=None):
        self.tag_suggestions = tag_suggestions
        default_attrs = {
            'class': 'tag-input-typing',
            'placeholder': 'Добавить тег…',
            'autocomplete': 'off',
            'spellcheck': 'false',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def get_tag_suggestions(self):
        if self.tag_suggestions is not None:
            return self.tag_suggestions
        return list(Tag.objects.order_by('name').values('name', 'slug'))

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        suggestions = self.get_tag_suggestions()
        context['widget']['tag_suggestions'] = suggestions
        context['widget']['tag_suggestions_json'] = escape(
            json.dumps(suggestions, ensure_ascii=False),
        )
        context['widget']['extra_attrs'] = flatatt(context['widget']['attrs'])
        return context

    def render(self, name, value, attrs, renderer=None):
        context = self.get_context(name, value, attrs or {})
        return render_to_string(self.template_name, context)