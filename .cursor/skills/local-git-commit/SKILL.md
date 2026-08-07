---
name: local-git-commit
description: Creates a local git commit in the current branch. Stages changes with git add, runs pre-commit hooks, and commits without pushing. Use when the user wants to commit changes locally, create a commit, or save work to git.
---

# Local Git Commit

## When to Use

Use when the user wants to create a local commit in the current branch. Never push commits to origin.

## Pre-Commit Hooks

Projects may use pre-commit hooks (from `.pre-commit-config.yaml`) that run automatically on `git commit`. Common hooks:

- **clang-format** – formats C/C++ files
- **commitizen** – validates commit message format (Conventional Commits)
- **qmlformat-all** – formats QML files (if project has QML)

Ensure pre-commit is installed: `pre-commit install`

## Workflow

### Step 1: Check for temp files

Before staging, list untracked files:

```bash
git status --porcelain
```

**Temp files** = anything that semantically does not belong to the project: intermediate data, build garbage, temporary outputs, cache files, etc. Examples: `temp/`, `tmp/`, `*.tmp`, build artifacts, generated caches, debug dumps.

If any untracked paths look like temp files (not yet in the index):

**Ask the user** what to do with them:
- **Add to index** – include in the commit
- **Delete** – remove the files
- **Add to .gitignore** – ignore them and do not add

Do not proceed until the user decides.

### Step 2: Stage changes

Always stage both new and modified files:

```bash
git add .
git add -u
```

- `git add .` – stages new and modified files in the current directory
- `git add -u` – stages updates and deletions of already tracked files

### Step 3: Verify staged changes

```bash
git status
```

Confirm the staged files match the user's intent.

### Step 4: Commit

Use Conventional Commits format (if commitizen is used):

```bash
git commit -m "type(scope): description"
```

**Common types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Example:**
```bash
git commit -m "feat(ui): add top toolbar component"
```

Pre-commit hooks will run automatically. **If hooks modify files** (e.g. formatters), the commit may fail. In that case:

1. Run `git add -u` to stage the formatter changes
2. Run `git commit -m "..."` again

Repeat until the commit succeeds.

## Constraints

- **Never** run `git push` or `git push origin`
- **Never** push commits to origin
- Always ask the user about temp files before staging
- Use Conventional Commits for the message when commitizen is configured
