from django.db.models import Q

from apps.core.models import Tag

TAG_SEARCH_SCOPE = '__tag__'
ALL_SEARCH_SCOPE = ''
STRUCT_TYPE_SEARCH_SCOPE = 'struct_type'
OBJECT_TYPE_SEARCH_SCOPE = 'object_type'
SCAN_METHOD_SEARCH_SCOPE = 'method'


def build_choice_label_filter(choices: list[tuple[str, str]] | tuple[tuple[str, str], ...], field_name: str):
    def filter_fn(query: str):
        matching = [
            value
            for value, label in choices
            if query.lower() in label.lower()
        ]
        if matching:
            return Q(**{f'{field_name}__in': matching})
        return None

    return filter_fn


class QuerySetFilterMixin:
    """GET-поиск с выбором области, фильтры выбора и фильтр по тегам для ListView."""

    search_param = 'q'
    search_scope_param = 'q_in'
    search_fields: tuple[str, ...] = ()
    search_scopes: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    search_placeholder = 'Поиск...'
    choice_filters: tuple[tuple[str, str], ...] = ()
    choice_filter_labels: dict[str, str] = {}
    enable_tag_filter = False
    tag_filter_param = 'tag'
    tag_relation = 'tags'

    def get_resolved_search_scopes(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        if self.search_scopes:
            return self.search_scopes
        scopes: list[tuple[str, str, tuple[str, ...]]] = [
            (ALL_SEARCH_SCOPE, 'Везде', self.search_fields),
        ]
        if self.enable_tag_filter:
            scopes.append((TAG_SEARCH_SCOPE, 'Тег', ()))
        return tuple(scopes)

    def get_custom_search_scope_filters(self) -> dict:
        return {}

    def _get_scopes_map(self) -> dict[str, tuple[str, str, tuple[str, ...]]]:
        return {scope[0]: scope for scope in self.get_resolved_search_scopes()}

    def _get_active_search_scope_values(self) -> list[str]:
        scopes_map = self._get_scopes_map()
        seen: set[str] = set()
        values: list[str] = []
        for raw in self.request.GET.getlist(self.search_scope_param):
            value = raw.strip()
            if not value or value == ALL_SEARCH_SCOPE or value not in scopes_map:
                continue
            if value not in seen:
                seen.add(value)
                values.append(value)
        return values

    def _get_search_scope_labels(self, scope_values: list[str]) -> str:
        if not scope_values:
            return 'Везде'
        scopes_map = self._get_scopes_map()
        labels = [scopes_map[value][1] for value in scope_values if value in scopes_map]
        return ', '.join(labels) if labels else 'Везде'

    def _get_active_tag_slugs(self) -> list[str]:
        if not self.enable_tag_filter:
            return []
        seen: set[str] = set()
        slugs: list[str] = []
        for slug in self.request.GET.getlist(self.tag_filter_param):
            normalized = slug.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                slugs.append(normalized)
        return slugs

    def _get_active_tags(self) -> list[dict[str, str]]:
        slugs = self._get_active_tag_slugs()
        if not slugs:
            return []
        labels = {
            slug: name
            for slug, name in Tag.objects.filter(slug__in=slugs).values_list('slug', 'name')
        }
        return [
            {
                'slug': slug,
                'label': labels.get(slug, slug),
                'remove_url': self._build_filter_url(remove_tag_slugs=(slug,)),
            }
            for slug in slugs
        ]

    def _build_search_condition(self, query: str) -> tuple[Q | None, bool]:
        active_scopes = self._get_active_search_scope_values()
        scopes_map = self._get_scopes_map()
        needs_distinct = False

        if not active_scopes:
            all_scope = scopes_map.get(ALL_SEARCH_SCOPE)
            all_fields = all_scope[2] if all_scope else self.search_fields
            if not all_fields and not self.enable_tag_filter:
                return None, False

            condition = Q()
            for field in all_fields:
                condition |= Q(**{f'{field}__icontains': query})
            if self.enable_tag_filter:
                condition |= Q(**{f'{self.tag_relation}__name__icontains': query})
                needs_distinct = True
            return condition, needs_distinct

        condition = Q()
        custom_filters = self.get_custom_search_scope_filters()
        for scope_value in active_scopes:
            _value, _label, scope_fields = scopes_map[scope_value]
            if scope_value in custom_filters:
                custom_q = custom_filters[scope_value](query)
                if custom_q is not None:
                    condition |= custom_q
                continue
            if scope_value == TAG_SEARCH_SCOPE:
                if not self.enable_tag_filter:
                    continue
                condition |= Q(**{f'{self.tag_relation}__name__icontains': query})
                needs_distinct = True
                continue
            for field in scope_fields:
                condition |= Q(**{f'{field}__icontains': query})

        if not condition:
            return None, False
        return condition, needs_distinct

    def filter_queryset(self, queryset):
        params = self.request.GET
        query = params.get(self.search_param, '').strip()
        needs_distinct = False

        if query:
            condition, scope_needs_distinct = self._build_search_condition(query)
            if condition is not None:
                queryset = queryset.filter(condition)
                needs_distinct = needs_distinct or scope_needs_distinct

        for param, field_name in self.choice_filters:
            value = params.get(param, '').strip()
            if value:
                queryset = queryset.filter(**{field_name: value})

        if self.enable_tag_filter:
            for slug in self._get_active_tag_slugs():
                queryset = queryset.filter(**{f'{self.tag_relation}__slug': slug})
                needs_distinct = True

        if needs_distinct:
            queryset = queryset.distinct()
        return queryset

    def get_queryset(self):
        return self.filter_queryset(super().get_queryset())

    def get_choice_filter_options(self) -> dict[str, list[tuple[str, str]]]:
        return {}

    def _build_filter_url(
        self,
        exclude_params: tuple[str, ...] = (),
        remove_tag_slugs: tuple[str, ...] = (),
    ) -> str:
        params = self.request.GET.copy()
        for param in exclude_params:
            params.pop(param, None)
        if remove_tag_slugs and self.enable_tag_filter:
            remaining = [
                slug
                for slug in params.getlist(self.tag_filter_param)
                if slug not in remove_tag_slugs
            ]
            if remaining:
                params.setlist(self.tag_filter_param, remaining)
            else:
                params.pop(self.tag_filter_param, None)
        params.pop('page', None)
        encoded = params.urlencode()
        if encoded:
            return f'{self.request.path}?{encoded}'
        return self.request.path

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

        query = params.get(self.search_param, '').strip()
        active_scope_values = self._get_active_search_scope_values()
        search_scope_label = self._get_search_scope_labels(active_scope_values)
        search_scope_options = [
            {
                'value': value,
                'label': label,
                'checked': value in active_scope_values,
            }
            for value, label, _fields in self.get_resolved_search_scopes()
            if value != ALL_SEARCH_SCOPE
        ]
        active_tags = self._get_active_tags() if self.enable_tag_filter else []

        pagination_query = params.copy()
        pagination_query.pop('page', None)

        has_active_filters = bool(query) or any(item['value'] for item in filters) or bool(active_tags)

        return {
            'search_query': query,
            'search_param': self.search_param,
            'search_scope_values': active_scope_values,
            'search_scope_param': self.search_scope_param,
            'search_scope_label': search_scope_label,
            'search_scope_options': search_scope_options,
            'search_placeholder': self.search_placeholder,
            'list_filters': filters,
            'active_tags': active_tags,
            'has_active_filters': has_active_filters,
            'filter_reset_url': self.request.path,
            'pagination_query': pagination_query.urlencode(),
            'remove_search_url': (
                self._build_filter_url((self.search_param, self.search_scope_param))
                if query
                else ''
            ),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_filter_context())
        return context
