# Materials App

Location: `apps/materials/`

Central catalog of composite materials.

## Model

**Material** — code, name, description, `struct_type` (FK to StructureType), tags, timestamps.

Related data:

* Property values (through material property model / formset)
* Composite layers (via `composites` app)
* Structure parameter row (SQL table via `structures`)
* Samples, attachments (separate views)

## Public UI

| URL | Action |
|-----|--------|
| `/materials/` | List |
| `/materials/create/` | Create |
| `/materials/<pk>/` | Detail — properties, layers, structure params, samples |
| `/materials/<pk>/edit/` | Edit form |
| `/materials/<pk>/delete/` | Delete |

Sub-routes: attachments, samples tab (`materials/sample_urls.py`, `attachment_urls.py`).

## Material Form

Key blocks:

1. **Basic fields** — code, name, type, tags
2. **Properties** — table with picker (`material_properties_formset.js`); no manual property name entry
3. **Structure fields** — dynamic fields from selected type (when SQL table exists)
4. **Composite layers** — if `allow_layers` on type; toolbar + DnD table (`composite_layers_formset.js`)

Changing structure type reloads the form to load new dynamic fields.

## Validation

* Structure type must have `is_created=True` (SQL table exists)
* Property values validated against reference property data types
* Layer materials must reference existing materials

## Tests

`apps/materials/tests.py` — CRUD, structure linkage, layers, attachments, SQL integration.
