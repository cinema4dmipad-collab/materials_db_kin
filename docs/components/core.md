# Core App

Location: `apps/core/`

Cross-cutting features: landing page, in-app help, tag management, list filtering utilities.

## Views and URLs

| URL | View | Description |
|-----|------|-------------|
| `/` | Dashboard | Entry page with links to main sections |
| `/help/` | Help page | User documentation (Russian) |
| `/tags/` | Tag list/create/edit/delete | Tag CRUD |

App URL config: `apps/core/urls.py`.

## List Filters

Shared filtering for list views across apps:

* `apps/core/list_filters.py` — filter definitions, queryset helpers
* `apps/core/templatetags/list_filter_tags.py` — template tags
* `static/js/list_filter_client.js` — client-side row filtering on detail pages

Templates: `includes/list_filter_bar.html`, `includes/client_filter_bar.html`.

## Tags

* Model and utilities: `apps/core/tag_utils.py`, signals in `apps/core/signals.py`
* Widget: `tag_names_input` — comma-separated entry with suggestions
* Context processor `tag_suggestions` injects existing tags into forms

Tags normalize on save; clickable badges on lists apply filter query params.

## Forms and Helpers

* `apps/core/forms.py` — shared form pieces
* `apps/core/number_utils.py` — numeric parsing/formatting
* `apps/core/property_form_display.py` — property label/unit display for formsets

## Management Commands

| Command | Purpose |
|---------|---------|
| `wait_for_db` | Block until PostgreSQL accepts connections (entrypoint) |
| `check_s3_storage` | Verify S3 bucket read/write |

## Tests

`apps/core/tests.py` — dashboard, help render, tag views, filter behaviour.
