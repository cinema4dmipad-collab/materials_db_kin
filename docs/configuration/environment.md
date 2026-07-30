# Environment Reference

Variables read by [`config/settings.py`](../../config/settings.py) and Docker Compose.

Copy from [`.env.example`](../../.env.example) or [`.env.prod.example`](../../.env.prod.example).

## Database

| Variable | Default (example) | Description |
|----------|-------------------|-------------|
| `DB_ENGINE` | `postgresql` | `postgresql` or empty for SQLite |
| `DB_NAME` | `materials_db` | PostgreSQL database name |
| `DB_USER` | `materials` | PostgreSQL user |
| `DB_PASSWORD` | — | PostgreSQL password |
| `DB_HOST` | `localhost` / `postgres` | Hostname (`postgres` in compose) |
| `DB_PORT` | `5432` | Port |
| `DB_WAIT_TIMEOUT` | `60` | Seconds to wait for DB in entrypoint |

## Backups

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_DIR` | `<BASE_DIR>/backups` / `/backups` in Docker | Directory for scheduled Postgres dumps |

See [`deploy/BACKUP.md`](../../deploy/BACKUP.md). Only PostgreSQL is backed up; SeaweedFS is not.

## Django

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Required when `DEBUG=False` |
| `DEBUG` | `False` | `True` for local development |
| `IMPORT_BATCH_UNDO` | same as `DEBUG` | Show «удалить результат последнего импорта». On staging set `true` without full `DEBUG` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `CSRF_TRUSTED_ORIGINS` | — | Comma-separated origins with scheme |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` with HTTPS |
| `CSRF_COOKIE_SECURE` | `false` | Set `true` with HTTPS |
| `SECURE_SSL_REDIRECT` | `false` | Force HTTPS redirect |
| `LOG_LEVEL` | `INFO` | Root log level hint |

## Gunicorn

Used in production container entrypoint ([`deploy/entrypoint.sh`](../../deploy/entrypoint.sh)):

| Variable | Default | Description |
|----------|---------|-------------|
| `GUNICORN_BIND` | `0.0.0.0:8000` | Listen address |
| `GUNICORN_WORKERS` | `2` | Worker processes |
| `GUNICORN_THREADS` | `1` | Threads per worker |
| `GUNICORN_TIMEOUT` | `3600` | Worker timeout (large HDF5 uploads) |
| `GUNICORN_GRACEFUL_TIMEOUT` | `3600` | Graceful shutdown |
| `GUNICORN_KEEPALIVE` | `5` | Keep-alive |
| `GUNICORN_LOG_LEVEL` | `info` | Gunicorn log level |

## S3 / Object Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_S3` | auto from bucket | Enable S3 backend |
| `AWS_ACCESS_KEY_ID` | — | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | — | S3 secret key |
| `AWS_STORAGE_BUCKET_NAME` | `materials-db` | Bucket name |
| `AWS_S3_ENDPOINT_URL` | `http://localhost:8333` | S3 API URL |
| `AWS_S3_REGION_NAME` | `us-east-1` | Region (required by boto3) |
| `AWS_S3_ADDRESSING_STYLE` | `path` | Path-style for SeaweedFS |
| `AWS_S3_VERIFY` | auto | TLS certificate verification |

## Docker Compose (local)

| Variable | Default | Description |
|----------|---------|-------------|
| `NGINX_HTTP_PORT` | `80` | Host port for nginx |
| `SEAWEEDFS_S3_PORT` | `8333` | Host port for S3 API |
| `SEAWEEDFS_FILER_PORT` | `8888` | Host port for SeaweedFS filer UI |

## Docker Build (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHON_IMAGE` | `python:3.13-slim-bookworm` | Base image for Dockerfile |
| `PIP_INDEX_URL` | — | PyPI mirror |
| `PIP_TRUSTED_HOST` | — | Trusted host for mirror |
| `PIP_MIRROR_URLS` | — | Fallback mirrors list |

## Production Images (Dokploy)

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_IMAGE` | `materials-db-web:prod` | Web container image tag |
| `NGINX_IMAGE` | — | Nginx image tag in prod compose |

## CI (GitLab)

Set in [`.gitlab-ci.yml`](../../.gitlab-ci.yml), not in `.env`:

| Variable | Value | Description |
|----------|-------|-------------|
| `SECRET_KEY` | test key | CI test runs |
| `DEBUG` | `True` | CI test runs |
| `USE_S3` | `false` | Disable S3 in CI |
| `DB_ENGINE` | empty | SQLite in default test job |

## Variables NOT Supported

Do not use — application ignores them:

* `DATABASE_URL`
* `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_SETTINGS_MODULE`

WSGI defaults to `config.settings` via [`config/wsgi.py`](../../config/wsgi.py).
