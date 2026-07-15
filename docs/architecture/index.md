# Architecture

This section describes the overall architecture of Materials DB: Django apps, dynamic structure storage, and request flow.

**Related**: [Technology Stack](tech-stack.md) · [Testing](testing.md) · [Workspaces & RBAC](workspaces-rbac.md) · [Права пользователей (таблицы)](workspaces-permissions.md)

## System Architecture

Materials DB is a **Django 6** server-rendered application. Business logic lives in `apps/*`; configuration in `config/`; templates in `templates/`; static assets in `static/`.

```
Browser
   ↓ HTTP
Nginx (prod) / runserver (dev)
   ↓
Gunicorn + Django (config.wsgi)
   ├── PostgreSQL — ORM models + dynamic structure tables
   └── S3 / local media — scans, attachments
```

## Django Apps

| App | Path | Responsibility |
|-----|------|----------------|
| **core** | `apps/core/` | Dashboard, help, tags CRUD, list filters, shared UI helpers |
| **references** | `apps/references/` | Property catalog (CRUD, groups) |
| **materials** | `apps/materials/` | Material CRUD, properties formset, attachments, samples tab |
| **composites** | `apps/composites/` | Composite layer model and diagram rendering |
| **structures** | `apps/structures/` | Structure types, fields, SQL executor, public type UI |
| **samples** | `apps/samples/` | Sample CRUD, property inheritance, attachments |
| **scans** | `apps/scans/` | HDF5 scan upload, validation, listing |
| **workspaces** | `apps/workspaces/` | Workspaces, membership, RBAC, sidebar context |

URL routing: [`config/urls.py`](../../config/urls.py).

## Workspaces & RBAC

Multi-workspace isolation with shared property catalog. See [Workspaces & RBAC](workspaces-rbac.md).

## Dynamic Structure Storage

Structure types use a **hybrid model**:

1. **Metadata** in Django ORM — `StructureType`, `StructureField` (migrations, admin, forms).
2. **Instance data** in raw SQL tables — one table per type, created by `SQLExecutor.create_table()`.

Key modules:

| Module | Role |
|--------|------|
| `identifiers.py` | Safe SQL identifiers, table/column name validation |
| `sql_executor.py` | CREATE/DROP TABLE, INSERT/SELECT/UPDATE/DELETE with quoted identifiers |
| `table_storage.py` | Read/write structure rows linked to materials |
| `type_forms.py` / `type_views.py` | Public UI for type definition and table creation |
| `property_mapping.py` | Map reference properties to structure fields |

After a SQL table is created (`is_created=True`), existing field definitions cannot be changed or deleted; new fields may still be added (`ALTER TABLE … ADD COLUMN`).

## Material ↔ Structure Link

A material references one `StructureType`. When the type has a created table, structure parameter values are stored in that type's SQL table row, keyed to the material. Materials cannot use types without a created SQL table.

## File Storage

Uploads use Django `FileField` with configurable backend:

* `USE_S3=false` — files under `media/`
* `USE_S3=true` — `django-storages` + boto3 → S3-compatible endpoint (SeaweedFS)

Large HDF5 uploads stream to disk (`FILE_UPLOAD_MAX_MEMORY_SIZE` = 10 MB); Gunicorn timeout is extended for multi-GB files.

## UI Patterns

* **Bootstrap 5** + KeenetiCA theme (`static/css/keenetica-theme.css`)
* **Formsets** — material properties, composite layers, structure fields
* **Property picker** — modal selection from reference catalog (`reference_properties_picker.js`)
* **List filter bar** — shared template `includes/list_filter_bar.html` and client filter JS
* **File transfer progress** — XHR upload/download indicator (`file_transfer_progress.js`)

## Admin vs Public UI

| Area | Public UI | Django Admin |
|------|-----------|--------------|
| Materials, samples, scans | ✓ | ✓ |
| Structure types | Type wizard + manage page | Full control, create-table action |
| Properties, tags | List + forms | ✓ |
| Users, groups | — | ✓ |

## Module Dependencies

```
config/settings.py
└── apps/
    ├── core (tags, filters, help)
    ├── references → used by materials, samples, structures
    ├── structures → used by materials (struct_type, dynamic fields)
    ├── composites → used by materials (layers)
    ├── materials → samples (FK)
    ├── samples → scans, attachments
    └── scans
```

## Request Flow (Example: Material Detail)

1. `MaterialDetailView` loads ORM material + related samples
2. If structure type is created, `table_storage` fetches SQL row
3. Composite layers queried from `composites` app
4. Template renders properties, layers diagram, structure fields, tabs

See [Components](../components/index.md) for per-app detail.
