from django.views.generic import ListView

from apps.structures.models import StructureType


class StructureTypeSelectView(ListView):
    model = StructureType
    template_name = 'structures/select_type.html'
    context_object_name = 'types'

    def get_queryset(self):
        return StructureType.objects.filter(is_active=True).prefetch_related('fields')
