---
name: create-defect-tms
description: Guides creation of Jira TMS/TestRay defects through the active Atlassian MCP server. Requires `docs/tms.project.yaml` in the workspace (from `/init-tms`); if missing, the agent must stop before any MCP calls. Use whenever the user runs /create-defect-tms or asks to file, register, create, triage, or clarify a defect/bug in Jira, TMS, TestRay, including Russian prompts such as "заведи дефект", "создай баг", "оформи дефект", "найди дубликаты", "свяжи с требованием" or "свяжи с тест-кейсом". The workflow searches for similar issues first, clarifies reproduction details and labels, writes a markdown draft for user confirmation, then creates and links the defect only after explicit approval.
---

# Create defect (TMS)

Use this skill to help a tester turn a short defect report into a confirmed Jira TMS/TestRay defect.

The skill instructions are in English, but every user-facing defect artifact must be in Russian: proposed title, description, reproduction steps, expected result, actual result, comments, and final Jira issue content.

## Project configuration (mandatory)

The open workspace **must** contain **`docs/tms.project.yaml`** at the repository root (created by **`/init-tms`**). This file is the team-approved TMS/Jira binding: project key, base URL, and defaults for this repository.

**Before any MCP tool call, any defect draft file, or duplicate search:** verify the file exists (for example by reading `docs/tms.project.yaml`). If it is **missing** or unreadable:

1. **Stop the workflow entirely.** Do not search Jira, do not create a markdown draft, do not explain the defect template in execution mode.
2. Reply to the user **in Russian** with a short notice that TMS is not configured for this repo, that they should run **`/init-tms`** at the project root with their Jira project link, and that **`/create-defect-tms`** can be retried after `docs/tms.project.yaml` exists.

If the file **exists**, read it immediately and use:

- `testray.scheme` — when `testray`, treat types and traceability as **TestRay** (Synapse) unless the user says otherwise
- `jira.project_key` — JQL scope and `jira_create_issue.project_key`
- `jira.base_url` — canonical links shown to the user
- `issue_types.defect` — default `issue_type` for new defects (expect **`Defect`** in TestRay-backed projects)
- `issue_types.functional_requirement` — expected type for **requirement** keys (**`Functional Requirement`**)
- `issue_types.test_case` / `issue_types.test_plan` — when the user links defects to test artifacts, validate `issuetype` against these names (`jira_get_issue`)
- `defaults.labels` / `defaults.components` — suggest during Q&A; apply only with confirmation

User instructions always override YAML when they conflict.

## MCP Server

- Use MCP server `user-mcp-atlassian-testray` (`mcp-atlassian-testray`).
- Before every MCP tool call, read the JSON descriptor for that tool from the active Cursor project MCP folder, for example `~/.cursor/projects/<workspace>/mcps/user-mcp-atlassian-testray/tools/jira_search.json`.
- Pass only parameters declared by the descriptor. Re-read descriptors when unsure about required fields, JSON string fields, or parameter names.
- If a tool named `mcp_auth` or similar exists for this server, authenticate first and do not parallelize authentication with other calls.
- Treat MCP write failures or read-only errors as environment, permission, or Jira workflow constraints. Report the blocker and keep the markdown draft intact.

For a compact tool map, read `reference.md`. For the canonical defect text layout (Russian), read `templates/defect-description.md` at the start of drafting and follow it verbatim for headings and section order.

## Operating Principles

- Be project-neutral **only where YAML does not define a value**. When `docs/tms.project.yaml` is present (required), use its fields for project key, base URL, and defect issue type unless the user overrides. Never invent project keys, issue types, or TMS semantics beyond that file and explicit user input.
- Ask only useful questions. If a missing field can be safely inferred from Jira search results or the user's current context, propose the inference and ask for confirmation.
- Search before creating. A possible duplicate must be discussed with the user before any new defect is filed.
- Keep a markdown draft as the memory layer. Update it after each clarification so the user can see what will be created.
- Do not create, link, transition, or comment on Jira issues until the user explicitly confirms the final draft.
- Use read-only subagents only when the parent system permits them, for example to review the draft for missing reproduction data or to summarize already-fetched search results. Keep all MCP calls and all draft-file updates in the main agent unless the user explicitly delegates otherwise.

## Workflow

### 1. Capture the Initial Report

Start from the user's short defect description. Extract any known values:

- affected project or Jira key prefix
- product area, component, feature, build, firmware, environment, browser/device, account/role
- observed behavior, expected behavior, impact, frequency
- reproduction steps, preconditions, test data
- attachments or logs
- requirement keys, test case keys, related defect keys, suspected duplicates
- desired assignee, priority, severity, labels, components

If the project key or issue type is missing, take them from `docs/tms.project.yaml` when present; otherwise you should have stopped at the mandatory gate. Use `jira_get_all_projects` only when the user needs help choosing among accessible projects after configuration issues. Use Jira metadata/search tools to verify project-specific names rather than guessing.

