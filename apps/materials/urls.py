from django.urls import path

from apps.materials.views import (
    MaterialCloneView,
    MaterialCreateView,
    MaterialDeleteView,
    MaterialDetailView,
    MaterialListView,
    MaterialPropertiesJSONView,
    MaterialUpdateView,
    MaterialVisibilityView,
)

app_name = 'materials'

urlpatterns = [
    path('', MaterialListView.as_view(), name='list'),
    path('create/', MaterialCreateView.as_view(), name='create'),
    path('<uuid:pk>/clone/', MaterialCloneView.as_view(), name='clone'),
    path('<uuid:pk>/edit/', MaterialUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', MaterialDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/visibility/', MaterialVisibilityView.as_view(), name='visibility'),
    path('<uuid:pk>/properties.json/', MaterialPropertiesJSONView.as_view(), name='properties_json'),
    path('<uuid:pk>/', MaterialDetailView.as_view(), name='detail'),
]
