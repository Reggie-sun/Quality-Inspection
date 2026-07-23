from __future__ import annotations

import math
from pathlib import Path

import fitz
import pytest

from app.balloons.placement import (
    BALLOON_RADIUS_PDF,
    GLYPH_INSET_PDF,
    OccupiedBalloon,
    PlacementItem,
    PlacementScene,
    evaluate_placement,
    glyph_bbox,
    glyph_inside_circle,
    place_balloons,
)


def close_anchor_items() -> tuple[PlacementItem, ...]:
    """P0-BAL-006: a dense same-page set must use one shared scene."""
    return tuple(
        PlacementItem(
            item_id=f"item-{number}",
            formal_number=number,
            anchor_bbox=(74.0, 54.0, 86.0, 66.0),
        )
        for number in range(1, 6)
    )


def dense_scene() -> PlacementScene:
    return PlacementScene(
        page_size=(180.0, 120.0),
        source_text_boxes=((74.0, 54.0, 86.0, 66.0),),
        protected_boxes=((0.0, 100.0, 180.0, 120.0),),
    )


def _boxes_intersect(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def _box_intersects_circle(
    box: tuple[float, float, float, float],
    center: tuple[float, float],
    radius: float,
) -> bool:
    closest_x = min(max(center[0], box[0]), box[2])
    closest_y = min(max(center[1], box[1]), box[3])
    return math.hypot(center[0] - closest_x, center[1] - closest_y) < radius


def no_cross_balloon_circle_or_number_overlap(placed: tuple[object, ...]) -> bool:
    for index, left in enumerate(placed):
        for right in placed[index + 1 :]:
            if math.dist(left.center, right.center) < left.radius + right.radius:
                return False
            if _boxes_intersect(left.glyph_bbox, right.glyph_bbox):
                return False
            if _box_intersects_circle(left.glyph_bbox, right.center, right.radius):
                return False
            if _box_intersects_circle(right.glyph_bbox, left.center, left.radius):
                return False
    return True


def test_batch_layout_has_no_balloon_or_number_overlap() -> None:
    """P0-BAL-006: stable multi-ring placement avoids cross-balloon overlap."""
    placed = place_balloons(close_anchor_items(), dense_scene())

    assert placed == place_balloons(close_anchor_items(), dense_scene())
    assert [item.formal_number for item in placed] == [1, 2, 3, 4, 5]
    assert all(not item.hard_collision_flags for item in placed)
    assert all(item.status == "placed" for item in placed)
    assert no_cross_balloon_circle_or_number_overlap(placed)


def test_exhausted_legal_positions_require_manual_resolution() -> None:
    """P0-BAL-007: a least-bad candidate never masquerades as formal success."""
    scene = PlacementScene(
        page_size=(36.0, 36.0),
        protected_boxes=((0.0, 0.0, 36.0, 36.0),),
    )
    placed = place_balloons(
        (
            PlacementItem(
                item_id="blocked",
                formal_number=1,
                anchor_bbox=(16.0, 16.0, 20.0, 20.0),
            ),
        ),
        scene,
    )

    assert len(placed) == 1
    assert placed[0].status == "manual_required"
    assert placed[0].center is not None
    assert placed[0].hard_collision_flags
    assert placed[0].reason == "no_legal_candidate"


def test_leader_crossing_is_a_deterministic_soft_penalty() -> None:
    """P0-BAL-006: equal-length legal candidates prefer no leader crossing."""
    occupied = OccupiedBalloon(
        item_id="existing",
        formal_number=1,
        center=(20.0, 100.0),
        radius=12.0,
        glyph_bbox=(17.0, 95.0, 23.0, 105.0),
        leader_target=(180.0, 100.0),
    )
    scene = PlacementScene(page_size=(300.0, 220.0), occupied=(occupied,))
    item = PlacementItem(
        item_id="candidate",
        formal_number=2,
        anchor_bbox=(95.0, 15.0, 105.0, 25.0),
    )

    crossing = evaluate_placement(item, scene, (100.0, 180.0))
    clear = evaluate_placement(item, scene, (260.0, 20.0))

    assert crossing.hard_collision_flags == ()
    assert clear.hard_collision_flags == ()
    assert math.isclose(
        math.dist(crossing.center, crossing.leader_target),
        math.dist(clear.center, clear.leader_target),
    )
    assert crossing.soft_score > clear.soft_score


def test_number_box_uses_the_approved_render_font_metrics() -> None:
    """P0-BAL-006: collision geometry uses the export font's line metrics."""
    font_path = Path(__file__).resolve().parents[3] / "assets/fonts/DejaVuSans.ttf"
    font = fitz.Font(fontfile=str(font_path))
    box = glyph_bbox(272, (100.0, 100.0))

    assert box[2] - box[0] == pytest.approx(font.text_length("272", fontsize=9))
    assert box[3] - box[1] == pytest.approx(
        (font.ascender - font.descender) * 9
    )


def test_three_digit_number_remains_readable_inside_the_formal_circle() -> None:
    """P0-BAL-006: current-four numbering is readable beyond 99 items."""
    center = (100.0, 100.0)
    box = glyph_bbox(272, center)

    assert BALLOON_RADIUS_PDF - GLYPH_INSET_PDF > 0
    assert glyph_inside_circle(box, center, BALLOON_RADIUS_PDF)
