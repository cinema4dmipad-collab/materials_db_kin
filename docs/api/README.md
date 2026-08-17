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
| GET | `/api/v1/scans/options/` | `scan.view` (методы `echo`/`shadow`/`immersion` и поля превью для диалога KeenetiX) |
| GET | `/api/v1/scans/{id}/` | `scan.view` |
| PUT | `/api/v1/scans/{id}/` | `scan.edit` (multipart: обязательный `file`, optional `preview` / `preview_b_xz` / `preview_b_yz`, `title`/`method`/`description`/`tag_names`; замена HDF5/превью в KeenetiX «Обновить скан») |
| GET | `/api/v1/scans/{id}/download/` | `scan.view` (stream HDF5; **503** if S3/SeaweedFS unreachable) |
| GET | `/api/v1/scans/{id}/preview/` | `scan.view` (inline C-scan; `preview_url` в JSON указывает сюда, не напрямую в S3) |
| GET | `/api/v1/scans/{id}/preview/{kind}/` | `scan.view` (`kind`: `c`, `b-xz`, `b-yz`) |
| POST | `/api/v1/samples/{id}/scans/` | `scan.create` (multipart: `file`, optional `preview` / `preview_b_xz` / `preview_b_yz`, `title`/`method`/`description`/`tag_names`; `X-Client: KeenetiX` → тег `источник::KeenetiX`). Перед POST KeenetiX показывает название и метод; в ответе `preview_url`, `preview_b_xz_url`, `preview_b_yz_url`. |

Пагинация: `limit` (1–200, default 50), `offset`.  
Фильтры: `material_id` у samples, `sample_id` у scans, `search` у samples (подстрока по `code` / `name` / `description`, без учёта регистра).

## Postman

Импорт: [`postman/Materials_DB_API_v1.postman_collection.json`](postman/Materials_DB_API_v1.postman_collection.json).

1. Variables: `baseUrl`, **`apiToken`** (обязательно; не поле Auth коллекции — так Postman не блокирует импорт Vault’ом). `workspaceId` можно не заполнять — подставится из `01 Workspaces`.
2. **Collection Runner → Persist responses → Run**. Папки: `happy_path` и `bad_requests` (401/400/404). В Failed — пояснение во втором аргументе `pm.expect`.
3. На 4xx/5xx тело ответа пишется в Console Runner.
4. Create scan опционален: выберите `.h5` в form-data или отключите шаг; без файла — 400/422.

## Клиент KeenetiX

Для агентов/разработки в репозитории KeenetiX:  
`KeenetiX/docs/integrations/materials-db-api.md` + правило `.cursor/rules/materials-db-api.mdc`.

Перед `POST /api/v1/samples/{id}/scans/` клиент показывает диалог: название, метод (эхо / теневой / иммерсивный), описание и три превью. Справочник полей — `GET /api/v1/scans/options/`. Те же поля уходят в multipart вместе с HDF5; запись в БД создаётся одним запросом.

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
