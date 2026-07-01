import uuid

from django.conf import settings
from django.db import models

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

    def delete(self, *args, **kwargs):
        for scan in self.scans.all():
            if scan.file:
                scan.file.delete(save=False)
        for attachment in self.attachments.all():
            if attachment.file:
                attachment.file.delete(save=False)
        super().delete(*args, **kwargs)


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
    value = models.CharField(max_length=500)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.sample.code} - {self.property.display_name}: {self.value}'

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

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
