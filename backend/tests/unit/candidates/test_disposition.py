import pytest

from app.candidates.disposition import (
    PRIMARY_DISPOSITION_RULE_VERSION,
    classify_primary_disposition,
    classify_technical_requirement,
    repeated_page_overlay_observation_ids,
)
from app.pdf.schemas import TextObservation


def _observation(
    raw_text: str,
    *,
    observation_id: str | None = None,
    page_index: int = 0,
    bbox_normalized: tuple[float, float, float, float] = (0.1, 0.1, 0.2, 0.2),
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id or f"obs-{page_index}-{raw_text}",
        source_type="native",
        observation_level="line",
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=page_index,
        bbox_pdf=(10.0, 10.0, 20.0, 20.0),
        bbox_normalized=bbox_normalized,
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )


@pytest.mark.parametrize(
    ("raw_text", "expected_disposition", "expected_reason", "requires_confirmation"),
    [
        ("设计", "non_inspection", "exact_metadata_label", False),
        (" 物料编码 ", "non_inspection", "exact_metadata_label", False),
        ("1:10", "non_inspection", "drawing_scale", False),
        ("2 : 15", "non_inspection", "drawing_scale", False),
        ("A-A", "non_inspection", "section_view_label", False),
        ("B - B", "non_inspection", "section_view_label", False),
        ("25", "ambiguous", "standalone_number", True),
        ("25.0", "ambiguous", "standalone_number", True),
        ("II", "ambiguous", "standalone_roman_label", True),
        ("IV", "ambiguous", "standalone_roman_label", True),
    ],
)
def test_classify_primary_disposition_is_conservative(
    raw_text: str,
    expected_disposition: str,
    expected_reason: str,
    requires_confirmation: bool,
) -> None:
    decision = classify_primary_disposition(_observation(raw_text))

    assert decision is not None
    assert decision.disposition == expected_disposition
    assert decision.reason == expected_reason
    assert decision.rule_version == PRIMARY_DISPOSITION_RULE_VERSION
    assert decision.requires_confirmation is requires_confirmation


@pytest.mark.parametrize(
    "raw_text",
    ["Φ20", "M6", "R5", "25±0.02", "检查焊缝不得有裂纹"],
)
def test_primary_disposition_does_not_capture_engineering_annotations(
    raw_text: str,
) -> None:
    assert classify_primary_disposition(_observation(raw_text)) is None


@pytest.mark.parametrize("raw_text", ["25", "II"])
def test_context_free_label_gate_yields_to_visual_context(raw_text: str) -> None:
    assert (
        classify_primary_disposition(
            _observation(raw_text),
            has_visual_context=True,
        )
        is None
    )


def test_repeated_overlay_requires_distinct_pages_and_stable_position() -> None:
    first = _observation("CONFIDENTIAL", observation_id="first", page_index=0)
    second = _observation(
        "CONFIDENTIAL",
        observation_id="second",
        page_index=1,
        bbox_normalized=(0.11, 0.1, 0.21, 0.2),
    )
    same_page = _observation(
        "CONFIDENTIAL",
        observation_id="same-page",
        page_index=0,
        bbox_normalized=(0.105, 0.1, 0.205, 0.2),
    )
    moved = _observation(
        "CONFIDENTIAL",
        observation_id="moved",
        page_index=2,
        bbox_normalized=(0.6, 0.6, 0.7, 0.7),
    )

    repeated = repeated_page_overlay_observation_ids(
        (first, second, same_page, moved)
    )

    assert repeated == frozenset({"first", "second", "same-page"})


@pytest.mark.parametrize(
    ("raw_text", "expected_disposition", "expected_reason", "requires_confirmation"),
    [
        (
            "CONFIDENTIAL",
            "non_inspection",
            "repeated_page_overlay",
            False,
        ),
        (
            "技术要求",
            "ambiguous",
            "repeated_page_text",
            True,
        ),
    ],
)
def test_repeated_page_text_requires_explicit_watermark_semantics(
    raw_text: str,
    expected_disposition: str,
    expected_reason: str,
    requires_confirmation: bool,
) -> None:
    observation = _observation(raw_text, observation_id="repeated")

    decision = classify_primary_disposition(
        observation,
        repeated_overlay_observation_ids={"repeated"},
    )

    assert decision is not None
    assert decision.disposition == expected_disposition
    assert decision.reason == expected_reason
    assert decision.requires_confirmation is requires_confirmation


@pytest.mark.parametrize(
    "raw_text",
    ["25", "Φ20", "检查焊缝不得有裂纹"],
)
def test_repeated_overlay_excludes_engineering_semantics(raw_text: str) -> None:
    repeated = repeated_page_overlay_observation_ids(
        (
            _observation(raw_text, observation_id="first", page_index=0),
            _observation(raw_text, observation_id="second", page_index=1),
        )
    )

    assert repeated == frozenset()


@pytest.mark.parametrize(
    "text",
    [
        "检查外观，不得有裂纹",
        "测量倒角，尺寸应为1×45°",
    ],
)
def test_executable_general_requirement(text: str) -> None:
    """P0-REC-007K: explicit executable checks become unballooned global items."""
    candidate = classify_technical_requirement(text, source_id=f"source:{text}")

    assert candidate is not None
    assert candidate.item_type == "general_requirement"
    assert candidate.scope == "global_requirement"
    assert candidate.balloon_required is False
    assert candidate.raw_text == text


@pytest.mark.parametrize(
    "text",
    ["技术要求", "详见图纸", "一般说明", "检查外观", "不得有裂纹"],
)
def test_non_executable_text_is_not_an_inspection_item(text: str) -> None:
    """P0-REC-007K: headings and vague references do not masquerade as items."""
    assert classify_technical_requirement(text, source_id=f"source:{text}") is None


def test_executable_requirement_requires_source_identity() -> None:
    """P0-REC-007K: accepted requirements require stable source identity."""
    with pytest.raises(TypeError, match="source_id"):
        classify_technical_requirement("检查外观，不得有裂纹")


@pytest.mark.parametrize("source_id", ["", "   "])
def test_executable_requirement_rejects_blank_source_identity(
    source_id: str,
) -> None:
    """P0-REC-007K: blank source identity cannot seed an accepted requirement."""
    with pytest.raises(ValueError, match="source_id"):
        classify_technical_requirement(
            "检查外观，不得有裂纹",
            source_id=source_id,
        )


def test_identical_requirements_at_distinct_sources_keep_distinct_identity() -> None:
    """P0-REC-007K / CAND-003: text alone cannot determine candidate identity."""
    text = "检查外观，不得有裂纹"

    first = classify_technical_requirement(
        text,
        (1, 2, 3, 4),
        source_id="view-1:observation-7",
    )
    second = classify_technical_requirement(
        text,
        (1, 2, 3, 4),
        source_id="view-2:observation-3",
    )

    assert first is not None
    assert second is not None
    assert first.candidate_id != second.candidate_id
