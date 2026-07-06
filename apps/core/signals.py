from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.context_processors import invalidate_all_tag_suggestions_cache, invalidate_tag_suggestions_cache
from apps.core.models import Tag


@receiver(post_save, sender=Tag)
@receiver(post_delete, sender=Tag)
def clear_tag_suggestions_cache(sender, instance, **kwargs):
    if instance.workspace_id:
        invalidate_tag_suggestions_cache(instance.workspace_id)
    else:
        invalidate_all_tag_suggestions_cache()
