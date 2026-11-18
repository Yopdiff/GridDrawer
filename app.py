from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from core.builder import build, find_openscad, get_version, plan
from core.arrangement import arrange
from core.layout import stats
from core.models import Project
from core.packaging import make_zip
from core.slicer import find_prusaslicer, get_version as get_prusaslicer_version, slice_beds
from core.validation import validate

ROOT = Path(__file__).parent
TEMPLATE = (ROOT / "box.scad").read_text(encoding="utf-8")
EXAMPLE = json.loads((ROOT / "seed_from_box_docx.json").read_text(encoding="utf-8"))
OUTPUT = ROOT / "output"
app = FastAPI(title="GridDrawer")
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
state = {
    "build": {"state": "idle", "done": 0, "total": 0, "items": []},
    "slice": {"state": "idle", "done": 0, "total": 0, "items": []},
    "run_dir": None, "slice_dir": None,
    "exe": find_openscad(), "prusa_exe": find_prusaslicer(),
}
lock = threading.Lock()


def has_errors(project: Project) -> list | None:
    issues = validate(project)
    if any(item.level == "error" for item in issues):
        return [item.model_dump() for item in issues]
    return None


def supports_manifold(version: str | None) -> bool:
    year = re.search(r"\b(20\d\d)\b", version or "")
    return bool(year and int(year.group(1)) >= 2024)


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/example")
def example():
    return EXAMPLE


@app.get("/api/status")
def status():
    exe = state["exe"]
    version = get_version(exe)
    prusa = state["prusa_exe"]
    return {
        "openscad": {"found": bool(exe), "path": exe, "version": version,
                     "manifold": supports_manifold(version)},
        "prusaslicer": {"found": bool(prusa), "path": prusa, "version": get_prusaslicer_version(prusa)},
    }


@app.put("/api/prusaslicer-path")
def prusaslicer_path(payload: dict):
    state["prusa_exe"] = find_prusaslicer(payload.get("path"))
    return status()


@app.put("/api/openscad-path")
def openscad_path(payload: dict):
    state["exe"] = find_openscad(payload.get("path"))
    return status()


@app.post("/api/validate")
def validate_api(project: Project):
    return {"issues": [item.model_dump() for item in validate(project)], "stats": stats(project)}


@app.post("/api/plan")
def plan_api(project: Project):
    if errors := has_errors(project):
        raise HTTPException(422, detail=errors)
    return {"jobs": [{"filename": job.filename, "spec": job.spec.model_dump(), "qty": job.qty, "columns": job.columns}
                     for job in plan(project)]}


