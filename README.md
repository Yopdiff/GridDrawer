# Toolbox Drawer Grid-Box Auto-Generator

A local web app that turns **measured drawer dimensions** into **ready-to-slice STL files** for a family of
open-top, rounded-corner boxes, using the author's existing OpenSCAD template (`templates/box.scad`).

> **This README is the source of truth for the project.** An AI coder should be able to build the whole
> application from this document plus the three reference files described in §2. Where this document and
> the code disagree, fix the code (or update this document deliberately).

---

## 1. Background: the manual workflow this replaces

| # | Manual step today | Pain |
|---|---|---|
| 1 | Measure every compartment in the toolbox drawers by hand. | Tedious, easy to mis-record. |
| 2 | Record the measurements in a Word table (`Box.docx`) that mimics the drawer layout. | Layout lives only in a document; nothing is computed from it. |
| 3 | Open `Box.scad` in OpenSCAD, edit `length` and `width` by hand, export an STL, repeat. | One export per size (19 sizes so far). Repetitive and error-prone. |
| 4 | Import every STL into PrusaSlicer one by one, arrange them to match the drawer. | Slow; layout has to be re-created by eye. |
| 5 | Export G-code, copy to USB, print. | Fine; stays manual. |

**Goal of this app:** replace steps 2 and 3 (and make step 4 shorter) with one tool:

1. The user describes the drawer as **vertical columns**, each filled with **boxes stacked front to back**.
2. The app shows a live 2D top view of that layout.
3. One click injects the dimensions into the OpenSCAD template, runs the OpenSCAD CLI, and returns the STLs
   (individually or as a ZIP).

Out of scope (still manual): slicing, G-code, printing.

---

## 2. Reference files supplied by the author

Put copies of these in the repo. They are the ground truth for behaviour and test data.

| File | Role | In this repo |
|---|---|---|
| `Box.scad` | The one and only box template. Only `length` and `width` were edited per STL. | `templates/box.scad` |
| `Box.docx` | A 9x6 Word table mimicking the drawer layout. Each cell is one box. | `examples/seed_from_box_docx.json` (already converted) |
| `image.png` (Windows Explorer screenshot) | The 19 STL files that were produced manually. Defines the **file naming convention**. | see §2.3 |

### 2.1 `Box.scad` (the template)

```openscad
// Open-top box with rounded vertical corners and a partial top cover
length = 115;   // mm
width  = 127;   // mm
height = 40;    // mm
wall   = 2;       // wall and floor thickness
r      = 4;       // outer corner radius (must be greater than wall)

cover_width = 32;    // how far the cover extends inward from the long wall
cover_thick = wall;  // cover thickness, flush with the top

$fn = 64;

module rounded_box(l, w, h, rad) {
    hull() {
        for (x = [rad, l - rad], y = [rad, w - rad])
            translate([x, y, 0]) cylinder(r = rad, h = h);
    }
}

union() {
    difference() {                                   // the box
        rounded_box(length, width, height, r);
        translate([wall, wall, wall])
            rounded_box(length - 2*wall, width - 2*wall, height, r - wall);
    }
    intersection() {                                 // partial top cover
        rounded_box(length, width, height, r);
        translate([0, 0, height - cover_thick])
            cube([length, cover_width, cover_thick]);
    }
}
```

Facts the implementation must respect:

* The box occupies `X: 0..length`, `Y: 0..width`, `Z: 0..height` (origin at one corner, not centred).
* The cover is a strip along the **Y = 0 edge**: it spans the full `length` in X and extends `cover_width`
  into Y. It is flush with the top and `cover_thick` thick. It is the partial lid a finger/tool slips under.
* Only these top-level variables are meant to be injected: `length`, `width`, `height`, `wall`, `r`,
  `cover_width`, `cover_thick`. `$fn` stays as-is (a user "quality" setting may override it).
* `cover_thick = wall;` is an **expression**, not a number. Leave it alone unless the user overrides it.
* The file uses CRLF line endings and has no trailing newline. Read with universal newlines, write `\n`.
* Defaults in the file: length 115, width 127, height 40, wall 2, r 4, cover_width 32.

### 2.2 `Box.docx` (the layout table), and how to read it

The Word document contains **one 9-row x 6-column table**. Each non-empty cell reads `A X B` optionally
followed by a single letter, e.g. `102.5X87.5 P`. Observed structure:

