from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import slugify

from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.permissions import is_system_admin

User = get_user_model()


def _add_bootstrap_classes(form):
    for field in form.fields.values():
        if isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css} form-check-input'.strip()
        elif isinstance(field.widget, forms.Select):
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css} form-select'.strip()
        else:
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css} form-control'.strip()
    return form


class WorkspaceForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ('slug', 'name', 'description', 'is_active')
        labels = {
            'slug': 'Код',
            'name': 'Название',
            'description': 'Описание',
            'is_active': 'Активно',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip()
        if not slug and self.cleaned_data.get('name'):
            slug = slugify(self.cleaned_data['name'])
        if not slug:
            raise forms.ValidationError('Укажите код пространства.')
        return slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_bootstrap_classes(self)


class WorkspaceMembershipForm(forms.ModelForm):
    class Meta:
        model = WorkspaceMembership
        fields = ('user', 'role')
        labels = {
            'user': 'Пользователь',
            'role': 'Роль',
        }

    def __init__(self, *args, workspace=None, acting_user=None, **kwargs):
        self.workspace = workspace
        self.acting_user = acting_user
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.order_by('username')
        if self.workspace and self.instance._state.adding:
            member_ids = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
            ).values_list('user_id', flat=True)
            self.fields['user'].queryset = User.objects.exclude(
                pk__in=member_ids,
            ).order_by('username')
        _add_bootstrap_classes(self)
        if not self.instance._state.adding:
            self.fields['user'].disabled = True
        if acting_user and not is_system_admin(acting_user):
            self.fields['role'].choices = [
                (WorkspaceRole.OPERATOR, dict(WorkspaceRole.choices)[WorkspaceRole.OPERATOR]),
            ]
            if self.instance._state.adding:
                self.fields['role'].initial = WorkspaceRole.OPERATOR

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if self.acting_user and not is_system_admin(self.acting_user):
            if role != WorkspaceRole.OPERATOR:
                raise forms.ValidationError('Менеджер может назначать только роль оператора.')
            if not self.instance._state.adding and self.instance.role == WorkspaceRole.MANAGER:
                raise forms.ValidationError('Нельзя изменить роль менеджера пространства.')
        return role

    def clean(self):
        cleaned = super().clean()
        user = cleaned.get('user')
        if self.workspace and user:
            qs = WorkspaceMembership.objects.filter(workspace=self.workspace, user=user)
            if not self.instance._state.adding:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Пользователь уже состоит в этом пространстве.')
        return cleaned


class UserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')
        labels = {
            'username': 'Логин',
            'email': 'E-mail',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'is_active': 'Активен',
            'is_staff': 'Доступ в админку Django',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Пароль'
        self.fields['password2'].label = 'Подтверждение пароля'
        _add_bootstrap_classes(self)


class WorkspaceSettingsForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ('name', 'description')
        labels = {
            'name': 'Название',
            'description': 'Описание',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_bootstrap_classes(self)


class UserMembershipAssignForm(forms.ModelForm):
    workspace = forms.ModelChoiceField(
        queryset=Workspace.objects.filter(is_active=True).order_by('name'),
        label='Пространство',
    )

    class Meta:
        model = WorkspaceMembership
        fields = ('workspace', 'role')
        labels = {
            'role': 'Роль',
        }

    def __init__(self, *args, user=None, **kwargs):
        self.target_user = user
        super().__init__(*args, **kwargs)
        _add_bootstrap_classes(self)

    def clean(self):
        cleaned = super().clean()
        workspace = cleaned.get('workspace')
        if self.target_user and workspace:
            if WorkspaceMembership.objects.filter(workspace=workspace, user=self.target_user).exists():
                raise forms.ValidationError('Пользователь уже состоит в этом пространстве.')
        return cleaned

    def save(self, commit=True):
        membership = super().save(commit=False)
        membership.user = self.target_user
        if commit:
            membership.save()
        return membership
