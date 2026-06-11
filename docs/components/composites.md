# Composites App

Location: `apps/composites/`

Supports **composite layer stacks** on materials when the structure type has `allow_layers=True`.

## Model

**CompositeLayer** — FK to material, sort order, layer material (FK to Material), reinforcement angle, thickness (mm).

Ordering is significant; UI allows reorder via drag-and-drop and toolbar buttons.

## Layer Diagram

`apps/composites/layer_diagram.py` builds SVG/stack visualization for material detail page.

Template include: `templates/materials/includes/composite_layer_diagram.html`  
Styles: `static/css/composite_layer_diagram.css`

## Form Integration

Material form embeds inline formset managed by `static/js/composite_layers_formset.js`:

* Add / duplicate / delete rows
* Move up/down, bulk selection
* Drag handle (⋮⋮) for reorder

Hidden fields (`id`, `DELETE`) at end of row.

## Admin

Registered in Django admin for direct layer inspection if needed.