* **Each table column is a vertical strip of the drawer.** All cells in a table column share the same `B`
  value (115 or 87.5), so `B` is the **strip (column) width**.
* **Cells going down a table column are boxes stacked front to back.** `A` varies from cell to cell, so
  `A` is the **box's depth along the stack**.
* Cells with a *vertical merge* (`vMerge`) are **one box**, not several. (Col 1 rows 1-2 is one
  `102.5X115`; Col 4 rows 2-4 is one `96X87.5`.) Count a merged cell once.
* Row heights in Word are uniform and **do not** represent physical size. Treat the table as a topology
  (which boxes are in which column, in what order), not as a scaled drawing.
* Empty cells are just unused table space.
* Cell shading colours seem to group identical sizes (e.g. yellow = `43.5X87.5`, light blue = `67.8X115`).
  The trailing letters `D`, `P`, `C` are per-box markers whose meaning is **not documented**. See §13.

Extracted result (merged cells counted once, boxes listed top to bottom):

| Column | Width `B` | Boxes (`A`, qty, marker) | Sum of `A` |
|---|---|---|---|
| 1 | 115 | 102.5 D, 67.8 D x3, 43.5 C, 67.8 D x2, 58.5 D | 543.5 |
| 2 | 87.5 | 102.5 P, 67.8 D, 43.5 x5, 43.5 C, 58.5 D | 489.8 |
| 3 | 87.5 | 102.5 P, 96, 67.8 D, 43.5 x5, 58.5 D | 542.3 |
| 4 | 87.5 | 102.5 P, 96, 67.8 x4, 84 P | 553.7 |
| 5 | 87.5 | 205, 145, 120, 109.5 | 579.5 |
| 6 | 115 | 127, 119, 93.5, 117.5, 109.5 | 566.5 |

Sum of column widths = 115 + 87.5x4 + 115 = **580 mm**, and column 5's stack is 579.5 mm, so the drawer
interior is probably about **580 x 580 mm** (unconfirmed, §13). Other columns end short of that;
the app should show the leftover as empty space, not as an error.

Total boxes: 8+9+9+7+4+5 = **42 boxes**, **19 unique sizes**.

### 2.3 The STL screenshot: naming convention and sanity data

The screenshot lists 19 files, all about 27 KB (same facet count, since only extents change):

`43.5X87.5, 43.5X115, 58.5X87.5, 58.5X115, 67.8X87.5, 67.8X115, 84X87.5, 93.5X115, 96X87.5, 102.5X87.5,
102.5X115, 109.5X87.5, 109.5X115, 117.5X115, 119X115, 120X87.5, 127X115, 145X87.5, 205X87.5` (`.stl`)

These are exactly the 19 unique `A X B` pairs in the Word table (verified).

**Naming rule: `{A}X{B}.stl` = `{width}X{length}.stl`**, using the scad variable names. Proof: the template's
defaults (length 115, width 127) correspond to the file `127X115.stl`, which exists. Format numbers with no
trailing zeros (`87.5`, `96`, not `96.0`), uppercase `X`, no spaces.

---

## 3. Domain model and terminology (read this before coding)

Two coordinate vocabularies exist. The code must keep them straight.

| UI / data-model term | Meaning | OpenSCAD variable | Word-table role |
|---|---|---|---|
| **column width** | Width of a vertical strip of the drawer; all boxes in it share it. | `length` (X) | `B` (115 / 87.5) |
| **box depth** | Extent of one box along the stack direction (front to back). | `width` (Y) | `A` |
| **qty** | Number of identical boxes in a row of the column table. | n/a | repeated cells |
| **tag** | Optional one-letter marker (D/P/C...). Stored and displayed, no logic. | n/a | trailing letter |

So a box in plan view has **x-extent = column width = scad `length`** and **y-extent = box depth = scad
`width`**. Plan view convention: columns run left to right; boxes stack top to bottom; each box's cover
strip is drawn on its **top** edge (that is the scad Y = 0 edge).

### 3.1 Data model (Pydantic v2; JSON-serialisable; this is also the save-file format)

