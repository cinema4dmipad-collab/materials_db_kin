from django.urls import path

from apps.structures.views import (
    DynamicStructureCreateView,
    DynamicStructureUpdateView,
    StructureInstanceDeleteView,
    StructureInstanceDetailView,
    StructureInstanceListView,
    StructureTypeSelectView,
)

app_name = 'structures'

urlpatterns = [
    path('', StructureTypeSelectView.as_view(), name='select_type'),
    path('list/', StructureInstanceListView.as_view(), name='list'),
    path('instances/', StructureInstanceListView.as_view(), name='instance_list'),
    path('instances/<slug:type_code>/', StructureInstanceListView.as_view(), name='instance_list_by_type'),
    path('create/<slug:type_code>/', DynamicStructureCreateView.as_view(), name='create'),
    path('<uuid:pk>/delete/', StructureInstanceDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/edit/', DynamicStructureUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/', StructureInstanceDetailView.as_view(), name='detail'),
]
