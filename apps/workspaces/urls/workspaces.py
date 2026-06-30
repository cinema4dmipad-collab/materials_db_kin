from django.urls import path

from apps.workspaces import views

app_name = 'workspaces'

urlpatterns = [
    path('select/', views.WorkspaceSelectView.as_view(), name='select'),
    path('switch/<uuid:pk>/', views.WorkspaceSwitchView.as_view(), name='switch'),
    path('create/', views.WorkspaceCreateView.as_view(), name='create'),
    path('<uuid:pk>/members/', views.WorkspaceMembersView.as_view(), name='members'),
    path('<uuid:pk>/members/add/', views.WorkspaceMemberCreateView.as_view(), name='member_add'),
    path(
        '<uuid:pk>/members/<uuid:membership_pk>/edit/',
        views.WorkspaceMemberUpdateView.as_view(),
        name='member_edit',
    ),
    path(
        '<uuid:pk>/members/<uuid:membership_pk>/delete/',
        views.WorkspaceMemberDeleteView.as_view(),
        name='member_delete',
    ),
    path('<uuid:pk>/settings/', views.WorkspaceSettingsView.as_view(), name='settings'),
]
