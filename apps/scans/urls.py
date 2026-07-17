from django.urls import path

from apps.scans.views import (
    ScanCreateView,
    ScanDeleteView,
    ScanDetailView,
    ScanDownloadView,
    ScanListView,
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
    path('<uuid:pk>/delete/', ScanDeleteView.as_view(), name='delete'),
]
