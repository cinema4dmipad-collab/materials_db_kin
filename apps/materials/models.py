import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.references.models import Property
from apps.workspaces.visibility import VisibilityMode, WorkspaceVisibilityMixin


class Material(WorkspaceVisibilityMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, verbose_name='Код')
    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    struct_type = models.ForeignKey(
        'structures.StructureType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='Тип структуры',
    )
    struct_props_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='ID параметров структуры',
    )
    home_workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='home_materials',
        verbose_name='Домашнее пространство',
    )
    visibility_mode = models.CharField(
        max_length=32,
        choices=VisibilityMode.choices,
        default=VisibilityMode.ALL_WORKSPACES,
        verbose_name='Режим видимости',
    )
    published_workspaces = models.ManyToManyField(
        'workspaces.Workspace',
        blank=True,
        related_name='published_materials',
        verbose_name='Опубликовано в пространствах',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')
    created_by = models.CharField(max_length=100, blank=True, verbose_name='Создал')
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_materials',
        verbose_name='Создал (пользователь)',
    )
    tags = models.ManyToManyField(
        'core.Tag',
        blank=True,
        related_name='materials',
        verbose_name='Теги',
    )

    def __str__(self):
        return f'{self.code} - {self.name}'

    @property
    def is_composite(self):
        return self.pk is not None and self.composite_layers.exists()

    @property
    def is_simple(self):
        return bool(self.struct_type_id)

    @property
    def supports_layers(self):
        return bool(self.struct_type_id and self.struct_type.allow_layers)

    def clean(self):
        super().clean()
        if self.struct_props_id and not self.struct_type_id:
            raise ValidationError(
                {'struct_type': 'Выберите тип структуры для параметров структуры.'}
            )
        if not self.struct_type_id or not self.struct_props_id:
            return
        if not self.struct_type.is_created:
            raise ValidationError(
                {'struct_type': 'SQL-таблица для выбранного типа структуры еще не создана.'}
            )
        if self.get_structure_params() is None:
            raise ValidationError(
                {'struct_props_id': 'Запись параметров структуры не найдена.'}
            )

    def get_structure_params(self):
        if not self.struct_type_id or not self.struct_props_id:
            return None

        from apps.structures.sql_executor import SQLExecutor

        return SQLExecutor.get_structure_instance(self.struct_type, self.struct_props_id)

    def delete(self, *args, **kwargs):
        for attachment in self.attachments.all():
            if attachment.file:
                attachment.file.delete(save=False)
        super().delete(*args, **kwargs)

    class Meta:
        ordering = ['code']
        verbose_name = 'материал'
        verbose_name_plural = 'материалы'
        constraints = [
            models.UniqueConstraint(
                fields=['home_workspace', 'code'],
                name='unique_material_code_per_workspace',
            ),
        ]


class MaterialAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Материал',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='material_attachments',
        verbose_name='Пространство',
    )
    file = models.FileField(
        upload_to='material_attachments/%Y/%m/%d/',
        verbose_name='Файл',
    )
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Загружен')
    uploaded_by = models.CharField(max_length=100, blank=True, verbose_name='Загрузил')
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_material_attachments',
        verbose_name='Загрузил (пользователь)',
    )

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'вложение'
        verbose_name_plural = 'вложения'

    def __str__(self):
        return self.title

    @property
    def filename(self):
        if not self.file:
            return ''
        return self.file.name.rsplit('/', 1)[-1]

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)


class MaterialProperty(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='properties')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='material_values')
    value = models.CharField(max_length=500)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.material.code} - {self.property.display_name}: {self.value}"

    def linked_material(self):
        if getattr(self.property, 'data_type', None) != Property.MATERIAL_LINK_DATA_TYPE:
            return None
        from apps.structures.forms import material_from_value

        return material_from_value(self.value)

    def choice_display_value(self):
        if getattr(self.property, 'data_type', None) != Property.CHOICE_DATA_TYPE:
            return self.value
        return self.property.choice_label_for_value(self.value)

    class Meta:
        unique_together = ['material', 'property']
