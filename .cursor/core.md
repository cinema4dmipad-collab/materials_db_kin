---
description: Django conventions — models, forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---

# План разработки базы композитов

## Статус проекта
- [x] Poetry инициализирован
- [x] Django установлен
- [x] Скелет проекта создан
- [x] Модели данных
- [x] Админка
- [x] Интерфейс (дашборд)

## Текущая структура проекта (ожидается)
composites_db/
├├───.cursor
├───config
│   └───__pycache__
├───core
│   ├───migrations
│   │   └───__pycache__
│   └───__pycache__
├───materials
│   ├───migrations
│   │   └───__pycache__
│   └───__pycache__
├───samples
│   ├───migrations
│   │   └───__pycache__
│   └───__pycache__
├───scans
│   ├───migrations
│   │   └───__pycache__
│   └───__pycache__
└───templates
    ├───base
    ├───footer
    └───header

text

## Зависимости (проверить в pyproject.toml)
```toml
[tool.poetry.dependencies]
python = "^3.13"
django = "^5.0"
psycopg2-binary = "^2.9"
python-dotenv = "^1.0"
Задача 1: Настройка проекта
1.1 Файл .env
Создать в корне проекта файл .env:

env
DEBUG=True
SECRET_KEY=django-insecure-temporary-key-for-dev
1.2 Обновить config/settings.py
python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Local apps
    'apps.core',
    'apps.materials',
    'apps.references',
    'apps.samples',
    'apps.scans',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
1.3 Обновить config/urls.py
python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
]
Задача 2: Модели данных
2.1 apps/references/models.py
python
from django.db import models
import uuid

class PropertyGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['sort_order', 'name']

class Property(models.Model):
    DATA_TYPES = [
        ('number', 'Число'),
        ('string', 'Строка'),
        ('boolean', 'Да/Нет'),
        ('date', 'Дата'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=50, blank=True)
    data_type = models.CharField(max_length=20, choices=DATA_TYPES, default='number')
    group = models.ForeignKey(PropertyGroup, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.display_name} ({self.unit})" if self.unit else self.display_name
    
    class Meta:
        ordering = ['group__sort_order', 'name']
2.2 apps/materials/models.py
python
from django.db import models
from apps.references.models import Property
import uuid

class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    class Meta:
        ordering = ['code']

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
2.3 apps/samples/models.py
python
from django.db import models
from apps.materials.models import Material
import uuid

class Sample(models.Model):
    OBJECT_TYPES = [
        ('sample', 'Образец'),
        ('prototype', 'Прототип'),
        ('production', 'Производственная партия'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='samples')
    object_type = models.CharField(max_length=20, choices=OBJECT_TYPES, default='sample')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"
2.4 apps/scans/models.py
python
from django.db import models
from apps.samples.models import Sample
import uuid

class ScanRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'В ожидании'),
        ('processing', 'В обработке'),
        ('completed', 'Завершён'),
        ('failed', 'Ошибка'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='scans')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title
2.5 apps/core/urls.py
python
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
2.6 apps/core/views.py
python
from django.shortcuts import render
from apps.materials.models import Material
from apps.samples.models import Sample

def dashboard(request):
    context = {
        'materials_count': Material.objects.count(),
        'samples_count': Sample.objects.count(),
        'recent_materials': Material.objects.order_by('-created_at')[:5],
    }
    return render(request, 'core/dashboard.html', context)
2.7 templates/core/dashboard.html
django
{% extends 'base.html' %}

{% block content %}
<h1>Дашборд</h1>

<div class="stats">
    <div class="stat-card">
        <h3>Материалы</h3>
        <p>{{ materials_count }}</p>
    </div>
    <div class="stat-card">
        <h3>Образцы</h3>
        <p>{{ samples_count }}</p>
    </div>
</div>

<h2>Последние материалы</h2>
<ul>
    {% for material in recent_materials %}
        <li>{{ material.code }} - {{ material.name }}</li>
    {% endfor %}
</ul>
{% endblock %}
2.8 templates/base.html
django
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>База композитов</title>
</head>
<body>
    <nav>
        <a href="{% url 'core:dashboard' %}">Дашборд</a>
        <a href="/admin/">Админка</a>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
Задача 3: Админка
3.1 apps/materials/admin.py
python
from django.contrib import admin
from .models import Material, MaterialProperty

class MaterialPropertyInline(admin.TabularInline):
    model = MaterialProperty
    extra = 1

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'created_at']
    search_fields = ['code', 'name']
    list_filter = ['created_at']
    inlines = [MaterialPropertyInline]

@admin.register(MaterialProperty)
class MaterialPropertyAdmin(admin.ModelAdmin):
    list_display = ['material', 'property', 'value']
    search_fields = ['material__code', 'property__name']
3.2 apps/references/admin.py
python
from django.contrib import admin
from .models import PropertyGroup, Property

@admin.register(PropertyGroup)
class PropertyGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order']
    list_editable = ['sort_order']

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'unit', 'data_type', 'group']
    list_filter = ['data_type', 'group']
    search_fields = ['display_name', 'name']
3.3 apps/samples/admin.py
python
from django.contrib import admin
from .models import Sample

@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'material', 'object_type', 'created_at']
    search_fields = ['code', 'name', 'material__code']
    list_filter = ['object_type', 'material']
3.4 apps/scans/admin.py
python
from django.contrib import admin
from .models import ScanRecord

@admin.register(ScanRecord)
class ScanRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'sample', 'status', 'created_at']
    search_fields = ['title', 'sample__code']
    list_filter = ['status', 'created_at']
Задача 4: Миграции и запуск
Выполнить команды:
bash
# Создать миграции
poetry run python manage.py makemigrations

# Применить миграции
poetry run python manage.py migrate

# Создать суперпользователя
poetry run python manage.py createsuperuser

# Запустить сервер
poetry run python manage.py runserver
Проверка
Открыть http://localhost:8000/ - дашборд

Открыть http://localhost:8000/admin/ - админка

Создать группу свойств (например, "Механические")

Создать свойство (например, "Плотность", единица "kg/m³")

Создать материал и добавить ему свойство