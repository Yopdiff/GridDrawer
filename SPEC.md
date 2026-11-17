# GridDrawer: technical specification

For installing and using the app, read [README.md](README.md). This file describes how the app is built.

Tool lookup: OpenSCAD is found by `find_openscad` in `core/builder.py`, PrusaSlicer by `find_prusaslicer`
in `core/slicer.py`.

A local web app that turns **measured drawer dimensions** into **ready-to-slice STL files** for open-top,
rounded-corner boxes, using the author's existing OpenSCAD template (`box.scad`). It then packs the boxes
onto print beds and slices each bed with PrusaSlicer.

> This document describes the app **as it is implemented now**. If code and this document disagree, fix one
> deliberately. Ideas that are not built are listed only in §9.

## Contents

1. [Overview](#1-overview) · 2. [Reference inputs](#2-reference-inputs) · 3. [Domain model](#3-domain-model) ·
4. [Stack and structure](#4-stack-and-structure) · 5. [Backend](#5-backend) · 6. [Frontend](#6-frontend-web) ·
7. [Setup and run](#7-setup-and-run) · 8. [Tests](#8-tests-teststest_corepy) · 9. [Not built](#9-not-built)

---

## 1. Overview

**Today (manual):** measure each drawer compartment, record it in a Word table (`Box.docx`), edit `length` and
`width` in `Box.scad` by hand and export one STL per size (19 so far), import every STL into PrusaSlicer and
arrange them by eye, export G-code, print.

**This app replaces the Word table and the manual OpenSCAD edits, and shortens the slicer arrangement:**

1. Describe the drawer as **vertical columns**, each filled with **boxes stacked front to back**.
2. See a live, to-scale 2D top view of the layout.
3. **Generate**: inject the dimensions into the OpenSCAD template, run the OpenSCAD CLI, and get the STLs
   (individually or as a ZIP).
4. **Arrange**: pack every box onto as few print beds as possible.
5. **Slice**: run the PrusaSlicer CLI once per bed and download the `.bgcode` or `.gcode` files.

**Scope: a single-user tool on the author's own Windows PC.** No accounts, hosting, Docker, HTTPS, CORS or
database. The server binds to `127.0.0.1`, runs **one build at a time**, and keeps only the latest build.
Prefer the simplest thing that works. Still required: input validation, clear error messages, and a failed
STL never stops the others.

---

## 2. Reference inputs

| File | Role | In this repo |
|---|---|---|
| `Box.scad` | The one box template; only `length` and `width` were edited per STL. | `box.scad` (repo root) |
| `Box.docx` | 9x6 Word table mimicking the drawer layout; each cell is one box. | `seed_from_box_docx.json` (repo root, converted) |
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
  expression; it is left alone. `$fn` is set from the quality setting.
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

In the on-screen plan view the origin is the **bottom-left** corner: columns run left to right, boxes stack
from the bottom edge upward, and each box's cover strip is drawn on its **bottom** edge (scad Y = 0). Boxes are placed flush: the author's measurements already include any margin, so there is
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
* `seed_from_box_docx.json` is the author's drawer; it is the demo project (**Load example**).
* `Project` rejects unknown top-level keys; `drawer.width`, `drawer.depth`, column `width` and box `depth`
  must be > 0 and `qty` >= 1, otherwise the API answers 422.
* `BoxSpec` (resolved, immutable, hashable): `length, width, height, wall, r, cover_width`.

Derived values (`core/layout.py`, `place(project) -> list[Placement]`, `stats(project)`):

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

The three numbers live in the project's `defaults`; the page has no fields for them, so change them by
editing a saved project file. In the author's drawer only the `43.5`-deep boxes use the short
cover (15.5 mm opening instead of 11.5 mm).

---

## 4. Stack and structure

**Back end: FastAPI. Front end: one static page of plain HTML + CSS + vanilla JavaScript.** No build step, no
Node, no JS framework, no CDN (works offline).

| Concern | Decision |
|---|---|
| Languages | Python 3.10+ (server); modern JavaScript, no bundler/transpiler (browser) |
| Server | FastAPI + uvicorn; serves `web/` and a small JSON API |
| Models/validation | Pydantic v2 |
| Canvas | DOM/CSS blocks positioned in mm-scaled pixels |
| CAD engine | OpenSCAD CLI via `subprocess.run([...])` (list form, never `shell=True`) |
| Slicer | PrusaSlicer console CLI, same way |
| Concurrency | `ThreadPoolExecutor`; builds and slices run in a background thread, the page polls |
| ZIP | stdlib `zipfile` in memory |
| State | Project JSON lives in the browser (`localStorage` autosave + `.json` download/upload) |
| Tests | `pytest` |
| Platform | Windows 10/11 primary; the tool lookups also know the usual macOS/Linux OpenSCAD paths |

**Prerequisites (not pip):** OpenSCAD 2021.01+ for STL generation; PrusaSlicer for slicing. Without
PrusaSlicer everything except step 3 works.

`requirements.txt`: `fastapi`, `uvicorn`, `pydantic`, `pytest`, plus `httpx` and `python-docx`, which nothing
in the repo uses yet (§9).

All logic lives in a framework-free `core/` package (no `import fastapi`); `app.py` and `web/` are thin layers.

```
GridDrawer/
├── README.md                    # user guide
├── SPEC.md                      # this file
├── requirements.txt
├── app.py                       # FastAPI: JSON API + serves web/
├── box.scad                     # the OpenSCAD template
├── seed_from_box_docx.json      # example project
├── core/
│   ├── models.py                # Project, Drawer, Column, BoxRow, Defaults, BoxSpec, Issue
│   ├── layout.py                # place(), stats(), move_box(), cover_width_for(), box_spec()
│   ├── scad_template.py         # set_var(), render_body(), with_header(), render_scad()
│   ├── naming.py                # fmt_num(), stl_filename()
│   ├── validation.py            # validate() -> list of Issue(level, msg, where)
│   ├── builder.py               # plan (dedupe), find OpenSCAD, parallel compile, cache, BOM
│   ├── arrangement.py           # arrange(): shelf packing onto print beds
│   ├── slicer.py                # find PrusaSlicer, merge STLs per bed, slice
│   └── packaging.py             # ZIP
├── web/                         # index.html, style.css, app.js (no build step)
├── tests/test_core.py           # all tests
└── output/                      # gitignored: builds, cache/, slices/
```

`run.bat` (a Windows launcher) is gitignored along with every other `*.bat`, so it exists only locally.

---

## 5. Backend

### 5.1 Template injection (`core/scad_template.py`)

* `app.py` reads `box.scad` once at startup.
* `set_var(src, name, value)` rewrites one top-level assignment line with a regex that keeps the trailing
  comment, so each generated `.scad` still reads like the original and opens in the OpenSCAD GUI. It raises
  `TemplateError` if the variable is not found. Patterns are compiled once per variable name.
* `render_body(template, spec, fn)` injects `length`, `width`, `height`, `wall`, `r`, `cover_width` and `$fn`.
  The result contains no timestamp, so identical inputs give identical text.
* `with_header(body, spec)` prepends `// GridDrawer generated <UTC time> <name>.stl`.
* `render_scad(template, spec, fn)` is the two combined; this is what gets written next to each STL.

### 5.2 Validation (`core/validation.py`)

`validate(project) -> list[Issue]` with `level` of `error` or `warning`. **Errors block building and
arranging; warnings do not.**

| Rule | Level |
|---|---|
| `r <= wall` | error |
| `height <= wall` | error |
| `cover_width` or `cover_width_short` `>= drawer.depth - wall` | error |
| Column `width <= 2*wall` | error |
| Box `depth <= 2*wall` | error |
| Box cover `>= depth - wall` (cover too wide for the box) | error |
| Column used depth > drawer depth | warning |
| Column widths > drawer width | warning |
| Box depth or column width outside 20-250 mm | warning |

Schema problems (non-positive sizes, `qty < 1`, unknown keys) are caught earlier by Pydantic and returned as 422.
The seed project with default settings produces no errors.

### 5.3 Build pipeline (`core/builder.py`)

* `plan(project) -> list[Job]`: **dedupe** identical `BoxSpec`s (one STL per unique size), each with its total
  `qty` and the names of the columns using it, sorted by file name.
* `build(project, template, exe, output_root, fn, workers, include_scad, force, manifold, on_progress)` writes
  one run directory and returns `{state, done, total, items, run_dir}`.
* **Command:** `openscad -o <name>.stl [--backend=Manifold] --export-format binstl <name>.scad`. Manifold is
  used only when the detected version's year is 2024 or later.
* **Per job:** timeout 180 s; success only if the exit code is 0 **and** the STL exists and is non-empty. A
  failed job is reported with its log; the others continue.
* **Concurrency:** `ThreadPoolExecutor(max_workers=workers)`, default 4, set from the sidebar.
* **Cache:** key = SHA-256 of `render_body` text (no timestamp) + OpenSCAD version + the Manifold flag; file
  `output/cache/<key>.stl`. A hit copies the file and reports the item as `cached`. `force` bypasses it.
* **Output:** `output/<YYYYmmdd-HHMMSS>/` with `*.scad`, `*.stl`, `bom.csv`, `project.json`.
* `find_openscad(user_path)` search order: given path, env `OPENSCAD_PATH`, `PATH` (`openscad.com`, then
  `openscad`), `C:\Program Files\OpenSCAD\`, the macOS app bundle, `/usr/bin/openscad`.
* `get_version(exe)` runs `--version` once per executable and remembers the answer.

### 5.4 Bed arrangement (`core/arrangement.py`)

`arrange(project, bed_width=250, bed_depth=210, margin=5, gap=2, allow_rotation=True)`:

* One item per physical box (the plan's jobs expanded by `qty`).
* A box that fits the usable area (bed minus `margin` on each side) in neither orientation goes to `failed`.
* Shelf packing: each item goes onto the best-fitting existing shelf, else a new shelf on an existing bed,
  else a new bed. Boxes may be rotated 90 degrees when allowed. `gap` separates neighbours.
* Two sort orders are tried (by area, by longest side); the result with the fewest beds wins, ties broken by
  less wasted shelf area.
* Returns `{bed: {width, depth, margin, gap}, beds: [{number, placements: [{filename, copy, x, y, width, depth,
  rotated}]}], failed, total, placed}`. Coordinates are in mm from the bed's bottom-left corner.

### 5.5 Slicing (`core/slicer.py`)

* `find_prusaslicer(user_path)` search order: given path, env `PRUSASLICER_PATH`, `PATH`
  (`prusa-slicer-console.exe`, `prusa-slicer`), then `C:\Program Files\Prusa3D\PrusaSlicer\` and
  `C:\Program Files\PrusaSlicer\` (console build first).
* `merge_translated_stls(source_dir, placements, target, cache)` writes one binary STL per bed with every box
  moved to its place (and rotated when `rotated`). Each source STL is parsed once per slice run.
* `slice_beds(arrangement, build_dir, output_dir, exe, ...)` runs, per bed:
  `prusa-slicer-console --export-gcode --dont-arrange --output bed-N.bgcode --print-profile P
  --printer-profile R --fill-density 15% --fill-pattern grid --nozzle-diameter 0.4 [support flags]
  --material-profile M [--binary-gcode] bed-N.stl`.
  Supports on: `--support-material --support-material-buildplate-only=0 --support-material-style snug`;
  off: `--support-material=0`.
* Defaults: print `0.20mm SPEED @MK4S HF0.4`, printer `Original Prusa MK4S HF0.4 nozzle`, material
  `Generic PLA @MK4S HF0.4`, supports on, binary G-code on. Timeout 900 s per bed.
* Two beds are sliced at a time (`workers=2`); `on_progress` is called as each bed finishes and the returned
  items are sorted by bed number. A bed succeeds only if the exit code is 0 and the output file is non-empty.
* **Output:** `output/slices/<YYYYmmdd-HHMMSS>/` with `bed-N.stl` and `bed-N.bgcode` (or `.gcode`).

### 5.6 Naming and packaging

* `fmt_num(x)`: `87.5 -> "87.5"`, `96.0 -> "96"`; `round(x, 3)` then strip zeros.
  `stl_filename(spec) = f"{fmt_num(width)}X{fmt_num(length)}.stl"`.
* ZIP (`core/packaging.py`): `stl/*.stl`, optional `scad/*.scad`, `bom.csv`, `project.json`.
* `bom.csv`: `filename,width_A,length_B,height,wall,r,cover_width,qty,columns` (`columns` like `Col 1; Col 6`).

### 5.7 HTTP API (`app.py`)

Stateless apart from one global `state` dict holding the latest build and the latest slice run. The client
sends the project on each call. State is lost when the server restarts; files stay in `output/`.

| Method and path | Purpose |
|---|---|
| `GET /`, `/static/*` | Serve `web/` |
| `GET /api/example` | The seed project |
| `GET /api/status` | `{openscad: {found, path, version, manifold}, prusaslicer: {found, path, version}}` |
| `PUT /api/openscad-path` | `{path}`: override the OpenSCAD path for this run; returns status |
| `PUT /api/prusaslicer-path` | `{path}`: override the PrusaSlicer path for this run; returns status |
| `POST /api/validate` | Project in; `{issues: [{level, msg, where}], stats}` out |
| `POST /api/plan` | Project in; `{jobs: [{filename, spec, qty, columns}]}` out; 422 on validation errors |
| `POST /api/arrange` | `{project, options: {bed_width, bed_depth, margin, gap, allow_rotation}}`; the arrangement of §5.4 |
| `POST /api/build` | `{project, options: {workers, fn, force, include_scad}}`; 422 on validation errors, missing OpenSCAD, or a build already running; starts a background build |
| `GET /api/build` | Latest build: `{state: idle\|running\|done\|failed, done, total, items: [{filename, status, seconds, log}], error?}` |
| `GET /api/build/files/{filename}` | One STL (attachment) |
| `GET /api/build/zip?include_scad=` | The ZIP |
| `POST /api/slice` | `{arrangement, options: {print_profile, printer_profile, material_profile, supports, binary_gcode}}`; 422 unless the latest build is `done`, PrusaSlicer is found and the arrangement has beds |
| `GET /api/slice` | Latest slice run: `{state, done, total, items: [{bed, filename, status, seconds, returncode, command, stdout, stderr, log}], error?}` |
| `GET /api/slice/debug` | Plain-text log of the latest slice run (attachment) |
| `GET /api/slice/files/{filename}` | One `.gcode` or `.bgcode` file (attachment) |

Item `status` is `done`, `cached` (builds only) or `failed`. Progress is live for both builds and slices:
`done` and `items` grow while `state` is `running`. If a build throws, its state becomes `failed` with `error`
set, so the page never polls forever. Downloads only serve files directly inside the latest run directory with
the expected extension. The server binds to `127.0.0.1`; no auth, no CORS. API errors are JSON `{detail}`.

---

## 6. Frontend (`web/`)

### 6.1 Layout

```
┌ Sidebar ───────────────┐ ┌ Main ─────────────────────────────────────────────┐
│ GridDrawer             │ │ Your drawer   [chips: boxes, sizes, width used]   │
│ tool pills             │ │                                  [+ Add column]   │
│ Load example / Clear   │ │ ┌ drawer preview card ──────────────────────────┐ │
│ Save / Open project    │ │ │ column heads: name, width, +, x               │ │
│ ▸ Drawer   width depth │ │ │ to-scale canvas with rulers                   │ │
│ ▸ Boxes    h wall r    │ │ └───────────────────────────────────────────────┘ │
│ ▸ STL build            │ │ issues (errors and warnings)                      │
│ ▸ Print bed            │ │ [1 Generate] [2 Arrange] [3 Slice]  step cards    │
│ ▸ Slicer profiles      │ │ STL files panel · Print beds panel · G-code panel │
└────────────────────────┘ └───────────────────────────────────────────────────┘
```

Sidebar groups are `<details>`; all are open at first except **Slicer profiles**.

| Group | Fields |
|---|---|
| Drawer | width, depth |
| Boxes | height, wall, radius |
| STL build | quality (`$fn` 32 / 64 / 96), workers, include SCAD in ZIP, force rebuild |
| Print bed | width, depth, edge margin, box gap, allow rotation |
| Slicer profiles | print, printer and material profile names, supports, binary G-code |

Tool pills show `OpenSCAD <version>` and `PrusaSlicer <version>`. A missing tool shows a red pill; clicking it
asks for the executable path and sends it to the matching `PUT` route.

### 6.2 Drawer canvas

* The origin is the bottom-left corner. Columns run left to right; boxes stack from the bottom upward.
* **Column heads** sit above the canvas: clicking the name opens the edit dialog (width, delete), `+` opens
  **Add boxes**, `x` deletes the column. Deleting renumbers the remaining columns `Col 1..n`.
* **Add columns** dialog: width and how many. The **+ Add column** button and the dashed slot in the free
  width both open it. A width that would exceed the drawer width is **refused** with the remaining space shown.
* **Add boxes** dialog: depth and how many, added to the top of the column's stack. A stack that would exceed
  the drawer depth is **refused**. Each column with free space shows a dashed **+ Add boxes** slot above its stack.
* **Delete a box:** the `x` that appears on hover or focus.
* **Reorder:** drag a box onto another box in the same column, or focus it and press Alt+Up / Alt+Down. Order
  is per individual box: the column's rows are expanded, one box moves, then consecutive equal depths are
  regrouped into `qty` rows (same logic as `move_box` in `core/layout.py`). Boxes cannot move between columns.
* Overflow (possible after shrinking the drawer or opening a project file) is tinted red and clipped.

### 6.3 Rendering

* The canvas scales to fit both the window width and height (0.35 to 1.6 px per mm) and re-renders on resize.
  Rulers pick a tick step from 10 to 500 mm so labels stay about 36 px apart.
* Boxes show `A x B` (hidden when under 18 px tall), a hatched strip for the cover on the bottom edge, and a
  tooltip with the size.
* **Colour by unique size:** each `A x B` gets one hue, used in both the drawer and the print-bed views.
* Summary chips: box count, unique sizes, used / total width (red when over).
* Print beds are drawn at 1 px per mm on a 50 mm grid.
* Clicks, drags and keys on the canvas are handled by delegated listeners, not per box.

### 6.4 Workflow and state

* Every project change saves to `localStorage` (`griddrawer.project`), redraws, and validates on the server
  150 ms after the last change. Stale validation replies are ignored.
* **Step 1 Generate** is disabled while anything is running, with errors, with no boxes, or without OpenSCAD.
  It shows a progress bar and `Compiling n / total`, polling `GET /api/build` every 500 ms.
* **Step 2 Arrange** is disabled while anything is running, with errors, or with no boxes.
* **Step 3 Slice** needs an up-to-date build, an up-to-date arrangement with nothing left over, and
  PrusaSlicer. While it runs, a modal loading screen (`<dialog id="sliceDialog">` opened with `showModal()`)
  sits in the centre of the window with a spinner, `n of N beds done` and a progress bar. The rest of the
  page is inert, the page cannot scroll, and Esc does not close it. It closes by itself when slicing ends,
  successfully or not, and the G-code panel scrolls into view. Progress comes from polling `GET /api/slice`
  every 800 ms.
* **Out of date:** a build depends on the box parameters and the set of unique sizes; an arrangement also
  depends on how many of each size. When those change, the panel is dimmed and badged **Out of date** and
  step 3 is disabled. Reordering boxes changes neither.
* After a reload the project is restored; the last build's file list is shown again if the server still has
  it and it matches the project.
* **Load example** and **Clear** ask for confirmation when the drawer is not empty. **Save project** downloads
  `griddrawer-project.json`; **Open project** loads one after the server accepts it.
* Failed files show their log in a collapsible block. No external network requests; system fonts only.

---

## 7. Setup and run

See [README.md](README.md) for the user-facing steps. In short:

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                     # serves http://127.0.0.1:8000
```

`python app.py` and `uvicorn app:app --host 127.0.0.1 --port 8000` are equivalent. Tests: `pytest -q`.
`.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `output/`, `*.bat`.

---

## 8. Tests (`tests/test_core.py`)

All tests use the seed project or small hand-made STLs; none needs OpenSCAD or PrusaSlicer installed.

1. **Counts:** 42 boxes, 19 unique sizes, 19 planned jobs.
2. **Cover rule and names:** 28 for depth 43.5, 32 for 45; `43.5X87.5.stl` is in the plan.
3. **Render and validation:** `43.5X87.5` renders `length = 87.5;` and `width  = 43.5;`; the seed has no errors.
4. **Reorder:** `[67.8 x3, 43.5]` moving index 3 to 0 gives `[43.5, 67.8 x3]`.
5. **Arrangement:** all 42 seed boxes are accounted for and every placement stays inside the bed margins.
6. **Merge, translated:** a triangle moved by (12, 34) lands there.
7. **Merge, rotated:** a rotated placement turns the geometry 90 degrees into its slot.
8. **Slice command:** default profiles, 15% grid infill, snug supports and `--binary-gcode` are on the command line.
9. **Slice without supports:** `--support-material=0` and no support style.
10. **Build cache:** a second build of the same project compiles nothing; all 19 items are `cached`.
11. **Slice progress:** `on_progress` fires once per bed and results come back in bed order.

Not covered by tests: the HTTP routes, the ZIP, failure isolation in a build, and a real OpenSCAD compile.

---

## 9. Not built

* `tools/import_docx.py` (re-import `Box.docx` into a project file). `python-docx` is already in
  `requirements.txt` for it. The seed file was converted once by hand.
* API tests with FastAPI's `TestClient` (`httpx` is in `requirements.txt` for them).
* Sidebar fields for the three cover settings; moving a box to another column; dragging whole columns.
* A log file (`output/app.log`); per-box overrides; 3MF export; a 3D preview.
