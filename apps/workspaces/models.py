import uuid

from django.conf import settings
from django.db import models


class WorkspaceRole(models.TextChoices):
    MANAGER = 'manager', 'Менеджер'
    OPERATOR = 'operator', 'Оператор'


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=50, unique=True, verbose_name='Код')
    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        ordering = ['name']
        verbose_name = 'пространство'
        verbose_name_plural = 'пространства'

    def __str__(self):
        return self.name


class WorkspaceMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Пространство',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_memberships',
        verbose_name='Пользователь',
    )
    role = models.CharField(
        max_length=20,
        choices=WorkspaceRole.choices,
        default=WorkspaceRole.OPERATOR,
        verbose_name='Роль',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'user'],
                name='unique_workspace_membership',
            ),
        ]
        verbose_name = 'участник пространства'
        verbose_name_plural = 'участники пространств'

    def __str__(self):
        return f'{self.user} @ {self.workspace} ({self.get_role_display()})'
