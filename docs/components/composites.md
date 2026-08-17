# Composites App

Location: `apps/composites/`

Supports **composite layer stacks** on materials when the structure type has `allow_layers=True`.

## Model

**CompositeLayer** — FK to material, sort order, layer material (FK to Material), reinforcement angle, thickness (mm).

Ordering is significant; UI allows reorder via drag-and-drop and toolbar buttons.

## Layer Diagram

`apps/composites/layer_diagram.py` builds the stack visualization for the material detail page.

Legend modes: material (one color per material), thickness (blue→white→red from min to max), angle (fixed −90°…+90°, 0° is white). Layer labels sit to the right of the color column; separators are black. Symmetric layups show a dashed mid-plane and “+ N симметричных слоёв”. After layers are set, the stacking-sequence formula is shown (`(0/90)4/(90/0)4`).

Template include: `templates/materials/includes/composite_layer_diagram.html`  
Styles: `static/css/composite_layer_diagram.css`

## Form Integration

Material form embeds inline formset managed by `static/js/composite_layers_formset.js`:

* Add / duplicate / delete rows
* Move up/down, bulk selection
* Drag handle (⋮⋮) for reorder
* Selecting a ply material fills layer thickness from that material’s **Толщина** structure field (or reference property), unless the row is locked

Hidden fields (`id`, `DELETE`) at end of row.

## Admin

Registered in Django admin for direct layer inspection if needed.
