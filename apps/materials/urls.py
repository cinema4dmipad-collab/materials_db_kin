from django.urls import path

from apps.materials.views import (
    MaterialCreateView,
    MaterialDeleteView,
    MaterialDetailView,
    MaterialLinkView,
    MaterialListView,
    MaterialPropertiesJSONView,
    MaterialTagsUpdateView,
    MaterialUpdateView,
    MaterialVisibilityView,
)

app_name = 'materials'

urlpatterns = [
    path('', MaterialListView.as_view(), name='list'),
    path('create/', MaterialCreateView.as_view(), name='create'),
    path('<uuid:pk>/link/', MaterialLinkView.as_view(), name='link'),
    path('<uuid:pk>/edit/', MaterialUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/tags/', MaterialTagsUpdateView.as_view(), name='tags'),
    path('<uuid:pk>/delete/', MaterialDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/visibility/', MaterialVisibilityView.as_view(), name='visibility'),
    path('<uuid:pk>/properties.json/', MaterialPropertiesJSONView.as_view(), name='properties_json'),
    path('<uuid:pk>/', MaterialDetailView.as_view(), name='detail'),
]
