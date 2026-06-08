from django.urls import path

from apps.references.views import (
    PropertyCreateView,
    PropertyDeleteView,
    PropertyListView,
    PropertyUpdateView,
)

app_name = 'references'

urlpatterns = [
    path('', PropertyListView.as_view(), name='list'),
    path('create/', PropertyCreateView.as_view(), name='create'),
    path('<uuid:pk>/edit/', PropertyUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', PropertyDeleteView.as_view(), name='delete'),
]