@app.post("/api/arrange")
def arrange_api(payload: dict):
    project = Project.model_validate(payload.get("project", {}))
    if errors := has_errors(project):
        raise HTTPException(422, detail=errors)
    options = payload.get("options", {})
    try:
        return arrange(
            project,
            bed_width=float(options.get("bed_width", 250)),
            bed_depth=float(options.get("bed_depth", 210)),
            margin=float(options.get("margin", 5)),
            gap=float(options.get("gap", 10)),
            allow_rotation=bool(options.get("allow_rotation", True)),
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@app.post("/api/build")
def build_api(payload: dict):
    project = Project.model_validate(payload.get("project", {}))
    if errors := has_errors(project):
        raise HTTPException(422, detail=errors)
    if not state["exe"]:
        raise HTTPException(422, detail="OpenSCAD was not found. Set its executable path first.")
    if not lock.acquire(blocking=False):
        raise HTTPException(422, detail="A build is already running.")
    options = payload.get("options", {})
    exe = state["exe"]
    total = len(plan(project))
    progress = state["build"] = {"state": "running", "done": 0, "total": total, "items": []}

    def on_progress(item):
        progress["items"].append(item)
        progress["done"] += 1

    def worker():
        try:
            result = build(project, TEMPLATE, exe, OUTPUT, fn=int(options.get("fn", 64)),
                           workers=int(options.get("workers", 4)), include_scad=bool(options.get("include_scad", True)),
                           force=bool(options.get("force", False)), manifold=supports_manifold(get_version(exe)),
                           on_progress=on_progress)
            state["run_dir"] = result["run_dir"]
            state["build"] = {key: value for key, value in result.items() if key != "run_dir"}
        except Exception as exc:  # never leave the page polling a build that died
            state["build"] = {"state": "failed", "done": progress["done"], "total": total,
                              "items": progress["items"], "error": str(exc)}
        finally:
            lock.release()
    threading.Thread(target=worker, daemon=True).start()
    return state["build"]


@app.get("/api/build")
def build_status():
    return state["build"]


@app.post("/api/slice")
def slice_api(payload: dict):
    if not state["run_dir"] or state["build"].get("state") != "done":
        raise HTTPException(422, detail="Generate STL files successfully before slicing.")
    if not state["prusa_exe"]:
        raise HTTPException(422, detail="PrusaSlicer was not found. Set its executable path first.")
    arrangement = payload.get("arrangement")
    if not isinstance(arrangement, dict) or not arrangement.get("beds"):
        raise HTTPException(422, detail="Arrange print beds before slicing.")
    options = payload.get("options", {})
    slice_dir = OUTPUT / "slices" / time.strftime("%Y%m%d-%H%M%S")
    progress = state["slice"] = {"state": "running", "done": 0, "total": len(arrangement["beds"]), "items": []}

    def on_progress(item):
        progress["items"].append(item)
        progress["done"] += 1

    def worker():
        try:
            result = slice_beds(
                arrangement, Path(state["run_dir"]), slice_dir, state["prusa_exe"],
                print_profile=str(options.get("print_profile", "0.20mm SPEED @MK4S HF0.4")),
                printer_profile=str(options.get("printer_profile", "Original Prusa MK4S HF0.4 nozzle")),
                material_profile=str(options.get("material_profile", "Generic PLA @MK4S HF0.4")),
                supports=bool(options.get("supports", True)),
                binary_gcode=bool(options.get("binary_gcode", True)),
                brim_width=max(0.0, float(options.get("brim_width", 5))),
                on_progress=on_progress,
            )
            state["slice"] = {key: value for key, value in result.items() if key != "output_dir"}
            state["slice_dir"] = result["output_dir"]
        except Exception as exc:
            state["slice"] = {"state": "failed", "done": 0, "total": len(arrangement["beds"]),
                               "items": [], "error": str(exc)}

    threading.Thread(target=worker, daemon=True).start()
    return state["slice"]


@app.get("/api/slice")
def slice_status():
    return state["slice"]


@app.get("/api/slice/debug")
def slice_debug():
    if not state["slice"].get("items"):
        raise HTTPException(404, detail="No slice diagnostics available")
    lines = ["GridDrawer slice diagnostics", f"state: {state['slice'].get('state')}"]
    for item in state["slice"]["items"]:
        lines += [
            "", f"Bed {item.get('bed')} · {item.get('status')}",
            f"returncode: {item.get('returncode', 'n/a')}",
            f"seconds: {item.get('seconds', 'n/a')}",
            "command:",
            subprocess.list2cmdline([str(value) for value in item.get("command", [])]),
            "stdout:", item.get("stdout", ""),
            "stderr:", item.get("stderr", ""),
            "error:", item.get("log", "") if item.get("returncode") is None else "",
        ]
    return Response("\n".join(lines), media_type="text/plain", headers={
        "Content-Disposition": "attachment; filename=grid-drawer-slice-debug.txt",
    })


@app.get("/api/slice/files/{filename}")
def download_slice(filename: str):
    slice_dir = Path(state["slice_dir"]) if state["slice_dir"] else None
    path = slice_dir / filename if slice_dir else None
    if not path or path.parent != slice_dir or path.suffix not in (".gcode", ".bgcode") or not path.is_file():
        raise HTTPException(404, detail="Slice file not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/build/files/{filename}")
def download_file(filename: str):
    run_dir = Path(state["run_dir"]) if state["run_dir"] else None
    path = run_dir / filename if run_dir else None
    if not path or path.parent != run_dir or path.suffix != ".stl" or not path.is_file():
        raise HTTPException(404, detail="File not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/build/zip")
def download_zip(include_scad: bool = False):
    if not state["run_dir"]:
        raise HTTPException(404, detail="No build available")
    data = make_zip(Path(state["run_dir"]), include_scad)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=grid-drawer.zip"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
