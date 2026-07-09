---
name: new-docs
description: Study a module in detail and add documentation to the project. Use /new-docs with a module name.
---

# New Docs — Module Documentation

When the user invokes this skill with a module name (e.g. `/new-docs mover_modules` or "Подробно изучи mover_modules и внеси документацию"), delegate the task to the **docs-agent** subagent.

## Invocation

- `/new-docs <MODULE>`
- "Подробно изучи \<MODULE\> и внеси документацию по нему в проект"

Extract `<MODULE>` from the user message — it may be a path (`mover_modules`, `config_modules`), a component name (`SDAQS`, `Reader`), or a file/package reference.

## Action

1. **Assess module size**: If the module is large (many subfolders, >10 files, or complex structure), split it into up to 3 logical submodules (e.g. by subfolder, layer, or responsibility). Launch **separate docs-agent subagents in parallel** for each submodule.

2. **Delegate to docs-agent** using the Task tool:
   - `subagent_type`: `docs-agent`
   - `prompt`: A detailed task description including:
     - The module/component to study (full path or name)
     - Instruction to explore the codebase thoroughly
     - Instruction to create or update documentation in `docs/` (Markdown only)
     - Reference to existing docs structure: `docs/overview/`, `docs/terms.md`, `docs/architecture/`, `docs/components/`, `docs/configuration/`, `docs/examples/`
     - Policy: no Sphinx/RST edits; use `.md` files only

   **If split into submodules**: Call mcp_task multiple times (up to 3) in parallel, each with a distinct submodule path. Example: `mover_modules/mover_bases`, `mover_modules/keenetix_frame_mover.py`, `mover_modules/keenetix_cnc_mover_plane.py`.

4. **Example prompt** for the subagent:

   ```
   Study the <MODULE> module in detail:
   - Explore its structure, classes, functions, and responsibilities
   - Trace dependencies and integration points
   - Create or update documentation in docs/ following the project structure
   - Use Markdown only (no RST/Sphinx)
- Place new docs in docs/components/, docs/architecture/, or docs/configuration/ as appropriate
- Add domain terms to docs/terms.md when documenting new modules
- Link from docs/components/index.md or docs/README.md if it's a major component
   ```

5. After subagent(s) complete, summarize the changes for the user.

## Documentation Policy (reminder)

- **Markdown only** in `docs/`
- Do not edit `docs/source/`, `conf.py`, or other Sphinx files
- Follow structure: `docs/README.md`, `docs/components/`, `docs/architecture/`, etc.
