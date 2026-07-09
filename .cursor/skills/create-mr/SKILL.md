---
name: create-mr
description: Creates or updates a GitLab merge request via a deterministic Python script (HTTPS API + glab config token). Use when the user wants to create an MR, open merge request, or push and create MR.
---

# create-mr

Creates or updates a merge request using one deterministic path.

## Before push (project policy)

**Before** `git push`, follow **this repository’s** release and contribution rules—not anything hardcoded in this skill.

1. Read the project’s own sources, for example: `docs/` (index, conventions, build/deployment pages), `.cursor/rules/`, `CONTRIBUTING*`, `AGENTS.md`, or `README` sections on versioning, changelog, and MR expectations.
2. Apply whatever that project requires for the current branch (e.g. version or changelog bumps, formatting, tests). If the repo documents nothing, use team conventions agreed for that project.
3. Commit those updates on the same branch, then push.

### Optional: changelog (when the project maintains one)

If the checked-out repository has a root `CHANGELOG.md` (or a documented changelog elsewhere, e.g. in `docs/`), and project policy or the diff implies a user- or operator-facing release:

- **Version bump ⇒ numbered changelog section.** If the branch bumps the shipped version (e.g. `GUI2_vr/Settings/version.h` for LUS), **`CHANGELOG.md` must have a matching `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD` section** with notes for that release. Do not leave ship-facing bullets only under `[Unreleased]` while the binary already reports the new version—follow that repo’s `docs/build/version.md` (LUS: explicit **Changelog alignment** rule).
- **LUS `CHANGELOG.md` language:** Write bullet prose **in English** (`docs/conventions.md` — Changelog); cite localized UI strings only in parentheses when useful for reviewers or field correlation.
- If there is **no** version bump, add concise bullets under `## [Unreleased]` (or per local convention). Prefer aligning wording with any semver rules in `docs/build/version.md` or equivalent.
- Skip changelog lines for doc-only, tooling-only, or internal refactors that do not bump the shipped version, unless the team tracks those in the changelog anyway.
- Repos differ: some keep notes under `[Unreleased]` until a tag. **Where the shipped version macro/file is bumped on the branch (e.g. LUS `version.h`), add the matching `## [X.Y.Z]` section in the same MR**—do not defer if project docs say so.

**Do not duplicate changelog content:**

- **One fact → one bullet.** If the branch already documents a change (e.g. under `[Unreleased]` or a versioned `## [X.Y.Z]`), **edit or refine that bullet** instead of adding a second bullet that restates the same behavior.
- **Avoid overlap across sections.** Do not describe the same feature in both `Added` and `Changed` unless the project template explicitly splits “new capability” vs “behavior change”; prefer a single clearest subsection.
- **Avoid `[Unreleased]` vs versioned double-entry.** After moving notes into `## [X.Y.Z]`, remove them from `[Unreleased]` so the same release is not described twice.
- **Follow-up commits / MR updates:** append only **net-new** user-visible deltas; do not re-copy prior bullets when fixing typos or addressing review—**replace** the existing line.

**MR description vs changelog:**

- The GitLab MR description should summarize scope for reviewers; it does **not** need to paste every changelog bullet verbatim. Link or paraphrase; keep changelog as the canonical shipped-history list.

If there is no changelog file and none is required by the project, ignore this subsection.

## Workflow

1. **Run mr-diff** (from repo root or any dir inside repo):
   ```bash
   ~/.cursor/skills/gitlab-mr-description/scripts/mr-diff.sh
   ```

2. **Fill the template** with description based on the diff. If diff is empty, tell the user there are no changes and do not create MR.

3. **Choose an overarching MR title** — one short phrase that summarizes the entire MR (not the last commit). Examples: `refactor: datagen, API, config; add complexity tooling`, `feat(api): debug metrics endpoint`.

4. **Save MR description** to a temporary file:
   ```bash
   cat > /tmp/mr_description.md <<'EOF'
   ## Summary
   ...
   EOF
   ```

5. **Run deterministic script** with `--title`:
   ```bash
   python3 ~/.cursor/skills/create-mr/scripts/create_mr.py \
     --description-file /tmp/mr_description.md \
     --title "refactor: datagen, API, config; add complexity tooling"
   ```

6. **Confirm** — script prints one MR URL to stdout.

7. **Open in browser** (optional): run:
   ```bash
   python3 ~/.cursor/skills/create-mr/scripts/open_mr.py
   ```

## Notes

- **Always pass `--title`** — otherwise the script uses the last commit message, which may be too narrow (e.g. `chore(rules): ...`). The title must summarize the whole MR.
- Target branch precedence is: explicit `--target`, then `MR_TARGET_BRANCH`, then inferred parent branch.
- Parent branch inference uses local git history and prefers `origin/*` branches other than the current branch. It excludes remote branches that already contain `HEAD`, ranks the remaining candidates by the merge-base with `HEAD`, then falls back to `origin/HEAD`, then `main`, `master`, or `develop` if available.
- Deterministic path is fixed to **HTTPS API only**.
- Token is read from `~/.config/glab-cli/config.yml` for the current Git remote host.
- Branch is always pushed first with `git push -u origin <branch>`.
- If MR already exists for the source branch, script updates it and returns the same URL.
- Optional env vars:
  - `MR_TARGET_BRANCH` (target branch override)
  - `MR_ASSIGNEE_IDS` (comma-separated numeric IDs)
  - `MR_ASSIGN_SELF=false` (disable auto-assign to current API user)
