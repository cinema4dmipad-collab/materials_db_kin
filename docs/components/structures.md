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

1. **Select type** — `/structures/` — card grid of types; click name/card → records; gear → manage
2. **Create type** — `/structures/types/create/` — name, description, color, layers flag, **SQL table name**, field formset
3. **Manage type** — `/structures/types/<code>/` — color, fields, create/drop SQL table; **delete draft** (`type_delete`) when `is_created=False`
4. **Materials list** — `/structures/<code>/` — materials matrix for this type **owned by the active workspace only** (no shared/published materials from other spaces); name, code, structure fields; wrapping headers with units; horizontal scroll with sticky name/code; click a column header to sort asc/desc (empty cells last); search/filter like materials (tags, description, dictionaries) even when those columns are hidden; CTA **«Создать материал»** → `materials:create?struct_type=…`; code/name link to `materials:detail`
5. **Migrate** — `/structures/migrate/` (superuser) — move all materials from source type to target with interactive field mapping; identical field names auto-mapped; optional delete source type+table after success (`migrate_service.py`)
6. **Diagnostics** — `/structures/diagnostics/` (superuser) — normalization checks; **«Что делать»** guidance; confirmable repair buttons (table/column/row fixes) where safe (`diagnostics.py`, `diagnostics_repairs.py`)

SQL row create/edit remains available for admin/manage flows; detail of a SQL row still shows linked materials. Page bookmarks (header «В закладки») cover the current URL; entity toggles on structure pages were removed.

After save, modal prompts to create SQL table. Manage page shows table name input before **Create**.

Once `is_created=True`:

* Existing field definitions locked (new fields may still be added)
* Table name locked
* Type name locked

## Forms and Views

* `type_forms.py` — `StructureTypeForm`, `StructureFieldInlineFormSet`
* `type_views.py` — create, edit, manage, create-table, drop-table, delete-draft
* `forms.py` / `views.py` — dynamic instance forms and lists
* `materials_grid.py` — materials × structure-fields table for the records list

Templates: `templates/structures/type_form.html`, `type_manage.html`, `list.html`, `includes/table_name_field.html`.

Field picker (`structure_type_form.js` + `reference_properties_picker.js`): blocks properties already present by **property id**, **column name**, or **label** (prevents `matrix` + `matrix_mat` both labeled «Матрица»). Round-trip «Создать свойство» saves a sessionStorage draft, restores it, and auto-adds `created_property` once.

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
