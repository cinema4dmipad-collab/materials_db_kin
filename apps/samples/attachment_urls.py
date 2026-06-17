from django.urls import path

from apps.samples.views import AttachmentDeleteView, AttachmentDownloadView, AttachmentListView

app_name = 'attachments'

urlpatterns = [
    path('', AttachmentListView.as_view(), name='list'),
    path('<uuid:pk>/download/', AttachmentDownloadView.as_view(), name='download'),
    path('<uuid:pk>/delete/', AttachmentDeleteView.as_view(), name='delete'),
]
