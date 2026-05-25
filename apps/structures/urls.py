from django.urls import path

from apps.structures.views import StructureTypeSelectView

app_name = 'structures'

urlpatterns = [
    path('', StructureTypeSelectView.as_view(), name='select_type'),
]
