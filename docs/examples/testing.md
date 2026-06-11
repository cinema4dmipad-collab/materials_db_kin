# Testing

Running the test suite locally and in CI.

## Run All Tests

```powershell
poetry run python manage.py test --verbosity 1
```

Single app:

```powershell
poetry run python manage.py test apps.structures.tests --verbosity 2
```

Single test class:

```powershell
poetry run python manage.py test apps.structures.tests.StructureIdentifierTests --verbosity 2
```

## Database Backend

| Environment | Typical DB |
|-------------|------------|
| Local default | SQLite (`db.sqlite3`) |
| `DB_ENGINE=postgresql` | PostgreSQL |
| GitLab CI `test` job | SQLite (`DB_ENGINE` empty) |
| GitLab `test:linux` | PostgreSQL service (disabled) |

For Postgres locally before tests:

```powershell
$env:DB_ENGINE="postgresql"
$env:DB_HOST="localhost"
$env:DB_NAME="materials_db_test"
$env:DB_USER="materials"
$env:DB_PASSWORD="..."
poetry run python manage.py test
```

## CI

Pipeline: [`.gitlab-ci.yml`](../../.gitlab-ci.yml)

* Stage: **test** only
* Job `test` runs on Windows shell runner with Poetry
* Build and deploy are handled by **Dokploy**, not CI

Trigger pipeline: push to default branch, merge request, or tag.

## Test Coverage Highlights

| Area | Module | What is tested |
|------|--------|----------------|
| SQL safety | `structures/tests.py` | Identifier validation, injection rejection |
| Dynamic tables | `structures/tests.py` | CREATE TABLE, CRUD, MaterialLink |
| Public UI | `structures/tests.py` | Type create, manage, create-table modal |
| Materials | `materials/tests.py` | Forms, layers, structure binding |
| Scans | `scans/tests.py` | HDF5 validation |
| Core | `core/tests.py` | Help page, filters, tags |

## Writing Tests

Use Django `TestCase` and `Client` for view tests:

```python
from django.test import TestCase
from django.urls import reverse

class MyViewTests(TestCase):
    def test_list_returns_200(self):
        response = self.client.get(reverse('materials:list'))
        self.assertEqual(response.status_code, 200)
```

For structure SQL tests, prefer creating types in setUp and dropping tables in tearDown when using `TransactionTestCase`.

See [Test Architecture](../architecture/testing.md) for structure details.

## Troubleshooting

**Tests fail on Windows with Postgres** — ensure `DB_*` env vars match running instance or unset `DB_ENGINE` for SQLite.

**Stale SQL tables in dev DB** — drop manually or use test DB isolation; dynamic tables are not removed by `migrate`.

**Long test run** — structures module is largest; use `--keepdb` is not supported by default Django test runner without third-party tools.
