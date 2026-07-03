from django.contrib import messages

from django.contrib.auth import get_user_model

from django.contrib.auth.views import LoginView, LogoutView

from django.db.models import Count

from django.db.models.deletion import ProtectedError

from django.http import HttpResponseForbidden

from django.shortcuts import get_object_or_404, redirect, render

from django.urls import reverse, reverse_lazy

from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView, View



from apps.workspaces.forms import (

    UserCreateForm,

    UserMembershipAssignForm,

    WorkspaceForm,

    WorkspaceGroupForm,

    WorkspaceMemberAddFormSet,

    WorkspaceSettingsForm,

    WorkspaceUserGroupsForm,

    available_users_for_workspace,

)
from apps.workspaces.picker_data import workspace_users_for_picker

from apps.workspaces.mixins import (

    AppViewMixin,

    LoginRequiredMixin,

    PermissionRequiredMixin,

    SystemAdminRequiredMixin,

    WorkspaceGroupManageMixin,

    WorkspaceMemberManageMixin,

)

from apps.workspaces.models import Workspace, WorkspaceGroup, WorkspaceGroupMembership

from apps.workspaces.permissions import (

    PERMISSION_SECTIONS,

    WorkspacePerm,

    can_manage_membership,

    get_user_groups,

    has_workspace_perm,

    is_system_admin,

)

from apps.workspaces.services import (

    ensure_default_groups,

    get_user_workspaces,

    redirect_url_after_workspace_switch,

    set_active_workspace,

)



User = get_user_model()





class WorkspaceLoginView(LoginView):

    template_name = 'registration/login.html'

    redirect_authenticated_user = True





class WorkspaceLogoutView(LogoutView):

    next_page = '/accounts/login/'





class UserProfileView(LoginRequiredMixin, TemplateView):

    template_name = 'accounts/profile.html'



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        user = self.request.user

        context['profile_user'] = user

        workspace_rows = []

        for workspace in get_user_workspaces(user):

            groups = get_user_groups(user, workspace)

            workspace_rows.append({'workspace': workspace, 'groups': groups})

        context['workspace_rows'] = workspace_rows

        return context





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

        next_url = redirect_url_after_workspace_switch(workspace, next_url, request.user)

        return redirect(next_url)





class WorkspaceCreateView(SystemAdminRequiredMixin, CreateView):

    model = Workspace

    form_class = WorkspaceForm

    template_name = 'administration/workspaces/form.html'

    success_url = reverse_lazy('administration:admin_workspaces')



    def form_valid(self, form):

        response = super().form_valid(form)

        ensure_default_groups(self.object)

        messages.success(self.request, 'Рабочее пространство создано.')

        return response



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['cancel_url'] = reverse('administration:admin_workspaces')

        context['page_title'] = 'Новое рабочее пространство'

        context['submit_label'] = 'Создать'

        return context





def _workspace_member_rows(workspace, acting_user=None):

    user_ids = (

        WorkspaceGroupMembership.objects.filter(group__workspace=workspace)

        .values_list('user_id', flat=True)

        .distinct()

    )

    rows = []

    for user in User.objects.filter(pk__in=user_ids).order_by('username'):

        groups = list(get_user_groups(user, workspace))

        can_manage = True

        if acting_user is not None:

            can_manage = can_manage_membership(acting_user, user, workspace)

        rows.append({'user': user, 'groups': groups, 'can_manage': can_manage})

    return rows





class WorkspaceMembersView(WorkspaceMemberManageMixin, ListView):

    template_name = 'workspaces/members.html'

    context_object_name = 'members'



    def get_queryset(self):

        return _workspace_member_rows(self.workspace, acting_user=self.request.user)



    def post(self, request, *args, **kwargs):

        formset = WorkspaceMemberAddFormSet(

            request.POST,

            workspace=self.workspace,

            acting_user=request.user,

            prefix='members',

        )

        if formset.is_valid():

            formset.save()

            added_count = sum(

                1

                for form in formset.forms

                if getattr(form, 'cleaned_data', None) and not form.cleaned_data.get('DELETE')

            )

            if added_count == 1:

                messages.success(request, 'Участник добавлен.')

            else:

                messages.success(request, f'Добавлено участников: {added_count}.')

            return redirect('workspaces:members', pk=self.workspace.pk)



        self.object_list = self.get_queryset()

        context = self.get_context_data(member_add_formset=formset)

        return self.render_to_response(context)



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context.update(

            self._build_members_context(

                kwargs.get('member_add_formset')

                or WorkspaceMemberAddFormSet(

                    workspace=self.workspace,

                    acting_user=self.request.user,

                    prefix='members',

                )

            )

        )

        return context



    def _build_members_context(self, member_add_formset):

        available_users = available_users_for_workspace(self.workspace)

        return {

            'workspace': self.workspace,

            'member_add_formset': member_add_formset,

            'available_users_picker': workspace_users_for_picker(available_users),

            'can_add_members': available_users.exists(),

            'is_system_admin': is_system_admin(self.request.user),

            'admin_workspaces_url': reverse('administration:admin_workspaces'),

        }





