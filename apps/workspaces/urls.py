from django.urls import path

from apps.workspaces import views

app_name = 'workspaces'

urlpatterns = [
    path('accounts/login/', views.WorkspaceLoginView.as_view(), name='login'),
    path('accounts/logout/', views.WorkspaceLogoutView.as_view(), name='logout'),
    path('workspaces/select/', views.WorkspaceSelectView.as_view(), name='select'),
    path('workspaces/switch/<uuid:pk>/', views.WorkspaceSwitchView.as_view(), name='switch'),
    path('workspaces/create/', views.WorkspaceCreateView.as_view(), name='create'),
    path('workspaces/<uuid:pk>/members/', views.WorkspaceMembersView.as_view(), name='members'),
    path(
        'workspaces/<uuid:pk>/members/add/',
        views.WorkspaceMemberCreateView.as_view(),
        name='member_add',
    ),
    path(
        'workspaces/<uuid:pk>/members/<uuid:membership_pk>/edit/',
        views.WorkspaceMemberUpdateView.as_view(),
        name='member_edit',
    ),
    path(
        'workspaces/<uuid:pk>/members/<uuid:membership_pk>/delete/',
        views.WorkspaceMemberDeleteView.as_view(),
        name='member_delete',
    ),
    path('workspaces/<uuid:pk>/settings/', views.WorkspaceSettingsView.as_view(), name='settings'),
    path('administration/users/', views.AdminUserListView.as_view(), name='admin_users'),
    path(
        'administration/users/create/',
        views.AdminUserCreateView.as_view(),
        name='admin_user_create',
    ),
    path(
        'administration/users/<int:pk>/edit/',
        views.AdminUserUpdateView.as_view(),
        name='admin_user_edit',
    ),
    path(
        'administration/users/<int:pk>/memberships/',
        views.AdminUserMembershipView.as_view(),
        name='admin_user_memberships',
    ),
]
