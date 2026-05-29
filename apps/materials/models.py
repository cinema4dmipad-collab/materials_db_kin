import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.references.models import Property


class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, verbose_name='Код')
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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')
    created_by = models.CharField(max_length=100, blank=True, verbose_name='Создал')
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


class MaterialAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Материал',
    )
    file = models.FileField(
        upload_to='material_attachments/%Y/%m/%d/',
        verbose_name='Файл',
    )
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Загружен')

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

    class Meta:
        unique_together = ['material', 'property']
