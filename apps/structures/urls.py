from django.urls import path

from apps.structures.type_views import (
    StructureTypeCreateTableView,
    StructureTypeCreateView,
    StructureTypeDropTableView,
    StructureTypeManageView,
    StructureTypeUpdateView,
)
from apps.structures.views import (
    StructureRecordCreateView,
    StructureRecordDeleteView,
    StructureRecordDetailView,
    StructureRecordListView,
    StructureRecordUpdateView,
    StructureTypeSelectView,
)

app_name = 'structures'

urlpatterns = [
    path('', StructureTypeSelectView.as_view(), name='select_type'),
    path('types/create/', StructureTypeCreateView.as_view(), name='type_create'),
    path('types/<slug:type_code>/', StructureTypeManageView.as_view(), name='type_manage'),
    path('types/<slug:type_code>/edit/', StructureTypeUpdateView.as_view(), name='type_edit'),
    path(
        'types/<slug:type_code>/create-table/',
        StructureTypeCreateTableView.as_view(),
        name='type_create_table',
    ),
    path(
        'types/<slug:type_code>/drop-table/',
        StructureTypeDropTableView.as_view(),
        name='type_drop_table',
    ),
    path('<slug:type_code>/', StructureRecordListView.as_view(), name='list'),
    path('<slug:type_code>/create/', StructureRecordCreateView.as_view(), name='create'),
    path('<slug:type_code>/<uuid:pk>/', StructureRecordDetailView.as_view(), name='detail'),
    path('<slug:type_code>/<uuid:pk>/edit/', StructureRecordUpdateView.as_view(), name='edit'),
    path('<slug:type_code>/<uuid:pk>/delete/', StructureRecordDeleteView.as_view(), name='delete'),
]
