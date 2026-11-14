from __future__ import annotations

import os
import shutil
import struct
import subprocess
import time
import shlex
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


def get_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def _read_binary_stl(path: Path) -> list[tuple[tuple[float, float, float], ...]]:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"STL is too small: {path.name}")
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if expected > len(data):
        raise ValueError(f"Unsupported or corrupt STL: {path.name}")
    triangles = []
    for offset in range(84, expected, 50):
        vertices = struct.unpack_from("<9f", data, offset + 12)
        triangles.append((tuple(vertices[0:3]), tuple(vertices[3:6]), tuple(vertices[6:9])))
    return triangles


def merge_translated_stls(source_dir: Path, placements: list[dict], target: Path) -> None:
    triangles = []
    for placement in placements:
        source = source_dir / placement["filename"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing STL from build: {source.name}")
        dx, dy = float(placement["x"]), float(placement["y"])
        rotated = bool(placement.get("rotated", False))
        source_length = float(placement["depth"]) if rotated else 0.0
        for triangle in _read_binary_stl(source):
            if rotated:
                triangles.append(tuple((y + dx, source_length - x + dy, z) for x, y, z in triangle))
            else:
                triangles.append(tuple((x + dx, y + dy, z) for x, y, z in triangle))
    if len(triangles) > 0xFFFFFFFF:
        raise ValueError("Too many triangles for a binary STL.")
    target.parent.mkdir(parents=True, exist_ok=True)
    header = b"GridDrawer arranged bed"[:80].ljust(80, b" ")
    with target.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(triangles)))
        for triangle in triangles:
            p1, p2, p3 = triangle
            handle.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            handle.write(struct.pack("<9f", *(p1 + p2 + p3)))
            handle.write(struct.pack("<H", 0))


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
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    beds = arrangement.get("beds", [])
    results = []
    for bed in beds:
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
            merge_translated_stls(build_dir, bed.get("placements", []), merged)
            completed = runner(command, capture_output=True, text=True, timeout=timeout)
            ok = completed.returncode == 0 and output.is_file() and output.stat().st_size > 0
            results.append({
                "bed": number, "filename": output.name,
                "status": "done" if ok else "failed",
                "seconds": round(time.monotonic() - started, 2),
                "returncode": completed.returncode,
                "command": command,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
                "log": (completed.stderr or completed.stdout or ""),
            })
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            results.append({
                "bed": number, "filename": output.name, "status": "failed",
                "seconds": round(time.monotonic() - started, 2),
                "command": command,
                "stdout": "", "stderr": "", "log": str(exc),
            })
    return {
        "state": "done" if all(item["status"] == "done" for item in results) else "failed",
        "done": sum(item["status"] == "done" for item in results),
        "total": len(results),
        "items": results,
        "output_dir": str(output_dir),
    }