class WorkspaceMemberCreateView(WorkspaceMemberManageMixin, CreateView):

    """Legacy POST endpoint — перенаправляет на список участников."""



    def post(self, request, *args, **kwargs):

        members_view = WorkspaceMembersView.as_view()

        return members_view(request, pk=self.kwargs['pk'])





class WorkspaceUserGroupsUpdateView(WorkspaceMemberManageMixin, View):

    template_name = 'workspaces/members.html'



    def get_target_user(self):

        return get_object_or_404(User, pk=self.kwargs['user_id'])



    def _forbidden_if_cannot_manage(self):

        if not can_manage_membership(

            self.request.user, self.get_target_user(), self.workspace

        ):

            return HttpResponseForbidden('Нельзя изменить группы этого участника.')

        return None



    def get(self, request, *args, **kwargs):

        forbidden = self._forbidden_if_cannot_manage()

        if forbidden:

            return forbidden

        target_user = self.get_target_user()

        form = WorkspaceUserGroupsForm(

            workspace=self.workspace,

            acting_user=request.user,

            target_user=target_user,

        )

        return self._render(request, form, target_user)



    def post(self, request, *args, **kwargs):

        forbidden = self._forbidden_if_cannot_manage()

        if forbidden:

            return forbidden

        target_user = self.get_target_user()

        form = WorkspaceUserGroupsForm(

            request.POST,

            workspace=self.workspace,

            acting_user=request.user,

            target_user=target_user,

        )

        if form.is_valid():

            form.save()

            messages.success(request, 'Группы участника обновлены.')

            return redirect('workspaces:members', pk=self.workspace.pk)

        return self._render(request, form, target_user)



    def _render(self, request, form, target_user):

        members_view = WorkspaceMembersView()

        members_view.workspace = self.workspace

        members_view.request = request

        context = members_view._build_members_context(

            WorkspaceMemberAddFormSet(

                workspace=self.workspace,

                acting_user=request.user,

                prefix='members',

            )

        )

        context['form'] = form

        context['edit_user'] = target_user

        context['members'] = _workspace_member_rows(self.workspace, acting_user=request.user)

        return render(request, self.template_name, context)





class WorkspaceUserRemoveView(WorkspaceMemberManageMixin, View):

    http_method_names = ['post']



    def post(self, request, *args, **kwargs):

        target_user = get_object_or_404(User, pk=kwargs['user_id'])

        if not can_manage_membership(request.user, target_user, self.workspace):

            return HttpResponseForbidden('Нельзя удалить этого участника.')

        WorkspaceGroupMembership.objects.filter(

            group__workspace=self.workspace,

            user=target_user,

        ).delete()

        messages.success(request, 'Участник удалён из пространства.')

        return redirect('workspaces:members', pk=self.workspace.pk)





class WorkspaceGroupListView(WorkspaceGroupManageMixin, ListView):

    template_name = 'workspaces/groups/list.html'

    context_object_name = 'groups'



    def get_queryset(self):

        return (

            WorkspaceGroup.objects.filter(workspace=self.workspace)

            .annotate(member_count=Count('memberships'))

            .order_by('name')

        )



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['workspace'] = self.workspace

        return context





class WorkspaceGroupCreateView(WorkspaceGroupManageMixin, CreateView):

    model = WorkspaceGroup

    form_class = WorkspaceGroupForm

    template_name = 'workspaces/groups/form.html'



    def get_form_kwargs(self):

        kwargs = super().get_form_kwargs()

        kwargs['workspace'] = self.workspace

        return kwargs



    def form_valid(self, form):

        form.instance.workspace = self.workspace

        messages.success(self.request, 'Группа создана.')

        return super().form_valid(form)



    def get_success_url(self):

        return reverse('workspaces:groups', kwargs={'pk': self.workspace.pk})



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['workspace'] = self.workspace

        context['page_title'] = 'Новая группа'

        context['submit_label'] = 'Создать'

        context['permission_sections'] = PERMISSION_SECTIONS

        return context





class WorkspaceGroupUpdateView(WorkspaceGroupManageMixin, UpdateView):

    model = WorkspaceGroup

    form_class = WorkspaceGroupForm

    template_name = 'workspaces/groups/form.html'

    pk_url_kwarg = 'group_pk'



    def get_queryset(self):

        return WorkspaceGroup.objects.filter(workspace=self.workspace)



    def get_form_kwargs(self):

        kwargs = super().get_form_kwargs()

        kwargs['workspace'] = self.workspace

        return kwargs



    def form_valid(self, form):

        messages.success(self.request, 'Группа обновлена.')

        return super().form_valid(form)



    def get_success_url(self):

        return reverse('workspaces:groups', kwargs={'pk': self.workspace.pk})



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['workspace'] = self.workspace

        context['page_title'] = 'Редактирование группы'

        context['submit_label'] = 'Сохранить'

        context['permission_sections'] = PERMISSION_SECTIONS

        return context





