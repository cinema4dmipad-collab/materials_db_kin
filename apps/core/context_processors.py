from django.core.cache import cache

from apps.core.models import Tag

TAG_SUGGESTIONS_CACHE_KEY = 'core:tag_suggestions'
TAG_SUGGESTIONS_CACHE_TIMEOUT = 300


def invalidate_tag_suggestions_cache() -> None:
    cache.delete(TAG_SUGGESTIONS_CACHE_KEY)


def tag_suggestions(request):
    tag_ids = cache.get(TAG_SUGGESTIONS_CACHE_KEY)
    if tag_ids is None:
        tag_ids = list(Tag.objects.order_by('name').values_list('pk', flat=True)[:250])
        cache.set(TAG_SUGGESTIONS_CACHE_KEY, tag_ids, TAG_SUGGESTIONS_CACHE_TIMEOUT)
    tags = Tag.objects.filter(pk__in=tag_ids).order_by('name')
    return {'tag_suggestions': tags}


def app_version(request):
    from django.conf import settings

    return {'app_version': settings.APP_VERSION}