### 2. Search for Similar Issues

Use `jira_search` before drafting a new defect. Build narrow JQL from what is known:

- include `project = KEY` when known
- include `issuetype = "<issue_types.defect>"` when that key exists in `docs/tms.project.yaml` (TestRay projects: **`Defect`**); if absent, ask once or omit the clause—do not silently default to `Bug`
- search by meaningful Russian and English keywords from the symptoms
- include labels, components, status, and updated date windows when they are reliable

Inspect likely candidates with `jira_get_issue` when summaries alone are not enough. Present the top matches in Russian with key, status, summary, why it may match, and a recommendation: duplicate, related issue, or not similar enough.

If a duplicate is likely, ask whether to stop, comment/link to the existing issue, or still create a new defect linked as duplicate/related.

### 3. Clarify by Question and Answer

Drive a short Q&A until the draft is actionable. Prefer grouped questions:

- "Какие шаги воспроизведения точные и минимальные?"
- "Что ожидалось и что получилось фактически?"
- "На какой версии/стенде/окружении воспроизведено?"
- "Воспроизводится всегда или периодически?"
- "Есть ли требование, тест-кейс, дефект-дубликат или связанная задача?"
- "Какие labels подходят: компонент, тип проверки, регрессия, окружение, релиз?"

When labels are missing, propose conservative labels from the text and Jira context. Keep labels lowercase ASCII when the Jira project appears to use technical labels; otherwise follow project conventions observed in similar issues.

### 4. Maintain the Markdown Draft

Read `templates/defect-description.md` once per draft. It defines **«Тело»** (Jira `description` and the draft section `## Описание дефекта`) and the short **«Черновик»** outline—do not add extra sections.

Create or update one draft file before asking for confirmation. Prefer the active workspace:

`<workspace>/.cursor/defect-drafts/<YYYYMMDD-HHMM>-<short-slug>.md`

If there is no writable project workspace, use:

`~/.cursor/defect-drafts/<YYYYMMDD-HHMM>-<short-slug>.md`

Build the draft using the numbered section order in **«Черновик»**; under `## Описание дефекта` paste **«Тело»** unchanged. For `jira_create_issue`, `summary` is one line (see template intro); `description` is **only** «Тело» (`### Краткое описание` … `### Вложения и логи`).

After every clarification, update the draft file and summarize what changed. Ask for explicit confirmation such as: "Подтверждаете создание дефекта по этому черновику?"

### 5. Create the Defect

Only after explicit confirmation:

1. Re-read `jira_create_issue.json`.
2. Call `jira_create_issue` with:
   - `project_key` from the user or verified Jira context
   - `summary` in Russian
   - `issue_type` from `docs/tms.project.yaml` `issue_types.defect` unless the user overrides (TestRay: **`Defect`**)
   - `description` in Russian Markdown: **only** the Description block defined in `templates/defect-description.md` (from `### Краткое описание` through `### Вложения и логи`), not the full draft metadata
   - `components`, `assignee`, and `additional_fields` only when confirmed
3. Put labels, priority, severity, custom fields, parent, or epic data in `additional_fields` only after verifying field names and expected JSON shape.
4. Update the draft status with the created Jira key.

### 6. Link Requirements, Test Cases, and Other Issues

Before linking, validate every target key with `jira_get_issue`. Record its issue type, summary, status, and intended role in the markdown draft. For **requirement** keys, the type should match `issue_types.functional_requirement` (default **`Functional Requirement`**). For **test case** / **test plan** keys, compare to `issue_types.test_case` / `issue_types.test_plan` when present in `docs/tms.project.yaml`. If a key does not match the claimed role, ask the user before proceeding.

For ordinary Jira links, read `jira_get_link_types.json`, inspect each candidate link type's inward and outward names, then use `jira_create_issue_link.json` with a verified link type and direction. For directional links such as duplicates or blockers, confirm which issue belongs in `inward_issue_key` and which belongs in `outward_issue_key`; record that direction in the draft before calling the tool.

Use ordinary Jira issue links for:

- defect to requirement
- defect to test case
- defect to duplicate defect
- defect to related task or blocker

Use `jira_testray_link_requirement` only for TestRay coverage linking between a requirement and one or more Test Case issues. It does not create a defect link and does not build the TestRay requirement parent/child tree.

If the user asks to modify a Functional Requirement hierarchy in TestRay, stop and use the dedicated Atlassian/TestRay instructions for Synapse requirement tree operations before acting.

### 7. Finish

Report in Russian:

- created issue key and link if available
- title
- links created
- labels/components/priority applied
- anything skipped because it needed more permissions, field metadata, or confirmation

Keep the final response concise and point to the markdown draft file.
