from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import fitz

from app.balloons.schemas import BBox, PdfPoint, PlacementStatus


BALLOON_RADIUS_PDF = 12.0
GLYPH_FONT_SIZE_PDF = 9.0
GLYPH_INSET_PDF = 1.0
DISTANCE_RINGS: tuple[float, ...] = (18.0, 30.0, 42.0, 56.0, 72.0, 90.0)
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
APPROVED_BALLOON_FONT_PATH = (
    Path(__file__).resolve().parents[2] / "assets/fonts/DejaVuSans.ttf"
)


@dataclass(frozen=True)
class PlacementInput:
    """Compatibility input for the retired single-item public test surface."""

    page_size: PdfPoint
    anchor_bbox: BBox
    forbidden: tuple[BBox, ...] = ()
    radius: float = 10.0
    gap: float = 18.0


@dataclass(frozen=True)
class PlacementItem:
    item_id: str
    formal_number: int
    anchor_bbox: BBox
    page_index: int = 0
    radius: float = BALLOON_RADIUS_PDF
    leader_target: PdfPoint | None = None


@dataclass(frozen=True)
class OccupiedBalloon:
    item_id: str
    formal_number: int
    center: PdfPoint
    radius: float
    glyph_bbox: BBox
    leader_target: PdfPoint


@dataclass(frozen=True)
class PlacementScene:
    page_size: PdfPoint
    source_text_boxes: tuple[BBox, ...] = ()
    protected_boxes: tuple[BBox, ...] = ()
    occupied: tuple[OccupiedBalloon, ...] = ()


@dataclass(frozen=True)
class PlacementResult:
    status: PlacementStatus
    center: PdfPoint
    hard_collision_flags: tuple[str, ...]
    reason: str | None
    item_id: str = ""
    formal_number: int = 0
    radius: float = BALLOON_RADIUS_PDF
    glyph_bbox: BBox = (0.0, 0.0, 0.0, 0.0)
    leader_target: PdfPoint = (0.0, 0.0)
    soft_score: float = 0.0

    @property
    def collision_flags(self) -> tuple[str, ...]:
        return self.hard_collision_flags


def anchor_center(bbox: BBox) -> PdfPoint:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


@lru_cache(maxsize=1)
def _balloon_font() -> fitz.Font:
    return fitz.Font(fontfile=str(APPROVED_BALLOON_FONT_PATH))


def glyph_bbox(formal_number: int, center: PdfPoint) -> BBox:
    text = str(formal_number)
    font = _balloon_font()
    width = max(
        5.0,
        font.text_length(text, fontsize=GLYPH_FONT_SIZE_PDF),
    )
    height = (font.ascender - font.descender) * GLYPH_FONT_SIZE_PDF
    return (
        center[0] - width / 2.0,
        center[1] - height / 2.0,
        center[0] + width / 2.0,
        center[1] + height / 2.0,
    )


def boxes_intersect(left: BBox, right: BBox) -> bool:
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def circle_intersects_box(center: PdfPoint, radius: float, box: BBox) -> bool:
    closest_x = min(max(center[0], box[0]), box[2])
    closest_y = min(max(center[1], box[1]), box[3])
    return math.hypot(center[0] - closest_x, center[1] - closest_y) < radius


def glyph_inside_circle(box: BBox, center: PdfPoint, radius: float) -> bool:
    readable_radius = radius - GLYPH_INSET_PDF
    return all(
        math.hypot(x - center[0], y - center[1]) <= readable_radius
        for x, y in (
            (box[0], box[1]),
            (box[0], box[3]),
            (box[2], box[1]),
            (box[2], box[3]),
        )
    )


def _inside_page(center: PdfPoint, page_size: PdfPoint, radius: float) -> bool:
    return (
        radius <= center[0] <= page_size[0] - radius
        and radius <= center[1] <= page_size[1] - radius
    )


