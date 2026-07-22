from __future__ import annotations

from dataclasses import dataclass, replace

from app.balloons.validator import validate_balloons


@dataclass(frozen=True)
class BalloonValue:
    inspection_item_id: str
    source_location_id: str
    page_index: int
    formal_number: int | None
    anchor_bbox_pdf: list[float]
    leader_target_pdf: list[float]
    center_pdf: list[float]
    placement_status: str
    collision_flags: list[str]
    status: str = "active"


def test_manual_required_and_formal_invalidity_are_distinct() -> None:
    """P0-BAL-014: layout quality alone differs from formal invalidity."""
    items = [
        {
            "item_id": "i1",
            "active": True,
            "balloon_required": True,
            "source_location_ids": ["s1"],
        }
    ]
    manual = BalloonValue(
        inspection_item_id="i1",
        source_location_id="s1",
        page_index=0,
        formal_number=1,
        anchor_bbox_pdf=[20, 20, 40, 40],
        leader_target_pdf=[30, 30],
        center_pdf=[60, 60],
        placement_status="manual_required",
        collision_flags=[],
    )

    assert validate_balloons(items, [manual], {0: (100, 100)}) == []

    invalid = replace(
        manual,
        formal_number=None,
        center_pdf=[120, 120],
        leader_target_pdf=[90, 90],
    )
    blockers = validate_balloons(items, [invalid], {0: (100, 100)})

    assert "manual_required" not in blockers
    assert "outside_cropbox" in blockers
    assert "unreadable_number" in blockers
    assert "invalid_leader" in blockers

    edge_overflow = replace(manual, center_pdf=[5, 50])
    assert "outside_cropbox" in validate_balloons(
        items,
        [edge_overflow],
        {0: (100, 100)},
    )