```jsonc
{
  "version": 1,
  "drawer":   { "width": 580, "depth": 580 },       // mm; total across columns / along stack
  "defaults": { "height": 40, "wall": 2, "r": 4,
                "cover_enabled": true, "cover_width": 32 },
  "columns": [
    { "name": "Col 1", "width": 115,                 // column width -> scad length
      "boxes": [
        { "depth": 102.5, "qty": 1, "tag": "D" },    // depth -> scad width
        { "depth": 67.8,  "qty": 3, "tag": "D",
          "height": null }                           // optional per-row overrides
      ] }
  ]
}
```

* Per-box-row optional overrides: `height`, `wall`, `r`, `cover_enabled`, `cover_width`. `null` means
  "use `defaults`".
* A box row with `qty = 3` is **three identical boxes** in the preview, but **one compile job** (§6.3).
* Real file: `examples/seed_from_box_docx.json` is the author's drawer, converted from `Box.docx`. Load it
  as the default demo/project.

### 3.2 Derived values

* `BoxSpec` (resolved, immutable, hashable): `length, width, height, wall, r, cover_enabled, cover_width`.
  `length` comes from the column, `width` from the box row, the rest from overrides or defaults.
* Per column: `used_depth = sum(depth * qty)`, `leftover = drawer.depth - used_depth`.
* Drawer: `used_width = sum(column.width)`, `leftover = drawer.width - used_width`.
* Negative leftover = **overflow**, a warning (not a blocker; the author may want to see it).

---

## 4. Technology decision (requirements, not suggestions)

**Framework: Streamlit** (single Python process, `streamlit run app.py`).

Why Streamlit rather than FastAPI:

* The UI is mostly editable tables and a preview; `st.data_editor` gives an Excel-like per-column grid with
  almost no code.
* No frontend build step, no JS toolchain, one command to run locally. The user is a hobbyist, not a web dev.
* Download buttons (`st.download_button`) and session state cover all delivery needs.

FastAPI is explicitly **not** used in v1. To keep that door open, **all logic lives in a framework-free
`core/` package** (no `import streamlit` there). `app.py` is a thin UI layer. A future FastAPI wrapper would
just import `core`.

| Concern | Decision |
|---|---|
| Language | Python **3.10+** |
| UI | **Streamlit >= 1.40** (`st.data_editor`, `st.session_state`, `st.download_button`, `st.html`/`components.html`) |
| Validation / models | **Pydantic v2** |
| Tabular editing | `pandas` (only as the `data_editor` data container) |
| 2D preview | **Hand-generated inline SVG** (no JS libs, crisp, scalable, hover tooltips via `<title>`) |
| CAD engine | **OpenSCAD CLI**, called through `subprocess.run([...])` as a list (never `shell=True`) |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` (subprocesses do the real work) |
| ZIP | stdlib `zipfile` (in memory with `io.BytesIO`) |
| Persistence | Project JSON (download / upload), plus last-session autosave to `data/last_project.json` |
| Tests | `pytest` |
| Platform | Windows 10/11 primary (the author's setup); macOS/Linux must also work |

External prerequisite (not pip-installable): **OpenSCAD 2021.01 or newer** installed locally. Prefer the
2024+ snapshot, where `--backend=Manifold` is much faster. The app must detect it (§7.1).

`requirements.txt` (file is included in this repo):

```
streamlit>=1.40,<2
pydantic>=2.7,<3
pandas>=2.2
pytest>=8.0
python-docx>=1.1      # only for the optional tools/import_docx.py
```

---

## 5. Project structure

```
box-generator/
├── README.md                    # this file
├── requirements.txt
├── app.py                       # Streamlit UI only; calls core/*
├── core/
│   ├── __init__.py
│   ├── models.py                # Pydantic models: Project, Column, BoxRow, Defaults, BoxSpec
│   ├── layout.py                # resolve project -> placed boxes, leftover/overflow stats
│   ├── scad_template.py         # load template, inject variables, render standalone .scad
│   ├── naming.py                # fmt_num(), stl_filename(spec)
│   ├── validation.py            # parameter + layout validation -> list of Issue(level, msg)
│   ├── openscad.py              # find executable, run CLI, parse errors, version check
│   ├── builder.py               # dedupe, parallel compile, caching, progress callbacks, BOM
│   ├── preview_svg.py           # layout -> SVG string
│   └── packaging.py             # build ZIP (STLs [+ SCADs] + bom.csv + project.json)
├── templates/
│   └── box.scad                 # copy of Box.scad (the template; do not "improve" its geometry)
├── examples/
│   └── seed_from_box_docx.json  # the author's real drawer
├── tools/
│   └── import_docx.py           # OPTIONAL: Box.docx -> project JSON (rules in §10)
├── data/                        # gitignored: last_project.json
├── output/                      # gitignored: per-job .scad/.stl, plus cache/
└── tests/
    ├── test_naming.py
    ├── test_scad_template.py
    ├── test_layout.py
    ├── test_validation.py
    ├── test_builder.py          # mocks the OpenSCAD runner
    └── test_seed_example.py     # acceptance tests from §11
