# Structures App

Location: `apps/structures/`

Dynamic **structure types**: configurable fields and per-type PostgreSQL tables.

## Models

| Model | Purpose |
|-------|---------|
| `StructureType` | Name, code, `table_name`, `display_color`, `allow_layers`, `is_created`, `is_active` |
| `StructureField` | Column metadata: name, label, type, defaults, sort order |

Field types include `CharField`, `IntegerField`, `DecimalField`, `DateField`, `MaterialLink`.

## SQL Layer

| Module | Role |
|--------|------|
| `sql_executor.py` | DDL/DML with validated quoted identifiers |
| `identifiers.py` | `validate_table_name`, `validate_field_column_name` |
| `table_storage.py` | Bridge ORM materials ↔ SQL rows |
| `default_values.py` | Default value validation for field types |

Table names **must** start with `structures_`, snake_case latin, max 100 chars, unique.

## Public UI Flow

1. **Select type** — `/structures/` — list of types
2. **Create type** — `/structures/types/create/` — name, description, color, layers flag, **SQL table name**, field formset
3. **Manage type** — `/structures/types/<code>/manage/` — color, fields, create/drop SQL table
4. **Records** — `/structures/<code>/` — CRUD on SQL-backed instances (when table created)

After save, modal prompts to create SQL table. Manage page shows table name input before **Create**.

Once `is_created=True`:

* Field definitions locked
* Table name locked
* Type name locked

## Forms and Views

* `type_forms.py` — `StructureTypeForm`, `StructureFieldInlineFormSet`
* `type_views.py` — create, edit, manage, create-table, drop-table
* `forms.py` / `views.py` — dynamic instance forms and lists

Templates: `templates/structures/type_form.html`, `type_manage.html`, `includes/table_name_field.html`.

## Admin

Structure types and fields in admin; **Create table** action calls `SQLExecutor.create_table()`.

## Management Commands

| Command | Purpose |
|---------|---------|
| `sync_structure_tables` | Create SQL tables for all types with `is_created=False` |

## Tests

`apps/structures/tests.py` — identifiers, forms, SQL executor, public UI, injection safety.

See also in-app help section «Типы структур» (`/help/#structures`).
