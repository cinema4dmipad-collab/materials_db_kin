import uuid

from django.db import models


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='tags',
        verbose_name='Пространство',
    )
    name = models.CharField(max_length=50, verbose_name='Название')
    slug = models.SlugField(max_length=50, verbose_name='Код')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        ordering = ['name']
        verbose_name = 'тег'
        verbose_name_plural = 'теги'
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'slug'],
                name='unique_tag_slug_per_workspace',
            ),
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='unique_tag_name_per_workspace',
            ),
        ]

    def __str__(self):
        return self.name
