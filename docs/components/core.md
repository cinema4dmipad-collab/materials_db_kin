# Core App

Location: `apps/core/`

Cross-cutting features: landing page, in-app help, tag management, list filtering utilities, user profile route.

## Views and URLs

| URL | Action |
|-----|------|
| `/` | Dashboard |
| `/help/` | Help page (Russian user guide) |
| `/tags/` | Tag list — tabs **Пространство** / **Общие**, filter **Активные** / **Архив** |
| `/accounts/profile/` | Current user profile (via `apps/workspaces`) |

App URL config: `apps/core/urls.py`, accounts in `apps/workspaces/urls/accounts.py`.

## List Filters

Shared filtering for list views across apps:

* `apps/core/list_filters.py` — scopes including `creator`, `struct_type`, tags
* `apps/core/templatetags/list_filter_tags.py` — filter link template tags
* `static/js/list_filter_client.js` — client-side row filtering on detail pages

Templates: `includes/list_filter_bar.html`, `includes/client_filter_bar.html`, `includes/creator_filter_link.html`, `includes/type_badge.html`.

**Interactive filters:** click structure type badge, object type, scan method, tag, or creator pill in lists to apply search scope.

## Tags

* Model: optional `workspace` (null = global tag); metadata `description`, `color` (`#RRGGBB`, blank = default style), `is_archived`
* **Пространство** — workspace-scoped tags; managers/operators can CRUD
* **Общие** — global tags; admin only (`can_manage_global_tags`)
* **Scoped tags** — name format `область::значение` (one `::`); slug uses `--`; at most one scoped tag per scope on assign (`dedupe_scoped_tag_names`)
* Archived tags stay on existing records but are hidden from picker / suggestions
* Forms see both via `tags_in_workspace()`; suggestions exclude archived
* Widget: `tag_names_input` — chips + suggestions (`json_script`); GitLab-like colored badges
* Helpers: `apps/core/tag_utils.py`, `apps/core/widgets.py`

## Forms and Helpers

* `apps/core/creator.py` — assign/display creator on create
* `apps/core/forms.py` — shared form pieces (e.g. `TagForm`)
* `apps/core/number_utils.py` — numeric parsing/formatting
* `apps/core/property_number_value.py` — scalar / range / ± tolerance for numeric properties
* `apps/core/property_form_display.py` — property label/unit display for formsets

## Management Commands

| Command | Purpose |
|---------|---------|
| `wait_for_db` | Block until PostgreSQL accepts connections (entrypoint) |
| `check_s3_storage` | Verify S3 bucket read/write |

## Tests

`apps/core/tests.py` — dashboard, help render, tag views/metadata, filter behaviour, creator scope.  
`apps/core/tests_property_number_value.py` — number value kinds formatting/validation.

In-app help source: `templates/core/help.html`.
