---
name: mcp-atlassian
description: Queries and updates Jira and Confluence via the Cursor MCP Atlassian integration (JQL, CQL, issues, pages, sprints, attachments). Use when the user mentions Jira, Confluence, Atlassian, JQL, CQL, issue keys, boards, sprints, TestRay requirement tree/parent-child requirements, Synapse REST, or wants tickets/docs pulled or updated through MCP.
---

# MCP Atlassian (Jira & Confluence)

## Server and invocation

- **MCP server id**: `user-mcp-atlassian` (metadata name: `mcp-atlassian`).
- **Before any tool call**: read that tool’s JSON descriptor under the active Cursor project’s MCP folder, e.g. `~/.cursor/projects/<workspace>/mcps/user-mcp-atlassian/tools/<tool_name>.json`, and pass only parameters defined there (required args, types, defaults).
- If a tool named `mcp_auth` (or similar) appears for this server, authenticate with that tool first and do not parallelize auth with other calls.

## Principles

1. **Prefer narrow reads**: use `fields` / `limit` / `spaces_filter` / `projects_filter` to limit payload size; for Confluence body text, default to markdown (`convert_to_markdown` true) unless macros/HTML are required (HTML costs more tokens).
2. **Confirm destructive or broad writes**: creating/deleting issues, transitions, bulk operations, or page deletes should match explicit user intent.
3. **Do not invent project or space keys**: `jira_create_issue` and similar tools require real keys from the user or from API results (e.g. `jira_get_all_projects`).
4. **Pagination**: Jira Cloud may return `page_token`; Server/DC typically uses `start_at` — follow the schema and prior response metadata.

## Common workflows

### Jira: find and inspect

1. `jira_search` with JQL (required). Tune `fields`, `limit`, `projects_filter`.
2. `jira_get_issue` for a known key; use `expand` (e.g. `transitions`, `changelog`) when needed.
3. Custom fields: `jira_search_fields` / `jira_get_field_options` before setting unknown fields.

### Jira: change status

1. `jira_get_transitions` for the issue.
2. `jira_transition_issue` with the `transition_id` from that response; add `fields` JSON if the transition requires resolution or other mandatory fields.

### Jira: create or update

- Create: `jira_create_issue` (project key, summary, issue type required). Extra data via `additional_fields` JSON string per descriptor examples.
- Update: `jira_update_issue`. Comments: `jira_add_comment` / `jira_edit_comment`.
- Links: `jira_get_link_types`, then `jira_create_issue_link` / `jira_remove_issue_link`; epic: `jira_link_to_epic`.
- Agile: `jira_get_agile_boards`, `jira_get_sprints_from_board`, `jira_get_sprint_issues`, `jira_add_issues_to_sprint`, `jira_create_sprint`, `jira_update_sprint`.

### Jira: development panel

- `jira_get_issue_development_info` or `jira_get_issues_development_info` for linked branches/PRs/commits when relevant.

### Confluence: find and read

1. `confluence_search` with plain text or CQL (`query` required); optional `spaces_filter`.
2. `confluence_get_page` by `page_id` **or** exact `title` + `space_key`.

### Confluence: edit and attachments

- Update/delete/move: `confluence_update_page`, `confluence_delete_page`, `confluence_move_page`.
- Comments: `confluence_get_comments`, `confluence_add_comment`, `confluence_reply_to_comment`.
- Files: `confluence_get_attachments`, `confluence_upload_attachment`, `confluence_upload_attachments`, `confluence_download_attachment`, `confluence_download_content_attachments`, `confluence_delete_attachment`.
- Labels: `confluence_get_labels`, `confluence_add_label`.
- History/diff/views: `confluence_get_page_history`, `confluence_get_page_diff`, `confluence_get_page_views`.
- Structure: `confluence_get_page_children`, `confluence_get_space_page_tree`.

### Jira Service Management (when applicable)

- `jira_get_service_desk_for_project`, `jira_get_service_desk_queues`, `jira_get_queue_issues`, `jira_get_issue_sla`.

### Proforma (when applicable)

- `jira_get_issue_proforma_forms`, `jira_get_proforma_form_details`, `jira_update_proforma_form_answers`.

### TestRay (Synapse): Functional Requirement hierarchy — parent and children

Build the requirement hierarchy shown in the **Requirements** panel (`requirement-member-panel`: Parent Link, Child Requirement Tree, etc.) through **Synapse public REST**, not through regular Jira **Issue Links**. Links such as **RTM Tree Relation** (`parent of` / `child of`) or **Relates** live in a different Jira link model and do not replace the TestRay requirement tree.

**How to set parent → children**

- `POST {JIRA_URL}/rest/synapse/latest/public/requirement/{parentRequirementKey}/addChildren`
- JSON body: `{"requirementKeys": ["CHILD-1", "CHILD-2", ...]}`
- A typical successful response is HTTP `200` with `{"message":"Success"}`.
- Use the same Jira access as MCP, for example `Authorization: Bearer` with the PAT from `JIRA_PERSONAL_TOKEN` against `{JIRA_URL}`.

**How to read the tree back**

- `GET .../requirement/{requirementKey}/getOnlyImmediateChildren` returns direct child requirements.
- `GET .../requirement/{requirementKey}/getChildren` returns the full subtree, per the TestRay DC REST documentation.

**Do not confuse this with other mechanisms**

- `jira_testray_link_requirement` in the extended MCP server links **Test Case** issues to a requirement (`linkTestCase` / coverage). It does **not** create a parent requirement → child requirement relationship.
- Jira **Parent Link** (often `customfield_10107`) is often unavailable through `jira_update_issue` when the field is not on the edit screen. Do not rely on it as the primary way to set the TestRay tree.
- **Requirement Suite** grouping (for example `customfield_10202`) is managed separately through `requirementSuite` / `addMember`. It represents folders/groups in the navigator, not the parent/child requirement hierarchy. When needed, consult the repository documentation (`docs/tasks/.../requirement-suites-*.md`).

**If hierarchy was accidentally created through Issue Links**

- Remove those links with `jira_remove_issue_link` (`link_id` comes from `issuelinks` in `jira_get_issue`), then set the tree through the `addChildren` calls above.

## Tool index

Jira (prefix `jira_`): search/get issue; get transitions; create/update/delete issue; comments; worklog; watchers; links; versions; components; boards/sprints; batch helpers; attachments download; user profile; Service Desk; Proforma; development info.

Confluence (prefix `confluence_`): search; get/create/update/delete/move page; comments; labels; attachments; space tree; children; history; diff; page views; images.

For a flat list of tool names, see [reference.md](reference.md).

## Errors

If tools return configuration or permission errors, treat as environment/auth scope issues: verify the MCP server is enabled, credentials/scopes allow the operation, and read-only mode is not blocking writes.
