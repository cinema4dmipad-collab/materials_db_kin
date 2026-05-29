from django.db.models import Count
from django.views.generic import ListView

from apps.core.list_filters import QuerySetFilterMixin
from apps.materials.tab_mixins import MaterialTabMixin
from apps.samples.models import Sample


class MaterialSamplesListView(QuerySetFilterMixin, MaterialTabMixin, ListView):
    model = Sample
    template_name = 'materials/samples/list.html'
    context_object_name = 'samples'
    active_tab = 'samples'
    enable_tag_filter = True
    search_fields = ('code', 'name')
    search_placeholder = 'Код, название или тег...'
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта', 'tag': 'Тег'}

    def get_queryset(self):
        return self.filter_queryset(
            self.material.samples.annotate(scan_count=Count('scans'))
            .prefetch_related('tags')
            .order_by('code')
        )

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}
