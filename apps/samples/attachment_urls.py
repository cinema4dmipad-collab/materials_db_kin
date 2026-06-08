from django.urls import path

from apps.samples.views import AttachmentDeleteView, AttachmentListView

app_name = 'attachments'

urlpatterns = [
    path('', AttachmentListView.as_view(), name='list'),
    path('<uuid:pk>/delete/', AttachmentDeleteView.as_view(), name='delete'),
]
