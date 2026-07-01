from django import forms


class UserPickerWidget(forms.Select):
    template_name = 'widgets/user_picker.html'

    def __init__(self, *args, users=None, **kwargs):
        self.users = users
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['users'] = self.users or []
        return context
