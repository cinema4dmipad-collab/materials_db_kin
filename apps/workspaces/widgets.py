from django import forms
from django.template.loader import render_to_string


class UserPickerWidget(forms.Select):
    template_name = 'widgets/user_picker.html'

    def __init__(self, *args, users=None, **kwargs):
        self.users = users
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['users'] = self.users or []
        return context


class GroupPickerWidget(forms.CheckboxSelectMultiple):
    template_name = 'widgets/group_picker.html'

    def __init__(self, attrs=None, group_items=None):
        self.group_items = group_items or []
        super().__init__(attrs=attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context['widget']
        group_items = self.group_items or []
        widget['group_items'] = group_items
        workspaces = {item['workspace'] for item in group_items if item.get('workspace')}
        widget['show_workspace_sections'] = len(workspaces) > 1
        return context

    def render(self, name, value, attrs, renderer=None):
        context = self.get_context(name, value, attrs)
        return render_to_string(self.template_name, context)
