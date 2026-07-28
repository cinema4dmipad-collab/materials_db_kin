import uuid

from django import forms
from django.forms.utils import flatatt
from django.template.loader import render_to_string
from django.utils.html import json_script

from apps.core.models import Tag
from apps.core.tag_utils import active_tags_queryset, dedupe_tag_suggestion_rows


class TagNamesWidget(forms.TextInput):
    template_name = 'widgets/tag_names_input.html'

    def __init__(self, attrs=None, tag_suggestions=None, *, allow_colors=False, colors_value=''):
        self.tag_suggestions = tag_suggestions
        self.allow_colors = bool(allow_colors)
        self.colors_value = colors_value or ''
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
            return dedupe_tag_suggestion_rows(list(self.tag_suggestions))
        return dedupe_tag_suggestion_rows(
            list(
                active_tags_queryset(Tag.objects.all()).order_by('name').values(
                    'name',
                    'slug',
                    'color',
                    'description',
                    'workspace_id',
                )
            )
        )

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        suggestions = self.get_tag_suggestions()
        # Do not leak internal workspace_id into the browser payload.
        public_suggestions = [
            {
                'name': item.get('name', ''),
                'slug': item.get('slug', ''),
                'color': item.get('color', ''),
                'description': item.get('description', ''),
            }
            for item in suggestions
        ]
        script_id = f'tag-suggestions-{uuid.uuid4().hex}'
        context['widget']['tag_suggestions'] = public_suggestions
        context['widget']['tag_suggestions_script_id'] = script_id
        context['widget']['tag_suggestions_json_script'] = json_script(public_suggestions, script_id)
        context['widget']['extra_attrs'] = flatatt(context['widget']['attrs'])
        context['widget']['allow_colors'] = self.allow_colors
        context['widget']['colors_value'] = self.colors_value
        return context

    def render(self, name, value, attrs, renderer=None):
        context = self.get_context(name, value, attrs or {})
        return render_to_string(self.template_name, context)
