"""Clickable table-header sort via GET ``sort`` / ``dir``."""

from __future__ import annotations

from django.db.models import F

SORT_PARAM = 'sort'
DIR_PARAM = 'dir'
DIR_ASC = 'asc'
DIR_DESC = 'desc'


def parse_table_sort(request, allowed_keys, default_key, default_dir=DIR_ASC):
    allowed = set(allowed_keys)
    key = (request.GET.get(SORT_PARAM) or '').strip()
    direction = (request.GET.get(DIR_PARAM) or '').strip().lower()
    if key not in allowed:
        return default_key, default_dir
    if direction not in (DIR_ASC, DIR_DESC):
        direction = default_dir
    return key, direction


def sort_preserve_params(params):
    """Hidden GET fields so the filter form keeps the current sort."""
    preserve = []
    sort_key = (params.get(SORT_PARAM) or '').strip()
    sort_dir = (params.get(DIR_PARAM) or '').strip()
    if sort_key:
        preserve.append((SORT_PARAM, sort_key))
    if sort_dir:
        preserve.append((DIR_PARAM, sort_dir))
    return preserve


def build_sort_state(request, column_keys, current_key, current_dir):
    base = request.GET.copy()
    base.pop('page', None)
    state = {}
    for key in column_keys:
        params = base.copy()
        if current_key == key:
            next_dir = DIR_DESC if current_dir == DIR_ASC else DIR_ASC
        else:
            next_dir = DIR_ASC
        params[SORT_PARAM] = key
        params[DIR_PARAM] = next_dir
        active = current_key == key
        state[key] = {
            'query': params.urlencode(),
            'active': active,
            'dir': current_dir if active else '',
            'aria_sort': (
                'ascending' if active and current_dir == DIR_ASC
                else 'descending' if active
                else 'none'
            ),
        }
    return state


def apply_orm_sort(queryset, sort_key, direction, column_map, extra=()):
    field = column_map[sort_key]
    expr = F(field)
    order = expr.desc(nulls_last=True) if direction == DIR_DESC else expr.asc(nulls_last=True)
    return queryset.order_by(order, *extra)


class TableSortMixin:
    """ORM list views: declare ``sort_columns`` as ``(key, field_lookup)`` pairs."""

    sort_columns = ()
    sort_default_key = 'code'
    sort_default_dir = DIR_ASC
    sort_extra = ('pk',)

    def apply_table_sort(self, queryset):
        keys = [key for key, _field in self.sort_columns]
        self.table_sort_key, self.table_sort_dir = parse_table_sort(
            self.request,
            keys,
            self.sort_default_key,
            self.sort_default_dir,
        )
        return apply_orm_sort(
            queryset,
            self.table_sort_key,
            self.table_sort_dir,
            dict(self.sort_columns),
            extra=self.sort_extra,
        )

    def get_table_sort_context(self):
        keys = [key for key, _field in self.sort_columns]
        key = getattr(self, 'table_sort_key', None)
        direction = getattr(self, 'table_sort_dir', None)
        if key is None or direction is None:
            key, direction = parse_table_sort(
                self.request,
                keys,
                self.sort_default_key,
                self.sort_default_dir,
            )
        return {
            'table_sort': build_sort_state(self.request, keys, key, direction),
        }
