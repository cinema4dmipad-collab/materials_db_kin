# Technology Stack

Overview of technologies and libraries used in Materials DB.

**Version constraints:** see [`pyproject.toml`](../../pyproject.toml).

## Runtime and Package Management

| Technology | Description |
|------------|-------------|
| **Python** | 3.13+ |
| **Poetry** | Dependency management (`poetry install`, `poetry run`) |
| **Django** | 6.x — web framework, ORM, admin, forms |
| **Gunicorn** | WSGI server in production containers |

## Database and Storage

| Library / Service | Description |
|-------------------|-------------|
| **PostgreSQL 16** | Primary database (ORM + dynamic structure tables) |
| **psycopg2-binary** | PostgreSQL adapter |
| **SQLite** | Fallback when `DB_ENGINE` is not `postgresql` (tests, quick local) |
| **django-storages** | S3 storage backend for uploads |
| **boto3** | AWS SDK used by django-storages |
| **SeaweedFS** | S3-compatible storage in Docker Compose |

## Frontend (Server-Rendered)

| Technology | Description |
|------------|-------------|
| **Django Templates** | HTML rendering |
| **Bootstrap 5** | Layout and components (CDN) |
| **Vanilla JavaScript** | Formsets, pickers, filters, file progress, layer table DnD |
| **Montserrat** | UI font (Google Fonts) |

No separate SPA; JS modules live under `static/js/`.

## Development Tools

| Tool | Description |
|------|-------------|
| **django-debug-toolbar** | Debug panel when `DEBUG=True` |
| **python-dotenv** | Load `.env` in `config/settings.py` |

## Container and Reverse Proxy

| Technology | Description |
|------------|-------------|
| **Docker / Compose** | Local stack: postgres, seaweedfs, web, nginx |
| **Nginx** | Static files and reverse proxy in prod compose (`deploy/nginx/`) |
| **Dokploy** | Production build and deployment (outside CI) |

## CI/CD

| Technology | Description |
|------------|-------------|
| **GitLab CI** | [`.gitlab-ci.yml`](../../.gitlab-ci.yml) — **test stage only** |
| **Poetry install scripts** | `deploy/ci/poetry_install.ps1` (Windows runner), `.sh` (Linux) |

Build and deploy to servers are **not** in GitLab CI; Dokploy handles image build and compose rollout.

## Project Layout

```
materials_db_v1/
├── apps/           # Django applications
├── config/         # settings, urls, wsgi
├── templates/      # HTML templates
├── static/         # CSS, JS, images
├── deploy/         # entrypoint, nginx, CI helpers
├── docs/           # This documentation
├── docker-compose.yml
├── docker-compose.prod.yml
└── pyproject.toml
```

## Security Notes

* SQL identifiers for dynamic tables validated in `apps/structures/identifiers.py` before any DDL/DML
* CSRF on all POST forms; `CSRF_TRUSTED_ORIGINS` for HTTPS deployments
* Production: `SECRET_KEY` required when `DEBUG=False`
* S3 credentials via environment variables only
