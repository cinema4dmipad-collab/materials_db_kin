from django.urls import path

from apps.workspaces import views

app_name = 'administration'

urlpatterns = [
    path('users/', views.AdminUserListView.as_view(), name='admin_users'),
    path('users/create/', views.AdminUserCreateView.as_view(), name='admin_user_create'),
    path('users/<int:pk>/edit/', views.AdminUserUpdateView.as_view(), name='admin_user_edit'),
    path(
        'users/<int:pk>/memberships/',
        views.AdminUserMembershipView.as_view(),
        name='admin_user_memberships',
    ),
]
