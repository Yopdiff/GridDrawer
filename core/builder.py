from __future__ import annotations

import csv
import hashlib
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .layout import box_spec, place
from .models import BoxSpec, Project
from .naming import stl_filename
from .scad_template import render_scad


@dataclass(frozen=True)
class Job:
    spec: BoxSpec
    filename: str
    qty: int
    columns: tuple[str, ...]


def plan(project: Project) -> list[Job]:
    grouped: dict[BoxSpec, dict] = {}
    for placement in place(project):
        spec = box_spec(project, placement.length, placement.depth)
        item = grouped.setdefault(spec, {"qty": 0, "columns": set()})
        item["qty"] += 1
        item["columns"].add(project.columns[placement.column].name)
    return [
        Job(spec, stl_filename(spec), value["qty"], tuple(sorted(value["columns"])))
        for spec, value in sorted(grouped.items(), key=lambda item: stl_filename(item[0]))
    ]


def find_openscad(user_path: str | None = None) -> str | None:
    candidates = [user_path, os.environ.get("OPENSCAD_PATH"), shutil.which("openscad.com"), shutil.which("openscad")]
    candidates += [
        r"C:\Program Files\OpenSCAD\openscad.com",
        r"C:\Program Files\OpenSCAD\openscad.exe",
        "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
        "/usr/bin/openscad",
    ]
    return next((str(Path(p)) for p in candidates if p and Path(p).is_file()), None)


def get_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        return None


def compile_scad(exe: str, scad: Path, stl: Path, manifold: bool = False) -> dict:
    command = [exe, "-o", str(stl)]
    if manifold:
        command.append("--backend=Manifold")
    command += ["--export-format", "binstl", str(scad)]
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        ok = result.returncode == 0 and stl.exists() and stl.stat().st_size > 0
        return {"ok": ok, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                "seconds": round(time.monotonic() - started, 2)}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": -1, "stdout": exc.stdout or "", "stderr": "OpenSCAD timed out", "seconds": 180}


def build(project: Project, template: str, exe: str, output_root: Path, fn: int = 64,
          workers: int = 4, include_scad: bool = True, force: bool = False, manifold: bool = False,
          on_progress=None) -> dict:
    run_dir = output_root / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = plan(project)
    results = []

    def one(job: Job):
        scad_text = render_scad(template, job.spec, fn)
        scad_path = run_dir / job.filename.replace(".stl", ".scad")
        stl_path = run_dir / job.filename
        scad_path.write_text(scad_text, encoding="utf-8", newline="\n")
        cache_key = hashlib.sha256(scad_text.encode()).hexdigest()
        cache_path = output_root / "cache" / f"{cache_key}.stl"
        cache_path.parent.mkdir(exist_ok=True)
        if not force and cache_path.exists():
            shutil.copyfile(cache_path, stl_path)
            return {"filename": job.filename, "status": "cached", "seconds": 0, "log": ""}
        result = compile_scad(exe, scad_path, stl_path, manifold)
        if result["ok"]:
            shutil.copyfile(stl_path, cache_path)
        return {"filename": job.filename, "status": "done" if result["ok"] else "failed",
                "seconds": result["seconds"], "log": result["stderr"] or result["stdout"]}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            if on_progress:
                on_progress(item)
    results.sort(key=lambda item: item["filename"])
    (run_dir / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")
    with (run_dir / "bom.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["filename", "width_A", "length_B", "height", "wall", "r", "cover_width", "qty", "columns"])
        for job in jobs:
            writer.writerow([job.filename, job.spec.width, job.spec.length, job.spec.height, job.spec.wall,
                             job.spec.r, job.spec.cover_width, job.qty, "; ".join(job.columns)])
    return {"state": "done" if all(item["status"] in ("done", "cached") for item in results) else "failed",
            "done": len(results), "total": len(jobs), "items": results, "run_dir": str(run_dir)}
