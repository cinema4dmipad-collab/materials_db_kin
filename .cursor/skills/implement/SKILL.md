---
name: implement
description: Enforces shard-aware implementation with mandatory Subagent usage, strict path contracts, and a single final integration gate.
---

# Implement

Orchestrates implementation tasks with strict, deterministic Subagent orchestration.
This skill is designed to reduce "single-agent drift" and must be followed literally.

## Mandatory Execution Rules

1. Use the `Subagent` tool for implementation and review whenever the task is not trivially small.
2. Never use legacy pseudo-calls such as `mcp_task(...)`; always invoke `Subagent`.
3. Do not skip shard review when a shard changed files.
4. Do not proceed to final response until integration gate completes (or a blocking issue is surfaced).

### Hard trigger for Subagent usage

You MUST launch Subagents if ANY of these are true:

- More than 1 file may be edited
- More than 1 directory/domain is involved
- User asks for refactor/migration/restructure
- Estimated work is more than ~15 minutes
- Any check/fix loop is likely

You MAY stay single-agent only when ALL are true:

- Exactly 1 small file change
- No cross-file dependency
- No expected review loop
- No behavioral risk

If uncertain, default to Subagents.

## Workflow

Execute these steps in order:

### Step 1: Planning (main chat)

In the main conversation:

1. Clarify the task only if required to avoid wrong edits.
2. Break work into shard candidates (paths + ownership boundaries).
3. Mark cross-shard dependencies and risk areas.
4. Decide split policy:
   - If split is obvious after planning: proceed without asking.
   - If split is ambiguous: ask user before launching workers.
5. Choose mode:
   - Parallel mode: up to 4 concurrent workers.
   - Sequential fallback: use when overlap/conflict risk is high.

### Step 2: Parallel shard implementation (worker-impl)

Launch `worker-impl` per shard (max 4 concurrent):

1. Send shard contract with required fields for that role (see role key matrix below).
2. Require worker to return `changed_files`.
3. Worker runs targeted checks only for files it changed in its shard.

### Step 3: Parallel shard review (reviewer-shard)

Launch `reviewer-shard` per completed shard:

1. Reviewer validates only shard-owned files.
2. Reviewer flags any path contract violation as blocking.
3. Reviewer avoids redundant heavy checks already deferred to final gate.

### Step 4: Fix loop (worker-fix, conditional)

If shard reviewer reports blocking issues:

1. Run `worker-fix` for that shard only.
2. Re-run `reviewer-shard` for that shard.
3. Repeat until shard is clean or escalated.

### Step 5: Integration review and final gate (reviewer-integration + main)

After shard approvals:

1. Run `reviewer-integration` for cross-shard risks (interfaces, side effects, behavior drift).
2. Main agent handles collision resolution if multiple shards touched same path:
   - Prefer sequential replay for conflicting shard set
   - Re-run affected shard review(s)
3. Run one final aggregated check in main agent.
4. Summarize results, risks, and follow-ups to user.

## Role Modes

- `worker-impl`: Implements assigned shard within path contract
- `worker-fix`: Applies reviewer feedback for a shard
- `reviewer-shard`: Reviews one shard for correctness and contract compliance
- `reviewer-integration`: Reviews cross-shard integration risks

## Invocation Mapping (mode -> subagent type)

Use these explicit mappings when launching tasks:

- `worker-impl` -> `worker` subagent
  - Pass `Role: worker-impl` in the prompt.
  - Example:
    `Subagent(subagent_type="worker", description="Implement shard A", prompt="Role: worker-impl\nTask: ...\nowner_paths: ...\nforbidden_paths: ...")`
- `worker-fix` -> `worker` subagent
  - Pass `Role: worker-fix` in the prompt.
  - Example:
    `Subagent(subagent_type="worker", description="Fix shard A", prompt="Role: worker-fix\nTask: ...\nFindings: ...\nowner_paths: ...\nforbidden_paths: ...")`
- `reviewer-shard` -> `reviewer` subagent
  - Pass `Role: reviewer-shard` in the prompt.
  - Example:
    `Subagent(subagent_type="reviewer", description="Review shard A", prompt="Role: reviewer-shard\nTask: ...\nowner_paths: ...\nforbidden_paths: ...\nchanged_files: ...")`
- `reviewer-integration` -> `reviewer` subagent
  - Pass `Role: reviewer-integration` in the prompt.
  - Example:
    `Subagent(subagent_type="reviewer", description="Review integration", prompt="Role: reviewer-integration\nshards: ...\nchanged_files: ...\ncross_shard_scope: ...")`

Role behavior is defined by user-level agent profiles:

- `~/.cursor/agents/worker.md`
- `~/.cursor/agents/reviewer.md`

