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

## Tests

`apps/materials/tests.py` — CRUD, structure linkage, layers, attachments, SQL integration.
