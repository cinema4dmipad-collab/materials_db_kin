import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='tags',
        null=True,
        blank=True,
        verbose_name='Пространство',
        help_text='Пусто — общий тег, доступен во всех пространствах.',
    )
    name = models.CharField(max_length=50, verbose_name='Название')
    slug = models.SlugField(max_length=50, verbose_name='Код')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tags',
        verbose_name='Создал',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'тег'
        verbose_name_plural = 'теги'
        constraints = [
            models.UniqueConstraint(
                fields=['slug'],
                condition=Q(workspace__isnull=True),
                name='unique_global_tag_slug',
            ),
            models.UniqueConstraint(
                fields=['name'],
                condition=Q(workspace__isnull=True),
                name='unique_global_tag_name',
            ),
            models.UniqueConstraint(
                fields=['workspace', 'slug'],
                condition=Q(workspace__isnull=False),
                name='unique_tag_slug_per_workspace',
            ),
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                condition=Q(workspace__isnull=False),
                name='unique_tag_name_per_workspace',
            ),
        ]

    @property
    def is_global(self) -> bool:
        return self.workspace_id is None

    def __str__(self):
        return self.name
