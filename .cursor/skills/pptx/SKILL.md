---
name: pptx
description: "MANDATORY: for ANY .pptx task, do NOT use Read/grep on the file as text — first extract text with this skill's venv: `python -m markitdown \"file.pptx\" -o out.md` OR `python scripts/pptx_markdown.py \"file.pptx\" -o out.md` (always `-o`; stdout mangles non-ASCII on Windows). Then optional thumbnail.py. Run Python ONLY via venv next to SKILL.md. If venv missing, STOP. Trigger on /pptx, deck, slides, presentation, .pptx."
license: Proprietary. LICENSE.txt has complete terms
---

# PPTX Skill

## Invoking `/pptx` or this skill — do not improvise

Slash command `/pptx` only **selects** this skill; the model must still **execute** it. A common failure is reaching for generic tools (`Read` on `.pptx`, raw binary, ad-hoc `zipfile` one-liners) **instead of** the steps below. That is **wrong**: `.pptx` is a ZIP of XML/media — not plain text — and the Read tool does not extract slide text.

**Mandatory order for reading or analyzing content** (structure, wording, style):

1. [Interpreter](#interpreter-non-negotiable): skill `venv` exists → use it. If missing → [stop and notify](#if-venv-is-missing-or-the-interpreter-is-absent); do not substitute another Python.
2. **Text (UTF-8):** write markdown to a file — **do not rely on bare stdout on Windows.**
   - `venv\Scripts\python.exe -m markitdown "path\to\file.pptx" -o "path\to\extracted.md"`  
   - or `venv\Scripts\python.exe scripts\pptx_markdown.py "path\to\file.pptx" -o "path\to\extracted.md"`  
   Quoted paths if spaces/non-ASCII. Then open/read `extracted.md` with the editor. See [markitdown stdout vs `-o`](#markitdown-stdout-vs--o-windows-and-unicode).
3. **Layout/visuals (if needed):** `venv\Scripts\python.exe scripts/thumbnail.py "path\to\file.pptx"`.
4. **Do not** use the editor `Read` tool on `.pptx` as a substitute for step 2. **Do not** use `python -c zipfile …` or unpack-by-hand as the *first* way to “get text” — only for debugging XML after the user asks, or after `markitdown` is unavailable and the user explicitly wants low-level inspection.

**Ask mode / no terminal:** you cannot run step 2 yourself — **say so**, then paste the **exact** commands for the user (skill-root path + quoted `.pptx` path). Do **not** claim you extracted slide text or style from the file without successful `markitdown` output or user-pasted output.

---

## Interpreter (non-negotiable)

**This skill’s Python is only the venv in the same directory as this `SKILL.md`.** That directory is the **skill root** (contains `SKILL.md`, `scripts/`, `requirements.txt`, and `venv/`).

| Required | Forbidden for this skill |
|----------|---------------------------|
| `venv\Scripts\python.exe` (Windows) or `venv/bin/python` (macOS/Linux) | `python`, `python3`, `py` |
| Paths **under the skill root** only | Project venv, Poetry (`poetry run python`), conda, global installs |
| Commands run with `cwd` = skill root **or** full paths to that `python.exe` | Relying on “whatever the workspace uses” |

**Before any Python step:** resolve the folder that contains **this** `SKILL.md` (e.g. `…/.cursor/skills/pptx/`). Use **that** `venv\Scripts\python.exe` (or `venv/bin/python`).

### If `venv/` is missing or the interpreter is absent

1. **Stop.** Do not run `python`, Poetry, the workspace venv, or any other interpreter as a substitute.
2. **Tell the user** clearly: the PPTX skill requires a venv at `<skill-root>/venv/` (give the absolute or resolved path), and it was not found (or `python.exe` / `python` is missing inside it).
3. **Optionally** point them to [Python environment (uv)](#python-environment-uv) so they can create it locally (needs [uv](https://docs.astral.sh/uv/)). Do **not** create or fix the venv automatically unless the user explicitly asks you to run those commands.

Workspace rules (e.g. “always Poetry”) **do not apply** to PPTX skill commands; they would use the wrong interpreter.

### markitdown stdout vs `-o` (Windows and Unicode)

The `markitdown` package’s CLI **re-encodes** markdown for the console using `sys.stdout.encoding` when you omit `-o`. On many Windows setups that is not UTF-8, so **Cyrillic and other non-ASCII text is corrupted** (mojibake or replacement characters). The same CLI writes **UTF-8** when you pass **`-o` / `--output`**.

**Rule:** always extract with `-o some.md` (or `scripts/pptx_markdown.py`, which writes UTF-8 only), then read the file — never treat raw terminal capture as the source of truth for slide text on Windows.

---

## Python environment (uv)

Dependencies live **only** in **`venv/` next to this `SKILL.md`**. All examples use that interpreter; **do not substitute** the repo’s or system’s Python.

| Platform | Interpreter |
|----------|-------------|
| Windows | `venv\Scripts\python.exe` |
| macOS / Linux | `venv/bin/python` |

Examples below use **Windows** paths; on macOS/Linux substitute `venv/bin/python` for `venv\Scripts\python.exe`.

**Create or refresh the venv** (user-run or only after explicit user request; requires [uv](https://docs.astral.sh/uv/)) — from the **skill root**:

```bash
cd /path/to/pptx-skill-folder
uv venv venv
uv pip install -p venv\Scripts\python.exe -r requirements.txt
```

On macOS/Linux, use `-p venv/bin/python` instead of `-p venv\Scripts\python.exe`.

---

## Quick Reference

**Every cell below must use the skill-root venv** — see [Interpreter (non-negotiable)](#interpreter-non-negotiable).

| Task | Guide |
|------|-------|
| Read/analyze content | `venv\Scripts\python.exe -m markitdown presentation.pptx -o extracted.md` (or `scripts\pptx_markdown.py … -o …`) |
| Edit or create from template | Read [editing.md](editing.md) |
| Create from scratch | Read [pptxgenjs.md](pptxgenjs.md) |

---

## Reading Content

```bash
# Text extraction (UTF-8 file — required for non-ASCII on Windows)
venv\Scripts\python.exe -m markitdown presentation.pptx -o presentation.md

# Same, via helper (always UTF-8)
venv\Scripts\python.exe scripts/pptx_markdown.py presentation.pptx -o presentation.md

# Visual overview
venv\Scripts\python.exe scripts/thumbnail.py presentation.pptx

# Raw XML
venv\Scripts\python.exe scripts/office/unpack.py presentation.pptx unpacked/
```

---

## Editing Workflow

**Read [editing.md](editing.md) for full details.**

1. Analyze template with `thumbnail.py`
2. Unpack → manipulate slides → edit content → clean → pack

---

## Creating from Scratch

**Read [pptxgenjs.md](pptxgenjs.md) for full details.**

Use when no template or reference presentation is available.

---

## Design Ideas

**Don't create boring slides.** Plain bullets on a white background won't impress anyone. Consider ideas from this list for each slide.

### Before Starting

- **Pick a bold, content-informed color palette**: The palette should feel designed for THIS topic. If swapping your colors into a completely different presentation would still "work," you haven't made specific enough choices.
- **Dominance over equality**: One color should dominate (60-70% visual weight), with 1-2 supporting tones and one sharp accent. Never give all colors equal weight.
- **Dark/light contrast**: Dark backgrounds for title + conclusion slides, light for content ("sandwich" structure). Or commit to dark throughout for a premium feel.
- **Commit to a visual motif**: Pick ONE distinctive element and repeat it — rounded image frames, icons in colored circles, thick single-side borders. Carry it across every slide.

### Color Palettes

Choose colors that match your topic — don't default to generic blue. Use these palettes as inspiration:

| Theme | Primary | Secondary | Accent |
|-------|---------|-----------|--------|
| **Midnight Executive** | `1E2761` (navy) | `CADCFC` (ice blue) | `FFFFFF` (white) |
| **Forest & Moss** | `2C5F2D` (forest) | `97BC62` (moss) | `F5F5F5` (cream) |
| **Coral Energy** | `F96167` (coral) | `F9E795` (gold) | `2F3C7E` (navy) |
| **Warm Terracotta** | `B85042` (terracotta) | `E7E8D1` (sand) | `A7BEAE` (sage) |
| **Ocean Gradient** | `065A82` (deep blue) | `1C7293` (teal) | `21295C` (midnight) |
| **Charcoal Minimal** | `36454F` (charcoal) | `F2F2F2` (off-white) | `212121` (black) |
| **Teal Trust** | `028090` (teal) | `00A896` (seafoam) | `02C39A` (mint) |
| **Berry & Cream** | `6D2E46` (berry) | `A26769` (dusty rose) | `ECE2D0` (cream) |
| **Sage Calm** | `84B59F` (sage) | `69A297` (eucalyptus) | `50808E` (slate) |
| **Cherry Bold** | `990011` (cherry) | `FCF6F5` (off-white) | `2F3C7E` (navy) |

### For Each Slide

**Every slide needs a visual element** — image, chart, icon, or shape. Text-only slides are forgettable.

**Layout options:**
- Two-column (text left, illustration on right)
- Icon + text rows (icon in colored circle, bold header, description below)
- 2x2 or 2x3 grid (image on one side, grid of content blocks on other)
- Half-bleed image (full left or right side) with content overlay

**Data display:**
- Large stat callouts (big numbers 60-72pt with small labels below)
- Comparison columns (before/after, pros/cons, side-by-side options)
- Timeline or process flow (numbered steps, arrows)

**Visual polish:**
- Icons in small colored circles next to section headers
- Italic accent text for key stats or taglines

### Typography

**Choose an interesting font pairing** — don't default to Arial. Pick a header font with personality and pair it with a clean body font.

| Header Font | Body Font |
|-------------|-----------|
| Georgia | Calibri |
| Arial Black | Arial |
| Calibri | Calibri Light |
| Cambria | Calibri |
| Trebuchet MS | Calibri |
| Impact | Arial |
| Palatino | Garamond |
| Consolas | Calibri |

| Element | Size |
|---------|------|
| Slide title | 36-44pt bold |
| Section header | 20-24pt bold |
| Body text | 14-16pt |
| Captions | 10-12pt muted |

### Spacing

- 0.5" minimum margins
- 0.3-0.5" between content blocks
- Leave breathing room—don't fill every inch

### Avoid (Common Mistakes)

- **Don't repeat the same layout** — vary columns, cards, and callouts across slides
- **Don't center body text** — left-align paragraphs and lists; center only titles
- **Don't skimp on size contrast** — titles need 36pt+ to stand out from 14-16pt body
- **Don't default to blue** — pick colors that reflect the specific topic
- **Don't mix spacing randomly** — choose 0.3" or 0.5" gaps and use consistently
- **Don't style one slide and leave the rest plain** — commit fully or keep it simple throughout
- **Don't create text-only slides** — add images, icons, charts, or visual elements; avoid plain title + bullets
- **Don't forget text box padding** — when aligning lines or shapes with text edges, set `margin: 0` on the text box or offset the shape to account for padding
- **Don't use low-contrast elements** — icons AND text need strong contrast against the background; avoid light text on light backgrounds or dark text on dark backgrounds
- **NEVER use accent lines under titles** — these are a hallmark of AI-generated slides; use whitespace or background color instead

---

## QA (Required)

**Assume there are problems. Your job is to find them.**

Your first render is almost never correct. Approach QA as a bug hunt, not a confirmation step. If you found zero issues on first inspection, you weren't looking hard enough.

### Content QA

```bash
venv\Scripts\python.exe -m markitdown output.pptx -o _qa.md
```

Check `_qa.md` for missing content, typos, wrong order.

**When using templates, check for leftover placeholder text** (search in `_qa.md`, e.g. `grep` on Unix or `Select-String` / `findstr` on Windows):

```bash
grep -iE "xxxx|lorem|ipsum|this.*(page|slide).*layout" _qa.md
```

If matches are found, fix them before declaring success.

### Visual QA

**⚠️ USE SUBAGENTS** — even for 2-3 slides. You've been staring at the code and will see what you expect, not what's there. Subagents have fresh eyes.

Convert slides to images (see [Converting to Images](#converting-to-images)), then use this prompt:

```
Visually inspect these slides. Assume there are issues — find them.

Look for:
- Overlapping elements (text through shapes, lines through words, stacked elements)
- Text overflow or cut off at edges/box boundaries
- Decorative lines positioned for single-line text but title wrapped to two lines
- Source citations or footers colliding with content above
- Elements too close (< 0.3" gaps) or cards/sections nearly touching
- Uneven gaps (large empty area in one place, cramped in another)
- Insufficient margin from slide edges (< 0.5")
- Columns or similar elements not aligned consistently
- Low-contrast text (e.g., light gray text on cream-colored background)
- Low-contrast icons (e.g., dark icons on dark backgrounds without a contrasting circle)
- Text boxes too narrow causing excessive wrapping
- Leftover placeholder content

For each slide, list issues or areas of concern, even if minor.

Read and analyze these images:
1. /path/to/slide-01.jpg (Expected: [brief description])
2. /path/to/slide-02.jpg (Expected: [brief description])

Report ALL issues found, including minor ones.
```

### Verification Loop

1. Generate slides → Convert to images → Inspect
2. **List issues found** (if none found, look again more critically)
3. Fix issues
4. **Re-verify affected slides** — one fix often creates another problem
5. Repeat until a full pass reveals no new issues

**Do not declare success until you've completed at least one fix-and-verify cycle.**

---

## Converting to Images

Convert presentations to individual slide images for visual inspection:

```bash
venv\Scripts\python.exe scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 150 output.pdf slide
```

This creates `slide-01.jpg`, `slide-02.jpg`, etc.

To re-render specific slides after fixes:

```bash
pdftoppm -jpeg -r 150 -f N -l N output.pdf slide-fixed
```

---

## Dependencies

### Python (installed into `venv/`)

**Install only with uv into this skill’s `venv/`** — not `pip` on system Python, not Poetry. Pinned in [requirements.txt](requirements.txt). Install with uv (see [Python environment](#python-environment-uv)):

- `markitdown[pptx]` — text extraction (use `-o` or `scripts/pptx_markdown.py` for UTF-8; see [markitdown stdout](#markitdown-stdout-vs--o-windows-and-unicode))
- `Pillow` — thumbnail grids
- `defusedxml`, `lxml` — unpack/pack/validate/clean scripts

### Other

- `npm install -g pptxgenjs` — creating from scratch ([pptxgenjs.md](pptxgenjs.md))
- LibreOffice (`soffice`) — PDF conversion (see `scripts/office/soffice.py`)
- Poppler (`pdftoppm`) — PDF to slide images
