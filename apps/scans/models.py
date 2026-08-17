import uuid

from django.conf import settings
from django.db import models

from apps.samples.models import Sample


class ScanRecord(models.Model):
    METHODS = [
        ('echo', 'Эхо'),
        ('shadow', 'Теневой'),
        ('immersion', 'Иммерсивный'),
    ]

    HDF5_EXTENSIONS = {'.h5', '.hdf5'}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='scans')
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='scan_records',
        verbose_name='Пространство',
    )
    file = models.FileField(
        upload_to='scans/%Y/%m/%d/',
        verbose_name='Файл скана (HDF5)',
    )
    preview = models.FileField(
        upload_to='scans/previews/%Y/%m/%d/',
        blank=True,
        verbose_name='Превью C-скана',
        help_text='Необязательное изображение (PNG/JPEG/WebP) C-скана для списка и карточки.',
    )
    preview_b_xz = models.FileField(
        upload_to='scans/previews/%Y/%m/%d/',
        blank=True,
        verbose_name='Превью B-скана-XZ',
        help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости XZ.',
    )
    preview_b_yz = models.FileField(
        upload_to='scans/previews/%Y/%m/%d/',
        blank=True,
        verbose_name='Превью B-скана-YZ',
        help_text='Необязательное изображение (PNG/JPEG/WebP) B-скана в плоскости YZ.',
    )
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    method = models.CharField(
        max_length=50,
        choices=METHODS,
        default='echo',
        verbose_name='Метод',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Загружен')
    uploaded_by = models.CharField(max_length=100, blank=True, verbose_name='Загрузил')
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_scans',
        verbose_name='Загрузил (пользователь)',
    )
    tags = models.ManyToManyField(
        'core.Tag',
        blank=True,
        related_name='scans',
        verbose_name='Теги',
    )

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'скан'
        verbose_name_plural = 'сканы'

    def __str__(self):
        return self.title

    @property
    def filename(self):
        if not self.file:
            return ''
        return self.file.name.rsplit('/', 1)[-1]

    @property
    def is_hdf5(self):
        if not self.file:
            return False
        extension = self.file.name.rsplit('.', 1)[-1].lower() if '.' in self.file.name else ''
        return f'.{extension}' in self.HDF5_EXTENSIONS

    def delete(self, *args, **kwargs):
        for attachment in self.attachments.all():
            if attachment.file:
                attachment.file.delete(save=False)
            if attachment.preview_image:
                attachment.preview_image.delete(save=False)
        if self.file:
            self.file.delete(save=False)
        from apps.scans.previews import delete_preview_files

        delete_preview_files(self)
        super().delete(*args, **kwargs)


class ScanAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(
        ScanRecord,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Скан',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='scan_attachments',
        verbose_name='Пространство',
    )
    file = models.FileField(
        upload_to='scan_attachments/%Y/%m/%d/',
        verbose_name='Файл',
    )
    preview_image = models.FileField(
        upload_to='scan_attachments/previews/%Y/%m/%d/',
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
        related_name='uploaded_scan_attachments',
        verbose_name='Загрузил (пользователь)',
    )

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'вложение скана'
        verbose_name_plural = 'вложения сканов'

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
