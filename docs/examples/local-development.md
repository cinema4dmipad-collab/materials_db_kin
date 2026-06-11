# Local Development

Setting up Materials DB on a developer machine.

## Prerequisites

* Python 3.13+
* [Poetry](https://python-poetry.org/)
* Docker Desktop (optional, recommended for Postgres + S3)

## Option A: Docker Compose (Recommended)

```powershell
git clone <repo-url> materials_db_v1
cd materials_db_v1
cp .env.example .env
```

Edit `.env`:

* `SECRET_KEY` — random string
* `DEBUG=True` for local UI debugging
* `DB_PASSWORD` — any value consistent with compose

Start stack:

```powershell
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Services:

| Service | Port (default) |
|---------|----------------|
| nginx | 80 |
| web (Gunicorn) | internal 8000 |
| postgres | internal |
| SeaweedFS S3 | 8333 |

Logs:

```powershell
docker compose logs -f web
```

Stop:

```powershell
docker compose down
```

## Option B: Poetry + Local SQLite

Fastest path without Docker:

```powershell
poetry install
cp .env.example .env
```

In `.env` — remove or comment `DB_ENGINE=postgresql` (uses `db.sqlite3`).

```powershell
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py runserver
```

Open http://127.0.0.1:8000/

**Note:** S3 uploads need SeaweedFS or set `USE_S3=false` for local `media/` files.

## Option C: Poetry + Local PostgreSQL

Set in `.env`:

```
DB_ENGINE=postgresql
DB_HOST=localhost
DB_NAME=materials_db
DB_USER=materials
DB_PASSWORD=...
```

Create database, then migrate and runserver as above.

## Debug Toolbar

When `DEBUG=True`, Django Debug Toolbar available at `/__debug__/`.

## Static Files

Development serves static from `static/` via Django. Production collects to `staticfiles/` and nginx.

## Common Issues

**Port 80 busy** — change `NGINX_HTTP_PORT` in `.env`.

**Poetry on Windows** — CI uses `deploy/ci/poetry_install.ps1`; same script pattern for fresh venv.

**Structure type has no SQL table** — create via manage UI; materials require `is_created=True` on type.