def _append_once(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _segment_intersects_box(start: PdfPoint, end: PdfPoint, box: BBox) -> bool:
    if box[0] <= start[0] <= box[2] and box[1] <= start[1] <= box[3]:
        return True
    if box[0] <= end[0] <= box[2] and box[1] <= end[1] <= box[3]:
        return True
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    for edge in (box[0], box[2]):
        if dx == 0:
            continue
        ratio = (edge - start[0]) / dx
        if 0.0 <= ratio <= 1.0:
            y = start[1] + ratio * dy
            if box[1] <= y <= box[3]:
                return True
    for edge in (box[1], box[3]):
        if dy == 0:
            continue
        ratio = (edge - start[1]) / dy
        if 0.0 <= ratio <= 1.0:
            x = start[0] + ratio * dx
            if box[0] <= x <= box[2]:
                return True
    return False


def _segments_cross(
    left_start: PdfPoint,
    left_end: PdfPoint,
    right_start: PdfPoint,
    right_end: PdfPoint,
) -> bool:
    """Return only proper crossings; shared endpoints are not visual crossings."""

    if {left_start, left_end} & {right_start, right_end}:
        return False

    def orientation(start: PdfPoint, end: PdfPoint, point: PdfPoint) -> float:
        return (end[0] - start[0]) * (point[1] - start[1]) - (
            end[1] - start[1]
        ) * (point[0] - start[0])

    left_a = orientation(left_start, left_end, right_start)
    left_b = orientation(left_start, left_end, right_end)
    right_a = orientation(right_start, right_end, left_start)
    right_b = orientation(right_start, right_end, left_end)
    return left_a * left_b < 0.0 and right_a * right_b < 0.0


def _evaluate(
    item: PlacementItem,
    scene: PlacementScene,
    center: PdfPoint,
) -> PlacementResult:
    target = item.leader_target or anchor_center(item.anchor_bbox)
    number_box = glyph_bbox(item.formal_number, center)
    flags: list[str] = []

    if not _inside_page(center, scene.page_size, item.radius):
        _append_once(flags, "outside_cropbox")
    if not glyph_inside_circle(number_box, center, item.radius):
        _append_once(flags, "owner_glyph_outside_circle")
        _append_once(flags, "unreadable_number")
    if not (
        item.anchor_bbox[0] <= target[0] <= item.anchor_bbox[2]
        and item.anchor_bbox[1] <= target[1] <= item.anchor_bbox[3]
    ) or target == center:
        _append_once(flags, "invalid_leader")

    for box in scene.protected_boxes:
        if circle_intersects_box(center, item.radius, box) or boxes_intersect(
            number_box, box
        ):
            _append_once(flags, "protected_overlap")
    for box in scene.source_text_boxes:
        if circle_intersects_box(center, item.radius, box) or boxes_intersect(
            number_box, box
        ):
            _append_once(flags, "source_text_overlap")

    for occupied in scene.occupied:
        if occupied.item_id == item.item_id:
            continue
        if math.dist(center, occupied.center) < item.radius + occupied.radius:
            _append_once(flags, "circle_overlap")
        if boxes_intersect(number_box, occupied.glyph_bbox):
            _append_once(flags, "glyph_overlap")
        if circle_intersects_box(occupied.center, occupied.radius, number_box) or (
            circle_intersects_box(center, item.radius, occupied.glyph_bbox)
        ):
            _append_once(flags, "glyph_circle_overlap")

    leader_length = math.dist(center, target)
    crossed_text = sum(
        _segment_intersects_box(center, target, box)
        for box in scene.source_text_boxes
        if box != item.anchor_bbox
    )
    crossed_leaders = sum(
        _segments_cross(
            center,
            target,
            occupied.center,
            occupied.leader_target,
        )
        for occupied in scene.occupied
        if occupied.item_id != item.item_id
    )
    local_density = sum(
        1
        for occupied in scene.occupied
        if math.dist(center, occupied.center) < item.radius * 5.0
    )
    soft_score = (
        leader_length
        + crossed_text * 20.0
        + crossed_leaders * 12.0
        + local_density * 4.0
    )
    return PlacementResult(
        status="placed" if not flags else "manual_required",
        center=center,
        hard_collision_flags=tuple(flags),
        reason=None if not flags else "no_legal_candidate",
        item_id=item.item_id,
        formal_number=item.formal_number,
        radius=item.radius,
        glyph_bbox=number_box,
        leader_target=target,
        soft_score=soft_score,
    )


def evaluate_placement(
    item: PlacementItem,
    scene: PlacementScene,
    center: PdfPoint,
) -> PlacementResult:
    """Validate one operator-selected position against the canonical scene."""

    return _evaluate(item, scene, center)


def _occupied(result: PlacementResult) -> OccupiedBalloon:
    return OccupiedBalloon(
        item_id=result.item_id,
        formal_number=result.formal_number,
        center=result.center,
        radius=result.radius,
        glyph_bbox=result.glyph_bbox,
        leader_target=result.leader_target,
    )


def place_balloons(
    items: tuple[PlacementItem, ...],
    scene: PlacementScene,
) -> tuple[PlacementResult, ...]:
    """Place a stable page batch through one finite collision scene."""

    return _place_with_rings(items, scene, DISTANCE_RINGS)


def _place_with_rings(
    items: tuple[PlacementItem, ...],
    scene: PlacementScene,
    distance_rings: tuple[float, ...],
) -> tuple[PlacementResult, ...]:

    occupied = list(scene.occupied)
    placed: list[PlacementResult] = []
    ordered = sorted(items, key=lambda item: (item.formal_number, item.item_id))
    for item in ordered:
        anchor = anchor_center(item.anchor_bbox)
        candidates: list[tuple[int, float, int, int, PlacementResult]] = []
        for ring_order, distance in enumerate(distance_rings):
            for direction_order, (dx, dy) in enumerate(DIRECTIONS):
                candidate_scene = replace(scene, occupied=tuple(occupied))
                result = _evaluate(
                    item,
                    candidate_scene,
                    (anchor[0] + dx * distance, anchor[1] + dy * distance),
                )
                candidates.append(
                    (
                        len(result.hard_collision_flags),
                        result.soft_score,
                        ring_order,
                        direction_order,
                        result,
                    )
                )
        _, _, _, _, selected = min(candidates, key=lambda value: value[:4])
        placed.append(selected)
        occupied.append(_occupied(selected))
    return tuple(placed)


def place_balloon(data: PlacementInput) -> PlacementResult:
    """Compatibility wrapper; production callers use only ``place_balloons``."""

    item = PlacementItem(
        item_id="legacy-single",
        formal_number=1,
        anchor_bbox=data.anchor_bbox,
        radius=data.radius,
    )
    scene = PlacementScene(
        page_size=data.page_size,
        source_text_boxes=data.forbidden,
    )
    anchor = anchor_center(data.anchor_bbox)
    candidates: list[PlacementResult] = []
    for dx, dy in DIRECTIONS:
        center = (anchor[0] + dx * data.gap, anchor[1] + dy * data.gap)
        evaluated = _evaluate(item, scene, center)
        legacy_flags: list[str] = []
        if not _inside_page(center, data.page_size, data.radius):
            legacy_flags.append("outside_cropbox")
        if any(
            box[0] <= center[0] <= box[2] and box[1] <= center[1] <= box[3]
            for box in data.forbidden
        ):
            legacy_flags.append("forbidden_overlap")
        candidates.append(
            replace(
                evaluated,
                status="placed" if not legacy_flags else "manual_required",
                hard_collision_flags=tuple(legacy_flags),
                reason=None if not legacy_flags else "no_valid_candidate",
            )
        )
    result = min(
        enumerate(candidates),
        key=lambda value: (len(value[1].hard_collision_flags), value[0]),
    )[1]
    if result.status == "manual_required":
        return replace(result, reason="no_valid_candidate")
    return result
