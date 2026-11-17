from __future__ import annotations

import os
import shutil
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path


def find_prusaslicer(user_path: str | None = None) -> str | None:
    candidates = [
        user_path,
        os.environ.get("PRUSASLICER_PATH"),
        shutil.which("prusa-slicer-console.exe"),
        shutil.which("prusa-slicer"),
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe",
        r"C:\Program Files\PrusaSlicer\prusa-slicer-console.exe",
        r"C:\Program Files\PrusaSlicer\prusa-slicer.exe",
    ]
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), None)


@lru_cache(maxsize=8)
def get_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


_TRIANGLE = struct.Struct("<12x9f2x")  # normal (ignored), 3 vertices, attribute bytes


def _read_binary_stl(path: Path) -> list[tuple[float, ...]]:
    """Return one 9-float tuple (x1, y1, z1, x2, ...) per triangle."""
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"STL is too small: {path.name}")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if expected > len(data):
        raise ValueError(f"Unsupported or corrupt STL: {path.name}")
    return list(_TRIANGLE.iter_unpack(memoryview(data)[84:expected]))


def merge_translated_stls(source_dir: Path, placements: list[dict], target: Path,
                          cache: dict | None = None) -> None:
    """Write one binary STL holding every placed box. `cache` shares parsed STLs between beds."""
    cache = {} if cache is None else cache
    pack = _TRIANGLE.pack
    chunks = []
    total = 0
    for placement in placements:
        name = placement["filename"]
        triangles = cache.get(name)
        if triangles is None:
            source = source_dir / name
            if not source.is_file():
                raise FileNotFoundError(f"Missing STL from build: {source.name}")
            triangles = cache[name] = _read_binary_stl(source)
        dx, dy = float(placement["x"]), float(placement["y"])
        if placement.get("rotated", False):
            oy = float(placement["depth"]) + dy  # rotate 90 degrees: (x, y) -> (y, depth - x)
            chunks.append(b"".join(
                pack(y1 + dx, oy - x1, z1, y2 + dx, oy - x2, z2, y3 + dx, oy - x3, z3)
                for x1, y1, z1, x2, y2, z2, x3, y3, z3 in triangles
            ))
        else:
            chunks.append(b"".join(
                pack(x1 + dx, y1 + dy, z1, x2 + dx, y2 + dy, z2, x3 + dx, y3 + dy, z3)
                for x1, y1, z1, x2, y2, z2, x3, y3, z3 in triangles
            ))
        total += len(triangles)
    if total > 0xFFFFFFFF:
        raise ValueError("Too many triangles for a binary STL.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(b"GridDrawer arranged bed".ljust(80, b" "))
        handle.write(struct.pack("<I", total))
        handle.writelines(chunks)


def slice_beds(
    arrangement: dict,
    build_dir: Path,
    output_dir: Path,
    exe: str,
    print_profile: str = "0.20mm SPEED @MK4S HF0.4",
    printer_profile: str = "Original Prusa MK4S HF0.4 nozzle",
    material_profile: str = "Generic PLA @MK4S HF0.4",
    supports: bool = True,
    binary_gcode: bool = True,
    timeout: int = 900,
    runner=subprocess.run,
    workers: int = 2,
    on_progress=None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    beds = arrangement.get("beds", [])
    stl_cache: dict = {}

    def one(bed: dict) -> dict:
        number = int(bed["number"])
        merged = output_dir / f"bed-{number}.stl"
        output = output_dir / f"bed-{number}.bgcode" if binary_gcode else output_dir / f"bed-{number}.gcode"
        command = [
            exe, "--export-gcode", "--dont-arrange", "--output", str(output),
            "--print-profile", print_profile, "--printer-profile", printer_profile,
            "--fill-density", "15%", "--fill-pattern", "grid",
            "--nozzle-diameter", "0.4",
        ]
        if supports:
            command += ["--support-material", "--support-material-buildplate-only=0",
                        "--support-material-style", "snug"]
        else:
            command.append("--support-material=0")
        if material_profile:
            command += ["--material-profile", material_profile]
        if binary_gcode:
            command.append("--binary-gcode")
        command.append(str(merged))
        started = time.monotonic()
        try:
            merge_translated_stls(build_dir, bed.get("placements", []), merged, stl_cache)
            completed = runner(command, capture_output=True, text=True, timeout=timeout)
            ok = completed.returncode == 0 and output.is_file() and output.stat().st_size > 0
            return {
                "bed": number, "filename": output.name,
                "status": "done" if ok else "failed",
                "seconds": round(time.monotonic() - started, 2),
                "returncode": completed.returncode,
                "command": command,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "log": (completed.stderr or completed.stdout or ""),
            }
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return {
                "bed": number, "filename": output.name, "status": "failed",
                "seconds": round(time.monotonic() - started, 2),
                "command": command,
                "stdout": "", "stderr": "", "log": str(exc),
            }

    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for future in as_completed([pool.submit(one, bed) for bed in beds]):
            item = future.result()
            results.append(item)
            if on_progress:
                on_progress(item)
    results.sort(key=lambda item: item["bed"])
    return {
        "state": "done" if all(item["status"] == "done" for item in results) else "failed",
        "done": sum(item["status"] == "done" for item in results),
        "total": len(results),
        "items": results,
        "output_dir": str(output_dir),
    }
