from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


BALLOON_RADIUS_PDF = 10.0


def _append_once(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _point(value: object) -> tuple[float, float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) != 2:
        return None
    try:
        point = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    return point if all(math.isfinite(part) for part in point) else None


def _bbox(value: object) -> tuple[float, float, float, float] | None:
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
    return getattr(value, name)


def validate_balloons(
    items: Iterable[Mapping[str, Any]],
    balloons: Iterable[object],
    page_sizes: Mapping[int, tuple[float, float]],
) -> list[str]:
    blockers: list[str] = []
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

        formal_number = _attribute(balloon, "formal_number")
        if not isinstance(formal_number, int) or formal_number < 1:
            _append_once(blockers, "unreadable_number")
        else:
            valid_numbers.append(formal_number)

        page_index = _attribute(balloon, "page_index")
        center = _point(_attribute(balloon, "center_pdf"))
        page_size = page_sizes.get(page_index) if isinstance(page_index, int) else None
        if (
            center is None
            or page_size is None
            or not (
                BALLOON_RADIUS_PDF
                <= center[0]
                <= page_size[0] - BALLOON_RADIUS_PDF
            )
            or not (
                BALLOON_RADIUS_PDF
                <= center[1]
                <= page_size[1] - BALLOON_RADIUS_PDF
            )
        ):
            _append_once(blockers, "outside_cropbox")

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
        if isinstance(flags, Sequence):
            if "outside_cropbox" in flags:
                _append_once(blockers, "outside_cropbox")
            if "forbidden_overlap" in flags:
                _append_once(blockers, "invalid_leader")

    if (
        len(valid_numbers) != len(active_balloons)
        or sorted(valid_numbers) != list(range(1, len(active_balloons) + 1))
    ):
        _append_once(blockers, "duplicate_or_gapped_number")
    return blockers
