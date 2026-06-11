# Configuration

Setup and configuration guide for local development and production.

## Table of Contents

- [Quick Start (Local)](#quick-start-local)
- [Environment Files](#environment-files)
- [Django Settings](#django-settings)
- [Database](#database)
- [Object Storage](#object-storage)
- [Docker Compose Profiles](#docker-compose-profiles)
- [Production (Dokploy)](#production-dokploy)
- [Troubleshooting](#troubleshooting)

## Quick Start (Local)

```powershell
cp .env.example .env
# edit SECRET_KEY, DB_PASSWORD if needed

docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Open http://localhost (nginx) or mapped port from `.env`.

Without Docker:

```powershell
poetry install
cp .env.example .env
# set DB_ENGINE=postgresql and DB_* or leave empty for SQLite
poetry run python manage.py migrate
poetry run python manage.py runserver
```

## Environment Files

| File | Purpose |
|------|---------|
| [`.env.example`](../../.env.example) | Local / Docker Compose template |
| [`.env.prod.example`](../../.env.prod.example) | Production template for Dokploy |
| [`.env.storage.example`](../../.env.storage.example) | Standalone SeaweedFS stack |

Full variable reference: [Environment Reference](environment.md).

**Important:** Settings read plain env names (`SECRET_KEY`, `DB_HOST`, …). The project does **not** use `DATABASE_URL` or `DJANGO_*` prefixed variables.

## Django Settings

Main module: [`config/settings.py`](../../config/settings.py).

Notable behaviour:

* `load_dotenv()` at startup — `.env` in project root
* `DEBUG=False` requires non-empty `SECRET_KEY`
* `USE_S3=true` requires `AWS_STORAGE_BUCKET_NAME`
* `LANGUAGE_CODE = ru-ru`, `TIME_ZONE = Europe/Moscow`
* Debug toolbar appended when `DEBUG=True`
* Large upload streaming: 10 MB in-memory threshold

## Database

Production and Docker use **PostgreSQL 16**.

| Variable | Description |
|----------|-------------|
| `DB_ENGINE` | Set to `postgresql` for Postgres; omit or empty for SQLite |
| `DB_NAME` | Database name |
| `DB_USER` / `DB_PASSWORD` | Credentials |
| `DB_HOST` / `DB_PORT` | Host and port |
| `DB_WAIT_TIMEOUT` | Entrypoint wait for DB (seconds) |

Migrations: standard Django — `python manage.py migrate`.

Dynamic structure tables are **not** Django migrations; created via UI or `sync_structure_tables` command.

## Object Storage

| Variable | Description |
|----------|-------------|
| `USE_S3` | `true` / `false` |
| `AWS_STORAGE_BUCKET_NAME` | Bucket name |
| `AWS_S3_ENDPOINT_URL` | e.g. `http://seaweedfs:8333` in Docker |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | S3 credentials |

When `USE_S3=false`, files go to `media/` under project root.

Check S3 connectivity:

```powershell
poetry run python manage.py check_s3_storage
```

## Docker Compose Profiles

| File | Use case |
|------|----------|
| [`docker-compose.yml`](../../docker-compose.yml) | Full local stack: postgres, seaweedfs, web, nginx |
| [`docker-compose.prod.yml`](../../docker-compose.prod.yml) | Production: pre-built images, external DB/S3 hostnames |
| [`docker-compose.prod.build.yml`](../../docker-compose.prod.build.yml) | Optional build section for prod images |
| [`docker-compose.storage.yml`](../../docker-compose.storage.yml) | SeaweedFS only |

## Production (Dokploy)

1. Create Postgres and SeaweedFS services in Dokploy (or use existing).
2. Add Docker Compose service pointing to `docker-compose.prod.yml`.
3. Copy `.env.prod.example` → `.env` on server; set internal hostnames for `DB_HOST` and `AWS_S3_ENDPOINT_URL`.
4. Map domain to nginx container port 80.
5. Build and redeploy via Dokploy (not GitLab CI).

See [Deployment examples](../examples/deployment.md).

## Troubleshooting

**Migrations fail on startup**
* Check Postgres is reachable; increase `DB_WAIT_TIMEOUT`
* Verify `DB_*` match Dokploy internal service names

**Upload fails / S3 errors**
* Run `check_s3_storage`
* Confirm bucket exists (seaweedfs-init in local compose creates it)
* `AWS_S3_VERIFY=false` for HTTP endpoints

**Material form: structure type disabled**
* SQL table for that type not created — open type manage page and create table

**CSRF errors behind proxy**
* Add public URL to `CSRF_TRUSTED_ORIGINS`
* Set `SECURE_PROXY_SSL_HEADER` is already configured for non-DEBUG
