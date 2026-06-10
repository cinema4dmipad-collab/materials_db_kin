 IMPLEMENT_SCHEMA_PLAN.md
# План: реализация связей между Material и динамическими структурами

## Цель
Связать модель Material с динамическими таблицами структур через StructureType.

## Архитектура

### Связи
StructureType (метаданные)
├── id
├── name ("Сэндвич")
├── code ("sandwich")
├── table_name ("structures_sandwich") ← имя таблицы в БД
└── is_created

Material (материалы)
├── id
├── code
├── name
├── struct_type → FK(StructureType) ← какой тип структуры
├── struct_props_id (UUID) ← ID записи в динамической таблице
└── created_at

Динамическая таблица (structures_sandwich)
├── id (UUID)
├── skin_material (VARCHAR)
├── core_thickness (DECIMAL)
└── created_at

text

## Что нужно реализовать

### 1. Обновить модель Material

В `apps/materials/models.py` добавить:

```python
from django.db import models
from apps.structures.models import StructureType
import uuid

class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Связь с типом структуры
    struct_type = models.ForeignKey(
        StructureType, 
        on_delete=models.PROTECT,
        null=True, 
        blank=True,
        related_name='materials',
        verbose_name="Тип структуры"
    )
    
    # Ссылка на запись в динамической таблице
    struct_props_id = models.UUIDField(
        null=True, 
        blank=True,
        verbose_name="ID параметров структуры"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_structure_params(self):
        """
        Возвращает параметры структуры из динамической таблицы
        """
        if not self.struct_type or not self.struct_props_id:
            return None
        
        from django.db import connection
        table_name = self.struct_type.table_name
        
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name} WHERE id = %s", [self.struct_props_id])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            
            if row:
                return dict(zip(columns, row))
        return None
    
    class Meta:
        ordering = ['code']
2. Добавить SQLExecutor методы для работы с динамическими таблицами
В apps/structures/sql_executor.py добавить:

python
@staticmethod
def get_structure_instances(structure_type: StructureType) -> list:
    """
    Возвращает все записи из динамической таблицы структуры
    """
    if not structure_type.is_created:
        return []
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id, * FROM {structure_type.table_name} ORDER BY created_at DESC")
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        return []

@staticmethod
def get_structure_instance(structure_type: StructureType, instance_id: str) -> dict:
    """
    Возвращает одну запись из динамической таблицы
    """
    if not structure_type.is_created:
        return None
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {structure_type.table_name} WHERE id = %s", [instance_id])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None
    except Exception as e:
        return None
3. Обновить админку Material
В apps/materials/admin.py:

python
from django.contrib import admin
from django import forms
from django.shortcuts import render
from django.urls import path
from .models import Material
from apps.structures.models import StructureType
from apps.structures.sql_executor import SQLExecutor


class MaterialForm(forms.ModelForm):
    """Форма с динамическим выбором параметров структуры"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Если выбран тип структуры, подгружаем доступные экземпляры
        struct_type = self.initial.get('struct_type') or self.data.get('struct_type')
        
        if struct_type:
            try:
                st = StructureType.objects.get(id=struct_type)
                if st.is_created:
                    instances = SQLExecutor.get_structure_instances(st)
                    choices = [('', '---------')] + [(inst['id'], inst.get('code', inst['id'][:8])) for inst in instances]
                    self.fields['struct_props_id'].widget = forms.Select(choices=choices)
            except StructureType.DoesNotExist:
                pass
    
    class Meta:
        model = Material
        fields = ['code', 'name', 'description', 'struct_type', 'struct_props_id']
        widgets = {
            'struct_props_id': forms.Select(attrs={'class': 'form-select'}),
        }


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    form = MaterialForm
    list_display = ['code', 'name', 'struct_type', 'created_at']
    list_filter = ['struct_type', 'created_at']
    search_fields = ['code', 'name']
    readonly_fields = ['struct_props_preview']
    
    def struct_props_preview(self, obj):
        """Показывает параметры структуры в админке"""
        if obj.struct_type and obj.struct_props_id:
            params = obj.get_structure_params()
            if params:
                # Показываем первые 3 параметра
                preview = []
                for key, value in list(params.items())[:3]:
                    if key not in ['id', 'created_at', 'created_by', 'updated_at']:
                        preview.append(f"{key}: {value}")
                return ', '.join(preview)
        return '-'
    struct_props_preview.short_description = "Параметры структуры"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ajax/load-structure-instances/', self.load_structure_instances, name='load_structure_instances'),
        ]
        return custom_urls + urls
    
    def load_structure_instances(self, request):
        """AJAX: подгружает экземпляры структур при выборе типа"""
        import json
        from django.http import JsonResponse
        
        structure_type_id = request.GET.get('structure_type_id')
        if structure_type_id:
            try:
                st = StructureType.objects.get(id=structure_type_id)
                if st.is_created:
                    instances = SQLExecutor.get_structure_instances(st)
                    options = [{'id': inst['id'], 'name': inst.get('code', inst['id'][:8])} for inst in instances]
                    return JsonResponse({'instances': options})
            except StructureType.DoesNotExist:
                pass
        
        return JsonResponse({'instances': []})
4. JavaScript для динамической загрузки
Создать static/admin/js/dynamic_structure.js:

javascript
(function($) {
    $(document).ready(function() {
        // Отслеживаем изменение типа структуры
        $('#id_struct_type').change(function() {
            var structureTypeId = $(this).val();
            var $propsSelect = $('#id_struct_props_id');
            
            if (structureTypeId) {
                // Очищаем текущие опции
                $propsSelect.empty();
                $propsSelect.append('<option value="">Загрузка...</option>');
                
                // Загружаем экземпляры через AJAX
                $.get('/admin/materials/material/ajax/load-structure-instances/', {
                    structure_type_id: structureTypeId
                }, function(data) {
                    $propsSelect.empty();
                    $propsSelect.append('<option value="">---------</option>');
                    if (data.instances && data.instances.length > 0) {
                        $.each(data.instances, function(index, instance) {
                            $propsSelect.append('<option value="' + instance.id + '">' + instance.name + '</option>');
                        });
                    } else {
                        $propsSelect.append('<option value="">Нет доступных структур</option>');
                    }
                });
            } else {
                $propsSelect.empty();
                $propsSelect.append('<option value="">Сначала выберите тип структуры</option>');
            }
        });
    });
})(django.jQuery);
5. Добавить JavaScript в админку
В apps/materials/admin.py:

python
class Media:
    js = ['admin/js/dynamic_structure.js']
6. Миграция
bash
poetry run python manage.py makemigrations materials
poetry run python manage.py migrate materials
Проверка
Зайти в админку /admin/materials/material/add/

Выбрать тип структуры (например, "Сэндвич")

Появится выпадающий список с доступными экземплярами структур

Выбрать нужный экземпляр

Сохранить материал

Проверить, что в списке материалов отображаются параметры структуры

Что ещё нужно
В StructureTypeAdmin добавить ссылку на создание структуры

В StructureTypeAdmin добавить кнопку "Посмотреть все экземпляры"

Добавить возможность создавать экземпляр структуры прямо из формы материала

Дополнительные улучшения (опционально)
Добавить валидацию: struct_props_id должен существовать в динамической таблице

Добавить каскадное удаление: при удалении структуры обнулять struct_props_id у материалов

Добавить отображение параметров структуры в карточке материала