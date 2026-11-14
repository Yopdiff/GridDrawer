from __future__ import annotations

from .layout import place, stats
from .models import Issue, Project


def validate(project: Project) -> list[Issue]:
    d = project.defaults
    issues: list[Issue] = []
    if d.r <= d.wall:
        issues.append(Issue(level="error", msg="Corner radius must be greater than wall thickness.", where="defaults.r"))
    if d.height <= d.wall:
        issues.append(Issue(level="error", msg="Height must be greater than wall thickness.", where="defaults.height"))
    if d.cover_width >= project.drawer.depth - d.wall:
        issues.append(Issue(level="error", msg="Cover width leaves no usable opening.", where="defaults.cover_width"))
    if d.cover_width_short >= project.drawer.depth - d.wall:
        issues.append(Issue(level="error", msg="Short cover width leaves no usable opening.", where="defaults.cover_width_short"))
    for ci, column in enumerate(project.columns):
        if column.width <= 2 * d.wall:
            issues.append(Issue(level="error", msg="Column width is too small for the wall thickness.", where=f"columns[{ci}]"))
        used = sum(row.depth * row.qty for row in column.boxes)
        if used > project.drawer.depth:
            issues.append(Issue(level="warning", msg=f"{column.name} overflows the drawer depth by {used - project.drawer.depth:g} mm.", where=column.name))
        for ri, row in enumerate(column.boxes):
            if row.depth <= 2 * d.wall:
                issues.append(Issue(level="error", msg="Box depth is too small for the wall thickness.", where=f"columns[{ci}].boxes[{ri}]"))
            cover = d.cover_width_short if row.depth < d.short_depth_below else d.cover_width
            if cover >= row.depth - d.wall:
                issues.append(Issue(level="error", msg="Cover is too wide for this box depth.", where=f"columns[{ci}].boxes[{ri}]"))
            if row.depth < 20 or row.depth > 250 or column.width < 20 or column.width > 250:
                issues.append(Issue(level="warning", msg="Box dimension is outside the recommended 20-250 mm print range.", where=f"columns[{ci}].boxes[{ri}]"))
    if sum(c.width for c in project.columns) > project.drawer.width:
        issues.append(Issue(level="warning", msg="Columns overflow the drawer width.", where="columns"))
    return issues
