import uuid

from django.db import models

from apps.materials.models import Material


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
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='samples',
    )
    object_type = models.CharField(
        max_length=50,
        choices=OBJECT_TYPES,
        default='unset',
        verbose_name='Тип объекта',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['code']

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
