from django.db.models import Q

from apps.core.models import Tag


class QuerySetFilterMixin:
    """GET-поиск, фильтры выбора и фильтр по тегам для ListView."""

    search_param = 'q'
    search_fields: tuple[str, ...] = ()
    search_placeholder = 'Поиск...'
    choice_filters: tuple[tuple[str, str], ...] = ()
    choice_filter_labels: dict[str, str] = {}
    enable_tag_filter = False
    tag_filter_param = 'tag'
    tag_relation = 'tags'

    def filter_queryset(self, queryset):
        params = self.request.GET
        query = params.get(self.search_param, '').strip()
        needs_distinct = False

        if query and self.search_fields:
            condition = Q()
            for field in self.search_fields:
                condition |= Q(**{f'{field}__icontains': query})
            if self.enable_tag_filter:
                condition |= Q(**{f'{self.tag_relation}__name__icontains': query})
                needs_distinct = True
            queryset = queryset.filter(condition)

        for param, field_name in self.choice_filters:
            value = params.get(param, '').strip()
            if value:
                queryset = queryset.filter(**{field_name: value})

        tag_slug = params.get(self.tag_filter_param, '').strip()
        if tag_slug and self.enable_tag_filter:
            queryset = queryset.filter(**{f'{self.tag_relation}__slug': tag_slug})
            needs_distinct = True

        if needs_distinct:
            queryset = queryset.distinct()
        return queryset

    def get_queryset(self):
        return self.filter_queryset(super().get_queryset())

    def get_choice_filter_options(self) -> dict[str, list[tuple[str, str]]]:
        return {}

    def get_tag_filter_options(self) -> list[tuple[str, str]]:
        return list(Tag.objects.order_by('name').values_list('slug', 'name'))

    def get_filter_context(self) -> dict:
        params = self.request.GET
        filters = []
        options_map = self.get_choice_filter_options()

        for param, _field_name in self.choice_filters:
            filters.append(
                {
                    'param': param,
                    'label': self.choice_filter_labels.get(param, param),
                    'value': params.get(param, '').strip(),
                    'options': options_map.get(param, []),
                }
            )

        if self.enable_tag_filter:
            filters.append(
                {
                    'param': self.tag_filter_param,
                    'label': self.choice_filter_labels.get(self.tag_filter_param, 'Тег'),
                    'value': params.get(self.tag_filter_param, '').strip(),
                    'options': self.get_tag_filter_options(),
                }
            )

        query = params.get(self.search_param, '').strip()
        pagination_query = params.copy()
        pagination_query.pop('page', None)

        return {
            'search_query': query,
            'search_param': self.search_param,
            'search_placeholder': self.search_placeholder,
            'list_filters': filters,
            'has_active_filters': bool(query) or any(item['value'] for item in filters),
            'filter_reset_url': self.request.path,
            'pagination_query': pagination_query.urlencode(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_filter_context())
        return context
