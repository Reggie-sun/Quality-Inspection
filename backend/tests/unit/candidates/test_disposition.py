import pytest

from app.candidates.disposition import (
    PRIMARY_DISPOSITION_RULE_VERSION,
    WELLI_LAYOUT_RULE_VERSION,
    classify_primary_disposition,
    classify_technical_requirement,
    repeated_page_overlay_observation_ids,
)
from app.pdf.schemas import ObservationRegionAssignment, TextObservation


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


def _layout_assignment(
    observation: TextObservation,
    *,
    region_id: str,
    cell_role: str,
    cell_id: str,
    boundary_distance_mm: float = 2.0,
) -> ObservationRegionAssignment:
    return ObservationRegionAssignment(
        observation_id=observation.observation_id,
        page_index=observation.page_index,
        profile_id="welli-a3-landscape/1",
        region_id=region_id,  # type: ignore[arg-type]
        cell_role=cell_role,
        cell_id=cell_id,
        assignment_evidence_codes=(
            "bbox_inside_role",
            "center_in_role",
            "horizontal_direction",
            "single_role",
        ),
        boundary_distance_mm=boundary_distance_mm,
        rule_version=WELLI_LAYOUT_RULE_VERSION,
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


@pytest.mark.parametrize(
    (
        "raw_text",
        "region_id",
        "cell_role",
        "cell_id",
        "expected_disposition",
        "expected_reason",
    ),
    (
        (
            "QX-ABC",
            "title_block",
            "title_metadata_value",
            "title-metadata-value",
            "reference_context",
            "welli_title_metadata_value",
        ),
        (
            "张三",
            "title_block",
            "title_approval_context",
            "title-approval-context",
            "reference_context",
            "welli_title_approval_context",
        ),
        (
            "更改文件号",
            "title_block",
            "title_metadata_value",
            "title-metadata-value",
            "non_inspection",
            "welli_title_fixed_label",
        ),
        (
            "更改描述",
            "revision_table",
            "revision_header",
            "revision-header",
            "non_inspection",
            "welli_revision_header",
        ),
        (
            "1",
            "revision_table",
            "revision_marker",
            "revision-marker-1",
            "reference_context",
            "welli_revision_marker",
        ),
        (
            "修订说明",
            "revision_table",
            "revision_description",
            "revision-description-1",
            "reference_context",
            "welli_revision_description",
        ),
        (
            "描图",
            "archive_strip",
            "archive_label",
            "archive-label-2",
            "non_inspection",
            "welli_archive_label",
        ),
        (
            "王工",
            "archive_strip",
            "archive_record",
            "archive-record-2",
            "reference_context",
            "welli_archive_record",
        ),
        (
            "1",
            "page_frame",
            "page_frame_number",
            "page-frame-top-1",
            "non_inspection",
            "welli_page_frame_number",
        ),
    ),
)
def test_welli_layout_decision_table(
    raw_text: str,
    region_id: str,
    cell_role: str,
    cell_id: str,
    expected_disposition: str,
    expected_reason: str,
) -> None:
    observation = _observation(raw_text, observation_id=f"welli:{cell_id}")
    assignment = _layout_assignment(
        observation,
        region_id=region_id,
        cell_role=cell_role,
        cell_id=cell_id,
    )

    decision = classify_primary_disposition(
        observation,
        layout_assignment=assignment,
    )

    assert decision is not None
    assert decision.disposition == expected_disposition
    assert decision.reason == expected_reason
    assert decision.rule_version == WELLI_LAYOUT_RULE_VERSION
    assert decision.requires_confirmation is False


def test_exact_existing_rule_precedes_welli_layout_decision() -> None:
    observation = _observation("设计", observation_id="welli:existing-label")
    assignment = _layout_assignment(
        observation,
        region_id="title_block",
        cell_role="title_approval_context",
        cell_id="title-approval-context",
    )

    decision = classify_primary_disposition(
        observation,
        layout_assignment=assignment,
    )

    assert decision is not None
    assert decision.reason == "exact_metadata_label"
    assert decision.rule_version == PRIMARY_DISPOSITION_RULE_VERSION


def test_revision_marker_exact_row_overrides_visual_context() -> None:
    observation = _observation("2", observation_id="welli:revision-marker-2")
    assignment = _layout_assignment(
        observation,
        region_id="revision_table",
        cell_role="revision_marker",
        cell_id="revision-marker-2",
    )

    decision = classify_primary_disposition(
        observation,
        has_visual_context=True,
        layout_assignment=assignment,
        engineering_preservation_observation_ids={observation.observation_id},
    )

    assert decision is not None
    assert decision.disposition == "reference_context"
    assert decision.reason == "welli_revision_marker"


@pytest.mark.parametrize(
    "raw_text",
    (
        "Φ20",
        "检查焊缝不得有裂纹",
        "3.2",
        "其余",
    ),
)
def test_engineering_preservation_set_vetoes_layout_disposition(
    raw_text: str,
) -> None:
    observation = _observation(
        raw_text,
        observation_id=f"welli:preserved:{raw_text}",
    )
    assignment = _layout_assignment(
        observation,
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-3",
    )

    assert (
        classify_primary_disposition(
            observation,
            layout_assignment=assignment,
            engineering_preservation_observation_ids={
                observation.observation_id
            },
        )
        is None
    )


def test_revision_description_row_preservation_vetoes_all_lines() -> None:
    remainder = _observation("其余", observation_id="welli:remainder")
    dimension = _observation("3.2", observation_id="welli:dimension")
    preservation_ids = {
        remainder.observation_id,
        dimension.observation_id,
    }

    for observation in (remainder, dimension):
        assignment = _layout_assignment(
            observation,
            region_id="revision_table",
            cell_role="revision_description",
            cell_id="revision-description-3",
        )
        assert (
            classify_primary_disposition(
                observation,
                layout_assignment=assignment,
                engineering_preservation_observation_ids=preservation_ids,
            )
            is None
        )


def test_layout_boundary_inside_one_millimetre_is_not_filtered() -> None:
    observation = _observation("plain prose", observation_id="welli:edge")
    assignment = _layout_assignment(
        observation,
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-1",
        boundary_distance_mm=0.999,
    )

    assert (
        classify_primary_disposition(
            observation,
            layout_assignment=assignment,
        )
        is None
    )


@pytest.mark.parametrize(
    ("cell_role", "cell_id", "raw_text"),
    (
        ("unknown", "unknown-cell", "plain"),
        ("revision_marker", "revision-marker-2", "1"),
        ("archive_label", "archive-label-2", "校描"),
    ),
)
def test_unknown_or_conflicting_layout_evidence_yields(
    cell_role: str,
    cell_id: str,
    raw_text: str,
) -> None:
    observation = _observation(raw_text, observation_id="welli:conflict")
    assignment = _layout_assignment(
        observation,
        region_id="revision_table",
        cell_role=cell_role,
        cell_id=cell_id,
    )

    assert (
        classify_primary_disposition(
            observation,
            layout_assignment=assignment,
        )
        is None
    )


def test_same_page_welli_watermark_precedes_remaining_generic_rules() -> None:
    observation = _observation(
        "伟立机器人",
        observation_id="welli:watermark",
    )

    decision = classify_primary_disposition(
        observation,
        welli_watermark_observation_ids={observation.observation_id},
    )

    assert decision is not None
    assert decision.disposition == "non_inspection"
    assert decision.reason == "welli_same_page_watermark"
    assert decision.rule_version == WELLI_LAYOUT_RULE_VERSION


def test_engineering_preservation_vetoes_same_page_watermark() -> None:
    observation = _observation(
        "伟立机器人",
        observation_id="welli:preserved-watermark",
    )

    assert (
        classify_primary_disposition(
            observation,
            welli_watermark_observation_ids={observation.observation_id},
            engineering_preservation_observation_ids={
                observation.observation_id
            },
        )
        is None
    )


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
