from apps.core.models import Tag


def tag_suggestions(request):
    return {
        'tag_suggestions': Tag.objects.order_by('name')[:250],
    }
