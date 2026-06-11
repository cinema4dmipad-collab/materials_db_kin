# Samples App

Location: `apps/samples/`

Physical **specimens** derived from materials.

## Model

**Sample** — code, name, material (FK), object type (test, control, product, …), tags, description.

**SampleProperty** — property values; copied from material on create, editable per sample.

**SampleAttachment** — generic files linked to sample.

## Public UI

| URL | Action |
|-----|--------|
| `/samples/` | List |
| `/samples/create/` | Create (optional `?material=<uuid>` preselect) |
| `/samples/<pk>/` | Detail — properties, scans tab, files tab |
| `/samples/<pk>/edit/` | Edit |

Attachments: `/samples/<pk>/attachments/`.

## Property Inheritance

When material is selected in the form, properties **prefill** from the material card. Changed values save only on the sample.

Adding a property not present on the material shows a warning (allowed — sample may have extra parameters).

Formset: `static/js/sample_properties_formset.js`.

## Relation to Scans

Samples are the anchor for HDF5 scans and file attachments. Create sample first, then attach scans from detail tabs or global scan list.

## Tests

`apps/samples/tests.py`.
