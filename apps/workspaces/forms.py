from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.db.models import Q
from django.utils.text import slugify

from apps.workspaces.models import Workspace, WorkspaceGroup, WorkspaceGroupMembership
from apps.workspaces.permissions import (
    PERMISSION_BUNDLE_KEYS,
    UI_PERMISSION_BUNDLES,
    WorkspacePerm,
    can_assign_group,
    expand_permission_bundles,
    is_system_admin,
    permission_bundles_for_permissions,
)
from apps.workspaces.services import assign_user_to_groups, assign_user_to_selected_groups, set_user_groups

from apps.workspaces.widgets import GroupPickerWidget, UserPickerWidget

User = get_user_model()


def available_users_for_workspace(workspace):
    member_ids = (
        WorkspaceGroupMembership.objects.filter(group__workspace=workspace)
        .values_list('user_id', flat=True)
        .distinct()
    )
    return User.objects.exclude(pk__in=member_ids).order_by('username')


def all_assignable_groups_queryset():
    return (
        WorkspaceGroup.objects.filter(workspace__is_active=True)
        .select_related('workspace')
        .order_by('workspace__name', 'name')
    )


def assignable_groups_queryset(workspace, acting_user):
    all_groups = WorkspaceGroup.objects.filter(workspace=workspace).order_by('name')
    if acting_user and not is_system_admin(acting_user):
        assignable = [
            group for group in all_groups if can_assign_group(acting_user, workspace, group)
        ]
        return WorkspaceGroup.objects.filter(pk__in=[group.pk for group in assignable])
    return all_groups


def member_groups_queryset(workspace, acting_user, target_user=None):
    queryset = assignable_groups_queryset(workspace, acting_user)
    if target_user is None:
        return queryset
    current_ids = WorkspaceGroup.objects.filter(
        workspace=workspace,
        memberships__user=target_user,
    ).values_list('pk', flat=True)
    return WorkspaceGroup.objects.filter(
        workspace=workspace,
    ).filter(
        Q(pk__in=queryset.values('pk')) | Q(pk__in=current_ids),
    ).order_by('name')


def configure_group_picker_field(field):
    queryset = field.queryset.select_related('workspace').order_by('workspace__name', 'name')
    field.widget.group_items = [
        {
            'id': str(group.pk),
            'name': group.name,
            'workspace': group.workspace.name,
        }
        for group in queryset
    ]


class WorkspaceGroupChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class WorkspaceMemberAddRowForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.HiddenInput,
    )
    groups = WorkspaceGroupChoiceField(
        queryset=WorkspaceGroup.objects.none(),
        widget=GroupPickerWidget(),
        label='Группы',
    )

    def __init__(self, *args, workspace=None, acting_user=None, **kwargs):
        self.workspace = workspace
        self.acting_user = acting_user
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields['groups'].queryset = assignable_groups_queryset(workspace, acting_user)
            configure_group_picker_field(self.fields['groups'])

    def clean_groups(self):
        groups = self.cleaned_data.get('groups')
        if not groups:
            raise forms.ValidationError('Выберите хотя бы одну группу.')
        if self.acting_user and self.workspace:
            for group in groups:
                if not can_assign_group(self.acting_user, self.workspace, group):
                    raise forms.ValidationError(
                        f'Нельзя назначить группу «{group.name}» — недостаточно прав.'
                    )
        return groups


class WorkspaceMemberAddFormSet(forms.BaseFormSet):
    def __init__(self, *args, workspace=None, acting_user=None, **kwargs):
        self.workspace = workspace
        self.acting_user = acting_user
        self.available_users = (
            available_users_for_workspace(workspace)
            if workspace
            else User.objects.none()
        )
        super().__init__(*args, **kwargs)
        for form in self.forms:
            self._configure_member_add_form(form)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['workspace'] = self.workspace
        kwargs['acting_user'] = self.acting_user
        return kwargs

    def _configure_member_add_form(self, form):
        form.workspace = self.workspace
        form.acting_user = self.acting_user
        form.fields['user'].queryset = self.available_users
        if self.workspace:
            form.fields['groups'].queryset = assignable_groups_queryset(
                self.workspace,
                self.acting_user,
            )
            configure_group_picker_field(form.fields['groups'])

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        self._configure_member_add_form(form)
        return form

    def clean(self):
        super().clean()
        if any(form.errors for form in self.forms):
            return

        active_users = []
        has_active = False
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            has_active = True
            user = form.cleaned_data.get('user')
            if user is None:
                continue
            if user.pk in active_users:
                form.add_error(None, 'Пользователь уже добавлен в список.')
            active_users.append(user.pk)

        if not has_active:
            raise forms.ValidationError('Добавьте хотя бы одного участника.')

    def save(self):
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            group_names = [group.name for group in form.cleaned_data['groups']]
            assign_user_to_groups(form.cleaned_data['user'], self.workspace, group_names)


WorkspaceMemberAddFormSet = forms.formset_factory(
    WorkspaceMemberAddRowForm,
    formset=WorkspaceMemberAddFormSet,
    extra=0,
    can_delete=True,
)


def _add_bootstrap_classes(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxSelectMultiple):
            continue
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


def _permission_bundle_choices():
    return [(key, label) for key, label, _codes in UI_PERMISSION_BUNDLES]


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
        if self.instance._state.adding:
            self.fields.pop('is_active', None)
        _add_bootstrap_classes(self)


