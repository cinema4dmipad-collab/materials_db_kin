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

При стандартном деплое Dokploy клонирует git-репозиторий; Dockerfile читает `.git/HEAD` из build context.

### Проверка после деплоя

```bash
docker exec <web-container> cat /app/BUILD_COMMIT
```

В логах сборки web должно быть: `Recorded BUILD_COMMIT=abc1234`

### Если hash пустой или в логах `#21 CACHED` со старым Dockerfile

Docker взял **закэшированный слой** из прошлой сборки (без hash). Нужна пересборка **без кэша**:

**Вариант A — переменная в Environment Dokploy** (Command оставить пустым):

```env
BUILD_CACHE_BUST=2
```

Увеличивайте число после каждой принудительной пересборки. Deploy с rebuild.

**Вариант B — одноразово в Command** (полная команда, `<appName>` — имя сервиса в Dokploy):

```text
compose -p <appName> -f docker-compose.prod.yml build --no-cache web && compose -p <appName> -f docker-compose.prod.yml up -d --remove-orphans
```

После успешной сборки **очистите Command** снова.

**Вариант C — SSH на сервер:**

```bash
cd /path/to/dokploy/compose/.../code
sh deploy/dokploy-deploy.sh
# или:
docker compose -p <appName> -f docker-compose.prod.yml build --no-cache web
docker compose -p <appName> -f docker-compose.prod.yml up -d
```

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
