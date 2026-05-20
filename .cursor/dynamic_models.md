## Цель
Создать интерфейс, где администратор может:
1. Создать новый тип структуры (например, "Сэндвич")
2. Определить поля (имя, тип, параметры)
3. Нажать кнопку — создать таблицу в БД
4. Пользователи видят форму с этими полями и заполняют

## Архитектура

### Модели для метаданных

```python
# apps/structures/models.py

from django.db import models
import uuid

class StructureType(models.Model):
    """Тип структуры — метаданные о таблице"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)  # "Сэндвич"
    table_name = models.CharField(max_length=100, unique=True)  # "structures_sandwich"
    is_created = models.BooleanField(default=False)  # создана ли таблица
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


class StructureField(models.Model):
    """Поле для конкретного типа структуры"""
    FIELD_TYPES = [
        ('CharField', 'Строка (CharField)'),
        ('TextField', 'Текст (TextField)'),
        ('IntegerField', 'Целое число'),
        ('FloatField', 'Число с плавающей точкой'),
        ('DecimalField', 'Десятичная дробь'),
        ('BooleanField', 'Да/Нет'),
        ('DateField', 'Дата'),
        ('DateTimeField', 'Дата и время'),
    ]
    
    structure_type = models.ForeignKey(StructureType, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100)  # snake_case
    label = models.CharField(max_length=200)  # Для отображения
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    
    # Параметры для DecimalField
    max_digits = models.IntegerField(null=True, blank=True, default=10)
    decimal_places = models.IntegerField(null=True, blank=True, default=2)
    
    # Параметры для CharField
    max_length = models.IntegerField(null=True, blank=True, default=255)
    
    class Meta:
        ordering = ['sort_order']
        unique_together = ['structure_type', 'name']
    
    def __str__(self):
        return f"{self.structure_type.name}.{self.name}"
Генератор таблиц (ядро системы)
python
# apps/structures/table_generator.py

from django.db import connection
from django.apps import apps
from django.core.management import call_command
from .models import StructureType, StructureField


class TableGenerator:
    """Класс для динамического создания таблиц"""
    
    @staticmethod
    def create_table(structure_type: StructureType):
        """Создаёт таблицу в БД для типа структуры"""
        
        # 1. Генерируем SQL CREATE TABLE
        sql = TableGenerator._generate_create_sql(structure_type)
        
        # 2. Выполняем SQL
        with connection.cursor() as cursor:
            cursor.execute(sql)
        
        # 3. Создаём Django модель динамически
        model = TableGenerator._create_django_model(structure_type)
        
        # 4. Регистрируем модель в Django apps
        apps.register_model('structures', model)
        
        # 5. Отмечаем, что таблица создана
        structure_type.is_created = True
        structure_type.save()
        
        return model
    
    @staticmethod
    def _generate_create_sql(structure_type: StructureType) -> str:
        """Генерирует SQL CREATE TABLE"""
        
        fields_sql = []
        
        # Первичный ключ
        fields_sql.append('id UUID PRIMARY KEY DEFAULT gen_random_uuid()')
        
        # Поля из структуры
        for field in structure_type.fields.all():
            field_sql = TableGenerator._field_to_sql(field)
            fields_sql.append(field_sql)
        
        # Метаполя
        fields_sql.append('created_at TIMESTAMP DEFAULT NOW()')
        fields_sql.append('updated_at TIMESTAMP DEFAULT NOW()')
        fields_sql.append('created_by VARCHAR(100)')
        
        # Собираем CREATE TABLE
        sql = f"""
            CREATE TABLE IF NOT EXISTS {structure_type.table_name} (
                {', '.join(fields_sql)}
            )
        """
        return sql
    
    @staticmethod
    def _field_to_sql(field: StructureField) -> str:
        """Конвертирует поле в SQL определение"""
        
        null_constraint = 'NOT NULL' if field.is_required else 'NULL'
        
        type_mapping = {
            'CharField': f'VARCHAR({field.max_length})',
            'TextField': 'TEXT',
            'IntegerField': 'INTEGER',
            'FloatField': 'FLOAT',
            'DecimalField': f'DECIMAL({field.max_digits}, {field.decimal_places})',
            'BooleanField': 'BOOLEAN',
            'DateField': 'DATE',
            'DateTimeField': 'TIMESTAMP',
        }
        
        sql_type = type_mapping.get(field.field_type, 'TEXT')
        return f'{field.name} {sql_type} {null_constraint}'
    
    @staticmethod
    def _create_django_model(structure_type: StructureType):
        """Динамически создаёт Django модель для таблицы"""
        
        from django.db import models
        
        # Атрибуты модели
        attrs = {
            '__module__': 'apps.structures.dynamic_models',
            'Meta': type('Meta', (), {
                'db_table': structure_type.table_name,
                'managed': False,  # Django не будет управлять миграциями
                'app_label': 'structures'
            }),
        }
        
        # Добавляем поля
        for field in structure_type.fields.all():
            field_class = getattr(models, field.field_type)
            field_kwargs = {
                'verbose_name': field.label,
            }
            
            if field.is_required:
                field_kwargs['blank'] = False
            else:
                field_kwargs['blank'] = True
                field_kwargs['null'] = True
            
            if field.field_type == 'CharField':
                field_kwargs['max_length'] = field.max_length or 255
            
            if field.field_type == 'DecimalField':
                field_kwargs['max_digits'] = field.max_digits or 10
                field_kwargs['decimal_places'] = field.decimal_places or 2
            
            attrs[field.name] = field_class(**field_kwargs)
        
        # Создаём модель
        model = type(structure_type.table_name.capitalize(), (models.Model,), attrs)
        return model
    
    @staticmethod
    def drop_table(structure_type: StructureType):
        """Удаляет таблицу"""
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS {structure_type.table_name}')
        
        structure_type.is_created = False
        structure_type.save()
    
    @staticmethod
    def add_column(structure_type: StructureType, field: StructureField):
        """Добавляет колонку в существующую таблицу"""
        sql = f"""
            ALTER TABLE {structure_type.table_name} 
            ADD COLUMN {TableGenerator._field_to_sql(field)}
        """
        with connection.cursor() as cursor:
            cursor.execute(sql)
Админка для управления
python
# apps/structures/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import StructureType, StructureField
from .table_generator import TableGenerator


class StructureFieldInline(admin.TabularInline):
    model = StructureField
    extra = 1
    fields = ['name', 'label', 'field_type', 'is_required', 'sort_order', 
              'max_length', 'max_digits', 'decimal_places']


@admin.register(StructureType)
class StructureTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'table_name', 'is_created', 'created_at']
    list_filter = ['is_created']
    inlines = [StructureFieldInline]
    actions = ['create_table_action']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<uuid:pk>/create-table/', self.create_table_view, name='create_table'),
            path('<uuid:pk>/drop-table/', self.drop_table_view, name='drop_table'),
        ]
        return custom_urls + urls
    
    def create_table_view(self, request, pk):
        structure_type = StructureType.objects.get(pk=pk)
        
        try:
            TableGenerator.create_table(structure_type)
            messages.success(request, f'Таблица {structure_type.table_name} создана')
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
        
        return redirect('admin:structures_structuretype_changelist')
    
    def drop_table_view(self, request, pk):
        structure_type = StructureType.objects.get(pk=pk)
        
        try:
            TableGenerator.drop_table(structure_type)
            messages.success(request, f'Таблица {structure_type.table_name} удалена')
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
        
        return redirect('admin:structures_structuretype_changelist')
    
    def create_table_action(self, request, queryset):
        for st in queryset:
            TableGenerator.create_table(st)
        self.message_user(request, f'Таблицы созданы для {queryset.count()} типов')
    create_table_action.short_description = 'Создать таблицы для выбранных типов'


@admin.register(StructureField)
class StructureFieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'structure_type', 'field_type', 'is_required']
    list_filter = ['structure_type', 'field_type']
Шаблон для админки (расширение)
django
<!-- templates/admin/structures/structuretype/change_form.html -->
{% extends "admin/change_form.html" %}

{% block object-tools-items %}
    {{ block.super }}
    {% if original and not original.is_created %}
        <li>
            <a href="{% url 'admin:create_table' original.pk %}" class="button" style="background-color: #28a745; color: white;">
                🔨 Создать таблицу в БД
            </a>
        </li>
    {% endif %}
    {% if original and original.is_created %}
        <li>
            <a href="{% url 'admin:drop_table' original.pk %}" class="button" style="background-color: #dc3545; color: white;" onclick="return confirm('Удалить таблицу? Данные будут потеряны!')">
                🗑️ Удалить таблицу
            </a>
        </li>
    {% endif %}
{% endblock %}
Команда для синхронизации
python
# apps/structures/management/commands/sync_structure_tables.py

from django.core.management.base import BaseCommand
from apps.structures.models import StructureType
from apps.structures.table_generator import TableGenerator


class Command(BaseCommand):
    help = 'Создаёт таблицы для всех типов структур, у которых is_created=False'
    
    def handle(self, *args, **options):
        to_create = StructureType.objects.filter(is_created=False)
        
        for st in to_create:
            self.stdout.write(f'Создаю таблицу для {st.name}...')
            TableGenerator.create_table(st)
            self.stdout.write(self.style.SUCCESS(f'  ✅ {st.table_name}'))
        
        self.stdout.write(self.style.SUCCESS(f'Готово. Создано {to_create.count()} таблиц'))
URL для пользовательского интерфейса
python
# apps/structures/urls.py

from django.urls import path
from . import views

app_name = 'structures'

urlpatterns = [
    path('', views.StructureTypeListView.as_view(), name='type_list'),
    path('<slug:type_code>/create/', views.DynamicStructureCreateView.as_view(), name='create'),
    path('<slug:type_code>/list/', views.DynamicStructureListView.as_view(), name='list'),
    path('<slug:type_code>/<uuid:pk>/', views.DynamicStructureDetailView.as_view(), name='detail'),
]
Требования к реализации
Установить расширение PostgreSQL (для UUID):

sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
Добавить в INSTALLED_APPS:

python
'structures',
Создать и применить миграции для мета-таблиц:

bash
poetry run python manage.py makemigrations structures
poetry run python manage.py migrate structures
Проверка
Администратор создаёт тип "Сэндвич" в админке

Добавляет поля (skin_material, core_thickness)

Нажимает "Создать таблицу" → таблица появляется в БД

Пользователь видит форму с этими полями

Данные сохраняются в созданную таблицу

Команды после деплоя
bash
# Создать таблицы для всех типов
poetry run python manage.py sync_structure_tables