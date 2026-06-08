from django.urls import path

from apps.materials.attachment_views import (
    MaterialAttachmentDeleteView,
    MaterialAttachmentListView,
)

app_name = 'material_attachments'

urlpatterns = [
    path('', MaterialAttachmentListView.as_view(), name='list'),
    path('<uuid:pk>/delete/', MaterialAttachmentDeleteView.as_view(), name='delete'),
]
