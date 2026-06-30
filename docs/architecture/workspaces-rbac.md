# Workspaces и RBAC

ADR для пространств (workspaces), ролей и авторизации в Materials DB.

**Статус:** в реализации (ветка `feature/rbac-workspaces`).

**Связанные документы:** [Architecture index](index.md) · [Tech stack](tech-stack.md) · [Права пользователей (таблицы)](workspaces-permissions.md)

## Решения

| Вопрос | Решение |
|--------|---------|
| Кто создаёт workspace | Только **admin** (`is_superuser`) |
| Опубликованные Material/Structure в чужом WS | Только **read**; edit/delete в `home_workspace` |
| Structure + dynamic SQL | Доступ через проверку Material/StructureType; прямой bypass запрещён |
| Миграция prod | Workspace **Legacy**; все данные и пользователи (role=manager) |
| Участники workspace | **Admin** создаёт пользователей и назначает **менеджеров**; **менеджер** добавляет **операторов** в своё пространство |
| Property (справочник) | Глобально, без workspace |
| StructureType | Глобально (admin); видны во всех пространствах |
| Tag | Только в своём workspace |
| API KeenetiX | Фаза 6, отдельно |

## Модели

### Workspace (`apps/workspaces/models.py`)

- `id` (UUID), `slug`, `name`, `description`, `is_active`, `created_at`

### WorkspaceMembership

- `workspace`, `user`, `role` ∈ `{manager, operator}`
- Unique `(workspace, user)`

### Visibility (Material)

- `home_workspace` — FK NOT NULL
- `visibility_mode`: `private` | `selected_workspaces` | `all_workspaces`
- `published_workspaces` — M2M (для `selected_workspaces`)

Material может быть общим по выбору владельца (publish). StructureType и Property — общие каталоги.

### Workspace-bound (жёсткая изоляция)

- `Tag`, `Sample`, `ScanRecord`, `SampleAttachment`, `MaterialAttachment` → `workspace` FK

### Global (общие каталоги)

- `Property`, `PropertyGroup` — без workspace
- `StructureType` — без ограничения по пространству; CRUD только admin

## Матрица прав

Проверка: `has_workspace_perm(user, workspace, codename)` в `apps/workspaces/permissions.py`.

| Codename | admin | manager | operator |
|----------|-------|---------|----------|
| `workspace.view` | ✓ | ✓ | ✓ |
| `workspace.manage_settings` | ✓ | ✓ | — |
| `workspace.manage_members` | ✓ | ✓ (только операторы) | — |
| `material.view` | ✓ | ✓ | ✓ |
| `material.create` | ✓ | ✓ | ✓ |
| `material.edit` | ✓ (любой WS) | ✓ (home WS) | ✓ (home WS) |
| `material.delete` | ✓ | ✓ | — |
| `material.publish` | ✓ | ✓ | — |
| `structure.view` | ✓ | ✓ | ✓ |
| `structure.create/edit/delete/publish` | ✓ | — | — |
| `sample.view/create/edit` | ✓ | ✓ | ✓ |
| `sample.delete` | ✓ | ✓ | — |
| `scan.view/create/edit` | ✓ | ✓ | ✓ |
| `scan.delete` | ✓ | ✓ | — |
| `property.view/create/edit/delete` | ✓ | ✓ | ✓ (global) |
| `user.manage` | ✓ | — | — |

Admin = `user.is_superuser`. Имеет все codename-права и может редактировать Material/StructureType в любом пространстве (не только `home_workspace`). Workspace role из `WorkspaceMembership`.

## Dynamic SQL

1. `StructureType` — общий каталог; список типов = все активные.
2. Edit/delete type — только admin (`is_superuser`).
3. `struct_props_id` — read/write только если `material.is_editable_in(active_ws)`.
4. Все views/SQLExecutor entry points — через `permissions.py`.

## UI

Верхняя navbar (как раньше): Материалы, Свойства, Теги, Структуры, Образцы, Сканы, Справка.

Sidebar слева — только пространство:

- Переключатель workspace
- Настройки WS, Участники (manager+)
- Пользователи, Создание WS (admin)

Session key: `active_workspace_id`. Без выбранного WS — redirect на `workspaces:select`.

## Миграция Legacy

Команда `migrate_to_workspaces`:

1. Создать workspace `legacy` («Legacy»)
2. `home_workspace=legacy` для Material, StructureType
3. `workspace=legacy` для Sample, Scan, attachments
4. Для каждого User → membership(role=manager)
5. `visibility_mode=all_workspaces` для существующих Material/Structure

## Фазы реализации

| Фаза | Содержание |
|------|------------|
| 0 | Этот документ |
| 1 | Login/logout, LoginRequiredMixin |
| 2 | Workspace models, middleware, sidebar, Legacy migration |
| 3 | Queryset scoping, FK, code unique per WS |
| 4 | Publication UI, read-only foreign |
| 5 | Admin UI users/membership, manager WS settings |
| 6 | API KeenetiX (отложено) |

## Зависимости

- `django.contrib.auth` — login, User
- `django-guardian` — object-level permissions (optional audit)