```

---

## 6. Functional requirements

### 6.1 FR-1: Template integration and variable injection (most important)

* Read `templates/box.scad` **as a string** at startup (cache it).
* Provide `render_scad(template: str, spec: BoxSpec, fn: int | None = None) -> str`.
* **Injection method (required):** rewrite the top-level assignment lines with a regex that preserves the
  trailing comment, so the generated file still reads like the original and can be opened in the OpenSCAD
  GUI for tweaking:

  ```python
  import re

  def set_var(src: str, name: str, value: float | int) -> str:
      pattern = re.compile(rf'^(\s*{re.escape(name)}\s*=\s*)([^;]+)(;.*)$', re.M)
      new, n = pattern.subn(lambda m: f"{m.group(1)}{fmt_num(value)}{m.group(3)}", src, count=1)
      if n != 1:
          raise TemplateError(f"variable '{name}' not found exactly once at top level")
      return new
  ```

  Rules: it must fail loudly (not silently) if a variable is missing; it must **only** touch the first
  top-level assignment; it must not modify `module`/geometry code.
* Variables injected: `length`, `width`, `height`, `wall`, `r`, `cover_width`, and `cover_thick` **only** if
  the user overrides it (otherwise keep `cover_thick = wall;`).
* **Cover disabled:** if `cover_enabled` is false, set `cover_width = 0` (v1 behaviour). A zero-size cube
  can produce a degenerate/warning-producing mesh, so for this case the renderer should instead
  comment out the `intersection() { ... }` block. Implement it by wrapping: the template author marks the
  block with `// [cover:begin]` / `// [cover:end]` sentinel comments (add them to the copy in
  `templates/box.scad`; this is the **only** permitted edit to the template, and it must not change
  geometry). Fall back to `cover_width = 0` if sentinels are absent.
* **Alternative documented for debugging, not the primary path:** OpenSCAD's `-D length=115` CLI override.
  Do not use it as the main mechanism, because the user wants a standalone, readable `.scad` per box.
* Every generated `.scad` begins with a comment header: generation timestamp, `A X B` name, and the
  resolved parameter values.

### 6.2 FR-2: Hierarchical input (columns, then boxes)

**Step 1, drawer and columns.** Inputs: drawer width and depth (mm, informational but used for leftover
math and the preview frame); a list of columns, each with a name and a **column width**. UI: a small
`st.data_editor` (dynamic rows) of `name | width`, plus buttons to add/remove/reorder columns.
The running total width and leftover are shown live.

**Step 2, boxes in each column.** For every column, a sub-table (one `st.data_editor` per column, inside
tabs or expanders) with rows `depth | qty | tag | (optional overrides)`, order = top to bottom in the
preview. Inputs must be validated (positive numbers, integer qty >= 1). The column header shows
`used / drawer depth` and leftover.

**Global parameters** (sidebar or top expander): `height`, `wall`, `r`, `cover_enabled`, `cover_width`,
`$fn` quality (low 32 / normal 64 / high 96). Defaults from `Box.scad`.

**Project I/O:** "Load example" (the seed JSON), "Download project (.json)", "Upload project (.json)".
Autosave to `data/last_project.json` on every change and restore on launch.

### 6.3 FR-3: 2D top-view preview (live)

Rendered on every rerun with the current inputs, from `core/preview_svg.py` and injected via `st.html`.

Must show:

* Drawer outline (to scale, using `drawer.width` x `drawer.depth`).
* Columns as vertical strips left to right; boxes stacked top to bottom, drawn **to scale** with rounded
  corners (radius `r`) and a hatched strip on the top edge (`cover_width`) when the cover is enabled.
* Colour per **unique size** (stable hash of `(depth, column width)` into a palette), so identical sizes
  match across columns, like the shading in `Box.docx`.
