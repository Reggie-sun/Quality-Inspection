from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.balloons.placement import (
    BALLOON_RADIUS_PDF,
    boxes_intersect,
    circle_intersects_box,
    glyph_bbox,
    glyph_inside_circle,
)
from app.balloons.schemas import BBox, PdfPoint


HARD_COLLISION_FLAGS = {
    "circle_overlap",
    "glyph_overlap",
    "glyph_circle_overlap",
    "owner_glyph_outside_circle",
    "outside_cropbox",
    "protected_overlap",
    "source_text_overlap",
    "unreadable_number",
    "invalid_leader",
}


def _append_once(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _point(value: object) -> PdfPoint | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) != 2:
        return None
    try:
        point = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    return point if all(math.isfinite(part) for part in point) else None


def _bbox(value: object) -> BBox | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) != 4:
        return None
    try:
        box = tuple(float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(part) for part in box):
        return None
    return box  # type: ignore[return-value]


def _attribute(value: object, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _inside_page(center: PdfPoint, page_size: PdfPoint) -> bool:
    return (
        BALLOON_RADIUS_PDF
        <= center[0]
        <= page_size[0] - BALLOON_RADIUS_PDF
        and BALLOON_RADIUS_PDF
        <= center[1]
        <= page_size[1] - BALLOON_RADIUS_PDF
    )


def _intersects_regions(
    center: PdfPoint,
    number_box: BBox,
    boxes: Sequence[BBox],
) -> bool:
    return any(
        circle_intersects_box(center, BALLOON_RADIUS_PDF, box)
        or boxes_intersect(number_box, box)
        for box in boxes
    )


def validate_balloons(
    items: Iterable[Mapping[str, Any]],
    balloons: Iterable[object],
    page_sizes: Mapping[int, PdfPoint],
    *,
    protected_boxes: Mapping[int, Sequence[BBox]] | None = None,
    source_text_boxes: Mapping[int, Sequence[BBox]] | None = None,
) -> list[str]:
    blockers: list[str] = []
    protected_by_page = protected_boxes or {}
    source_by_page = source_text_boxes or {}
    active_items = {
        str(item["item_id"]): item
        for item in items
        if item.get("active", True)
    }
    required_ids = {
        item_id
        for item_id, item in active_items.items()
        if item.get("balloon_required") is True
    }
    active_balloons = [
        balloon
        for balloon in balloons
        if _attribute(balloon, "status") == "active"
    ]
    balloon_item_ids = {
        str(_attribute(balloon, "inspection_item_id"))
        for balloon in active_balloons
    }
    if required_ids - balloon_item_ids:
        _append_once(blockers, "missing_required_balloon")

    valid_numbers: list[int] = []
    geometry: list[tuple[int, PdfPoint, BBox]] = []
    for balloon in active_balloons:
        item_id = str(_attribute(balloon, "inspection_item_id"))
        item = active_items.get(item_id)
        source_location_id = str(_attribute(balloon, "source_location_id"))
        if (
            item is None
            or item_id not in required_ids
            or source_location_id not in item.get("source_location_ids", [])
        ):
            _append_once(blockers, "item_balloon_disconnect")

        if _attribute(balloon, "placement_status") == "manual_required":
            _append_once(blockers, "manual_required")

        formal_number = _attribute(balloon, "formal_number")
        number_box: BBox | None = None
        valid_number = (
            isinstance(formal_number, int)
            and not isinstance(formal_number, bool)
            and formal_number >= 1
        )
        if not valid_number:
            _append_once(blockers, "unreadable_number")
        else:
            valid_numbers.append(formal_number)

        page_index = _attribute(balloon, "page_index")
        center = _point(_attribute(balloon, "center_pdf"))
        page_size = page_sizes.get(page_index) if isinstance(page_index, int) else None
        if center is None or page_size is None or not _inside_page(center, page_size):
            _append_once(blockers, "outside_cropbox")
        if center is not None and valid_number:
            number_box = glyph_bbox(formal_number, center)
            if not glyph_inside_circle(
                number_box,
                center,
                BALLOON_RADIUS_PDF,
            ):
                _append_once(blockers, "owner_glyph_outside_circle")
                _append_once(blockers, "unreadable_number")
            if isinstance(page_index, int):
                geometry.append((page_index, center, number_box))
                if _intersects_regions(
                    center,
                    number_box,
                    protected_by_page.get(page_index, ()),
                ):
                    _append_once(blockers, "protected_overlap")
                if _intersects_regions(
                    center,
                    number_box,
                    source_by_page.get(page_index, ()),
                ):
                    _append_once(blockers, "source_text_overlap")

        anchor = _bbox(_attribute(balloon, "anchor_bbox_pdf"))
        target = _point(_attribute(balloon, "leader_target_pdf"))
        if (
            anchor is None
            or target is None
            or not (anchor[0] <= target[0] <= anchor[2])
            or not (anchor[1] <= target[1] <= anchor[3])
            or target == center
        ):
            _append_once(blockers, "invalid_leader")

        flags = _attribute(balloon, "collision_flags")
        if isinstance(flags, Sequence) and not isinstance(flags, (str, bytes)):
            for flag in flags:
                if flag in HARD_COLLISION_FLAGS:
                    _append_once(blockers, str(flag))
                elif flag == "forbidden_overlap":
                    _append_once(blockers, "source_text_overlap")

    for index, (page_index, center, number_box) in enumerate(geometry):
        for other_page, other_center, other_box in geometry[index + 1 :]:
            if page_index != other_page:
                continue
            if math.dist(center, other_center) < BALLOON_RADIUS_PDF * 2.0:
                _append_once(blockers, "circle_overlap")
            if boxes_intersect(number_box, other_box):
                _append_once(blockers, "glyph_overlap")
            if circle_intersects_box(
                other_center,
                BALLOON_RADIUS_PDF,
                number_box,
            ) or circle_intersects_box(
                center,
                BALLOON_RADIUS_PDF,
                other_box,
            ):
                _append_once(blockers, "glyph_circle_overlap")

    if (
        len(valid_numbers) != len(active_balloons)
        or sorted(valid_numbers) != list(range(1, len(active_balloons) + 1))
    ):
        _append_once(blockers, "duplicate_or_gapped_number")
    return blockers
