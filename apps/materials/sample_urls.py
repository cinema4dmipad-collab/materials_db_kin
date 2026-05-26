from django.urls import path

from apps.materials.sample_views import MaterialSamplesListView

app_name = 'material_samples'

urlpatterns = [
    path('', MaterialSamplesListView.as_view(), name='list'),
]
