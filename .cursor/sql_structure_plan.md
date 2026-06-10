---
description: Django conventions — models, forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---
# SQL_STRUCTURES_PLAN.md
# План: динамические структуры через чистый SQL (без Django ORM)

## Контекст
Мы создаём систему для управления композитными материалами. Нужно, чтобы администраторы могли создавать новые типы структур (Сэндвич, Монолит, Соты) и их поля прямо через интерфейс, без написания кода и миграций.

**Техническое решение:** Чистый SQL, никаких динамических Django моделей.

## Архитектура

### Модели метаданных (эти модели НОРМАЛЬНЫЕ, через Django ORM)

```python
# apps/structures/models.py

from django.db import models
import uuid

class StructureType(models.Model):
    """Тип структуры — метаданные о динамической таблице"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    code = models.SlugField(max_length=50, unique=True, verbose_name="Код")
    description = models.TextField(blank=True, verbose_name="Описание")
    table_name = models.CharField(max_length=100, unique=True, verbose_name="Имя таблицы")
    is_created = models.BooleanField(default=False, verbose_name="Таблица создана")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Тип структуры"
        verbose_name_plural = "Типы структур"
    
    def __str__(self):
        return self.name


class StructureField(models.Model):
    """Поля для динамической таблицы"""
    
    FIELD_TYPES = [
        ('CharField', 'Строка (VARCHAR)'),
        ('TextField', 'Текст (TEXT)'),
        ('IntegerField', 'Целое число (INTEGER)'),
        ('DecimalField', 'Десятичная дробь (DECIMAL)'),
        ('BooleanField', 'Да/Нет (BOOLEAN)'),
        ('DateField', 'Дата (DATE)'),
        ('DateTimeField', 'Дата и время (TIMESTAMP)'),
    ]
    
    structure_type = models.ForeignKey(StructureType, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100, verbose_name="Имя колонки (snake_case)")
    label = models.CharField(max_length=200, verbose_name="Подпись в форме")
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES, verbose_name="Тип поля")
    is_required = models.BooleanField(default=False, verbose_name="Обязательное")
    sort_order = models.IntegerField(default=0, verbose_name="Порядок")
    
    # Параметры для CharField
    max_length = models.IntegerField(null=True, blank=True, default=255)
    
    # Параметры для DecimalField
    max_digits = models.IntegerField(null=True, blank=True, default=10)
    decimal_places = models.IntegerField(null=True, blank=True, default=2)
    
    # Значение по умолчанию
    default_value = models.CharField(max_length=500, blank=True)
    
    class Meta:
        ordering = ['sort_order']
        unique_together = ['structure_type', 'name']
        verbose_name = "Поле структуры"
        verbose_name_plural = "Поля структур"
    
    def __str__(self):
        return f"{self.structure_type.name}.{self.name}"
SQL Executor (ядро системы)
python
# apps/structures/sql_executor.py

from django.db import connection
from django.conf import settings
from .models import StructureType, StructureField


class SQLExecutor:
    """Выполняет SQL запросы для динамических таблиц"""
    
    @staticmethod
    def create_table(structure_type: StructureType) -> dict:
        """
        Создаёт таблицу в БД через прямой SQL.
        Возвращает словарь с результатом: {'success': True/False, 'error': str}
        """
        try:
            columns = SQLExecutor._build_columns(structure_type)
            sql = f"""
                CREATE TABLE IF NOT EXISTS {structure_type.table_name} (
                    {', '.join(columns)}
                )
            """
            
            with connection.cursor() as cursor:
                cursor.execute(sql)
            
            # Отмечаем, что таблица создана
            structure_type.is_created = True
            structure_type.save()
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _build_columns(structure_type: StructureType) -> list:
        """Формирует список определений колонок"""
        
        columns = [
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
        ]
        
        for field in structure_type.fields.all():
            col_def = SQLExecutor._column_definition(field)
            columns.append(col_def)
        
        columns.extend([
            "created_at TIMESTAMP DEFAULT NOW()",
            "updated_at TIMESTAMP DEFAULT NOW()",
            "created_by VARCHAR(100)",
            "updated_by VARCHAR(100)",
        ])
        
        return columns
    
    @staticmethod
    def _column_definition(field: StructureField) -> str:
        """Возвращает SQL определение колонки"""
        
        null_constraint = "NOT NULL" if field.is_required else "NULL"
        
        type_mapping = {
            'CharField': f"VARCHAR({field.max_length or 255})",
            'TextField': "TEXT",
            'IntegerField': "INTEGER",
            'DecimalField': f"DECIMAL({field.max_digits or 10}, {field.decimal_places or 2})",
            'BooleanField': "BOOLEAN",
            'DateField': "DATE",
            'DateTimeField': "TIMESTAMP",
        }
        
        sql_type = type_mapping.get(field.field_type, "TEXT")
        return f"{field.name} {sql_type} {null_constraint}"
    
    @staticmethod
    def drop_table(structure_type: StructureType) -> dict:
        """Удаляет таблицу из БД"""
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {structure_type.table_name}")
            
            structure_type.is_created = False
            structure_type.save()
            
            return {'success': True, 'error': None}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def table_exists(structure_type: StructureType) -> bool:
        """Проверяет, существует ли таблица в БД"""
        sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            )
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [structure_type.table_name])
            return cursor.fetchone()[0]
    
    @staticmethod
    def insert(structure_type: StructureType, data: dict) -> dict:
        """Вставляет запись в динамическую таблицу"""
        try:
            columns = []
            placeholders = []
            values = []
            
            for field in structure_type.fields.all():
                if field.name in data and data[field.name]:
                    columns.append(field.name)
                    placeholders.append("%s")
                    values.append(data[field.name])
            
            # Добавляем служебные поля
            columns.append("created_by")
            placeholders.append("%s")
            values.append(data.get('created_by', 'anonymous'))
            
            columns.append("created_at")
            placeholders.append("NOW()")
            
            sql = f"""
                INSERT INTO {structure_type.table_name} 
                ({', '.join(columns)}) 
                VALUES ({', '.join(placeholders)})
                RETURNING id
            """
            
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                row_id = cursor.fetchone()[0]
            
            return {'success': True, 'id': row_id, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_all(structure_type: StructureType, limit: int = 100, offset: int = 0) -> dict:
        """Получает все записи из динамической таблицы"""
        try:
            sql = f"""
                SELECT * FROM {structure_type.table_name} 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(sql, [limit, offset])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                
                records = [dict(zip(columns, row)) for row in rows]
                
                # Подсчёт общего количества
                cursor.execute(f"SELECT COUNT(*) FROM {structure_type.table_name}")
                total = cursor.fetchone()[0]
            
            return {'success': True, 'records': records, 'total': total, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_by_id(structure_type: StructureType, record_id: str) -> dict:
        """Получает запись по ID"""
        try:
            sql = f"SELECT * FROM {structure_type.table_name} WHERE id = %s"
            
            with connection.cursor() as cursor:
                cursor.execute(sql, [record_id])
                columns = [col[0] for col in cursor.description]
                row = cursor.fetchone()
                
                if row:
                    return {'success': True, 'record': dict(zip(columns, row)), 'error': None}
                else:
                    return {'success': False, 'error': 'Record not found'}
                    
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def update(structure_type: StructureType, record_id: str, data: dict) -> dict:
        """Обновляет запись"""
        try:
            set_clauses = []
            values = []
            
            for field in structure_type.fields.all():
                if field.name in data:
                    set_clauses.append(f"{field.name} = %s")
                    values.append(data[field.name])
            
            if not set_clauses:
                return {'success': True, 'error': None}
            
            set_clauses.append("updated_at = NOW()")
            values.append(record_id)
            
            sql = f"""
                UPDATE {structure_type.table_name} 
                SET {', '.join(set_clauses)}
                WHERE id = %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def delete(structure_type: StructureType, record_id: str) -> dict:
        """Удаляет запись"""
        try:
            sql = f"DELETE FROM {structure_type.table_name} WHERE id = %s"
            
            with connection.cursor() as cursor:
                cursor.execute(sql, [record_id])
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def add_column(structure_type: StructureType, field: StructureField) -> dict:
        """Добавляет колонку в существующую таблицу"""
        try:
            col_def = SQLExecutor._column_definition(field)
            sql = f"ALTER TABLE {structure_type.table_name} ADD COLUMN {col_def}"
            
            with connection.cursor() as cursor:
                cursor.execute(sql)
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
Админка для управления
python
# apps/structures/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from .models import StructureType, StructureField
from .sql_executor import SQLExecutor


class StructureFieldInline(admin.TabularInline):
    model = StructureField
    extra = 1
    fields = ['name', 'label', 'field_type', 'is_required', 'sort_order', 
              'max_length', 'max_digits', 'decimal_places']


@admin.register(StructureType)
class StructureTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'table_name', 'is_created', 'created_at']
    list_filter = ['is_created']
    search_fields = ['name', 'code', 'table_name']
    inlines = [StructureFieldInline]
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<uuid:pk>/create-table/', self.create_table_view, name='structuretype_create_table'),
            path('<uuid:pk>/drop-table/', self.drop_table_view, name='structuretype_drop_table'),
        ]
        return custom_urls + urls
    
    def create_table_view(self, request, pk):
        structure_type = StructureType.objects.get(pk=pk)
        
        if not structure_type.fields.exists():
            messages.error(request, 'Сначала добавьте поля для этой структуры')
        else:
            result = SQLExecutor.create_table(structure_type)
            if result['success']:
                messages.success(request, f'Таблица "{structure_type.table_name}" успешно создана')
            else:
                messages.error(request, f'Ошибка: {result["error"]}')
        
        return redirect('admin:structures_structuretype_changelist')
    
    def drop_table_view(self, request, pk):
        structure_type = StructureType.objects.get(pk=pk)
        result = SQLExecutor.drop_table(structure_type)
        
        if result['success']:
            messages.success(request, f'Таблица "{structure_type.table_name}" удалена')
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
        
        return redirect('admin:structures_structuretype_changelist')
    
    actions = ['create_tables_action']
    
    def create_tables_action(self, request, queryset):
        created = 0
        for st in queryset:
            if st.fields.exists():
                result = SQLExecutor.create_table(st)
                if result['success']:
                    created += 1
        self.message_user(request, f'Создано таблиц: {created}')
    create_tables_action.short_description = 'Создать таблицы для выбранных типов'


@admin.register(StructureField)
class StructureFieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'structure_type', 'field_type', 'is_required', 'sort_order']
    list_filter = ['structure_type', 'field_type']
    search_fields = ['name', 'label']
View для пользователя
python
# apps/structures/views.py

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import StructureType
from .sql_executor import SQLExecutor


class StructureTypeListView(ListView):
    """Список доступных типов структур"""
    model = StructureType
    template_name = 'structures/type_list.html'
    context_object_name = 'types'
    queryset = StructureType.objects.filter(is_created=True)


class DynamicRecordListView(ListView):
    """Список записей в динамической таблице"""
    template_name = 'structures/record_list.html'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(StructureType, code=self.kwargs['type_code'], is_created=True)
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        result = SQLExecutor.get_all(self.structure_type, limit=self.paginate_by)
        return result.get('records', []) if result['success'] else []
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        context['fields'] = self.structure_type.fields.all()
        return context


class DynamicRecordCreateView(CreateView):
    """Создание записи"""
    template_name = 'structures/record_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(StructureType, code=self.kwargs['type_code'], is_created=True)
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        context['fields'] = self.structure_type.fields.all()
        return context
    
    def post(self, request, *args, **kwargs):
        data = {}
        for field in self.structure_type.fields.all():
            value = request.POST.get(field.name)
            if value:
                if field.field_type == 'BooleanField':
                    data[field.name] = value == 'on'
                elif field.field_type in ['IntegerField', 'DecimalField']:
                    data[field.name] = float(value) if '.' in value else int(value)
                else:
                    data[field.name] = value
        
        data['created_by'] = request.user.username if request.user.is_authenticated else 'anonymous'
        
        result = SQLExecutor.insert(self.structure_type, data)
        
        if result['success']:
            messages.success(request, 'Запись успешно создана')
            return redirect('structures:record_detail', type_code=self.structure_type.code, pk=result['id'])
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
            return redirect('structures:record_create', type_code=self.structure_type.code)


class DynamicRecordDetailView(DetailView):
    """Детальный просмотр записи"""
    template_name = 'structures/record_detail.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(StructureType, code=self.kwargs['type_code'], is_created=True)
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        result = SQLExecutor.get_by_id(self.structure_type, self.kwargs['pk'])
        return result.get('record') if result['success'] else None
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        context['fields'] = self.structure_type.fields.all()
        return context


class DynamicRecordUpdateView(UpdateView):
    """Редактирование записи"""
    template_name = 'structures/record_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(StructureType, code=self.kwargs['type_code'], is_created=True)
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        result = SQLExecutor.get_by_id(self.structure_type, self.kwargs['pk'])
        return result.get('record') if result['success'] else None
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        context['fields'] = self.structure_type.fields.all()
        context['is_update'] = True
        return context
    
    def post(self, request, *args, **kwargs):
        data = {}
        for field in self.structure_type.fields.all():
            value = request.POST.get(field.name)
            if value:
                if field.field_type == 'BooleanField':
                    data[field.name] = value == 'on'
                elif field.field_type in ['IntegerField', 'DecimalField']:
                    data[field.name] = float(value) if '.' in value else int(value)
                else:
                    data[field.name] = value
        
        result = SQLExecutor.update(self.structure_type, self.kwargs['pk'], data)
        
        if result['success']:
            messages.success(request, 'Запись успешно обновлена')
            return redirect('structures:record_detail', type_code=self.structure_type.code, pk=self.kwargs['pk'])
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
            return redirect('structures:record_update', type_code=self.structure_type.code, pk=self.kwargs['pk'])


class DynamicRecordDeleteView(DeleteView):
    """Удаление записи"""
    template_name = 'structures/record_confirm_delete.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.structure_type = get_object_or_404(StructureType, code=self.kwargs['type_code'], is_created=True)
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        result = SQLExecutor.get_by_id(self.structure_type, self.kwargs['pk'])
        return result.get('record') if result['success'] else None
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.structure_type
        return context
    
    def post(self, request, *args, **kwargs):
        result = SQLExecutor.delete(self.structure_type, self.kwargs['pk'])
        
        if result['success']:
            messages.success(request, 'Запись успешно удалена')
            return redirect('structures:record_list', type_code=self.structure_type.code)
        else:
            messages.error(request, f'Ошибка: {result["error"]}')
            return redirect('structures:record_detail', type_code=self.structure_type.code, pk=self.kwargs['pk'])
URL маршруты
python
# apps/structures/urls.py

from django.urls import path
from . import views

app_name = 'structures'

urlpatterns = [
    # Типы структур
    path('', views.StructureTypeListView.as_view(), name='type_list'),
    
    # CRUD для динамических записей
    path('<slug:type_code>/', views.DynamicRecordListView.as_view(), name='record_list'),
    path('<slug:type_code>/create/', views.DynamicRecordCreateView.as_view(), name='record_create'),
    path('<slug:type_code>/<uuid:pk>/', views.DynamicRecordDetailView.as_view(), name='record_detail'),
    path('<slug:type_code>/<uuid:pk>/edit/', views.DynamicRecordUpdateView.as_view(), name='record_update'),
    path('<slug:type_code>/<uuid:pk>/delete/', views.DynamicRecordDeleteView.as_view(), name='record_delete'),
]
Шаблоны
django
{# templates/structures/type_list.html #}
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <h1>Типы структур</h1>
    <div class="row">
        {% for type in types %}
        <div class="col-md-4 mb-3">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">{{ type.name }}</h5>
                    <p class="card-text">{{ type.description|default:"Нет описания" }}</p>
                    <a href="{% url 'structures:record_list' type.code %}" class="btn btn-primary">
                        Перейти к записям
                    </a>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
django
{# templates/structures/record_list.html #}
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>{{ structure_type.name }}</h1>
        <a href="{% url 'structures:record_create' structure_type.code %}" class="btn btn-success">
            + Добавить
        </a>
    </div>
    
    <div class="card">
        <div class="card-body">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>ID</th>
                        {% for field in fields %}
                            <th>{{ field.label }}</th>
                        {% endfor %}
                        <th>Создано</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in object_list %}
                    <tr>
                        <td>{{ record.id|slice:":8" }}...</td>
                        {% for field in fields %}
                            <td>{{ record|get_item:field.name|default:"—" }}</td>
                        {% endfor %}
                        <td>{{ record.created_at|slice:":10" }}</td>
                        <td>
                            <a href="{% url 'structures:record_detail' structure_type.code record.id %}" class="btn btn-sm btn-info">Просмотр</a>
                            <a href="{% url 'structures:record_update' structure_type.code record.id %}" class="btn btn-sm btn-warning">Изменить</a>
                            <a href="{% url 'structures:record_delete' structure_type.code record.id %}" class="btn btn-sm btn-danger">Удалить</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
django
{# templates/structures/record_form.html #}
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <div class="card">
        <div class="card-header">
            <h2>{% if is_update %}Редактирование{% else %}Создание{% endif %}: {{ structure_type.name }}</h2>
        </div>
        <div class="card-body">
            <form method="post">
                {% csrf_token %}
                
                {% for field in fields %}
                <div class="mb-3">
                    <label class="form-label">
                        {{ field.label }}
                        {% if field.is_required %}*{% endif %}
                    </label>
                    
                    {% if field.field_type == 'BooleanField' %}
                        <div class="form-check">
                            <input type="checkbox" 
                                   name="{{ field.name }}" 
                                   class="form-check-input"
                                   {% if object and object|get_item:field.name %}checked{% endif %}>
                        </div>
                    {% else %}
                        <input type="text" 
                               name="{{ field.name }}" 
                               class="form-control"
                               value="{{ object|get_item:field.name|default:'' }}"
                               {% if field.is_required %}required{% endif %}>
                    {% endif %}
                    
                    <small class="text-muted">{{ field.get_field_type_display }}</small>
                </div>
                {% endfor %}
                
                <button type="submit" class="btn btn-primary">Сохранить</button>
                <a href="{% url 'structures:record_list' structure_type.code %}" class="btn btn-secondary">Отмена</a>
            </form>
        </div>
    </div>
</div>
{% endblock %}
Шаблонный фильтр для доступа к значениям
python
# apps/structures/templatetags/structures_extras.py

from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Возвращает значение из словаря по ключу"""
    if dictionary is None:
        return None
    return dictionary.get(key, '')
Подключение в settings.py
python
# config/settings.py

INSTALLED_APPS = [
    # ...
    'structures',
]

TEMPLATES = [
    {
        'OPTIONS': {
            'context_processors': [...],
            'libraries': {
                'structures_extras': 'apps.structures.templatetags.structures_extras',
            }
        },
    },
]
Инструкция по миграции
bash
# 1. Создать миграции для мета-таблиц
poetry run python manage.py makemigrations structures
poetry run python manage.py migrate structures

# 2. Добавить экстеншн для UUID в PostgreSQL
psql -d your_db -c "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";"

# 3. Запустить сервер
poetry run python manage.py runserver
Инструкция для администратора
Зайти в админку /admin/

Создать новый StructureType (например: name="Сэндвич", code="sandwich", table_name="structures_sandwich")

Добавить StructureField (skin_material, core_thickness и т.д.)

Нажать кнопку "Создать таблицу" (появится в админке после сохранения)

Готово! Пользователи видят структуру в интерфейсе и могут добавлять записи

Проверка работоспособности
bash
# Проверить, что таблица создана
psql -d your_db -c "\dt structures_*"

# Проверить через Python
poetry run python manage.py shell
>>> from apps.structures.models import StructureType
>>> from apps.structures.sql_executor import SQLExecutor
>>> st = StructureType.objects.get(code='sandwich')
>>> result = SQLExecutor.get_all(st)
>>> print(result['records'])