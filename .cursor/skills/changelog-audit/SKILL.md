---
name: changelog-audit
description: Orchestrate sequential version audit for CHANGELOG restoration. Use when restoring missing CHANGELOG entries from GitLab MRs and git history.
---

# changelog-audit

Orchestrates CHANGELOG restoration by extracting version info, fetching merged MRs, and producing draft entries.

## Workflow

1. **Run changelog-versions.py** — get version list with sha, date, has_existing_entry:
   ```bash
   python scripts/changelog/changelog-versions.py
   ```

2. **For each version** (or selected range):
   - Run **changelog-fetch-mrs.py** with `--sha-from PREV_SHA --sha-to CURR_SHA` (or `--date-from` / `--date-to`). Use `poetry run python` — script requires `requests`.
   - Pass MRs + git log to the prompt template (Generate mode) or existing entry (Supplement mode)
   - Output draft for review

3. **Review and merge** — human reviews draft before updating CHANGELOG.md

## Modes

Agent/orchestrator modes (not script flags):

| Mode | When | Args / Behavior |
|------|------|-----------------|
| `--version X.Y.Z` | Single version | Process only that version |
| `--all` | All missing | Process versions with `has_existing_entry: false` |
| `--from X --to Y` | Range | Process versions from X to Y (inclusive) |
| `--supplement` | Enrich existing | Use Supplement mode: suggest additions to existing entry |

## Scripts

- `scripts/changelog/changelog-versions.py` — extract versions from git + CHANGELOG
- `scripts/changelog/changelog-fetch-mrs.py` — fetch merged MRs from GitLab
- `.cursor/skills/changelog-audit/changelog-prompt.txt` — prompt template

## Dependencies

- **glab token** — GitLab API auth (GITLAB_TOKEN env or `~/.config/glab-cli/config.yml`, Windows: `%LOCALAPPDATA%\glab-cli\config.yml`)
- **main branch** — version commits on main (reference points for date ranges)
- **develop branch** — MR descriptions are written there; changelog-fetch-mrs.py uses `--target-branch develop` by default
- **GitLab project** — remote must be GitLab (git@host:path or https)

## Batch Processing

For `--all` or large ranges, delegate to worker subagent per version to avoid context overflow:

```
mcp_task(subagent_type="worker", prompt="Process version X.Y.Z: run changelog-fetch-mrs.py with --sha-from PREV --sha-to CURR, then generate CHANGELOG entry using changelog-prompt.txt. Output draft.")
```

Process versions sequentially (oldest first) or in small batches.

## Notes

- Version 2.7.1u (UZGA) is excluded by changelog-versions.py
- CHANGELOG section format: Summary, Features, Refactor, Bugfixes, Misc
