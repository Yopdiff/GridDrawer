from __future__ import annotations

from dataclasses import dataclass

from .models import BoxSpec, Project


@dataclass(frozen=True)
class Placement:
    column: int
    row_index: int
    x: float
    y: float
    length: float
    depth: float


def expand_depths(project: Project, column_index: int) -> list[float]:
    return [
        row.depth
        for row in project.columns[column_index].boxes
        for _ in range(row.qty)
    ]


def regroup(depths: list[float]):
    rows = []
    for depth in depths:
        if rows and rows[-1].depth == depth:
            rows[-1].qty += 1
        else:
            rows.append(type("Row", (), {"depth": depth, "qty": 1})())
    return rows


def move_box(project: Project, column_index: int, i: int, j: int) -> Project:
    column = project.columns[column_index]
    depths = expand_depths(project, column_index)
    if i == j or i < 0 or i >= len(depths) or j < 0 or j >= len(depths):
        return project
    item = depths.pop(i)
    depths.insert(j, item)
    column.boxes = regroup(depths)
    return project


def cover_width_for(project: Project, depth: float) -> float:
    d = project.defaults
    return d.cover_width_short if depth < d.short_depth_below else d.cover_width


def place(project: Project) -> list[Placement]:
    result = []
    x = 0.0
    for ci, column in enumerate(project.columns):
        y = 0.0
        row_index = 0
        for row in column.boxes:
            for _ in range(row.qty):
                result.append(Placement(ci, row_index, x, y, column.width, row.depth))
                y += row.depth
                row_index += 1
        x += column.width
    return result


def box_spec(project: Project, length: float, depth: float) -> BoxSpec:
    d = project.defaults
    return BoxSpec(
        length=length, width=depth, height=d.height, wall=d.wall, r=d.r,
        cover_width=cover_width_for(project, depth),
    )


def stats(project: Project) -> dict:
    placements = place(project)
    used_width = sum(c.width for c in project.columns)
    used_depths = [sum(row.depth * row.qty for row in c.boxes) for c in project.columns]
    unique = {(p.length, p.depth) for p in placements}
    return {
        "total_boxes": len(placements),
        "unique_sizes": len(unique),
        "used_width": used_width,
        "free_width": project.drawer.width - used_width,
        "columns": [
            {"name": c.name, "used_depth": used_depths[i],
             "free_depth": project.drawer.depth - used_depths[i]}
            for i, c in enumerate(project.columns)
        ],
    }
