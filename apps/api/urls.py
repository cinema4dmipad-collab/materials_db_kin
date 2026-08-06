from django.urls import path

from apps.api import controllers
from apps.api import desktop_views

app_name = 'api'

urlpatterns = [
    path('v1/workspaces/', controllers.WorkspaceListController.as_view(), name='workspaces'),
    path(
        'v1/desktop/connect/',
        controllers.DesktopConnectController.as_view(),
        name='desktop_connect',
    ),
    path(
        'v1/desktop/commands/',
        controllers.DesktopCommandsController.as_view(),
        name='desktop_commands',
    ),
    path(
        'v1/desktop/status/',
        desktop_views.desktop_status_view,
        name='desktop_status',
    ),
    path(
        'v1/desktop/open-scan/',
        desktop_views.desktop_open_scan_view,
        name='desktop_open_scan',
    ),
    path('v1/materials/', controllers.MaterialListController.as_view(), name='materials'),
    path(
        'v1/materials/<uuid:material_id>/',
        controllers.MaterialDetailController.as_view(),
        name='material_detail',
    ),
    path('v1/samples/', controllers.SampleListController.as_view(), name='samples'),
    path(
        'v1/samples/<uuid:sample_id>/',
        controllers.SampleDetailController.as_view(),
        name='sample_detail',
    ),
    path(
        'v1/samples/<uuid:sample_id>/scans/',
        controllers.ScanCreateController.as_view(),
        name='sample_scans_create',
    ),
    path('v1/scans/', controllers.ScanListController.as_view(), name='scans'),
    path(
        'v1/scans/<uuid:scan_id>/',
        controllers.ScanDetailController.as_view(),
        name='scan_detail',
    ),
    path(
        'v1/scans/<uuid:scan_id>/download/',
        controllers.ScanDownloadController.as_view(),
        name='scan_download',
    ),
]
