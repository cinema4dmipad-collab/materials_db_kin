import uuid

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
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
