from django.urls import path

from apps.samples.views import (
    SampleCreateView,
    SampleDeleteView,
    SampleDetailView,
    SampleListView,
    SampleTagsUpdateView,
    SampleUpdateView,
)

app_name = 'samples'

urlpatterns = [
    path('', SampleListView.as_view(), name='list'),
    path('create/', SampleCreateView.as_view(), name='create'),
    path('<uuid:pk>/edit/', SampleUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/tags/', SampleTagsUpdateView.as_view(), name='tags'),
    path('<uuid:pk>/delete/', SampleDeleteView.as_view(), name='delete'),
    path('<uuid:pk>/', SampleDetailView.as_view(), name='detail'),
]