* Label inside each box: `A X B` (and the tag if present). Hide the label if the box is too small to fit it.
* Empty/leftover space as a light dashed area; **overflow** (box beyond the drawer edge, or column wider
  than what is left) clipped, tinted red, and listed in a warning.
* A legend/summary: total boxes, unique sizes, used vs leftover width, and per-column used vs leftover depth.
* `<title>` tooltips on each box with full dimensions and resolved parameters.

Preview must be **pure** (no OpenSCAD call) so it responds instantly.

### 6.4 FR-4: Compile with OpenSCAD CLI

* **Deduplicate.** Identical `BoxSpec`s compile **once**. The manual workflow produced one STL per unique
  size, and quantity is only needed when arranging plates. The bill of materials lists the quantity.
* The **build plan** table is shown before compiling: filename | spec | qty | status. Sizes already in the
  disk cache show "cached".
* **Command** (list form, no shell):

  ```
  openscad -o <out>/<name>.stl [--backend=Manifold] <out>/<name>.scad
  ```
  Optional flags: `--export-format binstl` (smaller files than ASCII; recommended if supported).
  Use `--backend=Manifold` only when the detected version supports it (§7.1).
* **Concurrency:** `ThreadPoolExecutor(max_workers=N)`, N in the UI (default `min(4, cpu_count)`).
* **Per job:** timeout 180 s; capture stdout+stderr; success only if `returncode == 0` **and** the STL exists
  and is non-empty. Any failure is reported per file with the OpenSCAD log in an expander; one failure
  must not abort the rest.
* **Progress:** a `st.progress` bar plus a live per-file status list, updated through a callback from
  `builder`.
* **Cache:** key = SHA-256 of the rendered `.scad` text + OpenSCAD version + `$fn`. Cache path
  `output/cache/<key>.stl`. "Force rebuild" checkbox bypasses it.
* Output folder per run: `output/<YYYYmmdd-HHMMSS>/` containing `*.scad`, `*.stl`, `bom.csv`, `project.json`.
* File-name collisions: impossible because of dedupe; if two different specs map to the same name (e.g. same
  `A X B` but different `height`), append a suffix such as `_h30`. Rule: the plain `A X B` name is used when
  the height/wall/r/cover are the defaults, else append a short parameter suffix.

### 6.5 FR-5: Download

* After a run, show **per-file** `st.download_button`s (one per STL) and a primary **"Download all (ZIP)"**.
* ZIP layout: `stl/*.stl`, optionally `scad/*.scad` (checkbox), `bom.csv`, `project.json`.
* `bom.csv` columns: `filename,width_A,length_B,height,wall,r,cover_width,qty,columns` (`columns` lists
  which columns use it, e.g. `Col 1; Col 6`). This doubles as the **plate-arrangement cheat sheet**
  for PrusaSlicer.
* Results live in `st.session_state` so reruns (widget clicks) do not lose or recompile them.

### 6.6 Non-functional requirements

* Starts with one command and no network access. All paths via `pathlib`.
* A bad input never crashes the app; show `st.error` / `st.warning` with a clear message.
* The preview and validation recompute in well under 200 ms for 100 boxes.
* Core is unit-testable without Streamlit or OpenSCAD (the runner is injectable/mocked).
* Type hints throughout; no global mutable state outside `st.session_state`.
* Logging via `logging` (file `output/app.log`).

---

## 7. Module specifications

### 7.1 `core/openscad.py`

* `find_openscad(user_path: str | None) -> Path | None`; search order:
  1. `user_path` (sidebar field), 2. env var `OPENSCAD_PATH`, 3. `shutil.which("openscad")` /
  `openscad.com`, 4. Windows defaults: `C:\Program Files\OpenSCAD\openscad.exe`,
  `C:\Program Files\OpenSCAD (Nightly)\openscad.exe`, 5. macOS:
  `/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD`, Linux: `/usr/bin/openscad`, snap/flatpak paths.
  On Windows prefer `openscad.com` (console build) when present, since it returns proper exit codes and
  streams output.
* `get_version(exe) -> str` via `openscad --version` (it prints to stderr on some versions).
* `supports_manifold(version) -> bool` (2024.x+ / nightly).
* `compile_scad(exe, scad: Path, stl: Path, *, timeout=180, manifold=False, binary=False) -> RunResult`
  (`ok, returncode, stdout, stderr, seconds`).
