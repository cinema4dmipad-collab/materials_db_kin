from django.urls import path

from apps.api.token_urls import token_urlpatterns
from apps.workspaces import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.WorkspaceLoginView.as_view(), name='login'),
    path('logout/', views.WorkspaceLogoutView.as_view(), name='logout'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('profile/edit/', views.UserProfileUpdateView.as_view(), name='profile_edit'),
    path('profile/password/', views.UserPasswordChangeView.as_view(), name='password_change'),
    *token_urlpatterns,
]
