from django.urls import path

from apps.structures.migrate_views import (
    StructureMigrateWizardView,
    StructureNormalizationDiagnosticsView,
)
from apps.structures.type_views import (
    StructureTypeCreateTableView,
    StructureTypeCreateView,
    StructureTypeDeleteDraftView,
    StructureTypeDropTableView,
    StructureTypeManageView,
    StructureTypeUpdateView,
    StructureTypeVisibilityView,
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
    path('migrate/', StructureMigrateWizardView.as_view(), name='migrate'),
    path('diagnostics/', StructureNormalizationDiagnosticsView.as_view(), name='diagnostics'),
    path('types/create/', StructureTypeCreateView.as_view(), name='type_create'),
    path('types/<slug:type_code>/', StructureTypeManageView.as_view(), name='type_manage'),
    path('types/<slug:type_code>/visibility/', StructureTypeVisibilityView.as_view(), name='type_visibility'),
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
    path(
        'types/<slug:type_code>/delete/',
        StructureTypeDeleteDraftView.as_view(),
        name='type_delete',
    ),
    path('<slug:type_code>/', StructureRecordListView.as_view(), name='list'),
    path('<slug:type_code>/create/', StructureRecordCreateView.as_view(), name='create'),
    path('<slug:type_code>/<uuid:pk>/', StructureRecordDetailView.as_view(), name='detail'),
    path('<slug:type_code>/<uuid:pk>/edit/', StructureRecordUpdateView.as_view(), name='edit'),
    path('<slug:type_code>/<uuid:pk>/delete/', StructureRecordDeleteView.as_view(), name='delete'),
]
