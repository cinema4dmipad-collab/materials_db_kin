---
name: marimo-check
description: Runs marimo notebook validation with `marimo check` for Python marimo notebooks. Use when user asks to verify marimo notebooks, run marimo checks, or validate *_mnb.py/report notebook files before commit.
---

# Marimo Check

## Purpose

Validate marimo notebooks with a single default command.

## Default command

Run:

```bash
poetry run marimo check <notebook.py>
```

## When to use

- User asks to "run marimo check"
- User updates marimo notebook files (`*_mnb.py`, report notebooks)
- Pre-commit verification for marimo notebooks

## Workflow

1. Confirm target notebook path.
2. Run `poetry run marimo check <notebook.py>`.
3. If check fails, report exact error and failing cell/file context.
4. Re-run the same command after fixes.

## Output format

- `target`: notebook path
- `command`: executed check command
- `result`: pass/fail
- `details`: concise error summary if failed

## Example

```bash
poetry run marimo check examples/report_summary_mnb.py
```