* The sidebar shows "OpenSCAD found: vX at <path>" in green, or a red banner with install instructions and a
  path field, and **disables** the Generate button until found.

### 7.2 `core/layout.py`

`place(project) -> Layout` with `PlacedBox(spec, column_idx, x, y, w, h, index_in_column, tag)` and
stats (per-column used/leftover, drawer used/leftover, overflow list). Columns advance in X by column width;
boxes advance in Y by depth. `qty` expands to repeated placed boxes.

### 7.3 `core/validation.py`

Return `list[Issue]` with `level in {"error","warning"}`. **Errors block compilation; warnings do not.**

| Rule | Level |
|---|---|
| `length, width, height, wall, r > 0`; `qty` integer >= 1 | error |
| `r > wall` (template comment: "must be greater than wall") | error |
| `2*r <= min(length, width)` (hull of corner circles degenerates) | error |
| `height > wall` | error |
| `length > 2*wall` and `width > 2*wall` | error |
| `cover_width < width - wall` (cover must not close the whole top) | error |
| `cover_thick <= height - wall` | error |
| Remaining opening `width - cover_width < 10` mm (hard to reach in) | warning |
| Column used depth > drawer depth, or total column width > drawer width (overflow) | warning |
| Box smaller than 20 mm in any direction | warning |
| Very large box (> 250 mm) may exceed the print bed | warning |

Note: with the seed data the smallest box is `43.5` deep and `cover_width = 32`, leaving 11.5 mm open, so the
11.5 mm case must stay a *pass*. Choose thresholds accordingly.

### 7.4 `core/naming.py`

* `fmt_num(x)`: `87.5 -> "87.5"`, `96.0 -> "96"`, `115 -> "115"`; avoid float noise (`round(x, 3)` then strip).
* `stl_filename(spec) -> "{fmt(width)}X{fmt(length)}.stl"` (+ suffix rule from §6.4).

### 7.5 `core/builder.py`

`plan(project) -> list[Job]` (dedupe + qty + columns used), `run(plan, exe, options, on_progress) -> Results`.
Pure orchestration; the OpenSCAD call goes through an injectable function for tests.

### 7.6 `core/preview_svg.py`

`render_svg(layout, *, scale=None, max_px=1100) -> str`. Fit the drawer into a max pixel width; keep
`viewBox` in mm units so tooltips/labels stay simple; use `rx/ry` for rounded corners; use an SVG
`<pattern>` for the cover hatch.

---

## 8. UI specification (`app.py`)

```
┌ Sidebar ─────────────┐ ┌ Main ───────────────────────────────────────────┐
│ OpenSCAD status      │ │ 1. Drawer & columns   [table: name | width]     │
│ [path override]      │ │ 2. Boxes per column   [tabs: one grid each]     │
│ Global params        │ │ 3. Preview (SVG, live) + summary + warnings     │
│  height wall r       │ │ 4. Build plan table (dedupe, qty, cached?)      │
│  cover on/off, width │ │    [Generate STLs]  progress + per-file status  │
│  quality ($fn)       │ │ 5. Downloads: per file + [Download all (ZIP)]   │
│  workers, force      │ └─────────────────────────────────────────────────┘
│ Load example/Save/Up │
└──────────────────────┘
```

Behavioural rules:

