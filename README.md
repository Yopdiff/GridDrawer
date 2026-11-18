# GridDrawer

GridDrawer designs 3D-printed organizer boxes for a toolbox drawer. You lay out the drawer on screen, and the
app makes the STL files, arranges them on print beds, and slices them into G-code.

It is a small web app that runs on your own PC. Nothing is uploaded anywhere.

## What it does

1. **Lay out the drawer.** Split the drawer into columns and stack boxes in each one. The view is drawn to scale.
2. **Generate STL files.** One click makes one STL per unique box size with OpenSCAD.
3. **Arrange print beds.** Every box is packed onto as few beds as possible.
4. **Slice.** Each bed is sliced with PrusaSlicer into a `.bgcode` or `.gcode` file, ready to print.

Each box is open-topped with rounded corners and a partial cover along one edge. The shape comes from
[box.scad](box.scad).

## What you need

| Program | Needed for | Notes |
|---|---|---|
| Python 3.10 or newer | Running the app | |
| [OpenSCAD](https://openscad.org/downloads.html) 2021.01 or newer | Generating STL files | |
| PrusaSlicer (from [prusa3d.com](https://www.prusa3d.com)) | Slicing | Optional. Without it you can still make and download STL files. |

The app is developed on Windows 11. It looks for OpenSCAD and PrusaSlicer in their usual install folders.

## Install

Open a terminal in this folder and run:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

On macOS or Linux, the second command is `source .venv/bin/activate`.

## Run

```bash
python app.py
```

Then open http://127.0.0.1:8000 in your browser. To stop the app, press Ctrl+C in the terminal.

The two pills at the top of the sidebar show whether OpenSCAD and PrusaSlicer were found. If one is red, click
it and paste the full path to the program, for example
`C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe`. You can also set the `OPENSCAD_PATH` or
`PRUSASLICER_PATH` environment variable before starting the app.

## Using it

Click **Load example** to see a finished drawer (6 columns, 42 boxes, 19 different sizes).

### Lay out the drawer

All sizes are in millimetres.

- **Drawer size:** set the width and depth in the sidebar.
- **Add a column:** click **+ Add column**, or the dashed slot in the empty part of the drawer. A column's
  width is the length of every box in it.
- **Add boxes:** click the dashed **+ Add boxes** slot above a column's stack, or the **+** next to the column
  name. Enter the box depth and how many. Boxes stack from the bottom of the drawer upward.
- **Edit or delete a column:** click its name above the drawer, or the **×** beside it.
- **Delete a box:** hover over it and click the **×**.
- **Reorder boxes:** drag a box onto another box in the same column. With the keyboard, select a box and
  press Alt + ↑ or Alt + ↓.

Boxes of the same size share a colour. The striped band on each box is its cover.

The app will not let you add a column or box that does not fit in the drawer. Problems with the current
layout appear below the drawer: errors must be fixed before you can continue, warnings are only advice.

### Make the files

Work through the three numbered cards below the drawer.

1. **Generate** makes the STL files. Download them one at a time, or all together with **Download all (ZIP)**.
   The ZIP also holds a parts list (`bom.csv`) and the project file.
2. **Arrange** packs the boxes onto print beds and draws each bed.
3. **Slice** makes one G-code file per bed. It becomes available once the STL files and the arrangement are
   both up to date.

While slicing runs, a loading screen in the middle of the window shows how many beds are done. The page is
locked until it finishes, so nothing can be changed halfway through. It closes by itself and the G-code files
appear at the bottom of the page.

If you change box sizes afterwards, the STL files and beds are marked **Out of date**. Run the step again.
Reordering boxes does not change the files, so nothing goes out of date.

### Settings

| Sidebar group | What it controls |
|---|---|
| Drawer | Inside width and depth of the drawer. |
| Boxes | Height, wall thickness and corner radius of every box. The radius must be larger than the wall. |
| STL build | Curve quality, how many boxes to compile at once, whether the ZIP includes the OpenSCAD sources, and **Force rebuild**. |
| Print bed | Bed size, margin kept free at the edges, gap between boxes, and whether boxes may be turned 90°. |
| Slicer profiles | The PrusaSlicer print, printer and material profile names, brim width, supports, and binary G-code. |

The slicer profiles default to a Prusa MK4S with a 0.4 mm high-flow nozzle and generic PLA. Profile names must
match the names shown in your PrusaSlicer exactly. Slicing always uses 15% grid infill.

Every box gets a 5 mm brim around its outside to stop the corners lifting (warping). Set **Brim width** to 0
to turn it off. Brims of neighbouring boxes must not touch, so the box gap defaults to 10 mm. If you make the
brim wider than half the box gap, or wider than the edge margin, Slice stays greyed out until you widen them
and arrange again.

Boxes shallower than 45 mm get a 26 mm cover; all others get 32 mm.

### Saving your work

The drawer is saved in your browser automatically and comes back when you reopen the page. Use **Save project**
to keep a copy as a file, and **Open project** to load one. **Clear** empties the drawer.

## Where the files go

Everything the app writes is in the `output` folder:

| Folder | Contents |
|---|---|
| `output/<date-time>/` | One build: the STL files, their OpenSCAD sources, `bom.csv` and `project.json`. |
| `output/slices/<date-time>/` | One slice run: a combined STL and the G-code file for each bed. |
| `output/cache/` | Previously built STL files, reused so that repeat builds are fast. |

The app never deletes old runs. You can delete the `output` folder at any time; the only cost is that the next
build starts from scratch.

## If something goes wrong

- **A pill is red.** The program was not found. Click the pill and enter its path.
- **Generate is greyed out.** Fix the errors listed under the drawer, and check that OpenSCAD is found.
- **Slice is greyed out.** The line under the card says what is missing.
- **A file failed.** Open the **Log** or **Debug details** under the failed item. For slicing, **Download debug
  log** saves the full PrusaSlicer output. A wrong profile name is the usual cause.
- **A box is "too large for the bed".** Increase the bed size, reduce the margin, or allow rotation.

## For developers

How the app is built, including the API and the data format, is described in [SPEC.md](SPEC.md).

```bash
pytest -q
```

The server is in [app.py](app.py), the logic in [core/](core), the page in [web/](web), and the tests in
[tests/test_core.py](tests/test_core.py).
