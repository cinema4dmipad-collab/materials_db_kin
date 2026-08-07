# Samples App

Location: `apps/samples/`

Physical **specimens** derived from materials.

## Model

**Sample** — code, name, material (FK), object type (test, control, product, …), tags, workspace, creator, description.

**SampleProperty** — property values; copied from material on create, editable per sample. Numeric properties support scalar / range / ± (same as materials).

**SampleAttachment** — generic files linked to sample.

## Public UI

| URL | Action |
|-----|--------|
| `/samples/` | List |
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

## Property Inheritance

When material is selected in the form, properties **prefill** from the material card. Changed values save only on the sample.

Adding a property not present on the material shows a warning (allowed — sample may have extra parameters).

Formset: `static/js/sample_properties_formset.js`.

## Relation to Scans

Samples are the anchor for HDF5 scans and file attachments. Create sample first, then attach scans from detail tabs or global scan list.

## Tests

`apps/samples/tests.py`.
