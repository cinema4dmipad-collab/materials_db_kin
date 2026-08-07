from django import template
from django.http import QueryDict
from django.utils.safestring import mark_safe

from apps.core.list_filters import (
    CREATOR_SEARCH_SCOPE,
    OBJECT_TYPE_SEARCH_SCOPE,
    SCAN_METHOD_SEARCH_SCOPE,
    STRUCT_TYPE_SEARCH_SCOPE,
)

register = template.Library()


def _normalize_path(path: str) -> str:
    return path.rstrip('/') or '/'


def _filter_target_path(context, base_path: str | None) -> str:
    request = context.get('request')
    normalized = (base_path or '').strip()
    if normalized:
        return normalized
    return request.path if request else '/'


@register.simple_tag(takes_context=True)
def tag_filter_link(context, tag_slug: str, base_path: str | None = None) -> str:
    request = context.get('request')
    target_path = _filter_target_path(context, base_path)
    if base_path and request and _normalize_path(base_path) != _normalize_path(request.path):
        params = QueryDict(mutable=True)
    else:
        params = request.GET.copy() if request else QueryDict(mutable=True)
    tags = params.getlist('tag')
    if tag_slug not in tags:
        tags.append(tag_slug)
    params.setlist('tag', tags)
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{target_path}?{encoded}' if encoded else target_path


@register.simple_tag
def tag_badge_style(tag):
    color = getattr(tag, 'color', '') or ''
    if not color:
        return ''
    text_color = getattr(tag, 'badge_text_color', None)
    if not text_color:
        from apps.core.tag_utils import contrast_text_color

        text_color = contrast_text_color(color)
    return mark_safe(
        f'style="--label-background-color:{color};--label-text-color:{text_color};"'
    )


@register.filter
def coalesce_tag_styles(tags):
    """Use global tag colors for colorless workspace clones in badges."""
    from apps.core.tag_utils import coalesce_tags_for_display

    return coalesce_tags_for_display(tags)


@register.filter
def is_scoped_tag(name):
    from apps.core.tag_utils import split_scoped_tag_display

    scope, value, _plain_name = split_scoped_tag_display(str(name or ''))
    return scope is not None and value is not None


@register.filter
def scoped_tag_label(name):
    from django.utils.html import escape

    from apps.core.tag_utils import split_scoped_tag_display

    scope, value, plain_name = split_scoped_tag_display(str(name or ''))
    if scope is None or value is None:
        return mark_safe(f'<span class="entity-tag__text">{escape(plain_name)}</span>')
    return mark_safe(
        f'<span class="entity-tag__text">{escape(scope)}</span>'
        f'<span class="entity-tag__text-scoped">{escape(value)}</span>'
    )


@register.simple_tag(takes_context=True)
def struct_type_filter_link(context, struct_type_name: str, base_path: str | None = None) -> str:
    request = context.get('request')
    target_path = _filter_target_path(context, base_path)
    if base_path and request and _normalize_path(base_path) != _normalize_path(request.path):
        params = QueryDict(mutable=True)
    else:
        params = request.GET.copy() if request else QueryDict(mutable=True)
    params['q'] = struct_type_name
    params.setlist('q_in', [STRUCT_TYPE_SEARCH_SCOPE])
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{target_path}?{encoded}' if encoded else target_path


@register.simple_tag(takes_context=True)
def object_type_filter_link(context, object_type_label: str, base_path: str | None = None) -> str:
    request = context.get('request')
    target_path = _filter_target_path(context, base_path)
    if base_path and request and _normalize_path(base_path) != _normalize_path(request.path):
        params = QueryDict(mutable=True)
    else:
        params = request.GET.copy() if request else QueryDict(mutable=True)
    params['q'] = object_type_label
    params.setlist('q_in', [OBJECT_TYPE_SEARCH_SCOPE])
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{target_path}?{encoded}' if encoded else target_path


@register.simple_tag(takes_context=True)
def creator_filter_link(context, creator_label: str, base_path: str | None = None) -> str:
    request = context.get('request')
    target_path = _filter_target_path(context, base_path)
    if base_path and request and _normalize_path(base_path) != _normalize_path(request.path):
        params = QueryDict(mutable=True)
    else:
        params = request.GET.copy() if request else QueryDict(mutable=True)
    params['q'] = creator_label
    params.setlist('q_in', [CREATOR_SEARCH_SCOPE])
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{target_path}?{encoded}' if encoded else target_path


@register.simple_tag(takes_context=True)
def scan_method_filter_link(context, method_label: str, base_path: str | None = None) -> str:
    request = context.get('request')
    target_path = _filter_target_path(context, base_path)
    if base_path and request and _normalize_path(base_path) != _normalize_path(request.path):
        params = QueryDict(mutable=True)
    else:
        params = request.GET.copy() if request else QueryDict(mutable=True)
    params['q'] = method_label
    params.setlist('q_in', [SCAN_METHOD_SEARCH_SCOPE])
    params.pop('page', None)
    encoded = params.urlencode()
    return f'{target_path}?{encoded}' if encoded else target_path
