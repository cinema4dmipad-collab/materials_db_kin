# Dokploy: деплой materials-db

## Command (Run Command) — важно

Поле **Command** в Dokploy **полностью заменяет** стандартную команду и Dokploy всегда выполняет:

```bash
docker <ваш Command>
```

Поэтому **нельзя** указывать shell-скрипт:

```text
sh deploy/dokploy-deploy.sh   # ❌ станет: docker sh deploy/dokploy-deploy.sh
```

Это не запускает compose и контейнеры не поднимаются.

### Что указать в Command

**Оставьте поле пустым** — Dokploy сам выполнит:

```bash
docker compose -p <appName> -f docker-compose.prod.yml up -d --build --remove-orphans
```

Если нужны доп. флаги, укажите **полную** команду compose (не `sh ...`):

```bash
compose -p <appName> -f docker-compose.prod.yml up -d --build --remove-orphans --force-recreate
```

`<appName>` — имя Compose-сервиса в Dokploy (то же, что в логах деплоя).

## Git commit на странице /debug/

Hash записывается в образ при сборке (`/app/BUILD_COMMIT`). **GIT_COMMIT в runtime .env не нужен.**

При стандартном деплое Dokploy клонирует git-репозиторий на сервер; Dockerfile читает `.git` из build context и пишет hash автоматически.

После деплоя проверка:

```bash
docker exec <web-container> cat /app/BUILD_COMMIT
```

В логах сборки web должно быть: `Recorded BUILD_COMMIT=abc1234`

Если hash пустой — пересоберите web **без кэша** (Rebuild / `--no-cache`).

## Ручной деплой по SSH (не через поле Command)

На сервере в каталоге кода Dokploy:

```bash
sh deploy/dokploy-deploy.sh
```

Скрипт сам вызовет `docker compose` (для SSH, не для поля Command в UI).

## Скрипты

| Скрипт | Назначение |
|--------|------------|
| `deploy/dokploy-deploy.sh` | Полный деплой по SSH |
| `deploy/compose-prod.sh` | То же для локальной/ручной сборки |
| `deploy/write-build-commit.sh` | Только записать `.build-commit` на хосте |
