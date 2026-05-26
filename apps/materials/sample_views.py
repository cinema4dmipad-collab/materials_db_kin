from django.db.models import Count
from django.views.generic import ListView

from apps.materials.tab_mixins import MaterialTabMixin
from apps.samples.models import Sample


class MaterialSamplesListView(MaterialTabMixin, ListView):
    model = Sample
    template_name = 'materials/samples/list.html'
    context_object_name = 'samples'
    active_tab = 'samples'

    def get_queryset(self):
        return (
            self.material.samples.annotate(scan_count=Count('scans'))
            .order_by('code')
        )