## Shard Contract

Shard prompts must include keys required by their role:

- `owner_paths`: Paths the shard may modify
- `forbidden_paths`: Paths the shard must not modify
- `changed_files`: Files actually changed by worker (output)
- `cross_shard_scope`: Integration touchpoints (required for `reviewer-integration`)

### Required keys by role

- `worker-impl`: `owner_paths`, `forbidden_paths`
- `worker-fix`: `owner_paths`, `forbidden_paths`, `changed_files`
- `reviewer-shard`: `owner_paths`, `forbidden_paths`, `changed_files`
- `reviewer-integration`: `changed_files`, `cross_shard_scope`

Rules:

- Worker/reviewer operate only within `owner_paths`
- Any edit in `forbidden_paths` is a blocking violation
- If shard boundaries overlap or collisions occur, fallback to sequential for affected shards

### `changed_files` schema

`changed_files` must be:

- Relative paths from repo root
- Deduplicated
- Sorted lexicographically (ascending)

Example:

```json
[
  "app/gui/MainView.qml",
  "lus-net-lib/src/net/client.cpp"
]
```

## Check Strategy

- Shard workers run targeted checks only for `changed_files` in their shard
- Avoid repeated full-repo runs of heavy checks (for example, full `ruff` or repo-wide `qmlformat`)
- Main agent runs one final aggregated check after merge/integration review
- If aggregated check fails, route fixes to `worker-fix` only for impacted shard(s)

Minimum scope for the final aggregated check:

- Validate merged `changed_files` set from all shards
- Run required project checks that can catch cross-shard breakage
- Confirm no path contract violations remain
- Confirm integration reviewer decision is go

## Compliance Checklist (must satisfy before final response)

- At least one `worker` Subagent launched when hard trigger conditions are met.
- `reviewer-shard` launched for each shard that produced `changed_files`.
- `reviewer-integration` launched when 2+ shards exist or any cross-shard interface changed.
- `changed_files` collected, deduplicated, sorted.
- Final aggregated gate performed by main agent.
- Any blocking reviewer finding is fixed or explicitly escalated.

## Prompt Templates

Use concise prompts with required fields.

### Worker template (`worker-impl` / `worker-fix`)

```
Role: {role_mode}
Task: {task_summary}
owner_paths: {owner_paths}
forbidden_paths: {forbidden_paths}
changed_files: {changed_files_or_empty_on_start}
Constraints: {project_rules}
Checks: Run targeted checks only for changed files in owner_paths.
Output: brief summary + changed_files + checks run + unresolved risks.
```

### Reviewer template (`reviewer-shard`)

```
Role: reviewer-shard
Shard: {shard_id}
Task: {task_summary}
owner_paths: {owner_paths}
forbidden_paths: {forbidden_paths}
changed_files: {changed_files}
Focus: correctness, regressions, contract violations inside shard, missing tests.
Checks: targeted evidence only for changed_files in owner_paths.
Output: findings by severity + required fixes + go/no-go.
```

### Reviewer template (`reviewer-integration`)

```
Role: reviewer-integration
shards: {shard_list}
changed_files: {changed_files_merged}
cross_shard_scope: {interfaces_and_touchpoints}
Focus: cross-shard compatibility, side effects, behavior drift, ordering dependencies.
Checks: integration-focused checks; do not duplicate shard-only checks.
Output: findings by severity + required fixes + integration go/no-go.
```

### Final gate template (main agent)

```
Inputs:
- owner_paths (all shards)
- forbidden_paths (all shards)
- changed_files (merged)
Process:
1) verify no path contract violations
2) run one final aggregated check
3) confirm integration review outcome
Decision: approve or route targeted fixes.
```

## Failure Handling

If Subagent invocation fails due to transient tool/runtime issues:

1. Retry once with same payload.
2. If still failing, reduce shard count and retry sequentially.
3. If Subagent is unavailable after retries, stop and report explicit blocker (do not silently continue as single-agent for non-trivial tasks).

## Flow diagram

```
Planning -> Split decision (obvious=proceed, ambiguous=ask user)
      -> worker-impl shards (parallel, max 4)
      -> reviewer-shard (parallel)
      -> worker-fix/reviewer-shard loop (per shard)
      -> reviewer-integration
      -> final aggregated gate (main)
      -> done

Fallback: overlap/collision -> sequential for affected shards
```

## When to use / skip

Use:

- Multi-file or multi-domain work with clear shardable paths
- Tasks that benefit from parallel implementation + review
- Work requiring strong ownership boundaries and integration gate

Skip:

- Tiny changes where orchestration overhead is higher than coding
- Tasks with highly overlapping files and constant collisions
- Pure exploration or design-only discussions
