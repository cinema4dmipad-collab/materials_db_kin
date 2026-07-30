# Structures App

Location: `apps/structures/`

Dynamic **structure types**: configurable fields and per-type PostgreSQL tables.

## Models

| Model | Purpose |
|-------|---------|
| `StructureType` | Name, code, `table_name`, `display_color` (`#RRGGBB`), `allow_layers`, `is_created`, `is_active` |
| `StructureField` | Column metadata: name, label, type, defaults, `decimal_places`, sort order |

Field types include `CharField`, `IntegerField`, `DecimalField`, `DateField`, `MaterialLink`, `ChoiceField`. New `MaterialLink` / `ChoiceField` columns are added by picking a reference property with type «Материал» / «Выбор из списка» (not via a dedicated structure shortcut). Choice options are copied onto the structure field and rendered as a select on material forms.

`display_color` is a free hex color (presets + picker); legacy `tone-*` values migrated to hex. Decimal fields can store scalar / range / ± via `decimal_range.py` and `structure_decimal_forms.py` (SQL columns managed in `sql_executor.py`).

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

List/detail show linked material names for `MaterialLink` fields; **Развернуть** loads material properties via `structure_material_expand.js`. Bookmark toggles on list, detail, and type pages.

After save, modal prompts to create SQL table. Manage page shows table name input before **Create**.

Once `is_created=True`:

* Existing field definitions locked (new fields may still be added)
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
| `migrate_structure_decimal_ranges` | Backfill decimal range/tolerance columns for existing types |

## Tests

`apps/structures/tests.py` — identifiers, forms, SQL executor, public UI, injection safety.

See also in-app help section «Типы структур» (`/help/#structures`).
