---
description: Django conventions — models, forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---

# План: динамическое создание структур через интерфейс

## Цель
Создать интерфейс для администраторов, где они могут:
1. Создавать новый тип структуры (Сэндвич, Монолит, Соты и т.д.)
2. Определять поля для этого типа (название, тип данных, обязательность)
3. Автоматически создавать таблицу в БД под новую структуру
4. Пользователи заполняют структуры через динамические формы

## Архитектура

### Модели для метаданных

```python
# apps/structures/models.py

class StructureType(models.Model):
    """Тип структуры (Сэндвич, Монолит...)"""
    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


class StructureField(models.Model):
    """Поле для конкретного типа структуры"""
    FIELD_TYPES = [
        ('CharField', 'Строка'),
        ('TextField', 'Текст'),
        ('IntegerField', 'Целое число'),
        ('DecimalField', 'Десятичная дробь'),
        ('FloatField', 'Число с плавающей точкой'),
        ('BooleanField', 'Да/Нет'),
        ('DateField', 'Дата'),
        ('DateTimeField', 'Дата и время'),
        ('ForeignKey', 'Связь с другой моделью'),
    ]
    
    structure_type = models.ForeignKey(StructureType, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField(max_length=100)  # snake_case
    label = models.CharField(max_length=200)  # Для отображения
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=500, blank=True)
    help_text = models.CharField(max_length=500, blank=True)
    sort_order = models.IntegerField(default=0)
    
    # Параметры для DecimalField
    max_digits = models.IntegerField(null=True, blank=True)
    decimal_places = models.IntegerField(null=True, blank=True)
    
    # Параметры для CharField
    max_length = models.IntegerField(null=True, blank=True)
    
    # Для ForeignKey
    foreign_key_model = models.CharField(max_length=200, blank=True)
    
    class Meta:
        ordering = ['sort_order']
        unique_together = ['structure_type', 'name']
    
    def __str__(self):
        return f"{self.structure_type.name}.{self.name}"


class StructureInstance(models.Model):
    """Экземпляр конкретной структуры (создаётся пользователем)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    structure_type = models.ForeignKey(StructureType, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.structure_type.name}: {self.code}"


class StructureFieldValue(models.Model):
    """Значение поля для экземпляра структуры"""
    instance = models.ForeignKey(StructureInstance, on_delete=models.CASCADE, related_name='values')
    field = models.ForeignKey(StructureField, on_delete=models.CASCADE)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    value_integer = models.IntegerField(null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_fk_id = models.UUIDField(null=True, blank=True)
    
    class Meta:
        unique_together = ['instance', 'field']
    
    def get_value(self):
        field = self.field
        if field.field_type in ['CharField', 'TextField']:
            return self.value_text
        elif field.field_type in ['IntegerField']:
            return self.value_integer
        elif field.field_type in ['DecimalField', 'FloatField']:
            return self.value_number
        elif field.field_type == 'BooleanField':
            return self.value_boolean
        elif field.field_type == 'DateField':
            return self.value_date
        elif field.field_type == 'DateTimeField':
            return self.value_datetime
        return None
Генератор моделей (management команда)
python
# apps/structures/management/commands/generate_structure_model.py

import os
from django.core.management.base import BaseCommand
from django.apps import apps

class Command(BaseCommand):
    help = 'Генерирует Django модель для существующего типа структуры'
    
    def add_arguments(self, parser):
        parser.add_argument('structure_type_id', type=int)
    
    def handle(self, *args, **options):
        structure_type = StructureType.objects.get(id=options['structure_type_id'])
        
        # Генерируем код модели
        model_code = self.generate_model_code(structure_type)
        
        # Сохраняем в файл
        models_path = 'apps/structures/generated_models.py'
        with open(models_path, 'a') as f:
            f.write(model_code)
        
        # Создаём миграцию
        os.system('python manage.py makemigrations structures')
        os.system('python manage.py migrate')
        
        self.stdout.write(self.style.SUCCESS(f'Модель {structure_type.code} создана'))
    
    def generate_model_code(self, structure_type):
        fields = structure_type.fields.all()
        field_definitions = []
        
        for field in fields:
            if field.field_type == 'CharField':
                field_definitions.append(f"    {field.name} = models.CharField(max_length={field.max_length or 200})")
            elif field.field_type == 'DecimalField':
                field_definitions.append(f"    {field.name} = models.DecimalField(max_digits={field.max_digits or 10}, decimal_places={field.decimal_places or 2})")
            elif field.field_type == 'BooleanField':
                field_definitions.append(f"    {field.name} = models.BooleanField(default=False)")
            # ... остальные типы
        
        return f"""
class {structure_type.code.capitalize()}Structure(models.Model):
    structure_instance = models.OneToOneField(StructureInstance, on_delete=models.CASCADE)
{chr(10).join(field_definitions)}
    
    class Meta:
        db_table = 'structures_{structure_type.code.lower()}'
"""
Админка для управления структурами
python
# apps/structures/admin.py

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

class StructureFieldInline(admin.TabularInline):
    model = StructureField
    extra = 1
    fields = ['name', 'label', 'field_type', 'is_required', 'sort_order']

@admin.register(StructureType)
class StructureTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at', 'generate_model_button']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    inlines = [StructureFieldInline]
    
    def generate_model_button(self, obj):
        url = reverse('admin:generate_structure_model', args=[obj.id])
        return format_html('<a class="button" href="{}">Сгенерировать модель</a>', url)
    generate_model_button.short_description = 'Действие'

@admin.register(StructureInstance)
class StructureInstanceAdmin(admin.ModelAdmin):
    list_display = ['code', 'structure_type', 'created_at']
    search_fields = ['code']
    list_filter = ['structure_type']
Динамическая форма для пользователя
python
# apps/structures/forms.py

from django import forms
from .models import StructureType, StructureInstance, StructureFieldValue

def get_dynamic_form(structure_type):
    """Генерирует форму для конкретного типа структуры"""
    
    class DynamicStructureForm(forms.ModelForm):
        class Meta:
            model = StructureInstance
            fields = ['code']
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            
            for field in structure_type.fields.all():
                field_name = f'field_{field.id}'
                
                if field.field_type == 'CharField':
                    self.fields[field_name] = forms.CharField(
                        label=field.label,
                        required=field.is_required,
                        help_text=field.help_text,
                        initial=field.default_value
                    )
                elif field.field_type == 'DecimalField':
                    self.fields[field_name] = forms.DecimalField(
                        label=field.label,
                        required=field.is_required,
                        help_text=field.help_text
                    )
                # ... остальные типы
        
        def save(self, commit=True):
            instance = super().save(commit)
            
            for field in structure_type.fields.all():
                value = self.cleaned_data.get(f'field_{field.id}')
                field_value, created = StructureFieldValue.objects.get_or_create(
                    instance=instance,
                    field=field,
                    defaults={'value_text': str(value) if value else ''}
                )
                if not created:
                    field_value.value_text = str(value) if value else ''
                    field_value.save()
            
            return instance
    
    return DynamicStructureForm
View для пользователя
python
# apps/structures/views.py

from django.views.generic import CreateView, ListView, DetailView
from .models import StructureType, StructureInstance
from .forms import get_dynamic_form

class StructureTypeSelectView(ListView):
    """Выбор типа структуры"""
    model = StructureType
    template_name = 'structures/select_type.html'
    context_object_name = 'types'

class DynamicStructureCreateView(CreateView):
    """Создание структуры с динамической формой"""
    model = StructureInstance
    template_name = 'structures/dynamic_form.html'
    
    def get_form_class(self):
        structure_type = StructureType.objects.get(code=self.kwargs['type_code'])
        return get_dynamic_form(structure_type)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = StructureType.objects.get(code=self.kwargs['type_code'])
        return context
URL маршруты
python
# apps/structures/urls.py

urlpatterns = [
    path('', StructureTypeSelectView.as_view(), name='select_type'),
    path('create/<slug:type_code>/', DynamicStructureCreateView.as_view(), name='create'),
]
Требования к реализации
Никакого JSON — только реляционная модель

Динамические формы — генерируются на основе метаданных

Валидация — на основе параметров полей

Админка — полное управление типами и полями

Миграции — автоматическое создание моделей через management команду

Проверка
Администратор может создать тип "Сэндвич" с полями (skin_thickness, core_material)

Пользователь видит форму с этими полями

Данные сохраняются в StructureInstance + StructureFieldValue

Можно сгенерировать полноценную Django модель с таблицей

Команды для запуска
bash
# Создать новый тип структуры
poetry run python manage.py shell
>>> from apps.structures.models import StructureType
>>> st = StructureType.objects.create(name='Сэндвич', code='sandwich')

# Добавить поля через админку
# Затем сгенерировать модель
poetry run python manage.py generate_structure_model 1