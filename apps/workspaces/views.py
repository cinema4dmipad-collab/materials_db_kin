from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.workspaces.forms import (
    UserCreateForm,
    UserMembershipAssignForm,
    WorkspaceForm,
    WorkspaceMembershipForm,
    WorkspaceSettingsForm,
)
from apps.workspaces.mixins import (
    AppViewMixin,
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SystemAdminRequiredMixin,
    WorkspaceMemberManageMixin,
)
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.workspaces.permissions import WorkspacePerm, can_manage_membership, has_workspace_perm, is_system_admin
from apps.workspaces.services import (
    get_user_workspaces,
    set_active_workspace,
)

User = get_user_model()


class WorkspaceLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True


class WorkspaceLogoutView(LogoutView):
    next_page = '/accounts/login/'


class WorkspaceSelectView(LoginRequiredMixin, ListView):
    template_name = 'workspaces/select.html'
    context_object_name = 'workspaces'

    def get_queryset(self):
        return get_user_workspaces(self.request.user)

    def get(self, request, *args, **kwargs):
        if not self.get_queryset().exists() and is_system_admin(request.user):
            messages.info(request, 'Создайте рабочее пространство для начала работы.')
        return super().get(request, *args, **kwargs)


class WorkspaceSwitchView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        workspace = get_object_or_404(Workspace, pk=kwargs['pk'], is_active=True)
        if not has_workspace_perm(request.user, workspace, WorkspacePerm.VIEW):
            return HttpResponseForbidden('Нет доступа к этому пространству.')
        set_active_workspace(request, workspace)
        messages.success(request, f'Выбрано пространство «{workspace.name}».')
        next_url = request.POST.get('next') or reverse('core:dashboard')
        select_url = reverse('workspaces:select')
        if next_url.rstrip('/') == select_url.rstrip('/'):
            next_url = reverse('core:dashboard')
        return redirect(next_url)


class WorkspaceCreateView(SystemAdminRequiredMixin, CreateView):
    model = Workspace
    form_class = WorkspaceForm
    template_name = 'workspaces/create.html'
    success_url = reverse_lazy('workspaces:select')

    def form_valid(self, form):
        messages.success(self.request, 'Рабочее пространство создано.')
        return super().form_valid(form)


class WorkspaceMembersView(WorkspaceMemberManageMixin, ListView):
    template_name = 'workspaces/members.html'
    context_object_name = 'memberships'

    def get_queryset(self):
        return (
            WorkspaceMembership.objects.filter(workspace=self.workspace)
            .select_related('user')
            .order_by('user__username')
        )

    def post(self, request, *args, **kwargs):
        form = WorkspaceMembershipForm(
            request.POST,
            workspace=self.workspace,
            acting_user=request.user,
        )
        if form.is_valid():
            membership = form.save(commit=False)
            membership.workspace = self.workspace
            if not is_system_admin(request.user):
                membership.role = WorkspaceRole.OPERATOR
            membership.save()
            messages.success(request, 'Участник добавлен.')
            return redirect('workspaces:members', pk=self.workspace.pk)

        self.object_list = self.get_queryset()
        context = self.get_context_data(membership_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            self._build_members_context(
                kwargs.get('membership_form')
                or WorkspaceMembershipForm(
                    workspace=self.workspace,
                    acting_user=self.request.user,
                )
            )
        )
        return context

    def _build_members_context(self, membership_form):
        return {
            'workspace': self.workspace,
            'membership_form': membership_form,
            'can_add_members': membership_form.fields['user'].queryset.exists(),
            'can_assign_manager_role': is_system_admin(self.request.user),
            'is_system_admin': is_system_admin(self.request.user),
        }


class WorkspaceMemberCreateView(WorkspaceMemberManageMixin, CreateView):
    """Legacy POST endpoint — перенаправляет на список участников."""

    def post(self, request, *args, **kwargs):
        members_view = WorkspaceMembersView.as_view()
        kwargs['pk'] = self.kwargs['pk']
        return members_view(request, pk=self.kwargs['pk'])


