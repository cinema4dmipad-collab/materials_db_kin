# References App

Location: `apps/references/`

Shared catalog of measurable **properties** used in materials, samples, and structure field mapping, plus global **metadata dictionaries** for materials.

## Model

**Property** — name, code, unit, data type (`number`, `string`, `boolean`, `date`, `material_link`, `choice`), optional `decimal_places` (for `number`), optional group, description, creator. For `choice`, options live in related `PropertyChoice` rows (`label` / `value`).

**Manufacturer / Availability / Technology** — system-wide constant dictionaries (`code`, `name`, `description`). Not scoped to a workspace. Seeded with a small default set. Materials store optional FKs to these rows.

Codes are generated from names (transliteration + snake_case) with validation against SQL reserved words.

Numeric values on materials/samples use kind **точное / диапазон / ± погрешность** (`apps/core/property_number_value.py`); display precision follows `decimal_places`.

## Public UI

| URL | Action |
|-----|--------|
| `/properties/` | List with search/filters |
| `/properties/create/` | New property (**admin only**) |
| `/properties/<pk>/edit/` | Edit (**admin only**) |
| `/properties/<pk>/delete/` | Delete confirmation (**admin only**) |
| `/properties/dictionaries/` | Hub for metadata dictionaries |
| `/properties/dictionaries/<slug>/` | List manufacturers / availabilities / technologies |
| `/properties/dictionaries/<slug>/create|…/edit|…/delete` | CRUD (**admin only**) |

All workspace roles may **view** the catalogs and pick values in material forms. Sidebar: **Свойства** and **Справочники**.

Forms: `apps/references/forms.py`. Access: `can_manage_properties()` / system admin for mutations.

## Integration

* **Materials / samples** — property picker adds rows to formset; user enters value only
* **Import** — manufacturer / availability / technology resolve from global dictionaries; optional **create missing** with duplicate guards (name/code). Creates are deferred until apply and run inside the same DB transaction as materials (no orphan dictionary rows on failed import).
* **Structure types** — `property_mapping.py` maps Property → StructureField when adding from catalog
* **Admin** — property groups and bulk admin actions

## Workflow

1. Admin defines properties once in the catalog (with correct units and types).
2. Managers and operators reuse them across materials and samples via picker.
3. When designing structure types, import compatible properties as SQL columns.

See [Materials](materials.md) and [Structures](structures.md).
