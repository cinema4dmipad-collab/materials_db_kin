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
    description = models.TextField(blank=True, verbose_name='Описание')
    color = models.CharField(
        max_length=7,
        blank=True,
        verbose_name='Цвет',
        help_text='Hex-цвет (#RRGGBB). Пусто — стандартный стиль.',
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name='В архиве',
        help_text='Скрыт из выбора, но остаётся на уже помеченных записях.',
    )
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

    @property
    def badge_text_color(self) -> str | None:
        from apps.core.tag_utils import contrast_text_color

        if not self.color:
            return None
        return contrast_text_color(self.color)

    def __str__(self):
        return self.name


class BookmarkEntityType(models.TextChoices):
    MATERIAL = 'material', 'Материал'
    SAMPLE = 'sample', 'Образец'
    SCAN = 'scan', 'Скан'
    STRUCTURE_RECORD = 'structure_record', 'Запись структуры'
    STRUCTURE_TYPE = 'structure_type', 'Тип структуры'


class UserBookmark(models.Model):
    """Персональная закладка пользователя в рамках рабочего пространства."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookmarks',
        verbose_name='Пользователь',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='user_bookmarks',
        verbose_name='Пространство',
    )
    entity_type = models.CharField(
        max_length=20,
        choices=BookmarkEntityType.choices,
        verbose_name='Тип объекта',
    )
    entity_id = models.UUIDField(verbose_name='ID объекта')
    parent_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='Родительский ID',
        help_text='Для сканов — UUID образца.',
    )
    context_slug = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Контекст (slug)',
        help_text='Для записей структуры — code типа структуры.',
    )
    label = models.CharField(max_length=300, blank=True, verbose_name='Подпись')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'закладка'
        verbose_name_plural = 'закладки'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'workspace', 'entity_type', 'entity_id'],
                name='unique_user_bookmark_per_entity',
            ),
        ]

    def __str__(self):
        return self.label or f'{self.entity_type}:{self.entity_id}'
