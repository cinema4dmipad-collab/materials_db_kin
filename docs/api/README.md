# HTTP API v1

Общий REST API (django-modern-rest) для KeenetiX и других клиентов.

## Auth

1. Войдите в веб-интерфейс → **Профиль → Токены API**.
2. Создайте токен (имя, срок жизни / бессрочный). Секрет показывается **один раз**.
3. В запросах:

```http
Authorization: Bearer <token>
X-Workspace-Id: <uuid>
```

Права = права пользователя токена в выбранном workspace (`WorkspacePerm`). Нет доступа → **404**.

`GET /api/v1/workspaces/` — без `X-Workspace-Id` (список пространств пользователя).

## Endpoints

| Method | Path | Perm |
|--------|------|------|
| GET | `/api/v1/workspaces/` | membership |
| GET | `/api/v1/materials/` | `material.view` |
| GET | `/api/v1/materials/{id}/` | `material.view` (+ properties, structure) |
| GET | `/api/v1/samples/` | `sample.view` |
| GET | `/api/v1/samples/{id}/` | `sample.view` |
| GET | `/api/v1/scans/` | `scan.view` |
| GET | `/api/v1/scans/{id}/` | `scan.view` |
| GET | `/api/v1/scans/{id}/download/` | `scan.view` (stream HDF5; **503** if S3/SeaweedFS unreachable) |
| POST | `/api/v1/samples/{id}/scans/` | `scan.create` (multipart: `file`, optional `title`/`method`/`description`/`tag_names`; заголовок `X-Client: KeenetiX` добавляет тег `источник::KeenetiX`) |

Пагинация: `limit` (1–200, default 50), `offset`.  
Фильтры: `material_id` у samples, `sample_id` у scans, `search` у samples (подстрока по `code` / `name`, без учёта регистра).

## Postman

Импорт: [`postman/Materials_DB_API_v1.postman_collection.json`](postman/Materials_DB_API_v1.postman_collection.json).

1. Variables: `baseUrl`, **`apiToken`** (обязательно; не поле Auth коллекции — так Postman не блокирует импорт Vault’ом). `workspaceId` можно не заполнять — подставится из `01 Workspaces`.
2. **Collection Runner → Persist responses → Run**. Папки: `happy_path` и `bad_requests` (401/400/404). В Failed — пояснение во втором аргументе `pm.expect`.
3. На 4xx/5xx тело ответа пишется в Console Runner.
4. Create scan опционален: выберите `.h5` в form-data или отключите шаг; без файла — 400/422.

## Клиент KeenetiX

Для агентов/разработки в репозитории KeenetiX:  
`KeenetiX/docs/integrations/materials-db-api.md` + правило `.cursor/rules/materials-db-api.mdc`.

Desktop channel: кнопка «Открыть в KeenetiX» → `POST /api/v1/desktop/open-scan/`
(сессия браузера); KeenetiX с PAT делает `connect` + polling `commands`.
Активен последний desktop с токеном этого пользователя. Протокол `keenetix://` не используется.
См. `KeenetiX/docs/integrations/materials-db-api.md` § Desktop channel.

## OpenAPI / Redoc

Сейчас **не подключены**. django-modern-rest умеет OpenAPI + Redoc/Swagger из коробки — имеет смысл включить, когда контракт v1 стабилен и нужна браузерная документация для людей/внешних интеграторов.  
Для Cursor и KeenetiX достаточно этого README + Postman + клиентского markdown в KeenetiX.

## Тесты

```bash
DB_ENGINE=sqlite poetry run python manage.py test apps.api.tests
```
