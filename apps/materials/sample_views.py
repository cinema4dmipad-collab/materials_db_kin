from django.db.models import Count
from django.views.generic import ListView

from apps.core.list_filters import ALL_SEARCH_SCOPE, TAG_SEARCH_SCOPE, QuerySetFilterMixin
from apps.materials.tab_mixins import MaterialTabMixin
from apps.samples.models import Sample
from apps.workspaces.mixins import AppViewMixin
from apps.workspaces.services import samples_in_workspace


class MaterialSamplesListView(AppViewMixin, QuerySetFilterMixin, MaterialTabMixin, ListView):
    model = Sample
    template_name = 'materials/samples/list.html'
    context_object_name = 'samples'
    active_tab = 'samples'
    enable_tag_filter = True
    search_fields = ('code', 'name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('code', 'name')),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    search_placeholder = 'Введите текст для поиска...'
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта'}

    def get_queryset(self):
        return self.filter_queryset(
            samples_in_workspace(self.request.active_workspace)
            .filter(material=self.material)
            .annotate(scan_count=Count('scans'))
            .prefetch_related('tags')
            .order_by('code')
        )

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}