* Editing any input updates preview, stats and warnings immediately (normal Streamlit rerun).
* **Generate STLs** is disabled while there are validation **errors** or OpenSCAD is missing.
* Compilation happens **only** on button click (never on rerun). Results persist in `st.session_state`.
* UI language: English. (The author's OS is Korean; keep strings in one dict so a Korean version is easy.)
* Use `st.set_page_config(layout="wide")`.

---

## 9. Setup and run

```bash
# 1. Install OpenSCAD (https://openscad.org/downloads.html); the 2024+ snapshot is recommended.
# 2. Python 3.10+
cd box-generator
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
streamlit run app.py              # opens http://localhost:8501
```

If OpenSCAD is not on `PATH`, either set `OPENSCAD_PATH` or paste the full path into the sidebar field.
Run tests with `pytest -q`. `.gitignore`: `.venv/`, `data/`, `output/`, `__pycache__/`.

---

## 10. Optional tool: import `Box.docx`

`tools/import_docx.py <Box.docx> -> project.json` (the result is already saved as
`examples/seed_from_box_docx.json`; this tool lets the author re-import after editing the Word file).

Parsing rules (derived from §2.2):

1. Use `python-docx`; walk `table._tbl.tr_lst` and `tr.tc_lst` (**not** `table.rows[i].cells`, which
   repeats merged cells).
2. Skip any `w:tc` whose `w:vMerge` is present and not `restart` (continuation cell).
3. Match cell text with `^\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*([A-Za-z])?\s*$`
   -> `A` (depth), `B` (column width), optional tag.
4. Group by table column index; assert every `B` in a column is identical, otherwise warn.
5. Merge **consecutive** equal `(A, tag)` entries into one row with `qty`.
6. Set `drawer.width = sum(column widths)`, `drawer.depth = max(column used depth)`, then let the user edit.

---

## 11. Acceptance tests (must pass)

Using `examples/seed_from_box_docx.json` and the default parameters:

1. **Boxes and sizes:** 6 columns, **42 boxes**, **19 unique sizes**.
2. **Filenames:** the set of generated names equals exactly the 19 names in §2.3 (case and number format
   included, e.g. `96X87.5.stl`, not `96.0X87.5.stl`).
3. **Default render:** `render_scad` with `length=115, width=127, height=40` reproduces the original
   `Box.scad` assignments (only whitespace/CRLF differences allowed).
4. **Injection:** for `43.5X87.5` the generated file contains `length = 87.5;` and `width  = 43.5;`
   (note: A goes to `width`, B to `length`) and still ends with the original geometry code, unchanged.
5. **Missing variable:** a template lacking `wall` raises `TemplateError`.
6. **Column maths:** column sums equal 543.5, 489.8, 542.3, 553.7, 579.5, 566.5 (floating-point tolerant);
   total width = 580.
7. **Validation:** `r = 2` with `wall = 2` -> error; `cover_width = 43.5` on a 43.5-deep box -> error;
   the seed data with defaults -> **no errors**.
8. **Dedupe:** quantities are expanded in the preview but compiled once (mock runner called 19 times, not 42).
9. **Failure isolation:** a mock runner failing for one job still yields the other 18 STLs plus an error entry.
10. **ZIP:** contains 19 `.stl` files (when all succeed), `bom.csv`, `project.json`; BOM quantities sum to 42.
11. **Integration (only if OpenSCAD is installed, otherwise skip):** compile `127X115` and check the STL
    exists, is non-empty, and its bounding box is approximately 115 x 127 x 40 mm.

---

## 12. Non-goals and roadmap

Not in v1: automatic bin packing; nesting STLs on a print plate / 3MF export (PrusaSlicer arrangement stays
manual, though `bom.csv` helps); G-code; user accounts; a database; Docker.

Possible later, in this order:

1. Export a **3MF plate** per column (pre-arranged), cutting step 4 of the manual workflow further.
2. A `cover_side` option (cover on the opposite edge or on a short wall), implemented as an additional
   template variable.
3. 3D preview (`three.js` via STL) and per-box "dividers" / label recess.
4. A FastAPI wrapper over `core/` plus a small JS front end.

---

## 13. Open questions (assumptions made; confirm with the author)

| # | Question | Assumption used |
|---|---|---|
| 1 | What do the letters **D / P / C** in `Box.docx` mean? (Perhaps Done / Printing / Cancelled-or-Changed.) | Treated as a free-text one-letter **tag**: stored, shown in the label, no logic. |
| 2 | What do the **cell colours** mean? | Interpreted as "same size group"; the preview auto-colours by size instead. |
| 3 | True drawer interior size? Columns sum to 580 mm wide; the longest stack is 579.5 mm. | `drawer = 580 x 580`, editable. |
| 4 | Should the cover strip always sit on the Y = 0 edge, and does every box want a cover? | Yes by default (as in `Box.scad`); a per-box `cover_enabled` toggle exists. |
| 5 | Is a 3 mm-ish clearance between boxes and drawer walls or between boxes needed? | No; boxes are placed flush (`gap = 0`). A `gap` setting may be added later. |
| 6 | Is the `$fn = 64` mesh quality fine for the printer? | Yes; exposed as a quality setting. |
| 7 | Do boxes in a column ever need a different length than the column width? | No; the invariant `box length == column width` holds in all 42 cells. |
