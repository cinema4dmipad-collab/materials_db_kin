В проекте используются Bootstrap 5, но стили не отображаются. 

Проверь и исправь:

1. В templates/base.html подключены ли CDN ссылки на Bootstrap:
```html
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
Если нет — добавь их в <head> и перед </body>

Убедись, что все шаблоны наследуются от base.html:

django
{% extends 'base.html' %}
Добавь контейнеры и классы Bootstrap в шаблоны:

django
<div class="container mt-4">
    <div class="card">
        <div class="card-header">
            <h1>Заголовок</h1>
        </div>
        <div class="card-body">
            <table class="table table-striped table-hover">
                ...
            </table>
        </div>
    </div>
</div>
Проверь, что в config/settings.py есть:

python
STATIC_URL = 'static/'
Если нужно, добавь явную очистку кеша браузера (Ctrl+Shift+R)

Исправь все шаблоны, где отсутствуют Bootstrap классы.

text

## Или короче:
Bootstrap 5 не работает. Добавь CDN ссылки в base.html и Bootstrap классы во все шаблоны (container, card, table, btn).

text

## Проверь сам вручную:

Открой `templates/base.html` — там должно быть:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}База композитов{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="{% url 'core:dashboard' %}">База композитов</a>
            <div class="collapse navbar-collapse">
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'materials:list' %}">Материалы</a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>
    
    <main class="container mt-4">
        {% block content %}{% endblock %}
    </main>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>