# Samples App

Location: `apps/samples/`

Physical **specimens** derived from materials.

## Model

**Sample** — code, name, material (FK), object type (test, control, product, …), tags, workspace, creator, description; optional `struct_type` + `struct_props_id` for a **per-sample copy** of structure parameters (SQL row), independent of the material row.

**SampleProperty** — property values; copied from material on create, editable per sample. Numeric properties support scalar / range / ± (same as materials).

**SampleAttachment** — generic files linked to sample.

## Public UI

| URL | Action |
|-----|--------|
| `/samples/` | List — button **Импорт** next to **Создать** |
| `/samples/import/` | UI import CSV/XLSX (same wizard as materials); pick a **material** instead of structure type; requires `sample.create` |
| `/samples/import/example.csv` | Download sample CSV |
| `/samples/create/` | Create (optional `?material=<uuid>` preselect) |
| `/samples/<pk>/` | Detail — properties, scans tab, files tab; inline tags when `sample.workspace` is active |
| `/samples/<pk>/tags/` | POST — save tags from detail card |
| `/samples/<pk>/edit/` | Edit |

Attachments: `/samples/<pk>/attachments/`.

## Material selection

Sample form uses the shared **material picker** modal with tabs:

* **Пространство** — materials owned by active workspace
* **Общие** — published materials visible in workspace

`SampleForm` limits `material` queryset to `materials_visible_in(workspace)`.

## Property and structure inheritance

When material is selected (or changed) in the form:

* **Structure parameters** prefill from the material’s SQL row and save to the sample’s own `struct_props_id` (never writes the material row). Changing material discards the previous sample row and copies from the new material.
* **Catalog properties** prefill into `SampleProperty` rows; changed values save only on the sample.

Legacy samples without `struct_props_id` still **display** material structure params on the detail page until first save of the sample form.

Adding a property not present on the material shows a warning (allowed — sample may have extra parameters).

Form / JS: `apps/samples/forms.py` (`SampleForm` structure fields), `static/js/sample_properties_formset.js` (material change → `_apply_material` re-render).

## Import

`/samples/import/` — the same four-step wizard as material import (`apps/samples/import_views.py` subclasses `MaterialImportView`). Session keys are `sample_import_*` (isolated from material import).

Configure step: pick a **material** (picker modal). Mapping constructor loads:

* sample identity (name required; code generated if omitted)
* structure fields of that material’s `struct_type`
* catalog properties already on the material (operator can add more)
* description, object type, tags

Apply creates `Sample` rows in the active workspace, copies the material’s SQL structure row and `MaterialProperty` values, then overlays mapped columns. Tags from the file are assigned; import-review status tags (`статус::на проверке`) are **not** added.

## Relation to Scans

Samples are the anchor for HDF5 scans and file attachments. Create sample first, then attach scans from detail tabs or global scan list.

## Tests

`apps/samples/tests.py`, `apps/samples/tests_import.py`.
