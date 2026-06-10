---
description: Django conventions — forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---
Продолжаем проект. Модели и админка готовы.

Теперь создай:

## 1. Базовые view для материалов

В apps/materials/views.py:
- MaterialListView - список всех материалов (таблица с пагинацией)
- MaterialDetailView - детальная страница материала со всеми свойствами
- MaterialCreateView - создание материала с динамическим добавлением свойств
- MaterialUpdateView - редактирование
- MaterialDeleteView - удаление

## 2. Шаблоны для материалов

В templates/materials/:
- material_list.html - таблица с колонками: код, название, дата создания, действия
- material_detail.html - карточка материала, все поля и список свойств в виде таблицы
- material_form.html - форма с полями материала + formset для свойств

## 3. URL маршруты

В apps/materials/urls.py:
```python
urlpatterns = [
    path('', MaterialListView.as_view(), name='list'),
    path('<uuid:pk>/', MaterialDetailView.as_view(), name='detail'),
    path('create/', MaterialCreateView.as_view(), name='create'),
    path('<uuid:pk>/edit/', MaterialUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', MaterialDeleteView.as_view(), name='delete'),
]
В config/urls.py добавить:

python
path('materials/', include('apps.materials.urls')),
4. Базовый шаблон
В templates/base.html:

Общий navbar со ссылками (Дашборд, Материалы, Образцы, Сканы)

Блок для контента

Подключить Bootstrap 5 (CDN)

5. Для работы со свойствами в форме используй inlineformset_factory
python
from django.forms import inlineformset_factory
from apps.materials.models import Material, MaterialProperty
from apps.references.models import Property

MaterialPropertyFormSet = inlineformset_factory(
    Material,
    MaterialProperty,
    fields=['property', 'value'],
    extra=3,
    can_delete=True
)
Требования
Используй class-based views

Добавь контекстные данные для свойств в DetailView

В CreateView и UpdateView используй formset

Сделай пагинацию в списке (10 материалов на страницу)

Напиши полный код.

text

## Если хочешь проще (без formset на старте):
Сделай простые CRUD view для Material без свойств. Свойства добавим позже через отдельную форму.

MaterialListView (список)

MaterialDetailView (детали)

MaterialCreateView (только поля материала)

MaterialUpdateView (редактирование)

MaterialDeleteView (удаление)

Шаблоны с Bootstrap 5.