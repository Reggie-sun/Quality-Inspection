from __future__ import annotations

from dataclasses import dataclass

from app.balloons.schemas import BBox, PdfPoint, PlacementStatus


DIRECTIONS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)


@dataclass(frozen=True)
class PlacementInput:
    page_size: PdfPoint
    anchor_bbox: BBox
    forbidden: tuple[BBox, ...] = ()
    radius: float = 10.0
    gap: float = 18.0


@dataclass(frozen=True)
class PlacementResult:
    status: PlacementStatus
    center: PdfPoint
    collision_flags: tuple[str, ...]
    reason: str | None


def _inside(center: PdfPoint, page_size: PdfPoint, radius: float) -> bool:
    return (
        radius <= center[0] <= page_size[0] - radius
        and radius <= center[1] <= page_size[1] - radius
    )


def _in_box(center: PdfPoint, box: BBox) -> bool:
    return box[0] <= center[0] <= box[2] and box[1] <= center[1] <= box[3]


def place_balloon(data: PlacementInput) -> PlacementResult:
    x0, y0, x1, y1 = data.anchor_bbox
    anchor = ((x0 + x1) / 2, (y0 + y1) / 2)
    scored: list[tuple[int, int, PdfPoint, tuple[str, ...]]] = []
    for order, (dx, dy) in enumerate(DIRECTIONS):
        center = (anchor[0] + dx * data.gap, anchor[1] + dy * data.gap)
        flags: list[str] = []
        if not _inside(center, data.page_size, data.radius):
            flags.append("outside_cropbox")
        if any(_in_box(center, box) for box in data.forbidden):
            flags.append("forbidden_overlap")
        scored.append((len(flags), order, center, tuple(flags)))

    score, _, center, flags = min(scored)
    if score == 0:
        return PlacementResult("placed", center, (), None)
    return PlacementResult("manual_required", center, flags, "no_valid_candidate")
