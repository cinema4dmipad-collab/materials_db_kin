# References App

Location: `apps/references/`

Shared catalog of measurable **properties** used in materials, samples, and structure field mapping.

## Model

**Property** — name, code, unit, data type (`CharField`, `IntegerField`, `DecimalField`, `BooleanField`, `DateField`), optional group, description, creator.

Codes are generated from names (transliteration + snake_case) with validation against SQL reserved words.

## Public UI

| URL | Action |
|-----|--------|
| `/properties/` | List with search/filters |
| `/properties/create/` | New property (**admin only**) |
| `/properties/<pk>/edit/` | Edit (**admin only**) |
| `/properties/<pk>/delete/` | Delete confirmation (**admin only**) |

All workspace roles may **view** the catalog and pick properties in material/sample forms.

Forms: `apps/references/forms.py`. Access: `can_manage_properties()` in `apps/workspaces/permissions.py`.

## Integration

* **Materials / samples** — property picker adds rows to formset; user enters value only
* **Structure types** — `property_mapping.py` maps Property → StructureField when adding from catalog
* **Admin** — property groups and bulk admin actions

## Workflow

1. Admin defines properties once in the catalog (with correct units and types).
2. Managers and operators reuse them across materials and samples via picker.
3. When designing structure types, import compatible properties as SQL columns.

See [Materials](materials.md) and [Structures](structures.md).