class WorkspaceGroupDeleteView(WorkspaceGroupManageMixin, DeleteView):

    model = WorkspaceGroup

    template_name = 'workspaces/groups/confirm_delete.html'

    pk_url_kwarg = 'group_pk'



    def get_queryset(self):

        return WorkspaceGroup.objects.filter(workspace=self.workspace)



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['workspace'] = self.workspace

        context['member_count'] = self.object.memberships.count()

        return context



    def form_valid(self, form):

        if self.object.is_builtin:

            messages.error(self.request, 'Встроенную группу нельзя удалить.')

            return redirect('workspaces:groups', pk=self.workspace.pk)

        if self.object.memberships.exists():

            messages.error(

                self.request,

                'Нельзя удалить группу с участниками. Сначала переназначьте их в другие группы.',

            )

            return redirect('workspaces:groups', pk=self.workspace.pk)

        messages.success(self.request, 'Группа удалена.')

        return super().form_valid(form)



    def get_success_url(self):

        return reverse('workspaces:groups', kwargs={'pk': self.workspace.pk})





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





class AdminWorkspaceListView(SystemAdminRequiredMixin, ListView):

    model = Workspace

    template_name = 'administration/workspaces/list.html'

    context_object_name = 'workspaces'

    paginate_by = 25



    def get_queryset(self):

        return Workspace.objects.annotate(

            member_count=Count('groups__memberships__user', distinct=True),

        ).order_by('name')





class AdminWorkspaceUpdateView(SystemAdminRequiredMixin, UpdateView):

    model = Workspace

    form_class = WorkspaceForm

    template_name = 'administration/workspaces/form.html'

    context_object_name = 'workspace'



    def form_valid(self, form):

        messages.success(self.request, 'Пространство обновлено.')

        return super().form_valid(form)



    def get_success_url(self):

        return reverse('administration:admin_workspaces')



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['page_title'] = 'Редактирование пространства'

        context['cancel_url'] = reverse('administration:admin_workspaces')

        context['submit_label'] = 'Сохранить'

        return context





class AdminWorkspaceDeleteView(SystemAdminRequiredMixin, DeleteView):

    model = Workspace

    template_name = 'administration/workspaces/confirm_delete.html'

    context_object_name = 'workspace'

    success_url = reverse_lazy('administration:admin_workspaces')



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context['member_count'] = (

            WorkspaceGroupMembership.objects.filter(group__workspace=self.object)

            .values('user')

            .distinct()

            .count()

        )

        return context



    def form_valid(self, form):

        try:

            messages.success(self.request, 'Пространство удалено.')

            return super().form_valid(form)

        except ProtectedError:

            messages.error(

                self.request,

                'Нельзя удалить пространство — в нём есть материалы, образцы или другие связанные данные. '

                'Деактивируйте пространство или удалите связанные объекты.',

            )

            return redirect('administration:admin_workspace_edit', pk=self.object.pk)





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





def _admin_user_workspace_rows(target_user):

    rows = []

    workspace_ids = (

        WorkspaceGroupMembership.objects.filter(user=target_user)

        .values_list('group__workspace_id', flat=True)

        .distinct()

    )

    for workspace in Workspace.objects.filter(pk__in=workspace_ids).order_by('name'):

        groups = list(get_user_groups(target_user, workspace))

        rows.append({'workspace': workspace, 'groups': groups})

    return rows


class AdminUserMembershipView(SystemAdminRequiredMixin, View):

    template_name = 'administration/users/memberships.html'



    def get_target_user(self):

        return get_object_or_404(User, pk=self.kwargs['pk'])



    def get(self, request, *args, **kwargs):

        target_user = self.get_target_user()

        return self._render(

            request,

            target_user,

            _admin_user_workspace_rows(target_user),

            UserMembershipAssignForm(user=target_user),

        )



    def post(self, request, *args, **kwargs):

        target_user = self.get_target_user()

        form = UserMembershipAssignForm(request.POST, user=target_user)

        if form.is_valid():

            form.save()

            messages.success(request, 'Группы назначены.')

            return redirect('administration:admin_user_memberships', pk=target_user.pk)

        return self._render(

            request,

            target_user,

            _admin_user_workspace_rows(target_user),

            form,

        )



    def _render(self, request, target_user, workspace_rows, form):
        return render(
            request,
            self.template_name,
            {
                'target_user': target_user,
                'workspace_rows': workspace_rows,
                'membership_form': form,
            },
        )