class WorkspaceGroupForm(forms.ModelForm):
    permission_bundles = forms.MultipleChoiceField(
        choices=_permission_bundle_choices(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Разделы',
        help_text='Выбранный раздел включает все операции внутри него. Базовый доступ к пространству добавляется автоматически.',
    )

    class Meta:
        model = WorkspaceGroup
        fields = ('name', 'description')
        labels = {
            'name': 'Название',
            'description': 'Описание',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.permissions:
            self.initial['permission_bundles'] = permission_bundles_for_permissions(
                self.instance.permissions
            )
        if self.instance.is_builtin:
            self.fields['name'].disabled = True
        _add_bootstrap_classes(self)

    def clean(self):
        cleaned_data = super().clean()
        bundles = cleaned_data.get('permission_bundles') or []
        unknown = set(bundles) - PERMISSION_BUNDLE_KEYS
        if unknown:
            raise forms.ValidationError({'permission_bundles': 'Выбран неизвестный раздел прав.'})
        permissions = expand_permission_bundles(bundles)
        if not permissions:
            raise forms.ValidationError({'permission_bundles': 'Выберите хотя бы один раздел.'})
        cleaned_data['expanded_permissions'] = permissions
        return cleaned_data

    def save(self, commit=True):
        group = super().save(commit=False)
        group.permissions = self.cleaned_data['expanded_permissions']
        if self.workspace:
            group.workspace = self.workspace
        if commit:
            group.save()
        return group


class WorkspaceUserGroupsForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label='Пользователь',
        empty_label=None,
        widget=UserPickerWidget(),
    )
    groups = WorkspaceGroupChoiceField(
        queryset=WorkspaceGroup.objects.none(),
        widget=GroupPickerWidget(),
        label='Группы',
    )

    def __init__(self, *args, workspace=None, acting_user=None, target_user=None, **kwargs):
        self.workspace = workspace
        self.acting_user = acting_user
        self.target_user = target_user

        if target_user is not None and workspace is not None:
            kwargs.setdefault('initial', {})
            kwargs['initial']['groups'] = list(
                WorkspaceGroup.objects.filter(
                    workspace=workspace,
                    memberships__user=target_user,
                ).values_list('pk', flat=True)
            )

        super().__init__(*args, **kwargs)

        if workspace:
            self.fields['groups'].queryset = member_groups_queryset(
                workspace,
                acting_user,
                target_user,
            )
            configure_group_picker_field(self.fields['groups'])
        if target_user is None:
            member_ids = WorkspaceGroupMembership.objects.filter(
                group__workspace=workspace,
            ).values_list('user_id', flat=True)
            user_queryset = User.objects.exclude(pk__in=member_ids).order_by('username')
            self.fields['user'].queryset = user_queryset
            self.fields['user'].widget.users = list(user_queryset)
        else:
            user_queryset = User.objects.filter(pk=target_user.pk)
            self.fields['user'].queryset = user_queryset
            self.fields['user'].widget.users = list(user_queryset)
            self.fields['user'].initial = target_user.pk
            self.fields['user'].disabled = True
        _add_bootstrap_classes(self)

    def clean_groups(self):
        groups = self.cleaned_data.get('groups')
        if not groups:
            raise forms.ValidationError('Выберите хотя бы одну группу.')
        if self.acting_user and self.workspace:
            for group in groups:
                if not can_assign_group(self.acting_user, self.workspace, group):
                    raise forms.ValidationError(
                        f'Нельзя назначить группу «{group.name}» — недостаточно прав.'
                    )
        return groups

    def save(self):
        user = self.target_user or self.cleaned_data['user']
        group_names = [group.name for group in self.cleaned_data['groups']]
        if self.target_user:
            set_user_groups(user, self.workspace, group_names)
        else:
            assign_user_to_groups(user, self.workspace, group_names)
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')
        labels = {
            'email': 'E-mail',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_bootstrap_classes(self)


class UserPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'Текущий пароль'
        self.fields['new_password1'].label = 'Новый пароль'
        self.fields['new_password2'].label = 'Подтверждение нового пароля'
        _add_bootstrap_classes(self)


class UserAdminUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
            'is_staff',
            'is_superuser',
        )
        labels = {
            'username': 'Логин',
            'email': 'E-mail',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'is_active': 'Активен',
            'is_staff': 'Доступ в админку Django',
            'is_superuser': 'Системный администратор',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_bootstrap_classes(self)


class WorkspaceLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'
        self.fields['username'].widget.attrs.setdefault('autocomplete', 'username')
        self.fields['password'].widget.attrs.setdefault('autocomplete', 'current-password')
        _add_bootstrap_classes(self)


class UserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_staff')
        labels = {
            'username': 'Логин',
            'email': 'E-mail',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
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


class UserMembershipAssignForm(forms.Form):
    groups = WorkspaceGroupChoiceField(
        queryset=WorkspaceGroup.objects.none(),
        widget=GroupPickerWidget(),
        label='Группы',
    )

    def __init__(self, *args, user=None, **kwargs):
        self.target_user = user
        super().__init__(*args, **kwargs)
        self.fields['groups'].queryset = all_assignable_groups_queryset()
        configure_group_picker_field(self.fields['groups'])
        _add_bootstrap_classes(self)

    def clean_groups(self):
        groups = self.cleaned_data.get('groups')
        if not groups:
            raise forms.ValidationError('Выберите хотя бы одну группу.')
        return groups

    def save(self):
        assign_user_to_selected_groups(self.target_user, self.cleaned_data['groups'])
        return self.target_user
