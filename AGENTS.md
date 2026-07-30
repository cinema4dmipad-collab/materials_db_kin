# AGENTS.md — materials-db-v1

## Quick start

```bash
cp .env.example .env
docker compose up -d --build        # PostgreSQL + SeaweedFS + web + nginx
docker compose exec web python manage.py seed_data
```

## Commands

| Command | Purpose |
|---------|---------|
| `python manage.py test --verbosity 1` | Run all tests |
| `python manage.py test <app.tests.TestClass.test_method>` | Single test |
| `python manage.py seed_data` | Seed reference properties + 12 composite materials |
| `python manage.py sync_structure_tables` | Create SQL tables for all StructureType with `is_created=False` |
| `python manage.py wait_for_db` | Block until DB is ready (used in entrypoint) |
| `python manage.py check_s3_storage` | Verify S3 connectivity |
| `python manage.py run_scheduled_backup` | Create Postgres dump if auto-backup schedule is due |
| `python manage.py backup_now` | Create Postgres dump into `BACKUP_DIR` immediately |

## Architecture

- Settings: `config/settings.py` (env via `dotenv`)
- Apps under `apps/`: **core**, **materials**, **references**, **samples**, **scans**, **structures**, **composites**, **workspaces**, **analytics**
- **Workspaces** is a cross-cutting multi-tenancy layer — `WorkspaceVisibilityMixin` on every major model, middleware enforces session-based active workspace
- **Structures** are dynamic: `StructureType` + `StructureField` → raw SQL tables via `SQLExecutor`. Query via raw SQL, not ORM. `material.struct_type` + `material.struct_props_id` links materials to dynamic table rows.
- **S3 storage** is conditional (`USE_S3` env var); uses `django-storages` + `boto3`. Falls back to local `media/`.
- **DB**: PostgreSQL (prod) or SQLite (dev/CI). Set `DB_ENGINE=postgresql` to switch.
- **Backups**: PostgreSQL only (`pg_dump -Fc`); schedule via `backup-cron` + `/administration/backups/`. See `deploy/BACKUP.md`. SeaweedFS is not backed up by this feature.
- **Version**: `pyproject.toml [project].version` + git commit hash from `BUILD_COMMIT` file or CI env.

## Key conventions

- View code: `apps/materials/views.py` for materials CRUD, `apps/structures/views.py` for dynamic record CRUD, `apps/structures/type_views.py` for StructureType management
- URL config: `config/urls.py` wires all `apps/*/urls.py`. Material attachment/sample submounts at `materials/<uuid:pk>/attachments/` and `materials/<uuid:pk>/samples/`
- Templates: `templates/base.html` extends, Bootstrap 5.3 CDN, custom CSS/JS in `static/`
- Template library: `ui_tags` from `apps.core.templatetags.ui_tags`
- Form renderer: `django.forms.renderers.DjangoTemplates` (not default)
- `Material.code` uniqueness is scoped to workspace (`unique_material_code_per_workspace`), not global
- `Sample.code` uniqueness is scoped to workspace
- After `StructureType.is_created=True`, new `StructureField` rows can be added (`ALTER TABLE … ADD COLUMN`); existing fields cannot be modified or deleted
- Material links: create a reference property with `data_type=material_link`, then add it to a structure via the properties picker (creates a `MaterialLink` column). There is no separate «Ссылка на материал» shortcut on the structure form.

## CI / Deploy

- GitLab CI (self-hosted Windows runner). Linux test stage is `when: never`.
- Prod deploy via **Dokploy** (docker-compose mode, not Stack). **Command must be left empty** (see `deploy/DOKPLOY.md`).
- Entrypoint runs: `wait_for_db → migrate → collectstatic → gunicorn`
- Build cache busting: increment `BUILD_CACHE_BUST` env var in Dokploy to force rebuild
- File uploads: `FILE_UPLOAD_MAX_MEMORY_SIZE` and `DATA_UPLOAD_MAX_MEMORY_SIZE` are 10 MB (HDF5 files up to 20 GB stream to disk)

## Testing quirks

- `TestAutoLoginMiddleware` is injected in test mode — auto-authenticates as `test-automation` user with manager group in legacy workspace
- Tests use SQLite in CI (Windows runner). The docker-compose test services (`postgres`, `seaweedfs`) exist but the Linux CI stage is disabled.
