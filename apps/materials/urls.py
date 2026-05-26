from django.urls import path

from apps.materials.views import (
    MaterialCreateView,
    MaterialDeleteView,
    MaterialDetailView,
    MaterialListView,
    MaterialUpdateView,
)

app_name = 'materials'

urlpatterns = [
    path('', MaterialListView.as_view(), name='list'),
    path('create/', MaterialCreateView.as_view(), name='create'),
    path('<uuid:pk>/edit/', MaterialUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', MaterialDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/', MaterialDetailView.as_view(), name='detail'),
]
