from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def make_zip(run_dir: Path, include_scad: bool = False) -> bytes:
    import io
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for path in run_dir.glob("*.stl"):
            archive.write(path, f"stl/{path.name}")
        if include_scad:
            for path in run_dir.glob("*.scad"):
                archive.write(path, f"scad/{path.name}")
        for name in ("bom.csv", "project.json"):
            path = run_dir / name
            if path.exists():
                archive.write(path, name)
    return stream.getvalue()
