# Deployment

Production deployment with Dokploy and Docker Compose.

## Overview

| Concern | Tool |
|---------|------|
| Build Docker images | **Dokploy** |
| Run containers | **Dokploy** (Docker Compose mode) |
| Automated tests | **GitLab CI** (test stage only) |
| Database | PostgreSQL service in Dokploy |
| File storage | SeaweedFS or other S3-compatible service |

GitLab CI does **not** build or deploy this project — see [`.gitlab-ci.yml`](../../.gitlab-ci.yml).

## Production Compose File

[`docker-compose.prod.yml`](../../docker-compose.prod.yml):

* `web` — Gunicorn, image from `WEB_IMAGE` or local build tag
* `nginx` — reverse proxy, static files
* No bundled Postgres/S3 — connect to external Dokploy services via internal hostnames

Optional build overlay: [`docker-compose.prod.build.yml`](../../docker-compose.prod.build.yml).

## Environment on Server

```bash
cp .env.prod.example .env
# edit SECRET_KEY, DB_*, AWS_*, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
```

Critical points from [`.env.prod.example`](../../.env.prod.example):

* `DB_HOST` — internal Dokploy hostname for Postgres, **not** public IP
* `AWS_S3_ENDPOINT_URL` — internal SeaweedFS URL (e.g. `http://seaweedfs:8333`)
* Do not use `DATABASE_URL` or `DJANGO_*` variables

Generate secret key:

```powershell
poetry run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Dokploy Setup (Summary)

1. **Postgres** — create database `materials_db`, user, password
2. **SeaweedFS** (optional separate compose) — [`docker-compose.storage.yml`](../../docker-compose.storage.yml) + `.env.storage.example`
3. **Application service** — Add Service → Docker Compose → point to repo `docker-compose.prod.yml`
4. **Environment** — paste `.env` contents in Dokploy UI
5. **Domain** — map to `nginx:80`
6. **Deploy** — Dokploy builds/pulls images and starts stack
7. **First run** — exec migrate and createsuperuser in web container

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## HTTPS

When terminating TLS at reverse proxy:

* Set `CSRF_TRUSTED_ORIGINS=https://your-domain`
* `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`
* Optionally `SECURE_SSL_REDIRECT=true`

`SECURE_PROXY_SSL_HEADER` is enabled when `DEBUG=False`.

## Large File Uploads

Gunicorn timeout defaults to 3600 s in prod env — required for multi-GB HDF5 scans.

Nginx client body size may need tuning in [`deploy/nginx/nginx.conf`](../../deploy/nginx/nginx.conf) if uploads exceed default limit.

## Standalone Storage Stack

Deploy SeaweedFS separately:

```powershell
docker compose -f docker-compose.storage.yml --env-file .env.storage.example up -d
```

Share bucket name and credentials with app `.env`.

## Rollback

Dokploy keeps deployment history — redeploy previous successful build from UI.

Database and S3 data are external; rolling back app container does not revert DB migrations automatically. Plan migrations carefully.

## Related

* [Configuration](../configuration/index.md)
* [Environment reference](../configuration/environment.md)
