from django.urls import path

from apps.materials.attachment_views import (
    MaterialAttachmentCreateView,
    MaterialAttachmentDeleteView,
    MaterialAttachmentDownloadView,
    MaterialAttachmentListView,
    MaterialAttachmentPreviewView,
)

app_name = 'material_attachments'

urlpatterns = [
    path('', MaterialAttachmentListView.as_view(), name='list'),
    path('add/', MaterialAttachmentCreateView.as_view(), name='create'),
    path('<uuid:pk>/download/', MaterialAttachmentDownloadView.as_view(), name='download'),
    path('<uuid:pk>/preview/', MaterialAttachmentPreviewView.as_view(), name='preview'),
    path('<uuid:pk>/delete/', MaterialAttachmentDeleteView.as_view(), name='delete'),
]
