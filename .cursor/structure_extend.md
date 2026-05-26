---
description: Django conventions — models, forms, views
globs: apps/**/*.py,config/**/*.py
alwaysApply: false
---
## Интерфейс для пользователей (не админов)

### 1. Страница выбора типа структуры

```django
<!-- templates/structures/select_type.html -->
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <h1>Создание новой структуры</h1>
    <p>Выберите тип структуры:</p>
    
    <div class="row">
        {% for type in types %}
        <div class="col-md-4 mb-3">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">{{ type.name }}</h5>
                    <p class="card-text">{{ type.description }}</p>
                    <a href="{% url 'structures:create' type.code %}" class="btn btn-primary">
                        Создать {{ type.name }}
                    </a>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
2. Динамическая форма создания
django
<!-- templates/structures/dynamic_form.html -->
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <div class="card">
        <div class="card-header">
            <h2>Создание: {{ structure_type.name }}</h2>
        </div>
        <div class="card-body">
            <form method="post">
                {% csrf_token %}
                
                <!-- Поле code -->
                <div class="mb-3">
                    <label class="form-label">Код структуры *</label>
                    <input type="text" name="code" class="form-control" required>
                    <small class="text-muted">Уникальный идентификатор (например, SND-001)</small>
                </div>
                
                <!-- Динамические поля из StructureField -->
                {% for field in structure_type.fields.all %}
                <div class="mb-3">
                    <label class="form-label">
                        {{ field.label }}
                        {% if field.is_required %}*{% endif %}
                    </label>
                    
                    {% if field.field_type == 'CharField' %}
                        <input type="text" 
                               name="field_{{ field.id }}" 
                               class="form-control"
                               {% if field.is_required %}required{% endif %}>
                               
                    {% elif field.field_type == 'DecimalField' %}
                        <input type="number" 
                               step="0.01"
                               name="field_{{ field.id }}" 
                               class="form-control"
                               {% if field.is_required %}required{% endif %}>
                               
                    {% elif field.field_type == 'BooleanField' %}
                        <div class="form-check">
                            <input type="checkbox" 
                                   name="field_{{ field.id }}" 
                                   class="form-check-input">
                            <label class="form-check-label">Да</label>
                        </div>
                        
                    {% elif field.field_type == 'TextField' %}
                        <textarea name="field_{{ field.id }}" 
                                  class="form-control"
                                  rows="3"></textarea>
                    {% endif %}
                    
                    {% if field.help_text %}
                        <small class="text-muted">{{ field.help_text }}</small>
                    {% endif %}
                </div>
                {% endfor %}
                
                <button type="submit" class="btn btn-success">Сохранить структуру</button>
                <a href="{% url 'structures:select_type' %}" class="btn btn-secondary">Назад</a>
            </form>
        </div>
    </div>
</div>
{% endblock %}
3. Список созданных структур
django
<!-- templates/structures/list.html -->
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>Структуры</h1>
        <a href="{% url 'structures:select_type' %}" class="btn btn-primary">+ Новая структура</a>
    </div>
    
    <div class="card">
        <div class="card-body">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Код</th>
                        <th>Тип</th>
                        <th>Дата создания</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for instance in instances %}
                    <tr>
                        <td>{{ instance.code }}</td>
                        <td>{{ instance.structure_type.name }}</td>
                        <td>{{ instance.created_at|date:"d.m.Y H:i" }}</td>
                        <td>
                            <a href="{% url 'structures:detail' instance.id %}" class="btn btn-sm btn-info">Просмотр</a>
                            <a href="{% url 'structures:edit' instance.id %}" class="btn btn-sm btn-warning">Редактировать</a>
                            <a href="{% url 'structures:delete' instance.id %}" class="btn btn-sm btn-danger">Удалить</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
4. Просмотр структуры
django
<!-- templates/structures/detail.html -->
{% extends 'base.html' %}

{% block content %}
<div class="container">
    <div class="card">
        <div class="card-header">
            <h2>{{ instance.structure_type.name }}: {{ instance.code }}</h2>
        </div>
        <div class="card-body">
            <table class="table">
                <tr><th>Код</th><td>{{ instance.code }}</td></tr>
                <tr><th>Тип</th><td>{{ instance.structure_type.name }}</td></tr>
                <tr><th>Создана</th><td>{{ instance.created_at|date:"d.m.Y H:i" }}</td></tr>
            </table>
            
            <h4>Параметры:</h4>
            <table class="table table-striped">
                {% for value in instance.values.all %}
                <tr>
                    <th>{{ value.field.label }}</th>
                    <td>{{ value.get_value }}</td>
                </tr>
                {% endfor %}
            </table>
            
            <div class="mt-3">
                <a href="{% url 'structures:edit' instance.id %}" class="btn btn-warning">Редактировать</a>
                <a href="{% url 'structures:list' %}" class="btn btn-secondary">Назад</a>
            </div>
        </div>
    </div>
</div>
{% endblock %}
5. View для пользователя (дополнить)
python
# apps/structures/views.py дополнение

class StructureInstanceListView(ListView):
    """Список всех созданных структур"""
    model = StructureInstance
    template_name = 'structures/list.html'
    context_object_name = 'instances'
    paginate_by = 20

class StructureInstanceDetailView(DetailView):
    """Детальный просмотр структуры"""
    model = StructureInstance
    template_name = 'structures/detail.html'
    context_object_name = 'instance'

class StructureInstanceEditView(UpdateView):
    """Редактирование структуры"""
    model = StructureInstance
    template_name = 'structures/dynamic_form.html'
    
    def get_form_class(self):
        return get_dynamic_form(self.object.structure_type)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['structure_type'] = self.object.structure_type
        context['edit_mode'] = True
        return context
6. URL маршруты (полные)
python
# apps/structures/urls.py

urlpatterns = [
    # Выбор типа
    path('', StructureTypeSelectView.as_view(), name='select_type'),
    
    # Список и действия со структурами
    path('list/', StructureInstanceListView.as_view(), name='list'),
    path('create/<slug:type_code>/', DynamicStructureCreateView.as_view(), name='create'),
    path('<uuid:pk>/', StructureInstanceDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', StructureInstanceEditView.as_view(), name='edit'),
    path('<uuid:pk>/delete/', StructureInstanceDeleteView.as_view(), name='delete'),
]
7. Навигация в base.html
django
<!-- Добавить в меню -->
<li class="nav-item dropdown">
    <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
        Структуры
    </a>
    <ul class="dropdown-menu">
        <li><a class="dropdown-item" href="{% url 'structures:select_type' %}">Создать структуру</a></li>
        <li><a class="dropdown-item" href="{% url 'structures:list' %}">Все структуры</a></li>
    </ul>
</li>
text

## Полный сценарий для пользователя:

1. **Заходит на сайт** → видит меню "Структуры"
2. **Нажимает "Создать структуру"** → видит карточки типов (Сэндвич, Монолит)
3. **Выбирает тип** → открывается форма с нужными полями
4. **Заполняет** код и параметры → нажимает "Сохранить"
5. **Видит список** всех созданных структур
6. **Может просмотреть**, отредактировать или удалить

## Чтобы Cursor это добавил:

Скажи: