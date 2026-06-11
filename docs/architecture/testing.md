# Test Architecture

Structure of the Materials DB test suite and CI integration.

## Overview

Tests use Django's built-in `TestCase` / `TransactionTestCase` and live beside each app:

| App | Test module |
|-----|-------------|
| core | `apps/core/tests.py` |
| references | `apps/references/tests.py` |
| materials | `apps/materials/tests.py` |
| structures | `apps/structures/tests.py` |
| samples | `apps/samples/tests.py` |
| scans | `apps/scans/tests.py` |

Run all tests:

```powershell
poetry run python manage.py test --verbosity 1
```

## Database in Tests

Default CI and local runs typically use **SQLite** (`db.sqlite3`) when `DB_ENGINE` is empty or unset.

PostgreSQL integration is available via environment variables (`DB_ENGINE=postgresql`, `DB_HOST`, …). GitLab defines a `test:linux` job with Postgres service; it is currently disabled (`rules: when: never`).

## Major Test Areas

### Structures (`apps/structures/tests.py`)

Largest test module. Covers:

* SQL identifier validation and injection rejection
* `StructureTypeForm` — code generation, custom `table_name`
* `SQLExecutor` — create/drop table, CRUD, defaults, MaterialLink columns
* Public UI — type create, manage page, create-table modal, drop table
* Property mapping from reference catalog

### Materials (`apps/materials/tests.py`)

Material CRUD, structure linkage, composite layers, property formsets, attachments.

### Core (`apps/core/tests.py`)

List filters, tag views, help page render, dashboard.

### Scans (`apps/scans/tests.py`)

HDF5 validation, upload constraints, list/detail views.

## CI Pipeline

[`.gitlab-ci.yml`](../../.gitlab-ci.yml):

| Job | Runner | Action |
|-----|--------|--------|
| `test` | Windows shell (gr3) | `poetry run python manage.py test` |
| `test:linux` | Docker + Postgres | Disabled |

Pipeline triggers: merge requests, tags, default branch.

Variables in CI: `SECRET_KEY`, `DEBUG=True`, `USE_S3=false`, empty `DB_ENGINE` → SQLite.

## Writing New Tests

1. Prefer `TestCase` for ORM-only logic; `TransactionTestCase` when testing raw SQL DDL across connections.
2. Use `reverse()` for URL assertions — see existing structure view tests.
3. For dynamic tables, create `StructureType` + fields, call `SQLExecutor.create_table()`, assert with `SQLExecutor.table_exists()`.
4. Clean up: tests should not leave stray SQL tables; use test DB isolation or explicit drop in `tearDown` where needed.

## Related

* [Examples: Testing](../examples/testing.md) — commands and troubleshooting
* [Structures component](../components/structures.md) — SQL table lifecycle
