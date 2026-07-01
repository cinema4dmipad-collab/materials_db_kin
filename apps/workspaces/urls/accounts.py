from django.urls import path

from apps.workspaces import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.WorkspaceLoginView.as_view(), name='login'),
    path('logout/', views.WorkspaceLogoutView.as_view(), name='logout'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
]
