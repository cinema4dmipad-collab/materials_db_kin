import uuid

from django.conf import settings
from django.db import models

from apps.core.property_number_value import (
    VALUE_KIND_SCALAR,
    VALUE_KIND_CHOICES,
    format_property_number_display,
    sync_number_property_instance,
)
from apps.materials.models import Material
from apps.references.models import Property


class Sample(models.Model):
    OBJECT_TYPES = [
        ('unset', 'Не задано'),
        ('test', 'Испытательный'),
        ('control', 'Контрольный'),
        ('structural_similar', 'Конструктивно-подобный'),
        ('product', 'Изделие'),
        ('calibration', 'Настроечный'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='samples',
    )
    struct_type = models.ForeignKey(
        'structures.StructureType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='samples',
        verbose_name='Тип структуры',
    )
    struct_props_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='ID параметров структуры',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='samples',
        verbose_name='Пространство',
    )
    object_type = models.CharField(
        max_length=50,
        choices=OBJECT_TYPES,
        default='unset',
        verbose_name='Тип объекта',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_samples',
        verbose_name='Создал (пользователь)',
    )

    tags = models.ManyToManyField(
        'core.Tag',
        blank=True,
        related_name='samples',
        verbose_name='Теги',
    )

    class Meta:
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'code'],
                name='unique_sample_code_per_workspace',
            ),
        ]

    def __str__(self):
        return f'{self.code} - {self.name}'

    def get_structure_params(self):
        if not self.struct_type_id or not self.struct_props_id:
            return None

        from apps.structures.sql_executor import SQLExecutor

        return SQLExecutor.get_structure_instance(self.struct_type, self.struct_props_id)

    def delete(self, *args, **kwargs):
        struct_type_id = self.struct_type_id
        struct_props_id = self.struct_props_id
        for scan in self.scans.all():
            if scan.file:
                scan.file.delete(save=False)
        for attachment in self.attachments.all():
            if attachment.file:
                attachment.file.delete(save=False)
        super().delete(*args, **kwargs)
        _cleanup_sample_structure_row(struct_type_id, struct_props_id)


def _cleanup_sample_structure_row(struct_type_id, struct_props_id) -> None:
    if not struct_type_id or not struct_props_id:
        return
    from apps.materials.models import Material
    from apps.structures.models import StructureType
    from apps.structures.table_storage import delete_table_row

    if Material.objects.filter(
        struct_type_id=struct_type_id,
        struct_props_id=struct_props_id,
    ).exists():
        return
    if Sample.objects.filter(
        struct_type_id=struct_type_id,
        struct_props_id=struct_props_id,
    ).exists():
        return
    structure_type = StructureType.objects.filter(pk=struct_type_id).first()
    if structure_type is None:
        return
    try:
        delete_table_row(structure_type, uuid.UUID(str(struct_props_id)))
    except Exception:
        pass


class SampleProperty(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name='properties',
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='sample_values',
    )
    value_kind = models.CharField(
        max_length=10,
        choices=VALUE_KIND_CHOICES,
        default=VALUE_KIND_SCALAR,
    )
    value = models.CharField(max_length=500)
    value_b = models.DecimalField(max_digits=18, decimal_places=10, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.sample.code} - {self.property.display_name}: {self.value}'

    def display_value(self) -> str:
        if getattr(self.property, 'data_type', None) != 'number':
            return self.value
        return format_property_number_display(
            value_kind=self.value_kind,
            value=self.value,
            value_b=self.value_b,
            decimal_places=self.property.effective_decimal_places(),
        )

    def save(self, *args, **kwargs):
        if getattr(self.property, 'data_type', None) == 'number':
            sync_number_property_instance(self)
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['sample', 'property']


class SampleAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Образец',
    )
    file = models.FileField(
        upload_to='sample_attachments/%Y/%m/%d/',
        verbose_name='Файл',
    )
    preview_image = models.FileField(
        upload_to='sample_attachments/previews/%Y/%m/%d/',
        blank=True,
        verbose_name='Превью (изображение)',
        help_text='Миниатюра первой страницы (PNG) для списка вложений.',
    )
    preview_status = models.CharField(
        max_length=20,
        choices=[
            ('none', 'Нет'),
            ('skipped', 'Не требуется'),
            ('pending', 'Обработка'),
            ('ready', 'Готово'),
            ('failed', 'Ошибка'),
        ],
        default='none',
        verbose_name='Статус превью',
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
        related_name='uploaded_sample_attachments',
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

    @property
    def kind(self):
        from apps.core.attachments.kinds import detect_attachment_kind

        return detect_attachment_kind(self.filename)

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        if self.preview_image:
            self.preview_image.delete(save=False)
        super().delete(*args, **kwargs)
