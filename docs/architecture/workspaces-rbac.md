# Workspaces и RBAC

ADR для пространств (workspaces), групп с правами и авторизации в Materials DB.

**Статус:** в реализации (ветка `feature/rbac-workspaces`).

**Связанные документы:** [Architecture index](index.md) · [Tech stack](tech-stack.md) · [Права пользователей (таблицы)](workspaces-permissions.md)

## Решения

| Вопрос | Решение |
|--------|---------|
| Кто создаёт workspace | Только **admin** (`is_superuser`) |
| Участники workspace | Группы с настраиваемым набором codename; пользователь в нескольких группах |
| Эффективные права | Union permissions всех групп пользователя в WS |
| CRUD групп | `workspace.manage_settings` |
| Назначение в группы | `workspace.manage_members` + правила делегирования (`can_assign_group`) |
| Опубликованные Material в чужом WS | Только **read**; edit/delete в `home_workspace` |
| Миграция prod | Workspace **Legacy**; встроенные группы; пользователи в «Менеджер» |

## Модели

### Workspace

- `id` (UUID), `slug`, `name`, `description`, `is_active`, `created_at`

### WorkspaceGroup

- `workspace`, `name`, `description`, `permissions` (JSON list of codenames), `is_builtin`
- Unique `(workspace, name)`

### WorkspaceGroupMembership

- `group`, `user`
- Unique `(group, user)`

Участник пространства = есть хотя бы одна membership в группе этого WS.

### Visibility (Material)

- `home_workspace`, `visibility_mode`, `published_workspaces` — без изменений

### Workspace-bound

- `Tag`, `Sample`, `ScanRecord`, attachments → `workspace` FK

### Global

- `Property`, `PropertyGroup`, `StructureType` — без workspace

## Проверка прав

`has_workspace_perm(user, workspace, codename)` → union групп или admin bypass.

Встроенные шаблоны: `DEFAULT_GROUP_PERMISSIONS['manager']`, `['operator']` в `permissions.py`.

## UI

Sidebar — раздел **Пространство**: Настройки, Участники (по codename).

Sidebar — раздел **Администрирование**: Пользователи, Пространства (admin); **Группы** (`manage_settings`).

Session: `active_workspace_id`.

## Миграция Legacy

Команда `migrate_to_workspaces`:

1. Workspace `legacy`
2. Привязка данных к legacy
3. `ensure_default_groups` + назначение всех пользователей в группу «Менеджер»

Data migration `0004_workspace_groups`: `WorkspaceMembership` → группы «Менеджер»/«Оператор».

## Фазы

| Фаза | Содержание |
|------|------------|
| 0–4 | Базовый RBAC, scoping, publication |
| 5 | Admin UI, groups, multi-group members |
| 6 | API KeenetiX (отложено) |
