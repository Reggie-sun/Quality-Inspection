from __future__ import annotations

import pytest

from app.candidates.technical_requirements import (
    TECHNICAL_REQUIREMENT_RULE_VERSION,
    TechnicalRequirementEntry,
    classify_technical_requirement_entry,
    reconstruct_technical_requirement_entries,
)
from app.pdf.schemas import TextObservation


def observation(
    observation_id: str,
    raw_text: str,
    *,
    y0: float,
    y1: float,
    page_index: int = 0,
    direction: tuple[float, float] = (1.0, 0.0),
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level="line",
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=page_index,
        bbox_pdf=(10.0, y0, 160.0, y1),
        bbox_normalized=(0.05, y0 / 200.0, 0.80, y1 / 200.0),
        direction=direction,
        direction_angle_degrees=0.0,
        confidence=None,
    )


def entry_for(
    text: str,
    *,
    observation_id: str = "requirement",
) -> TechnicalRequirementEntry:
    entries = reconstruct_technical_requirement_entries(
        (
            observation("heading", "技术要求:", y0=10, y1=20),
            observation(observation_id, f"1.{text}", y0=24, y1=34),
        )
    )
    assert len(entries) == 1
    return entries[0]


def test_reconstructs_numbered_requirement_block_and_continuation() -> None:
    observations = (
        observation("heading", "技术要求:", y0=10, y1=20),
        observation("one", "1.未标注倒角C0.5", y0=24, y1=34),
        observation("three-a", "3.零件表面不应有划痕、擦", y0=48, y1=58),
        observation("three-b", "伤等损伤零件外观的缺陷", y0=59, y1=69),
    )

    entries = reconstruct_technical_requirement_entries(observations)

    assert [entry.ordinal for entry in entries] == [1, 3]
    assert entries[1].raw_text == "零件表面不应有划痕、擦伤等损伤零件外观的缺陷"
    assert entries[1].source_location_ids == ("three-a", "three-b")


@pytest.mark.parametrize(
    ("text", "category", "subtype"),
    [
        ("未标注倒角C0.5", "applicability_rule", "default_chamfer"),
        ("锐边去毛刺", "standalone_check", "deburr"),
        (
            "零件表面不应有划痕、擦伤等损伤零件外观的缺陷",
            "standalone_check",
            "surface_integrity",
        ),
        ("表面阳极氧化亮光银色处理", "standalone_check", "surface_treatment"),
        (
            "未注尺寸公差按GB/T 1804-m执行",
            "applicability_rule",
            "general_dimensional_tolerance",
        ),
        (
            "未注形位公差按GB/T 1184-k执行",
            "applicability_rule",
            "general_geometric_tolerance",
        ),
    ],
)
def test_classifies_approved_sample(
    text: str,
    category: str,
    subtype: str,
) -> None:
    decision = classify_technical_requirement_entry(entry_for(text))

    assert decision.category == category
    assert decision.subtype == subtype
    assert decision.rule_version == TECHNICAL_REQUIREMENT_RULE_VERSION
    assert decision.raw_text == text
    assert decision.source_location_ids == ["requirement"]


def test_heading_is_not_a_requirement() -> None:
    assert reconstruct_technical_requirement_entries(
        (observation("heading", "技术要求:", y0=10, y1=20),)
    ) == ()


def test_unnumbered_text_after_heading_is_not_collected() -> None:
    observations = (
        observation("heading", "技术要求:", y0=10, y1=20),
        observation("body", "锐边去毛刺", y0=24, y1=34),
    )

    assert reconstruct_technical_requirement_entries(observations) == ()


@pytest.mark.parametrize(
    "continuation",
    [
        observation("next-page", "伤等损伤零件外观的缺陷", y0=1, y1=11, page_index=1),
        observation(
            "rotated",
            "伤等损伤零件外观的缺陷",
            y0=35,
            y1=45,
            direction=(0.0, 1.0),
        ),
        observation("far", "伤等损伤零件外观的缺陷", y0=100, y1=110),
    ],
)
def test_page_direction_or_large_gap_stops_continuation(
    continuation: TextObservation,
) -> None:
    observations = (
        observation("heading", "技术要求:", y0=10, y1=20),
        observation("start", "1.零件表面不应有划痕、擦", y0=24, y1=34),
        continuation,
    )

    entries = reconstruct_technical_requirement_entries(observations)

    assert len(entries) == 1
    assert entries[0].raw_text == "零件表面不应有划痕、擦"
    assert entries[0].source_location_ids == ("start",)


def test_reconstructs_segments_from_one_multiline_observation() -> None:
    observations = (
        observation("block", "技术要求:\n1.锐边去毛刺\n2.表面阳极氧化处理", y0=10, y1=40),
    )

    entries = reconstruct_technical_requirement_entries(observations)

    assert [entry.ordinal for entry in entries] == [1, 2]
    assert [entry.source_segment_ids for entry in entries] == [
        ("block#1",),
        ("block#2",),
    ]


def test_identical_text_at_distinct_sources_has_distinct_requirement_id() -> None:
    first = classify_technical_requirement_entry(
        entry_for("锐边去毛刺", observation_id="source-a")
    )
    second = classify_technical_requirement_entry(
        entry_for("锐边去毛刺", observation_id="source-b")
    )

    assert first.requirement_id != second.requirement_id


@pytest.mark.parametrize(
    "text",
    [
        "未注尺寸公差按ISO 2768-m执行",
        "未注形位公差按企业标准Q/ABC 12执行",
    ],
)
def test_unknown_standard_is_unsupported_and_requires_review(text: str) -> None:
    decision = classify_technical_requirement_entry(entry_for(text))

    assert decision.category == "unsupported"
    assert decision.subtype == "unsupported"
    assert decision.match_outcome == "unresolved"
    assert decision.review_required is True


def test_standard_reference_is_parsed_without_numeric_conversion() -> None:
    decision = classify_technical_requirement_entry(
        entry_for("未注尺寸公差按GB/T1804-m执行")
    )

    assert decision.parsed_parameters == {
        "standard_code": "GB/T 1804",
        "tolerance_class": "m",
    }
    assert decision.sip_suggestion.inspection_standard == "GB/T 1804-m"
    assert decision.sip_suggestion.key_dimension is None
