from decimal import Decimal

import pytest

from app.candidates.grouping import group_observations
from app.pdf.schemas import TextObservation


def _observation(
    observation_id: str,
    text: str,
    *,
    page_index: int = 0,
    x0: float = 10.0,
    y0: float = 10.0,
    direction: tuple[float, float] = (1.0, 0.0),
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level="line",
        raw_text=text,
        normalized_text=text,
        page_index=page_index,
        bbox_pdf=(x0, y0, x0 + 30.0, y0 + 8.0),
        bbox_normalized=(0.0, 0.0, 0.1, 0.1),
        direction=direction,
        direction_angle_degrees=0.0,
        confidence=None,
    )


@pytest.mark.parametrize(
    ("text", "quantity", "thread_spec"),
    [
        ("16 × M5", 16, "M5"),
        ("4 x M6通", 4, "M6"),
    ],
)
def test_quantity_prefix_groups_one_item(
    text: str,
    quantity: int,
    thread_spec: str,
) -> None:
    """P0-REC-007G: a quantity prefix remains one item with shared quantity."""
    candidates = group_observations([_observation("quantity", text)])

    assert len(candidates) == 1
    assert candidates[0].item_type == "thread"
    assert candidates[0].quantity == quantity
    assert candidates[0].thread_spec == thread_spec


@pytest.mark.parametrize("depth_text", ["深20", "↓20"])
def test_depth_belongs_to_ordered_requirement(depth_text: str) -> None:
    """P0-REC-007H: a nearby depth line binds after its primary requirement."""
    candidates = group_observations(
        [
            _observation("diameter", "Φ10", y0=10.0),
            _observation("depth", depth_text, y0=20.0),
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].item_type == "composite"
    assert [part["kind"] for part in candidates[0].sub_requirements] == [
        "diameter_dimension",
        "depth",
    ]
    assert candidates[0].sub_requirements[1]["value"] == Decimal("20")
    assert candidates[0].depth is None


@pytest.mark.parametrize("through_text", ["通", "贯穿"])
def test_through_belongs_to_ordered_requirement(through_text: str) -> None:
    """P0-REC-007I: a nearby through line binds after its primary requirement."""
    candidates = group_observations(
        [
            _observation("thread", "M6", y0=10.0),
            _observation("through", through_text, y0=20.0),
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].item_type == "composite"
    assert [part["kind"] for part in candidates[0].sub_requirements] == [
        "thread",
        "through",
    ]
    assert candidates[0].sub_requirements[1]["value"] is True
    assert candidates[0].through is None


def test_multiline_composite_preserves_order() -> None:
    """P0-REC-007J: spatial order is authoritative for composite requirements."""
    observations = [
        _observation("through", "贯穿", y0=30.0),
        _observation("primary", "Φ10", y0=10.0),
        _observation("depth", "深20", y0=20.0),
    ]

    candidate = group_observations(observations)[0]

    assert candidate.item_type == "composite"
    assert candidate.raw_text == "Φ10\n深20\n贯穿"
    assert [part["order"] for part in candidate.sub_requirements] == [0, 1, 2]
    assert [part["raw_text"] for part in candidate.sub_requirements] == [
        "Φ10",
        "深20",
        "贯穿",
    ]


def test_identical_text_in_different_views_remains_separate() -> None:
    """P0-REC-007J: equal text alone never merges observations across views."""
    candidates = group_observations(
        [
            _observation("view-a", "M6", page_index=0),
            _observation("view-b", "M6", page_index=1),
        ]
    )

    assert len(candidates) == 2
    assert candidates[0].raw_text == candidates[1].raw_text == "M6"
    assert candidates[0].candidate_id != candidates[1].candidate_id


def test_modifier_does_not_cross_page_or_direction() -> None:
    """P0-REC-007H: incompatible spatial evidence cannot bind a modifier."""
    observations = [
        _observation("primary", "Φ10", page_index=0),
        _observation("other-page", "深20", page_index=1, y0=20.0),
    ]

    with pytest.raises(ValueError, match="orphan candidate modifier"):
        group_observations(observations)
