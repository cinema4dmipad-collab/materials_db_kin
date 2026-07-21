# Materials App

Location: `apps/materials/`

Central catalog of composite materials.

## Model

**Material** — code, name, description, `struct_type` (FK to StructureType), tags, `home_workspace`, `visibility_mode`, creator (`created_by_user`), timestamps.

Related data:

* Property values (through material property model / formset)
* Composite layers (via `composites` app)
* Structure parameter row (SQL table via `structures`)
* Samples, attachments (separate views)

## Public UI

| URL | Action |
|-----|--------|
| `/materials/` | List — tabs **Пространство** / **Общие** |
| `/materials/create/` | Create (own workspace only) |
| `/materials/import/` | UI import CSV/XLSX (preview dry-run, then apply); requires `material.create` |
| `/materials/import/example.csv` | Download sample CSV |
| `/materials/<pk>/` | Detail — properties, layers, structure params, samples; inline tags when editable |
| `/materials/<pk>/tags/` | POST — save tags from detail card |
| `/materials/<pk>/edit/` | Edit form |
| `/materials/<pk>/delete/` | Delete |

Sub-routes: attachments, samples tab (`materials/sample_urls.py`, `attachment_urls.py`).

### List scopes

* **Пространство** — `materials_owned_by(active_workspace)`
* **Общие** — `materials_shared_in(active_workspace)` (published materials visible in workspace, including own published)

Shared materials from other workspaces are read-only in the active workspace.

## Material picker

Shared modal (`includes/reference_materials_modal.html`, `reference_materials_picker.js`):

* Tabs **Пространство** / **Общие** (same logic as list)
* Search and grouping by structure type
* **Создать** link on workspace tab only

Data: `apps/materials/picker_data.py` — each item includes `scopes: ['workspace']`, `['shared']`, or both.

Used in: sample form, composite layers, structure dynamic fields.

## Material Form

Key blocks:

1. **Basic fields** — code, name, type, tags
2. **Properties** — table with picker (`material_properties_formset.js`); no manual property name entry. For `number`: value kind (scalar / range / ±) via `property_number_value.js`
3. **Structure fields** — dynamic fields from selected type (when SQL table exists); decimal fields support the same range/tolerance UI when configured
4. **Composite layers** — if `allow_layers` on type; toolbar + DnD table (`composite_layers_formset.js`)

Changing structure type reloads the form to load new dynamic fields.

## Validation

* Structure type must have `is_created=True` (SQL table exists)
* Property values validated against reference property data types
* Layer materials must reference existing materials

## Import (materials + properties)

Shared service: `apps/materials/imports/` (`MaterialImporter`).

**UI:** `/materials/import/` — hybrid wizard for arbitrary CSV/XLSX:
1. Upload  
2. Sheet + header/group rows + **match policy** + required **StructureType**  
3. **Mapping constructor** (1C-style): table «file column → expression (target field)» + catalog of material / structure / property targets; click row then catalog item to review auto-mapping; parse mode per column (auto / text / number)  
4. **Staging draft / review** (skip rows, exclude fields/properties); on validation errors — Apply/iterate blocked, only «Fix mapping»  
5. Apply → SQL structure row (`struct_props_id`) + optional `MaterialProperty` leftovers  

Mapping profiles: model `MaterialImportProfile` (per workspace, includes `structure_type_id`).  
Permission: `material.create`.

**CLI:**

```bash
poetry run python manage.py import_materials path/to/file.csv --workspace legacy --dry-run
poetry run python manage.py import_materials path/to/file.xlsx --workspace legacy
```

**Format:** one row per material property; repeat `code` for multiple properties on the same material.

| Column | Required | Notes |
|--------|----------|-------|
| `code` | yes | Unique per `home_workspace` |
| `name` | on create | |
| `description`, `struct_type`, `tags` | no | `tags`: `tag1;tag2` |
| `property_name` | for property rows | Must exist in reference catalog (`Property.name`) |
| `value_kind` | no | `scalar` (default), `range`, `tolerance` — numbers only |
| `value`, `value_b`, `notes` | depends | Same semantics as material property forms |

**Behaviour:**

* Idempotent upsert by `(home_workspace, code)` and `(material, property)`
* Tags are **merged** with existing tags on update (not replaced)
* `--dry-run` validates and prints planned counts without writing
* `home_workspace` column, if present, must match `--workspace`
* Does not create reference properties
* `material_link` / structure `MaterialLink`: cell may be material **code**, unique **name**, or **UUID** (visible in the active workspace). Links are applied in a second pass, so targets from the same import file are allowed.
* XLSX merged cells are expanded (top-left value copied into the whole merge range) before staging.
* Empty cells stay empty (`NULL` / omitted): import does not apply `StructureField.default_value` and does not invent values; a row with only name/code is enough to create a material.
* Mapped structure/property fields appear in the review draft even when the cell is blank (written as empty/`NULL`). Unchecking include (or mapping to skip) ignores the field even if Excel has a value.
* After column mapping, choose apply mode: **batch** (full draft review, then write all) or **row-by-row** (go straight to the first draft; confirm/skip each active row; committed rows stay if a later row fails).
* Numeric cells may include units or strip width (`12,5 мм`, `4050/ 50мм`): the leading number is stored; the unit suffix is discarded (field unit comes from the structure/property).
* Each create/update via import sets `Material.import_source_filename` to the source file basename (last import wins). The materials list has a choice filter «Источник импорта».

Example file: `apps/materials/fixtures/import_examples/materials_sample.csv`

## Tests

`apps/materials/tests.py` — CRUD, structure linkage, layers, attachments, SQL integration.  
`apps/materials/tests_import.py` — CSV/XLSX readers, import service/command, UI import flow.
