from django.urls import path

from apps.scans.attachment_views import (
    ScanAttachmentCreateView,
    ScanAttachmentDeleteView,
    ScanAttachmentDownloadView,
    ScanAttachmentListView,
    ScanAttachmentPreviewView,
)
from apps.scans.views import (
    ScanCreateView,
    ScanDeleteView,
    ScanDetailView,
    ScanDownloadView,
    ScanListView,
    ScanPreviewView,
    ScanTagsUpdateView,
    ScanUpdateView,
)

app_name = 'scans'

urlpatterns = [
    path('', ScanListView.as_view(), name='list'),
    path('create/', ScanCreateView.as_view(), name='create'),
    path('<uuid:pk>/', ScanDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', ScanUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/tags/', ScanTagsUpdateView.as_view(), name='tags'),
    path('<uuid:pk>/download/', ScanDownloadView.as_view(), name='download'),
    path('<uuid:pk>/preview/', ScanPreviewView.as_view(), name='preview'),
    path('<uuid:pk>/delete/', ScanDeleteView.as_view(), name='delete'),
    path(
        '<uuid:scan_pk>/attachments/',
        ScanAttachmentListView.as_view(),
        name='attachment_list',
    ),
    path(
        '<uuid:scan_pk>/attachments/add/',
        ScanAttachmentCreateView.as_view(),
        name='attachment_create',
    ),
    path(
        '<uuid:scan_pk>/attachments/<uuid:pk>/download/',
        ScanAttachmentDownloadView.as_view(),
        name='attachment_download',
    ),
    path(
        '<uuid:scan_pk>/attachments/<uuid:pk>/preview/',
        ScanAttachmentPreviewView.as_view(),
        name='attachment_preview',
    ),
    path(
        '<uuid:scan_pk>/attachments/<uuid:pk>/delete/',
        ScanAttachmentDeleteView.as_view(),
        name='attachment_delete',
    ),
]
