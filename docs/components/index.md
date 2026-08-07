# Components

Main application modules and their responsibilities.

## Table of Contents

- [Core](core.md) — dashboard, help, tags, list filters
- [References](references.md) — property catalog
- [Materials](materials.md) — material cards, properties, layers
- [Composites](composites.md) — layer stack model and diagram
- [Structures](structures.md) — dynamic types and SQL tables
- [Samples](samples.md) — specimens linked to materials
- [Scans](scans.md) — HDF5 scan files
- [HTTP API v1](../api/README.md) — Bearer PAT + workspace header for external clients (KeenetiX)

## Dependency Graph

```
references ─────────────────────────┐
                                    ▼
structures ──► materials ──► samples ──► scans
                  │
                  └── composites (layers)
core ── tags, filters, help (cross-cutting)
api ── PAT over the same domain models (read + scan upload/download)
```

## Public URLs (Summary)

| Section | Base URL |
|---------|----------|
| Dashboard | `/` |
| Help | `/help/` |
| Materials | `/materials/` |
| Properties | `/properties/` |
| Tags | `/tags/` |
| Structures | `/structures/` |
| Samples | `/samples/` |
| All scans | `/scans/` |
| HTTP API v1 | `/api/v1/` |
| Admin | `/admin/` |

## Shared UI Assets

| Asset | Location |
|-------|----------|
| Base layout | `templates/base.html` |
| List filter bar | `templates/includes/list_filter_bar.html` |
| Tag badges | `templates/includes/tag_badges.html` |
| Property picker | `static/js/reference_properties_picker.js` |
| File progress | `static/js/file_transfer_progress.js` |
