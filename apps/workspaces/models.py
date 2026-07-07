import uuid

from django.conf import settings
from django.db import models


BUILTIN_GROUP_MANAGER = 'Менеджер'
BUILTIN_GROUP_OPERATOR = 'Оператор'


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


class WorkspaceGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='groups',
        verbose_name='Пространство',
    )
    name = models.CharField(max_length=100, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    permissions = models.JSONField(default=list, verbose_name='Права')
    is_builtin = models.BooleanField(default=False, verbose_name='Встроенная')

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='unique_workspace_group_name',
            ),
        ]
        verbose_name = 'группа пространства'
        verbose_name_plural = 'группы пространств'

    def __str__(self):
        return f'{self.name} ({self.workspace.name})'

    def permission_set(self) -> frozenset:
        return frozenset(self.permissions or [])

    def has_perm(self, codename: str) -> bool:
        return codename in self.permission_set()

    @property
    def permission_bundle_labels(self):
        from apps.workspaces.permissions import permission_bundle_labels_for_permissions

        return permission_bundle_labels_for_permissions(self.permissions)


class WorkspaceGroupMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        WorkspaceGroup,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Группа',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_group_memberships',
        verbose_name='Пользователь',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'user'],
                name='unique_workspace_group_membership',
            ),
        ]
        verbose_name = 'участник группы'
        verbose_name_plural = 'участники групп'

    def __str__(self):
        return f'{self.user} @ {self.group}'

    @property
    def workspace(self):
        return self.group.workspace


class WorkspaceMaterialLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='material_links',
        verbose_name='Пространство',
    )
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.CASCADE,
        related_name='workspace_links',
        verbose_name='Материал',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлено')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'material'],
                name='unique_workspace_material_link',
            ),
        ]
        verbose_name = 'ссылка на материал'
        verbose_name_plural = 'ссылки на материалы'

    def __str__(self):
        return f'{self.material} @ {self.workspace}'
