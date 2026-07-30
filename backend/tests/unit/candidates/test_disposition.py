import pytest

from app.candidates.disposition import (
    PRIMARY_DISPOSITION_RULE_VERSION,
    classify_primary_disposition,
    repeated_page_overlay_observation_ids,
)
from app.pdf.schemas import TextObservation


def _observation(
    raw_text: str,
    *,
    observation_id: str | None = None,
    page_index: int = 0,
    source_type: str = "native",
    bbox_normalized: tuple[float, float, float, float] = (0.1, 0.1, 0.2, 0.2),
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id or f"obs-{page_index}-{raw_text}",
        source_type=source_type,
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


def test_body_standalone_number_yields_to_parser() -> None:
    observation = _observation(
        "25",
        bbox_normalized=(0.40, 0.40, 0.44, 0.42),
    )

    assert classify_primary_disposition(observation) is None


@pytest.mark.parametrize(
    "bbox_normalized",
    [
        (0.24, 0.00, 0.26, 0.015),
        (0.74, 0.985, 0.76, 1.00),
    ],
)
def test_page_frame_number_is_non_inspection(
    bbox_normalized: tuple[float, float, float, float],
) -> None:
    decision = classify_primary_disposition(
        _observation("1", bbox_normalized=bbox_normalized)
    )

    assert decision is not None
    assert decision.disposition == "non_inspection"
    assert decision.reason == "page_frame_number"
    assert decision.rule_version == PRIMARY_DISPOSITION_RULE_VERSION
    assert decision.requires_confirmation is False


def test_title_block_number_remains_reviewable() -> None:
    decision = classify_primary_disposition(
        _observation(
            "260710",
            bbox_normalized=(0.70, 0.83, 0.76, 0.86),
        )
    )

    assert decision is not None
    assert decision.disposition == "ambiguous"
    assert decision.reason == "title_block_number"
    assert decision.rule_version == PRIMARY_DISPOSITION_RULE_VERSION
    assert decision.requires_confirmation is True


@pytest.mark.parametrize(
    ("bbox_normalized", "expected_reason"),
    [
        ((0.20, 0.01, 0.30, 0.03), "page_frame_number"),
        ((0.20, 0.0102, 0.30, 0.0302), None),
        ((0.20, 0.97, 0.30, 0.99), "page_frame_number"),
        ((0.20, 0.9698, 0.30, 0.9898), None),
        ((0.64, 0.81, 0.66, 0.83), "title_block_number"),
        ((0.638, 0.81, 0.66, 0.83), None),
        ((0.64, 0.808, 0.66, 0.83), None),
    ],
)
def test_standalone_number_region_boundaries(
    bbox_normalized: tuple[float, float, float, float],
    expected_reason: str | None,
) -> None:
    decision = classify_primary_disposition(
        _observation("25", bbox_normalized=bbox_normalized)
    )

    if expected_reason is None:
        assert decision is None
    else:
        assert decision is not None
        assert decision.reason == expected_reason


def test_page_frame_precedes_title_block_at_bottom_right() -> None:
    decision = classify_primary_disposition(
        _observation("1", bbox_normalized=(0.90, 0.97, 0.94, 0.99))
    )

    assert decision is not None
    assert decision.disposition == "non_inspection"
    assert decision.reason == "page_frame_number"


@pytest.mark.parametrize("source_type", ["native", "ocr"])
def test_standalone_number_region_uses_canonical_bbox_for_text_sources(
    source_type: str,
) -> None:
    decision = classify_primary_disposition(
        _observation(
            "1",
            source_type=source_type,
            bbox_normalized=(0.20, 0.00, 0.30, 0.02),
        )
    )

    assert decision is not None
    assert decision.reason == "page_frame_number"


@pytest.mark.parametrize(
    "raw_text",
    ["Φ20", "M6", "R5", "25±0.02", "检查焊缝不得有裂纹"],
)
def test_primary_disposition_does_not_capture_engineering_annotations(
    raw_text: str,
) -> None:
    assert classify_primary_disposition(_observation(raw_text)) is None


@pytest.mark.parametrize(
    ("raw_text", "bbox_normalized"),
    [
        ("1", (0.24, 0.00, 0.26, 0.015)),
        ("260710", (0.70, 0.83, 0.76, 0.86)),
        ("II", (0.1, 0.1, 0.2, 0.2)),
    ],
)
def test_context_free_label_gate_yields_to_visual_context(
    raw_text: str,
    bbox_normalized: tuple[float, float, float, float],
) -> None:
    assert (
        classify_primary_disposition(
            _observation(raw_text, bbox_normalized=bbox_normalized),
            has_visual_context=True,
        )
        is None
    )


@pytest.mark.parametrize("raw_text", ["设计", "1:10", "A-A"])
def test_exact_noise_gate_does_not_yield_to_visual_context(raw_text: str) -> None:
    decision = classify_primary_disposition(
        _observation(raw_text),
        has_visual_context=True,
    )

    assert decision is not None
    assert decision.disposition == "non_inspection"


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
