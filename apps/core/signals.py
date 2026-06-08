from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.context_processors import invalidate_tag_suggestions_cache
from apps.core.models import Tag


@receiver(post_save, sender=Tag)
@receiver(post_delete, sender=Tag)
def clear_tag_suggestions_cache(sender, **kwargs):
    invalidate_tag_suggestions_cache()
