from __future__ import annotations

from dataclasses import dataclass

from app.balloons.schemas import BBox, PdfPoint


@dataclass(frozen=True)
class NumberableItem:
    item_id: str
    balloon_required: bool
    page_index: int
    source_bbox: BBox
    stable_seed: str
    direction: PdfPoint = (1.0, 0.0)


@dataclass(frozen=True)
class NumberedItem:
    item_id: str
    number: int


def assign_numbers(
    items: list[NumberableItem],
    start: int = 1,
) -> list[NumberedItem]:
    if start < 1:
        raise ValueError("start must be >= 1")
    ordered = sorted(
        (item for item in items if item.balloon_required),
        key=lambda item: (
            item.page_index,
            item.source_bbox[1],
            item.source_bbox[0],
            item.direction,
            item.stable_seed,
            item.item_id,
        ),
    )
    return [
        NumberedItem(item.item_id, start + index)
        for index, item in enumerate(ordered)
    ]


def assign_suggested_numbers(
    items: list[NumberableItem],
    start: int = 1,
) -> list[NumberedItem]:
    return assign_numbers(items, start=start)


def assign_formal_numbers(
    items: list[NumberableItem],
    start: int = 1,
) -> list[NumberedItem]:
    return assign_numbers(items, start=start)
