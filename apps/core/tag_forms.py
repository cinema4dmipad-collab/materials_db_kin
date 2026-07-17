from django import forms

from apps.core.tag_utils import active_tags_queryset, assign_tags, format_tags_for_input, parse_tag_input, validate_tag_names
from apps.core.widgets import TagNamesWidget


class TagNamesFormMixin:
    tag_field_name = 'tag_names'

    def __init__(self, *args, workspace=None, **kwargs):
        self.tag_workspace = workspace
        super().__init__(*args, **kwargs)
        self._setup_tag_names_field()

    def _setup_tag_names_field(self):
        initial = ''
        if getattr(self.instance, 'pk', None):
            initial = format_tags_for_input(self.instance.tags.all())

        widget_kwargs = {}
        if self.tag_workspace is not None:
            from apps.workspaces.services import tags_in_workspace

            widget_kwargs['tag_suggestions'] = list(
                active_tags_queryset(tags_in_workspace(self.tag_workspace)).values(
                    'name',
                    'slug',
                    'color',
                    'description',
                )
            )

        self.fields[self.tag_field_name] = forms.CharField(
            required=False,
            label='Теги',
            help_text='Введите название и нажмите Enter, или выберите из списка. Повторный клик по тегу убирает его.',
            initial=initial,
            widget=TagNamesWidget(**widget_kwargs),
        )

    def clean_tag_names(self):
        names = parse_tag_input(self.cleaned_data.get(self.tag_field_name, ''))
        validate_tag_names(names)
        return names

    def save_tags(self, instance) -> None:
        if not hasattr(instance, 'tags'):
            return
        names = self.cleaned_data.get(self.tag_field_name, [])
        assign_tags(instance, names, workspace=self.tag_workspace)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            self.save_tags(instance)
        return instance