class WorkspaceMemberUpdateView(WorkspaceMemberManageMixin, UpdateView):
    model = WorkspaceMembership
    form_class = WorkspaceMembershipForm
    template_name = 'workspaces/members.html'
    pk_url_kwarg = 'membership_pk'

    def dispatch(self, request, *args, **kwargs):
        workspace = get_object_or_404(Workspace, pk=kwargs['pk'])
        membership = get_object_or_404(
            WorkspaceMembership.objects.filter(workspace=workspace),
            pk=kwargs['membership_pk'],
        )
        if not can_manage_membership(request.user, membership):
            return HttpResponseForbidden('Нельзя изменить эту роль.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return WorkspaceMembership.objects.filter(workspace=self.workspace)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workspace'] = self.workspace
        kwargs['acting_user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not is_system_admin(self.request.user):
            form.instance.role = WorkspaceRole.OPERATOR
        messages.success(self.request, 'Роль участника обновлена.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('workspaces:members', kwargs={'pk': self.workspace.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            WorkspaceMembersView._build_members_context(
                self,
                WorkspaceMembershipForm(
                    workspace=self.workspace,
                    acting_user=self.request.user,
                ),
            )
        )
        context['memberships'] = (
            WorkspaceMembership.objects.filter(workspace=self.workspace)
            .select_related('user')
            .order_by('user__username')
        )
        context['form'] = context.get('form')
        return context


class WorkspaceMemberDeleteView(WorkspaceMemberManageMixin, DeleteView):
    model = WorkspaceMembership
    pk_url_kwarg = 'membership_pk'

    def dispatch(self, request, *args, **kwargs):
        workspace = get_object_or_404(Workspace, pk=kwargs['pk'])
        membership = get_object_or_404(
            WorkspaceMembership.objects.filter(workspace=workspace),
            pk=kwargs['membership_pk'],
        )
        if not can_manage_membership(request.user, membership):
            return HttpResponseForbidden('Нельзя удалить этого участника.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return WorkspaceMembership.objects.filter(workspace=self.workspace)

    def form_valid(self, form):
        messages.success(self.request, 'Участник удалён из пространства.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('workspaces:members', kwargs={'pk': self.workspace.pk})


class WorkspaceSettingsView(AppViewMixin, PermissionRequiredMixin, UpdateView):
    model = Workspace
    form_class = WorkspaceSettingsForm
    template_name = 'workspaces/settings.html'
    permission_codename = WorkspacePerm.MANAGE_SETTINGS

    def get_object(self, queryset=None):
        workspace = get_object_or_404(Workspace, pk=self.kwargs['pk'], is_active=True)
        if workspace.pk != getattr(self.request.active_workspace, 'pk', None) and not is_system_admin(
            self.request.user
        ):
            return get_object_or_404(Workspace, pk=self.request.active_workspace.pk)
        return workspace

    def form_valid(self, form):
        messages.success(self.request, 'Настройки пространства сохранены.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('workspaces:settings', kwargs={'pk': self.object.pk})


class AdminUserListView(SystemAdminRequiredMixin, ListView):
    model = User
    template_name = 'administration/users/list.html'
    context_object_name = 'users'
    paginate_by = 25

    def get_queryset(self):
        return User.objects.order_by('username')


class AdminUserCreateView(SystemAdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'administration/users/form.html'
    success_url = reverse_lazy('administration:admin_users')

    def form_valid(self, form):
        messages.success(self.request, 'Пользователь создан.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Создание пользователя'
        return context


class AdminUserUpdateView(SystemAdminRequiredMixin, UpdateView):
    model = User
    fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser')
    template_name = 'administration/users/form.html'
    success_url = reverse_lazy('administration:admin_users')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['username'].label = 'Логин'
        form.fields['email'].label = 'E-mail'
        form.fields['first_name'].label = 'Имя'
        form.fields['last_name'].label = 'Фамилия'
        form.fields['is_active'].label = 'Активен'
        form.fields['is_staff'].label = 'Доступ в админку Django'
        form.fields['is_superuser'].label = 'Системный администратор'
        return form

    def form_valid(self, form):
        messages.success(self.request, 'Пользователь обновлён.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Редактирование пользователя'
        return context


class AdminUserMembershipView(SystemAdminRequiredMixin, View):
    template_name = 'workspaces/members.html'

    def get_target_user(self):
        return get_object_or_404(User, pk=self.kwargs['pk'])

    def get(self, request, *args, **kwargs):
        target_user = self.get_target_user()
        memberships = WorkspaceMembership.objects.filter(user=target_user).select_related('workspace')
        return self._render(
            request,
            target_user,
            memberships,
            UserMembershipAssignForm(user=target_user),
        )

    def post(self, request, *args, **kwargs):
        target_user = self.get_target_user()
        form = UserMembershipAssignForm(request.POST, user=target_user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Участие в пространстве назначено.')
            return redirect('administration:admin_user_memberships', pk=target_user.pk)
        memberships = WorkspaceMembership.objects.filter(user=target_user).select_related('workspace')
        return self._render(request, target_user, memberships, form)

    def _render(self, request, target_user, memberships, form):
        from django.shortcuts import render

        return render(
            request,
            'administration/users/memberships.html',
            {
                'target_user': target_user,
                'memberships': memberships,
                'membership_form': form,
            },
        )
