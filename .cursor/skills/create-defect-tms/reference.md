# Jira TMS Defect Reference

## Bundled template

- `templates/defect-description.md`: canonical Russian layout for Jira `summary`, Jira `description`, and the on-disk draft. Do not invent alternate headings when filling defect text.

## Project defaults

- **`docs/tms.project.yaml`** at the repo root is **mandatory**. When present: `testray.scheme`, `jira.*`, **`issue_types`** (**`Defect`**, **`Functional Requirement`**, **`Test Case`**, **`Test Plan`**), `links.*`, optional **`links.panels`**. TMS navigation playbook: **`docs/tms.panels.md`** (from **`/init-tms`**); **`docs/tms.boards.md`** only if Agile Kanban is used (**`--with-boards`**).

## MCP tools

This reference lists the MCP tools normally used by `create-defect-tms`. Always read the live descriptor under `mcps/user-mcp-atlassian-testray/tools/<tool>.json` before calling a tool.

## Discovery

- `jira_get_all_projects`: list accessible projects when the user does not know the project key.
- `jira_get_agile_boards`: list Kanban/Scrum boards when the project uses **`--with-boards`** (optional legacy).
- `jira_search_fields`: find project-specific fields such as severity, affected version, environment, or custom TMS fields.
- `jira_get_field_options`: inspect allowed values for a known custom field.
- `jira_get_link_types`: list valid Jira issue link types before linking issues.

## Similar-Issue Search

- `jira_search`: search with narrow JQL before creating a defect. Prefer explicit `fields` and a small `limit`.
- `jira_get_issue`: inspect candidate duplicates or related issues. Request only fields needed for the decision.

## Defect Creation and Updates

- `jira_create_issue`: create the confirmed defect. Required inputs are `project_key`, `summary`, and `issue_type`; description and confirmed metadata are optional.
- `jira_update_issue`: update fields only after explicit user confirmation.
- `jira_add_comment`: add Russian Markdown comments to existing issues when the user chooses to comment instead of creating a new defect, or when linking rationale should be recorded.

## Links

- `jira_create_issue_link`: link the created defect to requirements, test cases, duplicates, or related issues using a verified Jira link type.
- `jira_remove_issue_link`: remove an incorrect link only after explicit user confirmation.

## TestRay-Specific Tools

- `jira_testray_get_linked_test_cases`: read TestRay test case coverage for a requirement.
- `jira_testray_link_requirement`: link Test Case issues to a requirement in the TestRay requirement link panel. Do not use this for defect links or requirement hierarchy.

For Functional Requirement parent/child trees, use Synapse requirement hierarchy guidance from the Atlassian/TestRay workflow, not ordinary Jira issue links.
