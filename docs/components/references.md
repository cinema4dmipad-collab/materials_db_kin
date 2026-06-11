# References App

Location: `apps/references/`

Shared catalog of measurable **properties** used in materials, samples, and structure field mapping.

## Model

**Property** — name, code, unit, data type (`CharField`, `IntegerField`, `DecimalField`, `BooleanField`, `DateField`), optional group, description.

Codes are generated from names (transliteration + snake_case) with validation against SQL reserved words.

## Public UI

| URL | Action |
|-----|--------|
| `/properties/` | List with search/filters |
| `/properties/create/` | New property |
| `/properties/<pk>/edit/` | Edit |
| `/properties/<pk>/delete/` | Delete confirmation |

Forms: `apps/references/forms.py`.

## Integration

* **Materials / samples** — property picker adds rows to formset; user enters value only
* **Structure types** — `property_mapping.py` maps Property → StructureField when adding from catalog
* **Admin** — property groups and bulk admin actions

## Workflow

1. Define properties once in the catalog (with correct units and types).
2. Reuse across many materials and samples via picker.
3. When designing structure types, import compatible properties as SQL columns.

See [Materials](materials.md) and [Structures](structures.md).
