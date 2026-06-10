---
description: Django conventions — models, forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---
Реализуй полноценную интеграцию Sample и ScanRecord с S3 хранилищем в существующий проект.

## Контекст
У меня уже есть модель Material (материалы). Теперь нужно добавить образцы (Sample) и сканы (ScanRecord) с хранением файлов в S3.

## Связи
- Material (1) → Sample (M) : один материал может иметь много образцов
- Sample (1) → ScanRecord (M) : один образец может иметь много сканов
- ScanRecord (1) → S3 : каждый скан хранит файл в S3

## Что нужно сделать

### 1. Модель Sample (apps/samples/models.py)
```python
class Sample(models.Model):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    code = CharField(max_length=50, unique=True)
    name = CharField(max_length=200)
    material = ForeignKey('materials.Material', on_delete=CASCADE, related_name='samples')
    object_type = CharField(max_length=50, choices=ObjectType.choices, default='sample')
    created_at = DateTimeField(auto_now_add=True)
    created_by = CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"
2. Модель ScanRecord (apps/scans/models.py)
python
class ScanRecord(models.Model):
    SCAN_TYPES = [
        ('microstructure', 'Микроструктура'),
        ('spectrum', 'Спектр'),
        ('surface', 'Поверхность'),
        ('cross_section', 'Поперечное сечение'),
        ('other', 'Другое'),
    ]
    
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    sample = ForeignKey('samples.Sample', on_delete=CASCADE, related_name='scans')
    
    # S3 файл
    file = FileField(upload_to='scans/%Y/%m/%d/', verbose_name="Файл скана")
    
    title = CharField(max_length=200)
    description = TextField(blank=True)
    scan_type = CharField(max_length=50, choices=SCAN_TYPES, default='microstructure')
    
    # Параметры сканирования
    magnification = IntegerField(null=True, blank=True, verbose_name="Увеличение (×)")
    resolution = CharField(max_length=50, blank=True, verbose_name="Разрешение (dpi)")
    
    uploaded_at = DateTimeField(auto_now_add=True)
    uploaded_by = CharField(max_length=100, blank=True)
    
    def __str__(self):
        return self.title
    
    def delete(self, *args, **kwargs):
        # Удаляем файл из S3 при удалении записи
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
3. Настройка S3 в settings.py
python
# Установить: poetry add django-storages boto3
INSTALLED_APPS = [
    ...
    'storages',
]

# S3 конфигурация (добавить в .env)
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')

AWS_DEFAULT_ACL = 'private'
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600

STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    }
}
4. Админка
В MaterialAdmin добавить SampleInline (чтобы видеть образцы внутри материала)

В SampleAdmin добавить ScanInline (чтобы видеть сканы внутри образца)

ScanInline должен показывать preview файла (если изображение)

5. Формы и вьюхи
ScanCreateView: загрузка файла с валидацией (размер, тип)

ScanListView: список сканов образца

ScanDeleteView: удаление файла из S3

6. Шаблоны
templates/samples/detail.html: отображение образца и всех его сканов

templates/scans/form.html: форма загрузки скана

templates/scans/list.html: список сканов

7. Миграции и тесты
Создать миграции для приложений samples и scans

Написать тесты для загрузки/удаления файлов

Требования к реализации
При удалении образца — все связанные сканы удаляются из S3

При удалении материала — каскадно удаляются образцы и сканы

Файлы должны загружаться в S3, а не на сервер

В админке должна быть возможность просматривать загруженные изображения

Добавить валидацию файлов (расширения, размер)

Команды для выполнения
poetry add django-storages boto3

poetry run python manage.py makemigrations samples scans

poetry run python manage.py migrate

poetry run python manage.py createsuperuser (если ещё нет)

Создай все необходимые файлы с полной реализацией.