---
name: init-tms
description: Initializes TestRay-backed TMS/Jira project context—docs, `docs/tms.project.yaml` (Defect, Functional Requirement, Test Case, Test Plan), **`docs/tms.panels.md`** (saved filters; project issue navigator + optional **`RapidBoard.jspa?rapidView=`** Kanban URLs when `board_id` exists / `--with-boards`), reference **`docs/tms.boards.md`** (same first three table columns), and a Cursor rule for `/create-defect-tms`. Use for /init-tms, "init tms", TestRay, Jira project links, or navigation setup for requirements/test cases/defects/test plans inside the project.
---

# Init TMS (TestRay)

Configure the **current open workspace** (application repo, not `~/.cursor` alone): **`docs/tms.project.yaml`**, **`docs/tms.md`**, **`docs/tms.panels.md`**, optionally **`docs/tms.boards.md`**, **`.cursor/rules/tms-context.mdc`**.

Skill text is English. **`docs/tms.md`** / **`docs/tms.panels.md`** may be Russian for the team.

## TestRay / Jira model (defaults)

| Role | Jira issue type |
|------|-----------------|
| Requirement | **`Functional Requirement`** |
| Test case | **`Test Case`** |
| Defect | **`Defect`** |
| Test plan | **`Test Plan`** |

- TestRay / Synapse semantics: **`mcp-atlassian`** skill.
- **`create-defect-tms`** creates **`Defect`** only; other types are navigation/documentation context.

## Project panels (four facets) — **preferred**

Goal: **saved filters** shared to the project. **`docs/tms.panels.md`** lists (1) project issue navigator (`/projects/{KEY}/issues?filter=`), (2) **Rapid Kanban** links matching classic Jira: `{base}/secure/RapidBoard.jspa?rapidView={board_id}` (**`rapidView`** = Agile REST `board_id` after **`--with-boards`** or manual board creation).

Important: a Rapid Board URL alone does **not** mean the board columns match issue statuses. Column mapping is **Board settings → Columns** per board. The bundle script **does not** create/edit Jira statuses or workflows; **`GET /rest/api/2/project/{KEY}/statuses`** only reflects your scheme. If every issue type still shares one workflow, Jira returns identical status lists until you split workflows. Optional **`--configure-board-columns`** pushes a 1:1 mapping from that API (off by default).

Reference table headings match **`docs/tms.boards.md`** (three shared columns).

Four facets (same as TestRay rows):

1. **Требования** → `Functional Requirement`
2. **Тест-кейсы** → `Test Case`
3. **Дефекты** → `Defect`
4. **Тест-планы** → `Test Plan`

**Default vs boards:** Prefer **filters + project navigator** links for project-scoped lists. Use **`--with-boards`** (or reuse existing **`board_id`**) when the team wants **Rapid Board** URLs. After **`--with-boards`**, Kanban columns remain Jira defaults unless you set **`--configure-board-columns`** or map columns in the UI.

**Deterministic automation:** **`skills/init-tms/scripts/jira_create_testray_boards.py`** — `JIRA_URL` + `JIRA_PERSONAL_TOKEN`, creates filters with `sharePermissions: project`, writes **`docs/tms.panels.md`** (tabular links), idempotent **`--state-file`**. **`--with-boards`** creates four Agile Kanban boards. **`--configure-board-columns`** (optional) aligns board columns to **`GET /project/{KEY}/statuses`** per facet.

If the project already used the old default state path **`docs/tms.boards.state.json`**, pass **`--state-file docs/tms.boards.state.json`** when migrating so duplicate filters are not created.

Otherwise the agent must:

1. **Write** **`docs/tms.panels.md`** from **`templates/tms.panels.md.example`**, substituting **`PROJECT_KEY`**, **`jira.base_url`**, and **`issue_types.*`** from the resolved config (user overrides if Jira type names differ).
2. When **not** running the bundle script for this project, instruct that **each** manual filter must be **shared** to all project consumers (roles / groups—template text).

3. Optionally suggest **Project shortcuts** in the Jira UI pointing at the four URLs (often no supported REST for shortcuts on DC).

**Post-setup verify:** `jira_search` with each facet JQL, or read filter IDs from **`docs/tms.panels.state.json`**.

## Optional: Agile Kanban (`--with-boards`)

**`docs/tms.boards.md`** from **`templates/tms.boards.md.example`** only when the team wants global Kanban in addition to panels. **MCP** typically does not create boards; the script can with **`--with-boards`**.

Derived URL pattern: **`links.project_summary`** = `{jira.base_url}/projects/{project_key}/summary` (adjust if your Jira uses a `/jira` context path—follow the user's sample links).

## Preconditions

- User at **project root**. Create **`docs/`** and **`.cursor/rules/`** if missing.

## Inputs to collect

1. **Jira project link** (required) → `project_key`, **`jira.base_url`** (scheme + host + port, **no** trailing slash; if browse URLs use `/jira`, keep that prefix inside `links.*` only if needed).
2. Optional: display name for docs.
3. Optional: overrides for any **`issue_types.*`** when Jira names differ.
4. Optional: labels/components (user-supplied).
5. Optional: Synapse/TestRay note (one line in `docs/tms.md`).

## Validate when possible

MCP: `jira_get_all_projects`; optional **`jira_get_agile_boards`** (`project_key`) only if **`--with-boards`** was used.

## Files to write

| Path | Purpose |
|------|--------|
| `docs/tms.project.yaml` | `testray`, `jira`, `links` (**include `project_summary`**, optional **`links.panels`**), **`issue_types`** (all four), optional `defaults`. |
| `docs/tms.md` | Compact hub; link **`docs/tms.panels.md`**. |
| **`docs/tms.panels.md`** | JQL table + REST script + project URLs + shortcuts note. |
| **`docs/tms.boards.md`** | Optional legacy Agile doc (`templates/tms.boards.md.example`). |
| `.cursor/rules/tms-context.mdc` | From **`templates/tms-context.mdc.example`**. |

When **updating** existing YAML, preserve keys; add missing `issue_types.test_case`, `issue_types.test_plan`, `links.project_summary`, **`docs/tms.panels.md`**, and optional **`links.panels`** if absent.

### `docs/tms.project.yaml` schema (`schema_version: 1`)

```yaml
schema_version: 1
testray:
  scheme: testray
jira:
  project_key: PROJ
  base_url: http://host:8083
links:
  project: <browse or admin URL>
  project_summary: http://host:8083/projects/PROJ/summary
  # panels:
  #   requirements: http://host:8083/projects/PROJ/issues?filter=...
  #   test_cases: ...
  #   defects: ...
  #   test_plans: ...
issue_types:
  defect: Defect
  functional_requirement: Functional Requirement
  test_case: Test Case
  test_plan: Test Plan
```

Optional: `defaults`, legacy `links.boards`, `notes`.

### Rule file

Copy **`templates/tms-context.mdc.example`** → **`.cursor/rules/tms-context.mdc`**.

## After setup

- List paths; suggest **commit** in the project repo.
- **`/create-defect-tms`** still **requires** `docs/tms.project.yaml`.

## Bundled templates

- `templates/tms.project.yaml.example`
- `templates/tms.md.example`
- **`templates/tms.panels.md.example`**
- **`templates/tms.boards.md.example`** (legacy Agile)
- `templates/tms-context.mdc.example`

Use these when generating project files.

## Script

**`skills/init-tms/scripts/jira_create_testray_boards.py`** — REST automation: **filters + project panel URLs** by default (`--write-panels-doc`), **`--state-file`**, **`--dry-run`**, **`--with-boards`** for optional Kanban.
