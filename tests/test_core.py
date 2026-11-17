import json
import struct
from pathlib import Path

from core.builder import plan
from core.arrangement import arrange
from core.layout import cover_width_for, move_box, stats
from core.models import Project
from core.naming import stl_filename
from core.scad_template import render_scad, TemplateError
from core.validation import validate
from core.slicer import merge_translated_stls, slice_beds

ROOT = Path(__file__).parents[1]


def project():
    return Project.model_validate(json.loads((ROOT / "seed_from_box_docx.json").read_text()))


def test_seed_counts_and_plan():
    p = project()
    assert stats(p)["total_boxes"] == 42
    assert stats(p)["unique_sizes"] == 19
    assert len(plan(p)) == 19


def test_cover_and_names():
    p = project()
    assert cover_width_for(p, 43.5) == 28
    assert cover_width_for(p, 45) == 32
    assert "43.5X87.5.stl" in {stl_filename(job.spec) for job in plan(p)}


def test_render_and_validation():
    p = project()
    spec = next(job.spec for job in plan(p) if stl_filename(job.spec) == "43.5X87.5.stl")
    text = render_scad((ROOT / "box.scad").read_text(), spec)
    assert "length = 87.5;" in text and "width  = 43.5;" in text
    assert not [i for i in validate(p) if i.level == "error"]


def test_move_regroups():
    p = Project.model_validate({
        "drawer": {"width": 200, "depth": 200},
        "columns": [{"name": "Col 1", "width": 100,
                     "boxes": [{"depth": 67.8, "qty": 3}, {"depth": 43.5, "qty": 1}]}],
    })
    move_box(p, 0, 3, 0)
    assert p.columns[0].boxes[0].depth == 43.5
    assert p.columns[0].boxes[1].qty == 3


def test_arrangement_places_seed_boxes_on_beds():
    result = arrange(project())
    assert result["total"] == 42
    assert result["placed"] + len(result["failed"]) == 42
    assert result["beds"]
    for bed in result["beds"]:
        for item in bed["placements"]:
            assert item["x"] >= result["bed"]["margin"]
            assert item["y"] >= result["bed"]["margin"]
            assert item["x"] + item["width"] <= result["bed"]["width"] - result["bed"]["margin"]
            assert item["y"] + item["depth"] <= result["bed"]["depth"] - result["bed"]["margin"]


def test_slice_merges_arranged_stls_with_xy_translation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    stl = source / "box.stl"
    with stl.open("wb") as handle:
        handle.write(b"test".ljust(80, b" "))
        handle.write(struct.pack("<I", 1))
        handle.write(struct.pack("<3f", 0, 0, 1))
        handle.write(struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0))
        handle.write(struct.pack("<H", 0))
    target = tmp_path / "merged.stl"
    merge_translated_stls(source, [{"filename": "box.stl", "x": 12, "y": 34}], target)
    data = target.read_bytes()
    assert struct.unpack_from("<3f", data, 96) == (12, 34, 0)


def test_slice_rotates_geometry_when_arrangement_rotates_box(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    stl = source / "box.stl"
    with stl.open("wb") as handle:
        handle.write(b"test".ljust(80, b" "))
        handle.write(struct.pack("<I", 1))
        handle.write(struct.pack("<3f", 0, 0, 1))
        handle.write(struct.pack("<9f", 0, 0, 0, 10, 0, 0, 0, 2, 0))
        handle.write(struct.pack("<H", 0))
    target = tmp_path / "merged.stl"
    merge_translated_stls(source, [{
        "filename": "box.stl", "x": 5, "y": 7, "width": 2, "depth": 10, "rotated": True,
    }], target)
    data = target.read_bytes()
    assert struct.unpack_from("<9f", data, 96) == (5, 17, 0, 5, 7, 0, 7, 17, 0)


def test_slice_command_uses_requested_profiles_and_overrides(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    stl = source / "box.stl"
    with stl.open("wb") as handle:
        handle.write(b"test".ljust(80, b" "))
        handle.write(struct.pack("<I", 0))
    commands = []

    def fake_runner(command, **kwargs):
        commands.append(command)
        Path(command[command.index("--output") + 1]).write_bytes(b"bgcode")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    result = slice_beds(
        {"beds": [{"number": 1, "placements": [{"filename": "box.stl", "x": 0, "y": 0}]}]},
        source, tmp_path / "output", "prusa-slicer-console.exe", runner=fake_runner,
    )
    assert result["state"] == "done"
    command = commands[0]
    assert "--dont-arrange" in command
    assert ["--print-profile", "0.20mm SPEED @MK4S HF0.4"] == command[command.index("--print-profile"):command.index("--print-profile") + 2]
    assert "--fill-density" in command and "15%" in command
    assert "--fill-pattern" in command and "grid" in command
    assert "--support-material" in command and "--support-material-style" in command
    assert "--binary-gcode" in command
    assert ["--material-profile", "Generic PLA @MK4S HF0.4"] == command[command.index("--material-profile"):command.index("--material-profile") + 2]


def test_slice_command_can_disable_supports(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    stl = source / "box.stl"
    stl.write_bytes(b"test".ljust(84, b"\0"))
    commands = []

    def fake_runner(command, **kwargs):
        commands.append(command)
        Path(command[command.index("--output") + 1]).write_bytes(b"gcode")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    slice_beds(
        {"beds": [{"number": 1, "placements": [{"filename": "box.stl", "x": 0, "y": 0}]}]},
        source, tmp_path / "output", "prusa-slicer-console.exe", supports=False, binary_gcode=False,
        runner=fake_runner,
    )
    assert "--support-material=0" in commands[0]
    assert "--support-material-style" not in commands[0]


def test_build_cache_hits_on_second_run(tmp_path, monkeypatch):
    import core.builder as builder
    calls = []

    def fake_compile(exe, scad, stl, manifold=False):
        calls.append(stl.name)
        stl.write_bytes(b"stl")
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": "", "seconds": 0.01}

    monkeypatch.setattr(builder, "compile_scad", fake_compile)
    monkeypatch.setattr(builder, "get_version", lambda exe: "test 1.0")
    monkeypatch.setattr(builder.time, "strftime", lambda fmt: f"run-{len(calls)}")
    template = (ROOT / "box.scad").read_text()
    first = builder.build(project(), template, "openscad", tmp_path)
    assert first["state"] == "done" and len(calls) == 19
    second = builder.build(project(), template, "openscad", tmp_path)
    assert len(calls) == 19  # nothing recompiled
    assert all(item["status"] == "cached" for item in second["items"])


def test_slice_reports_progress_in_bed_order(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "box.stl").write_bytes(b"test".ljust(84, b"\0"))

    def fake_runner(command, **kwargs):
        Path(command[command.index("--output") + 1]).write_bytes(b"bgcode")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    seen = []
    beds = [{"number": n, "placements": [{"filename": "box.stl", "x": 0, "y": 0}]} for n in (1, 2, 3)]
    result = slice_beds({"beds": beds}, source, tmp_path / "out", "prusa", runner=fake_runner,
                        on_progress=seen.append)
    assert len(seen) == 3
    assert [item["bed"] for item in result["items"]] == [1, 2, 3]
