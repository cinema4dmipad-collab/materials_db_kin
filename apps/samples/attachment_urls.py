from django.urls import path

from apps.samples.views import (
    AttachmentCreateView,
    AttachmentDeleteView,
    AttachmentDownloadView,
    AttachmentListView,
    AttachmentPreviewView,
)

app_name = 'attachments'

urlpatterns = [
    path('', AttachmentListView.as_view(), name='list'),
    path('add/', AttachmentCreateView.as_view(), name='create'),
    path('<uuid:pk>/download/', AttachmentDownloadView.as_view(), name='download'),
    path('<uuid:pk>/preview/', AttachmentPreviewView.as_view(), name='preview'),
    path('<uuid:pk>/delete/', AttachmentDeleteView.as_view(), name='delete'),
]
