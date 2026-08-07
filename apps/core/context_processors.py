from django.core.cache import cache

from apps.core.tag_utils import active_tags_queryset
from apps.workspaces.models import Workspace
from apps.workspaces.services import tags_in_workspace

TAG_SUGGESTIONS_CACHE_KEY = 'core:tag_suggestions'
TAG_SUGGESTIONS_CACHE_TIMEOUT = 300


def invalidate_tag_suggestions_cache(workspace_id=None) -> None:
    if workspace_id is None:
        return
    cache.delete(f'{TAG_SUGGESTIONS_CACHE_KEY}:{workspace_id}')


def invalidate_all_tag_suggestions_cache() -> None:
    for workspace_id in Workspace.objects.filter(is_active=True).values_list('pk', flat=True):
        invalidate_tag_suggestions_cache(workspace_id)


def tag_suggestions(request):
    workspace = getattr(request, 'active_workspace', None)
    if workspace is None:
        return {'tag_suggestions': []}

    cache_key = f'{TAG_SUGGESTIONS_CACHE_KEY}:{workspace.pk}'
    tag_ids = cache.get(cache_key)
    if tag_ids is None:
        tag_ids = list(
            active_tags_queryset(tags_in_workspace(workspace))
            .order_by('name')
            .values_list('pk', flat=True)[:250]
        )
        cache.set(cache_key, tag_ids, TAG_SUGGESTIONS_CACHE_TIMEOUT)
    tags = active_tags_queryset(tags_in_workspace(workspace)).filter(pk__in=tag_ids).order_by('name')
    return {'tag_suggestions': tags}


def app_version(request):
    from django.conf import settings

    return {'app_version': settings.APP_VERSION}
