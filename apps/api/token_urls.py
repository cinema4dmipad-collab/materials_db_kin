from django.urls import path

from apps.api import token_views

token_urlpatterns = [
    path('tokens/create/', token_views.TokenCreateView.as_view(), name='token_create'),
    path(
        'tokens/<int:pk>/update/',
        token_views.TokenUpdateView.as_view(),
        name='token_update',
    ),
    path(
        'tokens/<int:pk>/rotate/',
        token_views.TokenRotateView.as_view(),
        name='token_rotate',
    ),
    path(
        'tokens/<int:pk>/revoke/',
        token_views.TokenRevokeView.as_view(),
        name='token_revoke',
    ),
    path(
        'tokens/dismiss-secret/',
        token_views.TokenSecretDismissView.as_view(),
        name='token_dismiss_secret',
    ),
]
