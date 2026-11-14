from __future__ import annotations

from dataclasses import dataclass

from .builder import plan
from .models import Project


@dataclass(frozen=True)
class Placement:
    filename: str
    x: float
    y: float
    width: float
    depth: float
    rotated: bool


def arrange(project: Project, bed_width: float = 250, bed_depth: float = 210,
            margin: float = 5, gap: float = 2, allow_rotation: bool = True) -> dict:
    usable_width = bed_width - 2 * margin
    usable_depth = bed_depth - 2 * margin
    if usable_width <= 0 or usable_depth <= 0:
        raise ValueError("Bed margins leave no usable print area.")

    items = [
        (job.filename, job.spec.length, job.spec.width, copy + 1)
        for job in plan(project)
        for copy in range(job.qty)
    ]
    failed = []
    pack_items = []
    for item in items:
        filename, width, depth, copy = item
        if _fits(width, depth, usable_width, usable_depth, allow_rotation):
            pack_items.append(item)
        else:
            failed.append({"filename": filename, "copy": copy, "reason": "Box does not fit on the configured bed."})

    orders = [
        sorted(pack_items, key=lambda item: (item[1] * item[2], max(item[1], item[2])), reverse=True),
        sorted(pack_items, key=lambda item: (max(item[1], item[2]), min(item[1], item[2])), reverse=True),
    ]
    results = [_pack(order, usable_width, usable_depth, margin, gap, allow_rotation) for order in orders]
    best = min(results, key=lambda result: (
        len(result),
        sum(
            usable_width * usable_depth
            - sum(shelf["used_width"] * shelf["height"] for shelf in bed["shelves"])
            for bed in result
        ),
    ))
    beds = [{"number": index, "placements": bed["placements"]} for index, bed in enumerate(best, start=1)]
    return {
        "bed": {"width": bed_width, "depth": bed_depth, "margin": margin, "gap": gap},
        "beds": beds,
        "failed": failed,
        "total": len(pack_items) + len(failed),
        "placed": sum(len(bed["placements"]) for bed in best),
    }


def _pack(items, usable_width, usable_depth, margin, gap, allow_rotation):
    beds = []
    for filename, width, depth, copy in items:
        best = None
        for bed_index, bed in enumerate(beds):
            for shelf_index, shelf in enumerate(bed["shelves"]):
                for placed_width, placed_depth, rotated in _item_orientations(width, depth, allow_rotation):
                    if placed_width + gap <= usable_width - shelf["used_width"] and placed_depth <= shelf["height"]:
                        score = (0, shelf["height"] - placed_depth, usable_width - shelf["used_width"] - placed_width)
                        if best is None or score < best[0]:
                            best = (score, bed_index, shelf_index, placed_width, placed_depth, rotated)
            used_depth = sum(shelf["height"] for shelf in bed["shelves"]) + gap * len(bed["shelves"])
            for placed_width, placed_depth, rotated in _item_orientations(width, depth, allow_rotation):
                if used_depth + placed_depth <= usable_depth and placed_width <= usable_width:
                    score = (1, usable_depth - used_depth - placed_depth, usable_width - placed_width)
                    if best is None or score < best[0]:
                        best = (score, bed_index, None, placed_width, placed_depth, rotated)
        if best is None:
            beds.append({"shelves": [], "placements": []})
            bed_index = len(beds) - 1
            orientation = next(
                (
                    candidate
                    for candidate in _item_orientations(width, depth, allow_rotation)
                    if candidate[0] + gap <= usable_width and candidate[1] + gap <= usable_depth
                ),
                None,
            )
            if orientation is None:
                continue
            placed_width, placed_depth, rotated = orientation
            shelf_index = None
        else:
            _, bed_index, shelf_index, placed_width, placed_depth, rotated = best
        bed = beds[bed_index]
        if shelf_index is None:
            y = margin + sum(shelf["height"] for shelf in bed["shelves"]) + gap * len(bed["shelves"])
            shelf = {"y": y, "height": placed_depth, "used_width": 0}
            bed["shelves"].append(shelf)
        else:
            shelf = bed["shelves"][shelf_index]
            y = shelf["y"]
        x = margin + shelf["used_width"]
        bed["placements"].append({
            "filename": filename, "copy": copy, "x": x, "y": y,
            "width": placed_width, "depth": placed_depth, "rotated": rotated,
        })
        shelf["used_width"] += placed_width + gap
    return beds


def _item_orientations(width, depth, allow_rotation):
    for placed_width, placed_depth, rotated in (
        (width, depth, False),
        (depth, width, True),
    ):
        if (rotated and (not allow_rotation or placed_width == placed_depth)):
            continue
        yield placed_width, placed_depth, rotated


def _fits(width, depth, bed_width, bed_depth, allow_rotation):
    return (width <= bed_width and depth <= bed_depth) or (
        allow_rotation and depth <= bed_width and width <= bed_depth
    )
