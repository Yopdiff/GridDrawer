# Toolbox Drawer Box Generator

A local web app that turns **measured drawer dimensions** into **ready-to-slice STL files** for open-top,
rounded-corner boxes, using the author's existing OpenSCAD template (`templates/box.scad`).

> This README is the source of truth. An AI coder should be able to build the whole app from this document
> plus the reference files in §2. If code and README disagree, fix one deliberately.

## Contents

1. [Overview](#1-overview) · 2. [Reference inputs](#2-reference-inputs) · 3. [Domain model](#3-domain-model) ·
4. [Stack and structure](#4-stack-and-structure) · 5. [Backend](#5-backend) · 6. [Frontend](#6-frontend) ·
7. [Setup and run](#7-setup-and-run) · 8. [Acceptance tests](#8-acceptance-tests) · 9. [Extras and roadmap](#9-extras-and-roadmap)

---

## 1. Overview

**Today (manual):** measure each drawer compartment, record it in a Word table (`Box.docx`), edit `length` and
`width` in `Box.scad` by hand and export one STL per size (19 so far), import every STL into PrusaSlicer and
arrange them by eye, export G-code, print.

**This app replaces the Word table and the manual OpenSCAD edits, and shortens the slicer arrangement:**

1. Describe the drawer as **vertical columns**, each filled with **boxes stacked front to back**.
2. See a live, to-scale 2D top view of the layout.
3. One click injects the dimensions into the OpenSCAD template, runs the OpenSCAD CLI, and returns the STLs
   (individually or as a ZIP).

Still manual: slicing, G-code, printing.

**Scope: a single-user tool on the author's own Windows PC.** No accounts, hosting, Docker, HTTPS, CORS or
database. The server binds to `127.0.0.1`, runs **one build at a time**, and keeps only the latest build.
Prefer the simplest thing that works. Still required: input validation, clear error messages, and a failed
STL never stops the others.

---

## 2. Reference inputs

| File | Role | In this repo |
|---|---|---|
| `Box.scad` | The one box template; only `length` and `width` were edited per STL. | `templates/box.scad` (unmodified) |
| `Box.docx` | 9x6 Word table mimicking the drawer layout; each cell is one box. | `examples/seed_from_box_docx.json` (converted) |
| Explorer screenshot | The 19 STLs made manually; defines the file naming. | §2.3 |

### 2.1 `Box.scad`

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

* The box occupies `X: 0..length`, `Y: 0..width`, `Z: 0..height` (corner origin, not centred).
* The cover is a strip along the **Y = 0 edge**: full `length` in X, `cover_width` deep in Y, flush with the top.
* Injected variables: `length`, `width`, `height`, `wall`, `r`, `cover_width`. `cover_thick = wall;` is an
  expression; leave it. `$fn` is set from the quality setting.
* The file has CRLF line endings and no trailing newline: read with universal newlines, write `\n`.
* Defaults in the file: length 115, width 127, height 40, wall 2, r 4, cover_width 32.

### 2.2 `Box.docx`

One 9-row x 6-column table. Each non-empty cell reads `A X B` (some have a trailing letter such as `P`; those
letters are the author's private notes: **ignore them**).

* **Each table column is a vertical strip of the drawer**; all its cells share the same `B` (115 or 87.5), the
  **column width**.
* **Cells going down a column are boxes stacked front to back**; `A` is the **box depth**.
* A *vertically merged* cell (`vMerge`) is **one box**; count it once.
* Row heights in Word are uniform and mean nothing. The table is a topology (which boxes, in which column, in
  what order), not a scaled drawing. Empty cells are unused space.
* **Cell colours mark boxes of the same size.** The app reproduces this by colouring identical sizes alike.

Extracted (merged cells counted once, top to bottom):

| Column | Width `B` | Boxes (`A`, quantity) | Sum of `A` |
|---|---|---|---|
| 1 | 115 | 102.5, 67.8 x3, 43.5, 67.8 x2, 58.5 | 543.5 |
| 2 | 87.5 | 102.5, 67.8, 43.5 x6, 58.5 | 489.8 |
| 3 | 87.5 | 102.5, 96, 67.8, 43.5 x5, 58.5 | 542.3 |
| 4 | 87.5 | 102.5, 96, 67.8 x4, 84 | 553.7 |
| 5 | 87.5 | 205, 145, 120, 109.5 | 579.5 |
| 6 | 115 | 127, 119, 93.5, 117.5, 109.5 | 566.5 |

Column widths sum to **580 mm** and the longest stack is 579.5 mm, so the default drawer is **580 x 580 mm**
(editable). Shorter columns leave empty space, which is not an error. Total: **42 boxes, 19 unique sizes**.

### 2.3 STL names

The 19 manual files (about 27 KB each, since only extents change):

`43.5X87.5, 43.5X115, 58.5X87.5, 58.5X115, 67.8X87.5, 67.8X115, 84X87.5, 93.5X115, 96X87.5, 102.5X87.5,
102.5X115, 109.5X87.5, 109.5X115, 117.5X115, 119X115, 120X87.5, 127X115, 145X87.5, 205X87.5` (`.stl`)

They are exactly the 19 unique `A X B` pairs in the Word table.

**Naming rule: `{width}X{length}.stl`** (scad variable names; `A` = width, `B` = length). Check: the template's
defaults (length 115, width 127) are the existing file `127X115.stl`. Numbers have no trailing zeros
(`87.5`, `96`, not `96.0`); uppercase `X`; no spaces.

---

## 3. Domain model

### 3.1 Terms and axes

| Term | Meaning | OpenSCAD | Word table |
|---|---|---|---|
| **column width** | Width of a vertical strip; every box in it has this length. | `length` (X) | `B` |
| **box depth** | Extent of a box along the stack (front to back). | `width` (Y) | `A` |
| **quantity** | Identical boxes in one row of a column. | n/a | repeated cells |
| **cover width** | Derived from depth (§3.3), never entered per box. | `cover_width` | n/a |

In plan view: columns run left to right, boxes stack top to bottom, and each box's cover strip is on its **top**
edge (scad Y = 0). Boxes are placed flush: the author's measurements already include any margin, so there is
no clearance or gap setting.

### 3.2 Data model

Pydantic v2 models; the JSON below is also the project save-file format.

```jsonc
{
  "version": 1,
  "drawer":   { "width": 580, "depth": 580 },       // mm; frame and leftover display only
  "defaults": { "height": 40, "wall": 2, "r": 4,
                "cover_width": 32,                    // normal cover
                "cover_width_short": 28,              // about 1 inch, for shallow boxes
                "short_depth_below": 45 },            // depth < 45 mm -> short cover
  "columns": [
    { "name": "Col 1", "width": 115,                 // -> scad length
      "boxes": [
        { "depth": 102.5, "qty": 1 },                // -> scad width
        { "depth": 67.8,  "qty": 3 }
      ] }
  ]
}
```

* All parameters are global (no per-box overrides), so every file in a build shares them.
* A row with `qty = 3` is three boxes on the canvas but **one compile job**.
* `examples/seed_from_box_docx.json` is the author's drawer; it is the demo project.
* `BoxSpec` (resolved, immutable, hashable): `length, width, height, wall, r, cover_width`.

Derived values (`core/layout.py`, `place(project) -> Layout`):

* Each box is placed at `x = sum of previous column widths`, `y = sum of previous depths in its column`;
  `qty` expands to repeated boxes.
* Per column `leftover = drawer.depth - sum(depth * qty)`; drawer `leftover = drawer.width - sum(column widths)`.
  Negative leftover is **overflow**: a warning, not a blocker.

### 3.3 Cover rule

Every box has the cover. Its width depends on the box depth:

```
cover_width = 28  if depth < 45
            = 32  otherwise          # depth of exactly 45 uses 32
```

The three numbers are editable in the sidebar. In the author's drawer only the `43.5`-deep boxes use the short
cover (15.5 mm opening instead of 11.5 mm).

---

## 4. Stack and structure

**Back end: FastAPI. Front end: one static page of plain HTML + CSS + vanilla JavaScript.** Light and simple:
two runtime pip packages, no build step, no Node, no JS framework, no CDN (works offline).

Streamlit was rejected: the main screen is a custom interactive canvas (hover "+" buttons, dialogs, drag and
drop), which Streamlit cannot do natively, and it adds heavy dependencies and page reloads.

| Concern | Decision |
|---|---|
| Languages | Python 3.10+ (server); ES2020 JavaScript, no bundler/transpiler (browser) |
| Server | FastAPI + uvicorn; serves `web/` and a small JSON API |
| Models/validation | Pydantic v2 |
| Canvas | DOM/CSS blocks positioned in mm-scaled pixels (inline SVG also acceptable) |
| CAD engine | OpenSCAD CLI via `subprocess.run([...])` (list form, never `shell=True`) |
| Concurrency | `ThreadPoolExecutor`; build runs in the background, page polls |
| ZIP | stdlib `zipfile` in memory |
| State | Project JSON lives in the browser (`localStorage` autosave + `.json` download/upload) |
| Tests | `pytest` (+ `httpx` for the optional API test) |
| Platform | Windows 10/11 primary; macOS/Linux should also work |

**Prerequisite (not pip):** OpenSCAD 2021.01+ installed; the 2024+ snapshot is preferred (`--backend=Manifold`
is much faster).

`requirements.txt`:

```
fastapi>=0.115,<1
uvicorn>=0.30,<1
pydantic>=2.7,<3
pytest>=8.0
httpx>=0.27            # tests only
python-docx>=1.1       # only for tools/import_docx.py
```

All logic lives in a framework-free `core/` package (no `import fastapi`); `app.py` and `web/` are thin layers.

```
box-generator/
├── README.md
├── requirements.txt
├── run.bat                      # Windows launcher: venv, start uvicorn, open browser
├── app.py                       # FastAPI: JSON API + serves web/
├── core/
│   ├── models.py                # Project, Column, BoxRow, Defaults, BoxSpec
│   ├── layout.py                # place(), leftover/overflow stats, move_box()
│   ├── scad_template.py         # load template, inject variables, render .scad
│   ├── naming.py                # fmt_num(), stl_filename()
│   ├── validation.py            # list of Issue(level, msg)
│   ├── openscad.py              # find executable, version, run CLI
│   ├── builder.py               # plan (dedupe), parallel compile, cache, BOM
│   └── packaging.py             # ZIP
├── web/                         # index.html, style.css, app.js (no build step)
├── templates/box.scad           # the template, unmodified
├── examples/seed_from_box_docx.json
├── tools/import_docx.py         # optional (§9)
├── output/                      # gitignored: per-build files and cache/
└── tests/                       # one test file per core module, plus test_seed_example.py (§8)
```

---

## 5. Backend

### 5.1 Template injection (most important)

* Read `templates/box.scad` as a string once at startup. `render_scad(template, spec, fn=None) -> str`.
* **Method (required):** rewrite the top-level assignment lines with a regex that keeps the trailing comment,
  so each generated `.scad` still reads like the original and opens in the OpenSCAD GUI:

  ```python
  def set_var(src: str, name: str, value: float | int) -> str:
      pattern = re.compile(rf'^(\s*{re.escape(name)}\s*=\s*)([^;]+)(;.*)$', re.M)
      new, n = pattern.subn(lambda m: f"{m.group(1)}{fmt_num(value)}{m.group(3)}", src, count=1)
      if n != 1:
          raise TemplateError(f"variable '{name}' not found exactly once at top level")
      return new
  ```

  It fails loudly on a missing variable, touches only the first top-level assignment, and never edits modules
  or geometry. (OpenSCAD's `-D length=115` override works too but is not the primary path, because a
  standalone readable `.scad` per box is wanted.)
* Each generated `.scad` starts with a comment header: timestamp, `A X B` name, resolved values.

### 5.2 Validation (`core/validation.py`)

`list[Issue]` with `level` of `error` or `warning`. **Errors block building; warnings do not.**

| Rule | Level |
|---|---|
| `length, width, height, wall, r > 0`; `qty` integer >= 1 | error |
| `r > wall` (template comment) | error |
| `2*r <= min(length, width)` | error |
| `height > wall`; `length > 2*wall`; `width > 2*wall` | error |
| `cover_width < width - wall`; `cover_thick <= height - wall` | error |
| Opening `width - cover_width < 10` mm | warning |
| Column used depth > drawer depth, or column widths > drawer width | warning |
| Box under 20 mm in any direction, or over 250 mm (print bed) | warning |

The seed project with default settings must produce **no errors and no warnings** about boxes (the 43.5 box
has a 15.5 mm opening).

### 5.3 Build pipeline (`core/builder.py`)

* `plan(project) -> list[Job]`: **dedupe** identical `BoxSpec`s (one STL per unique size; quantity only appears
  in the BOM), each with its qty and the columns using it. File names are unique because parameters are global
  and `cover_width` is a function of depth.
* `run(plan, exe, options, on_progress)`: orchestration only; the OpenSCAD call is an injectable function so
  tests can mock it.
* **Command:** `openscad -o <out>/<name>.stl [--backend=Manifold] [--export-format binstl] <out>/<name>.scad`.
  Use Manifold only when the detected version supports it; binary STL is smaller.
* **Per job:** timeout 180 s; capture stdout and stderr; success only if exit code is 0 **and** the STL exists
  and is non-empty. A failure is reported per file with the log; the rest continue.
* **Concurrency:** `ThreadPoolExecutor(max_workers=N)`, N from the sidebar (default `min(4, cpu_count)`).
* **Cache:** key = SHA-256 of rendered `.scad` text + OpenSCAD version + `$fn`; file `output/cache/<key>.stl`;
  a "force rebuild" option bypasses it.
* **Output:** `output/<YYYYmmdd-HHMMSS>/` with `*.scad`, `*.stl`, `bom.csv`, `project.json`.

### 5.4 OpenSCAD runner (`core/openscad.py`)

* `find_openscad(user_path)` search order: sidebar path, env `OPENSCAD_PATH`, `PATH` (`openscad.com` /
  `openscad`), Windows defaults (`C:\Program Files\OpenSCAD\`, `...\OpenSCAD (Nightly)\`), macOS
  (`/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD`), Linux (`/usr/bin/openscad`, snap, flatpak). On
  Windows prefer `openscad.com` (console build: proper exit codes and output).
* `get_version(exe)` via `--version` (may print to stderr); `supports_manifold(version)` for 2024.x+.
* `compile_scad(exe, scad, stl, *, timeout=180, manifold=False, binary=False) -> RunResult`
  (`ok, returncode, stdout, stderr, seconds`).

### 5.5 Naming, packaging and downloads

* `fmt_num(x)`: `87.5 -> "87.5"`, `96.0 -> "96"`; `round(x, 3)` then strip zeros.
  `stl_filename(spec) = f"{fmt_num(width)}X{fmt_num(length)}.stl"`.
* ZIP: `stl/*.stl`, optional `scad/*.scad`, `bom.csv`, `project.json`.
* `bom.csv`: `filename,width_A,length_B,height,wall,r,cover_width,qty,columns` (`columns` like `Col 1; Col 6`).
  It doubles as the plate-arrangement cheat sheet for PrusaSlicer.
* The latest build stays available (memory and `output/<run>/`) until the next starts, so a page reload loses
  nothing.

### 5.6 HTTP API (`app.py`)

Stateless apart from the latest build (one global object). The client sends the project on each call.

| Method and path | Purpose |
|---|---|
| `GET /`, `/static/*` | Serve `web/` |
| `GET /api/example` | The seed project |
| `GET /api/status` | `{openscad: {found, path, version, manifold}}` |
| `PUT /api/openscad-path` | Override the OpenSCAD path for this run; returns status |
| `POST /api/validate` | Project in; `{issues:[{level,msg,where}], stats}` out |
| `POST /api/plan` | Project in; deduped jobs (filename, spec, qty, columns, cached?) out |
| `POST /api/build` | `{project, options:{workers, force, include_scad, fn}}`; 422 on validation errors, missing OpenSCAD, or a build already running; starts a background build |
| `GET /api/build` | Latest build: `{state: idle\|running\|done\|failed, done, total, items:[{filename,status,seconds,log}]}` |
| `GET /api/build/files/{filename}` | One STL (attachment) |
| `GET /api/build/zip?include_scad=` | The ZIP |

Match requested filenames against the build's known list rather than joining them into a path. Bind to
`127.0.0.1`; no auth, no CORS. API errors are JSON `{detail}`. Use `pathlib` for paths and `logging` to
`output/app.log`. A bad input never crashes the app.

---

## 6. Frontend

### 6.1 Layout (`web/`)

```
┌ Sidebar ───────────────┐ ┌ Main ─────────────────────────────────────────────┐
│ OpenSCAD status        │ │ Your drawer  (hint text)                          │
│ Drawer width / depth   │ │ ┌ drawer canvas (to scale) ─────────────────────┐ │
│ Box parameters         │ │ │ Col 1 │ Col 2 │ ...   hover edge => "+"       │ │
│  height wall r         │ │ │ boxes stacked top to bottom, hover => "+"     │ │
│  cover 32 / 28 mm      │ │ └───────────────────────────────────────────────┘ │
│  quality ($fn)         │ │ summary + warnings                                │
│  workers, force        │ │ [Generate STL files]  build plan + progress       │
│ Load example / Clear   │ │ Downloads: per file + [Download all (ZIP)]        │
│ Save / Upload project  │ └───────────────────────────────────────────────────┘
└────────────────────────┘
```

Sidebar: OpenSCAD status (green "found vX at path", or a red banner with install help and a path field),
drawer size, `height`, `wall`, `r`, cover settings (§3.3), `$fn` quality (low 32 / normal 64 / high 96),
workers, force rebuild, and project actions (load example, clear, save `.json`, upload `.json`). Defaults come
from `Box.scad`. A reference prototype exists as the interactive "Drawer builder" artboard
(https://claude.ai/artifact/R5S6fV7dm5F3Ke75weWBAa); port its markup, CSS and logic to plain JS.

### 6.2 Drawer canvas interaction

1. **Empty drawer first.** The app opens with an empty, to-scale drawer outline and the hint "Hover over the top
   or bottom edge to add a column".
2. **Add column.** Hovering the **top or bottom edge** reveals a round "+" (also on keyboard focus; a transparent
   hover strip plus CSS `:hover` / `:focus-within`). It opens an **Add column** `<dialog>`: width in mm (quick
   chips 115 and 87.5), Add/Cancel. The new column appears as a dashed strip right of the last one. A column
   wider than the free width warns, but is allowed.
3. **Add boxes.** Hovering the **bottom of a column's stack** reveals a "+". It opens **Add boxes**: depth and
   quantity (length is fixed to the column width). Boxes are drawn immediately, stacked top to bottom.
   Overflow past the drawer depth warns in the dialog and is shown clipped.
4. **Edit and delete.** Click a box to edit or delete its row; click a column name above the drawer to change
   its width or delete the column.
5. **Reorder by drag and drop** (HTML5 drag events, no library):
   * Only **within the same column**; other columns reject the drop (a box's length must equal its column
     width). The drop target is highlighted.
   * Dropping on a box moves the dragged box to that position and shifts the others (array "move").
   * Order is per individual box: expand the column's rows into single boxes, move one, then **regroup
     consecutive equal depths** into `qty` rows. Dragging one box out of a `qty = 3` row splits it; dropping it
     next to an equal box merges them. Implement as `move_box(column, i, j)` in `core/layout.py`, mirrored in
     `app.js`.
   * Reordering changes only project order and the BOM's column listing, never the unique sizes or the STLs.
   * Keyboard alternative: Alt+Up / Alt+Down on a focused box; each box has an `aria-label` saying so.
   * Not included: moving a box to another column, or dragging whole columns.
6. **Generate STL files** calls `POST /api/validate`, then `POST /api/build`, then shows the build plan
   (filename, size, qty, status incl. "cached"), a progress bar polled from `GET /api/build` about once a
   second, per-file status (queued / compiling / done / cached / failed, with the log for failures), and
   download links (`/api/build/files/{filename}`) plus a primary **Download all (ZIP)**.

### 6.3 Rendering rules

* To scale, 1 px per mm by default (zoom to fit if the drawer exceeds the window). Drawn client-side on every
  change with no server call; the server's `core/layout.py` stays authoritative for validation and the plan,
  so keep both consistent (shared test case).
* Columns: dashed strips with a clickable name above. Boxes: rounded corners (radius `r`), a hatched strip on
  the top edge equal to that box's cover width (28 or 32 mm), and a label `A X B` (hidden if too small).
* **Colour by unique size** (palette keyed by `(depth, column width)`): identical sizes always share a
  colour, different sizes never do.
* Leftover space stays white; overflow is clipped and tinted red.
* A summary line: total boxes, unique sizes, used vs free width, per-column used depth. `title` tooltips show
  full dimensions.

### 6.4 Behaviour rules

* Editing updates the canvas, summary and local warnings immediately; server validation runs before a build.
  **Errors** (or missing OpenSCAD) disable **Generate STL files**.
* Compilation happens only on that button; a reload keeps the project (localStorage) and shows the latest
  build again.
* Accessibility: real `<button>`s and `<label>`s, `aria-label` on "+" buttons, text contrast >= 4.5:1, dialogs
  close on Esc.
* English UI with all strings in one object in `app.js` (easy to add Korean). No external network requests
  (system font stack). Preview and validation stay well under 200 ms for 100 boxes.

---

## 7. Setup and run

```bash
# 1. Install OpenSCAD (https://openscad.org/downloads.html); the 2024+ snapshot is recommended.
# 2. Python 3.10+
cd box-generator
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Run, then open http://127.0.0.1:8000
uvicorn app:app --host 127.0.0.1 --port 8000
```

On Windows, double-click `run.bat`: it creates the venv on first run, starts uvicorn and opens the browser.
`python app.py` should do the same on any OS. If OpenSCAD is not on `PATH`, set `OPENSCAD_PATH` or paste the
path into the sidebar. Run tests with `pytest -q`. `.gitignore`: `.venv/`, `output/`, `__pycache__/`.

---

## 8. Acceptance tests

Using `examples/seed_from_box_docx.json` and default settings:

1. **Counts:** 6 columns, **42 boxes**, **19 unique sizes**; column sums 543.5, 489.8, 542.3, 553.7, 579.5,
   566.5; total width 580.
2. **Names:** generated file names equal exactly the 19 names in §2.3 (e.g. `96X87.5.stl`, not `96.0X87.5.stl`).
3. **Default render:** `render_scad` with `length=115, width=127, height=40` reproduces the original `Box.scad`
   assignments (whitespace/CRLF differences aside).
4. **Injection:** for `43.5X87.5` the file contains `length = 87.5;`, `width  = 43.5;` and
   `cover_width = 28;` (A goes to `width`, B to `length`), and the geometry code is unchanged.
5. **Missing variable:** a template without `wall` raises `TemplateError`.
6. **Cover rule:** `cover_width_for(depth)` gives 28 for 43.5 and 44.9, 32 for 45 and 58.5; in the seed only
   `43.5X87.5` and `43.5X115` get 28.
7. **Validation:** `r = 2` with `wall = 2` is an error; a cover as wide as a 43.5-deep box is an error; the
   seed with defaults has no errors.
8. **Dedupe:** the mock runner is called 19 times, not 42.
9. **Failure isolation:** one failing job still yields the other 18 STLs plus an error entry.
10. **ZIP:** 19 `.stl` files (all succeeded), `bom.csv`, `project.json`; BOM quantities sum to 42.
11. **Reorder:** `move_box` keeps the multiset of boxes, splits and re-merges `qty` rows (`[67.8 x3, 43.5]`
    moving index 3 to 0 gives `[43.5, 67.8 x3]`), and treats `i == j` or an out-of-range `j` as a no-op.
12. **Integration (skip if OpenSCAD is missing):** compiling `127X115` yields a non-empty STL with a bounding
    box of about 115 x 127 x 40 mm.
13. **API (optional, mocked runner):** `POST /api/plan` returns 19 jobs with quantities summing to 42;
    `POST /api/build` then polling `GET /api/build` reaches `done` with 19 items; `/api/build/zip` returns a valid
    archive; `/api/build` returns 422 when validation fails.

---

## 9. Extras and roadmap

**Optional tool, `tools/import_docx.py <Box.docx>` -> project JSON** (the result already exists as the seed;
this re-imports after the Word file changes):

1. Use `python-docx`; walk `table._tbl.tr_lst` and `tr.tc_lst` (not `table.rows[i].cells`, which repeats merged
   cells) and skip any `w:tc` whose `w:vMerge` is present and not `restart`.
2. Match cell text with `^\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*([A-Za-z])?\s*$` -> `A` (depth),
   `B` (column width); ignore any trailing letter.
3. Group by table column; warn if the `B` values in a column differ; merge consecutive equal `A` into one row
   with `qty`; set `drawer.width = sum(column widths)` and `drawer.depth = max(column used depth)`.

**Not in v1:** automatic bin packing, 3MF plate nesting, G-code, accounts, database, Docker.

**Possible later, in order:** (1) export a pre-arranged 3MF plate per column; (2) a `cover_side` option via an
extra template variable; (3) 3D STL preview and label recesses; (4) a stdlib-only server (no pip install) behind
the same `core/` and `web/`.
