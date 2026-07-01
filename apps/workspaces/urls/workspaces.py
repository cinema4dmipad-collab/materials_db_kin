from django.urls import path

from apps.workspaces import views

app_name = 'workspaces'

urlpatterns = [
    path('select/', views.WorkspaceSelectView.as_view(), name='select'),
    path('switch/<uuid:pk>/', views.WorkspaceSwitchView.as_view(), name='switch'),
    path('create/', views.WorkspaceCreateView.as_view(), name='create'),
    path('<uuid:pk>/groups/', views.WorkspaceGroupListView.as_view(), name='groups'),
    path('<uuid:pk>/groups/create/', views.WorkspaceGroupCreateView.as_view(), name='group_create'),
    path(
        '<uuid:pk>/groups/<uuid:group_pk>/edit/',
        views.WorkspaceGroupUpdateView.as_view(),
        name='group_edit',
    ),
    path(
        '<uuid:pk>/groups/<uuid:group_pk>/delete/',
        views.WorkspaceGroupDeleteView.as_view(),
        name='group_delete',
    ),
    path('<uuid:pk>/members/', views.WorkspaceMembersView.as_view(), name='members'),
    path('<uuid:pk>/members/add/', views.WorkspaceMemberCreateView.as_view(), name='member_add'),
    path(
        '<uuid:pk>/members/<int:user_id>/edit/',
        views.WorkspaceUserGroupsUpdateView.as_view(),
        name='member_edit',
    ),
    path(
        '<uuid:pk>/members/<int:user_id>/delete/',
        views.WorkspaceUserRemoveView.as_view(),
        name='member_delete',
    ),
    path('<uuid:pk>/settings/', views.WorkspaceSettingsView.as_view(), name='settings'),
]
