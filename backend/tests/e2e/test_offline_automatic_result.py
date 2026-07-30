from __future__ import annotations

import json
import socket
import uuid
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.advisor import CandidateAdvisor
from app.candidates.coverage import CoverageEntry, check_coverage
from app.candidates.confidence import CandidateSourceSignal
from app.candidates.models import AutomaticResult
from app.candidates.duplicates import DuplicateRelation
from app.config import Settings
from app.db import engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    PageInventory,
    TextObservation,
    VisualObservation,
)
from app.processing.automatic_result import (
    CandidateSnapshot,
    CoverageBlocking,
    candidate_snapshot_from_inventory,
)
from app.processing.pipeline import ConfidencePolicyError, InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.projects.models import Project
from app.projects.state import ProjectState
from app.providers.base import VisionResult
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


ROOT = Path(__file__).resolve().parents[3]
QWEN_FIXTURE = (
    ROOT
    / ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json"
)
class PassingPreflight:
    def check(self) -> None:
        return None


@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


def _page_with_observations(
    page_index: int,
    observations: tuple[TextObservation, ...],
    *,
    visual_observations: tuple[VisualObservation, ...] = (),
    layout_profile_match: LayoutProfileMatch | None = None,
    width: float = 100.0,
    height: float = 100.0,
) -> PageInventory:
    return PageInventory(
        page_index=page_index,
        width=width,
        height=height,
        rotation=0,
        page_type="vector",
        processing_route="native",
        support_level="supported",
        review_required=False,
        unsupported_reason=None,
        classification_confidence=1.0,
        classification_rule_version="fixture/1",
        classification_evidence={
            "native_char_count": sum(
                len(observation.raw_text) for observation in observations
            )
        },
        pdf_to_render_matrix=(1, 0, 0, 1, 0, 0),
        render_to_pdf_matrix=(1, 0, 0, 1, 0, 0),
        observations=observations,
        visual_observations=visual_observations,
        layout_profile_match=layout_profile_match,
    )


def _page(observation: TextObservation) -> PageInventory:
    return _page_with_observations(observation.page_index, (observation,))


def _text_observation(
    raw_text: str,
    *,
    observation_id: str | None = None,
    page_index: int = 0,
    bbox_normalized: tuple[float, float, float, float] = (
        0.01,
        0.02,
        0.03,
        0.04,
    ),
    bbox_pdf: tuple[float, float, float, float] = (1, 2, 3, 4),
    source_type: str = "native",
    observation_level: str = "line",
    parent_region_id: str | None = None,
    direction_angle_degrees: float = 0.0,
    direction: tuple[float, float] = (1.0, 0.0),
) -> TextObservation:
    return TextObservation(
        observation_id=observation_id or f"observation-{page_index}-{raw_text}",
        source_type=source_type,
        observation_level=observation_level,
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=page_index,
        bbox_pdf=bbox_pdf,
        bbox_normalized=bbox_normalized,
        direction=direction,
        direction_angle_degrees=direction_angle_degrees,
        confidence=None if source_type == "native" else 0.9,
        parent_region_id=parent_region_id,
    )


def _layout_assignment(
    observation: TextObservation,
    *,
    region_id: str,
    cell_role: str,
    cell_id: str,
    boundary_distance_mm: float = 2.0,
    physical_page_outer_edge: bool = False,
) -> ObservationRegionAssignment:
    evidence_codes = (
        "bbox_inside_role",
        "center_in_role",
        "horizontal_direction",
        "single_role",
    )
    if physical_page_outer_edge:
        evidence_codes += ("physical_page_outer_edge",)
    return ObservationRegionAssignment(
        observation_id=observation.observation_id,
        page_index=observation.page_index,
        profile_id="welli-a3-landscape/1",
        region_id=region_id,  # type: ignore[arg-type]
        cell_role=cell_role,
        cell_id=cell_id,
        assignment_evidence_codes=evidence_codes,
        boundary_distance_mm=boundary_distance_mm,
        rule_version="p0-a2-welli-layout/1",
    )


def _layout_match(
    page_index: int,
    assignments: tuple[ObservationRegionAssignment, ...],
) -> LayoutProfileMatch:
    return LayoutProfileMatch(
        page_index=page_index,
        profile_id="welli-a3-landscape/1",
        match_state="high_confidence",
        geometry_evidence_codes=("body_frame", "revision_grid", "title_grid"),
        text_anchor_evidence_codes=(
            "revision_anchor_quorum",
            "title_anchor_quorum",
        ),
        assignments=assignments,
        rule_version="p0-a2-welli-layout/1",
    )


def _visual_observation(
    observation_id: str,
    associated_text_observation_ids: tuple[str, ...],
    *,
    page_index: int = 0,
) -> VisualObservation:
    return VisualObservation(
        observation_id=observation_id,
        source_type="visual",
        observation_level="annotation_context",
        page_index=page_index,
        bbox_pdf=(0.5, 1.0, 4.0, 5.0),
        bbox_normalized=(0.005, 0.01, 0.04, 0.05),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=associated_text_observation_ids,
    )


def _source(
    db_session: Session,
    storage: LocalFileStorage,
    project: Project,
    *,
    raw_text: str = "M6",
) -> StoredFile:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    page.insert_text((20.0, 30.0), raw_text)
    content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    stored = storage.write_verified(
        f"projects/{project.id}/source.pdf",
        content,
        sha256(content).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    db_session.add_all([project, source_file])
    db_session.commit()
    return source_file


def test_candidate_snapshot_source_signals_default_and_preserve() -> None:
    empty = CandidateSnapshot(
        candidates=(),
        coverage_entries=(),
        expected_observation_ids=(),
        duplicate_relations=(),
    )
    signal = CandidateSourceSignal(
        source_location_id="observation-1",
        source_type="native",
        normalized_value=Decimal("1"),
    )
    populated = CandidateSnapshot(
        candidates=(),
        coverage_entries=(),
        expected_observation_ids=(),
        duplicate_relations=(),
        source_signals=(signal,),
    )

    assert empty.source_signals == ()
    assert populated.source_signals == (signal,)
    assert replace(
        populated,
        provider_call_ids=("provider-call-1",),
    ).source_signals == (signal,)


@pytest.mark.parametrize("text", ("DRAFT", "DRAWING", "GENERAL"))
def test_plain_text_is_not_misclassified_as_roughness(text: str) -> None:
    """ITEM-003: an embedded 'ra' substring is not a roughness signal."""
    observation = TextObservation(
        observation_id=f"plain-{text.lower()}",
        source_type="native",
        observation_level="line",
        raw_text=text,
        normalized_text=text,
        page_index=0,
        bbox_pdf=(1, 2, 3, 4),
        bbox_normalized=(0.01, 0.02, 0.03, 0.04),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    assert snapshot.coverage_entries[0].disposition == "ambiguous"


@pytest.mark.parametrize(
    ("raw_text", "expected_reason"),
    [
        ("设计", "exact_metadata_label"),
        ("1:10", "drawing_scale"),
        ("A-A", "section_view_label"),
    ],
)
def test_candidate_snapshot_prefilters_exact_drawing_noise(
    raw_text: str,
    expected_reason: str,
) -> None:
    observation = _text_observation(raw_text)

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert snapshot.expected_observation_ids == (observation.observation_id,)
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "non_inspection"
    assert entry.requires_confirmation is False
    assert entry.disposition_reason == expected_reason
    assert entry.disposition_rule_version == "p0-a1-r1"


def test_candidate_snapshot_preserves_body_standalone_number() -> None:
    observation = _text_observation(
        "25",
        bbox_normalized=(0.40, 0.40, 0.44, 0.42),
    )

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0]["payload"]["item_type"] == "linear_dimension"
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "candidate"
    assert entry.candidate_id == snapshot.candidates[0]["candidate_id"]
    assert entry.requires_confirmation is False


def test_candidate_snapshot_excludes_page_frame_number() -> None:
    observation = _text_observation(
        "1",
        bbox_normalized=(0.24, 0.00, 0.26, 0.015),
    )

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "non_inspection"
    assert entry.requires_confirmation is False
    assert entry.disposition_reason == "page_frame_number"
    assert entry.disposition_rule_version == "p0-a1-r1"


def test_candidate_snapshot_keeps_title_block_number_reviewable() -> None:
    observation = _text_observation(
        "260710",
        bbox_normalized=(0.70, 0.83, 0.76, 0.86),
    )

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "ambiguous"
    assert entry.requires_confirmation is True
    assert entry.disposition_reason == "title_block_number"
    assert entry.disposition_rule_version == "p0-a1-r1"


def test_candidate_snapshot_keeps_roman_label_reviewable() -> None:
    observation = _text_observation("II")

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "ambiguous"
    assert entry.requires_confirmation is True
    assert entry.disposition_reason == "standalone_roman_label"
    assert entry.disposition_rule_version == "p0-a1-r1"


def test_candidate_snapshot_preserves_visual_page_frame_number() -> None:
    observation = _text_observation(
        "1",
        bbox_normalized=(0.24, 0.00, 0.26, 0.015),
    )
    visual = VisualObservation(
        observation_id="visual-page-frame-number",
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=(0.5, 1.0, 3.5, 5.0),
        bbox_normalized=(0.005, 0.01, 0.035, 0.05),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=(observation.observation_id,),
    )
    page = replace(_page(observation), visual_observations=(visual,))

    snapshot = candidate_snapshot_from_inventory((page,))

    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0]["payload"]["item_type"] == "linear_dimension"
    assert tuple(
        entry.disposition for entry in snapshot.coverage_entries
    ) == ("candidate", "ambiguous")


def test_candidate_snapshot_filters_only_confirmed_cross_page_overlay() -> None:
    first = _text_observation(
        "CONFIDENTIAL",
        observation_id="watermark-page-0",
        page_index=0,
        bbox_normalized=(0.1, 0.1, 0.2, 0.2),
    )
    second = _text_observation(
        "CONFIDENTIAL",
        observation_id="watermark-page-1",
        page_index=1,
        bbox_normalized=(0.11, 0.1, 0.21, 0.2),
    )

    snapshot = candidate_snapshot_from_inventory(
        (_page(first), _page(second))
    )

    assert snapshot.candidates == ()
    assert snapshot.expected_observation_ids == (
        first.observation_id,
        second.observation_id,
    )
    assert tuple(entry.disposition for entry in snapshot.coverage_entries) == (
        "non_inspection",
        "non_inspection",
    )
    assert {
        entry.disposition_reason for entry in snapshot.coverage_entries
    } == {"repeated_page_overlay"}


@pytest.mark.parametrize(
    ("raw_text", "expected_candidate_count", "expected_disposition"),
    [
        ("焊缝不得有裂纹", 2, "candidate"),
        ("Ra 3.2", 2, "candidate"),
        ("∥0.05 A", 2, "candidate"),
        ("未注公差按 GB/T 1804-m", 0, "ambiguous"),
        ("技术要求", 0, "ambiguous"),
    ],
)
def test_candidate_snapshot_preserves_repeated_cross_page_engineering_text(
    raw_text: str,
    expected_candidate_count: int,
    expected_disposition: str,
) -> None:
    first = _text_observation(
        raw_text,
        observation_id="engineering-page-0",
        page_index=0,
        bbox_normalized=(0.1, 0.1, 0.2, 0.2),
    )
    second = _text_observation(
        raw_text,
        observation_id="engineering-page-1",
        page_index=1,
        bbox_normalized=(0.11, 0.1, 0.21, 0.2),
    )

    snapshot = candidate_snapshot_from_inventory(
        (_page(first), _page(second))
    )

    assert len(snapshot.candidates) == expected_candidate_count
    assert tuple(entry.disposition for entry in snapshot.coverage_entries) == (
        expected_disposition,
        expected_disposition,
    )
    assert all(
        entry.disposition_reason != "repeated_page_overlay"
        for entry in snapshot.coverage_entries
    )
    if expected_disposition == "ambiguous":
        assert all(
            entry.requires_confirmation
            and entry.disposition_reason == "repeated_page_text"
            for entry in snapshot.coverage_entries
        )


def test_candidate_snapshot_preserves_existing_composite_grouping() -> None:
    primary = replace(
        _text_observation("Φ10", observation_id="diameter"),
        bbox_pdf=(1, 2, 31, 10),
    )
    depth = replace(
        _text_observation("深20", observation_id="depth"),
        bbox_pdf=(1, 11, 31, 19),
    )

    snapshot = candidate_snapshot_from_inventory(
        (_page_with_observations(0, (primary, depth)),)
    )

    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0]["payload"]["item_type"] == "composite"
    assert tuple(entry.disposition for entry in snapshot.coverage_entries) == (
        "candidate",
        "candidate",
    )
    assert tuple(
        entry.observation_id for entry in snapshot.coverage_entries
    ) == ("diameter", "depth")


def test_primary_disposition_failure_is_not_silently_downgraded() -> None:
    observation = _text_observation("设计")

    with (
        patch(
            "app.processing.automatic_result.classify_primary_disposition",
            side_effect=RuntimeError("disposition unavailable"),
        ),
        pytest.raises(RuntimeError, match="disposition unavailable"),
    ):
        candidate_snapshot_from_inventory((_page(observation),))


@pytest.mark.parametrize(
    "raw_text",
    ["Φ20", "M6", "R5", "25±0.02", "检查焊缝不得有裂纹"],
)
def test_candidate_snapshot_preserves_engineering_semantics(raw_text: str) -> None:
    observation = _text_observation(raw_text)

    snapshot = candidate_snapshot_from_inventory((_page(observation),))

    assert len(snapshot.candidates) == 1
    assert len(snapshot.coverage_entries) == 1
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "candidate"
    assert entry.candidate_id == snapshot.candidates[0]["candidate_id"]
    assert entry.disposition_reason is None
    assert entry.disposition_rule_version is None


def test_matched_revision_marker_and_visual_leave_candidate_path() -> None:
    marker = _text_observation("1", observation_id="welli:revision-marker-1")
    assignment = _layout_assignment(
        marker,
        region_id="revision_table",
        cell_role="revision_marker",
        cell_id="revision-marker-1",
    )
    visual = _visual_observation(
        "visual:revision-marker-1",
        (marker.observation_id,),
    )
    page = _page_with_observations(
        0,
        (marker,),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    coverage = {
        entry.observation_id: entry for entry in snapshot.coverage_entries
    }

    assert snapshot.candidates == ()
    assert coverage[marker.observation_id].disposition == "reference_context"
    assert coverage[marker.observation_id].disposition_reason == (
        "welli_revision_marker"
    )
    assert coverage[visual.observation_id].disposition == "reference_context"
    assert coverage[visual.observation_id].disposition_reason == (
        "welli_layout_visual_context"
    )
    assert snapshot.required_visual_observation_ids == ()


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
            "1",
            "page_frame",
            "page_frame_number",
            "page-frame-top-1",
            "non_inspection",
            "welli_page_frame_number",
        ),
        (
            "260508",
            "title_block",
            "title_metadata_value",
            "title-metadata-value",
            "reference_context",
            "welli_title_metadata_value",
        ),
        (
            "20260730",
            "title_block",
            "title_approval_context",
            "title-approval-context",
            "reference_context",
            "welli_title_approval_context",
        ),
    ),
)
def test_matched_layout_text_routes_before_parser(
    raw_text: str,
    region_id: str,
    cell_role: str,
    cell_id: str,
    expected_disposition: str,
    expected_reason: str,
) -> None:
    observation = _text_observation(
        raw_text,
        observation_id=f"welli:{cell_id}",
    )
    assignment = _layout_assignment(
        observation,
        region_id=region_id,
        cell_role=cell_role,
        cell_id=cell_id,
    )
    page = _page_with_observations(
        0,
        (observation,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert snapshot.candidates == ()
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == expected_disposition
    assert entry.disposition_reason == expected_reason
    assert entry.disposition_rule_version == "p0-a2-welli-layout/1"


def test_same_page_welli_watermark_routes_all_native_lines() -> None:
    points_per_mm = 72.0 / 25.4
    observations = tuple(
        _text_observation(
            "伟立机器人",
            observation_id=f"welli:watermark:{row}:{column}",
            bbox_pdf=(
                (x_mm - 8.0) * points_per_mm,
                (y_mm - 2.0) * points_per_mm,
                (x_mm + 8.0) * points_per_mm,
                (y_mm + 2.0) * points_per_mm,
            ),
            direction_angle_degrees=-30.0,
            direction=(0.8660254038, -0.5),
        )
        for row, y_mm in enumerate((40.0, 120.0, 200.0))
        for column, x_mm in enumerate((50.0, 150.0, 250.0))
    )
    page = _page_with_observations(
        0,
        observations,
        layout_profile_match=_layout_match(0, ()),
        width=420.0 * points_per_mm,
        height=297.0 * points_per_mm,
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert snapshot.candidates == ()
    assert {
        (
            entry.disposition,
            entry.disposition_reason,
            entry.disposition_rule_version,
        )
        for entry in snapshot.coverage_entries
    } == {
        (
            "non_inspection",
            "welli_same_page_watermark",
            "p0-a2-welli-layout/1",
        )
    }


def test_revision_description_engineering_evidence_preserves_entire_row() -> None:
    dimension = replace(
        _text_observation("3.2", observation_id="welli:dimension"),
        bbox_pdf=(10.0, 10.0, 20.0, 14.0),
    )
    remainder = replace(
        _text_observation("其余", observation_id="welli:remainder"),
        bbox_pdf=(22.0, 10.0, 32.0, 14.0),
    )
    assignments = tuple(
        _layout_assignment(
            observation,
            region_id="revision_table",
            cell_role="revision_description",
            cell_id="revision-description-3",
        )
        for observation in (dimension, remainder)
    )
    page = _page_with_observations(
        0,
        (dimension, remainder),
        layout_profile_match=_layout_match(0, assignments),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    coverage = {
        entry.observation_id: entry for entry in snapshot.coverage_entries
    }

    assert coverage[dimension.observation_id].disposition == "candidate"
    assert coverage[remainder.observation_id].disposition == "ambiguous"
    assert all(
        entry.disposition_reason != "welli_revision_description"
        for entry in snapshot.coverage_entries
    )


def test_plain_revision_change_prose_is_not_preserved_by_coarse_weld_hint() -> None:
    observation = _text_observation(
        "更新焊接说明",
        observation_id="welli:plain-revision-description",
    )
    assignment = _layout_assignment(
        observation,
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-1",
    )
    page = _page_with_observations(
        0,
        (observation,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert snapshot.candidates == ()
    entry = snapshot.coverage_entries[0]
    assert entry.disposition == "reference_context"
    assert entry.disposition_reason == "welli_revision_description"


def test_page_frame_edge_control_number_with_visual_context_is_resolved() -> None:
    observation = _text_observation(
        "1",
        observation_id="welli:page-frame-bottom-1",
    )
    assignment = _layout_assignment(
        observation,
        region_id="page_frame",
        cell_role="page_frame_number",
        cell_id="page-frame-bottom-1",
        boundary_distance_mm=0.0,
        physical_page_outer_edge=True,
    )
    visual = _visual_observation(
        "visual:page-frame-bottom-1",
        (observation.observation_id,),
    )
    page = _page_with_observations(
        0,
        (observation,),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    coverage = {
        entry.observation_id: entry for entry in snapshot.coverage_entries
    }

    assert snapshot.candidates == ()
    assert coverage[observation.observation_id].disposition_reason == (
        "welli_page_frame_number"
    )
    assert coverage[visual.observation_id].disposition_reason == (
        "welli_layout_visual_context"
    )
    assert snapshot.required_visual_observation_ids == ()


def test_page_frame_internal_band_boundary_keeps_visual_unresolved() -> None:
    observation = _text_observation(
        "1",
        observation_id="welli:page-frame-inner-1",
    )
    assignment = _layout_assignment(
        observation,
        region_id="page_frame",
        cell_role="page_frame_number",
        cell_id="page-frame-bottom-1",
        boundary_distance_mm=0.0,
    )
    visual = _visual_observation(
        "visual:page-frame-inner-1",
        (observation.observation_id,),
    )
    page = _page_with_observations(
        0,
        (observation,),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    coverage = {
        entry.observation_id: entry for entry in snapshot.coverage_entries
    }

    assert coverage[observation.observation_id].disposition == "candidate"
    assert coverage[visual.observation_id].disposition == "ambiguous"
    assert snapshot.required_visual_observation_ids == (visual.observation_id,)


def test_technical_requirement_precedes_overlapping_layout_assignment() -> None:
    observation = _text_observation(
        "检查焊缝不得有裂纹",
        observation_id="welli:requirement",
    )
    assignment = _layout_assignment(
        observation,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    page = _page_with_observations(
        0,
        (observation,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0]["payload"]["item_type"] == (
        "general_requirement"
    )
    assert snapshot.coverage_entries[0].disposition == "candidate"


def test_ocr_observation_appended_after_match_gets_no_layout_decision() -> None:
    observation = _text_observation(
        "25",
        observation_id="ocr:after-layout",
        source_type="ocr",
        observation_level="region",
    )
    invalid_assignment = _layout_assignment(
        observation,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    page = _page_with_observations(
        0,
        (observation,),
        layout_profile_match=_layout_match(0, (invalid_assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert len(snapshot.candidates) == 1
    assert snapshot.coverage_entries[0].disposition == "candidate"
    assert snapshot.coverage_entries[0].disposition_rule_version is None


def test_no_sidecar_snapshot_is_byte_compatible() -> None:
    observation = _text_observation("25", observation_id="no-sidecar")
    page = _page(observation)

    baseline = candidate_snapshot_from_inventory((page,))
    explicit_none = candidate_snapshot_from_inventory(
        (replace(page, layout_profile_match=None),)
    )

    assert explicit_none == baseline


@pytest.mark.parametrize(
    ("cell_role", "cell_id", "raw_text", "expected_disposition"),
    (
        (
            "revision_header",
            "revision-header",
            "更改描述",
            "non_inspection",
        ),
        (
            "title_metadata_value",
            "title-metadata-value",
            "QX-ABC",
            "reference_context",
        ),
    ),
)
def test_valid_line_and_child_span_visual_relation_is_resolved(
    cell_role: str,
    cell_id: str,
    raw_text: str,
    expected_disposition: str,
) -> None:
    line = _text_observation(raw_text, observation_id=f"line:{cell_id}")
    span = _text_observation(
        raw_text,
        observation_id=f"span:{cell_id}",
        observation_level="span",
        parent_region_id=line.observation_id,
    )
    region_id = (
        "revision_table"
        if cell_role == "revision_header"
        else "title_block"
    )
    assignment = _layout_assignment(
        line,
        region_id=region_id,
        cell_role=cell_role,
        cell_id=cell_id,
    )
    visual = _visual_observation(
        f"visual:{cell_id}",
        (line.observation_id, span.observation_id),
    )
    page = _page_with_observations(
        0,
        (line, span),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    visual_entry = next(
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == visual.observation_id
    )

    assert visual_entry.disposition == expected_disposition
    assert visual_entry.disposition_reason == "welli_layout_visual_context"
    assert visual_entry.requires_confirmation is False
    assert snapshot.required_visual_observation_ids == ()


@pytest.mark.parametrize(
    ("parent_region_id", "associated_mode"),
    (
        (None, "line-and-span"),
        ("line:layout", "span-only"),
        ("line:other", "line-and-span"),
    ),
)
def test_invalid_child_span_relation_keeps_visual_required(
    parent_region_id: str | None,
    associated_mode: str,
) -> None:
    line = _text_observation("QX-ABC", observation_id="line:layout")
    span = _text_observation(
        "QX-ABC",
        observation_id="span:layout",
        observation_level="span",
        parent_region_id=parent_region_id,
    )
    assignment = _layout_assignment(
        line,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    associated = (
        (span.observation_id,)
        if associated_mode == "span-only"
        else (line.observation_id, span.observation_id)
    )
    visual = _visual_observation("visual:invalid-span", associated)
    page = _page_with_observations(
        0,
        (line, span),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))
    visual_entry = next(
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == visual.observation_id
    )

    assert visual_entry.disposition == "ambiguous"
    assert visual_entry.requires_confirmation is True
    assert snapshot.required_visual_observation_ids == (
        visual.observation_id,
    )


def test_cross_page_span_parent_keeps_visual_required() -> None:
    parent = _text_observation(
        "QX-ABC",
        observation_id="line:cross-page",
        page_index=1,
    )
    span = _text_observation(
        "QX-ABC",
        observation_id="span:cross-page",
        page_index=0,
        observation_level="span",
        parent_region_id=parent.observation_id,
    )
    visual = _visual_observation(
        "visual:cross-page",
        (parent.observation_id, span.observation_id),
        page_index=0,
    )
    page_zero = _page_with_observations(
        0,
        (span,),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, ()),
    )
    assignment = _layout_assignment(
        parent,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    page_one = _page_with_observations(
        1,
        (parent,),
        layout_profile_match=_layout_match(1, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page_zero, page_one))

    assert snapshot.required_visual_observation_ids == (
        visual.observation_id,
    )


def test_mixed_layout_and_engineering_visual_relation_stays_required() -> None:
    layout_line = _text_observation(
        "QX-ABC",
        observation_id="line:layout-safe",
    )
    engineering_line = _text_observation(
        "M6",
        observation_id="line:engineering",
    )
    assignment = _layout_assignment(
        layout_line,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    visual = _visual_observation(
        "visual:mixed",
        (layout_line.observation_id, engineering_line.observation_id),
    )
    page = _page_with_observations(
        0,
        (layout_line, engineering_line),
        visual_observations=(visual,),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    assert snapshot.required_visual_observation_ids == (
        visual.observation_id,
    )
    visual_entry = next(
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == visual.observation_id
    )
    assert visual_entry.disposition == "ambiguous"


def test_layout_snapshot_writes_exactly_one_coverage_per_selected_source() -> None:
    line = _text_observation("QX-ABC", observation_id="line:exact-once")
    span = _text_observation(
        "QX-ABC",
        observation_id="span:exact-once",
        observation_level="span",
        parent_region_id=line.observation_id,
    )
    assignment = _layout_assignment(
        line,
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
    )
    resolved = _visual_observation(
        "visual:resolved",
        (line.observation_id, span.observation_id),
    )
    unresolved = _visual_observation("visual:unresolved", ())
    page = _page_with_observations(
        0,
        (line, span),
        visual_observations=(resolved, unresolved),
        layout_profile_match=_layout_match(0, (assignment,)),
    )

    snapshot = candidate_snapshot_from_inventory((page,))

    coverage_ids = tuple(
        entry.observation_id for entry in snapshot.coverage_entries
    )
    assert coverage_ids == snapshot.expected_observation_ids
    assert len(coverage_ids) == len(set(coverage_ids))
    assert span.observation_id not in coverage_ids
    report = check_coverage(
        snapshot.coverage_entries,
        expected_observation_ids=snapshot.expected_observation_ids,
    )
    assert report.blocking_count == 0
    assert snapshot.required_visual_observation_ids == (
        unresolved.observation_id,
    )


def test_offline_provider_fixtures_freeze_one_automatic_result(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """D3-T2: sanitized fixtures yield one coverage-checked immutable result."""
    qwen = json.loads(QWEN_FIXTURE.read_text(encoding="utf-8"))["payload"]
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(
        db_session,
        storage,
        project,
        raw_text="Ra 3.2",
    )
    provider_network_connections = 0

    class FixtureVisionProvider:
        @staticmethod
        def review_candidate(_image: bytes, _prompt: str) -> VisionResult:
            return VisionResult(
                request_id=qwen["request_id"],
                payload={
                    "schema_version": "candidate-review/1",
                    "raw_text": "Ra 3.2",
                    "item_type": "roughness",
                    "normalized_text": "Ra 3.2",
                    "requires_confirmation": True,
                },
                usage=dict(qwen["usage"]),
            )

    def forbidden_ocr_factory(_settings: Settings):
        raise AssertionError("native fixture must not construct OCR Provider")

    advisor = CandidateAdvisor(
        Settings(storage_root=storage.root),
        storage,
        project_id=str(project.id),
        provider_factory=lambda _settings: FixtureVisionProvider(),
    )
    recognition = RuntimeRecognition(
        Settings(storage_root=storage.root),
        provider_factory=forbidden_ocr_factory,
        advisor=advisor,
    )

    def block_network(*_args, **_kwargs):
        nonlocal provider_network_connections
        provider_network_connections += 1
        raise AssertionError("offline Provider fixture attempted network access")

    pipeline = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=recognition.build_inventory,
        candidate_snapshot_builder=recognition.build_candidate_snapshot,
    )
    task_key = "process:offline-fixtures"

    with (
        patch.object(socket, "socket", new=block_network),
        patch.object(socket, "create_connection", new=block_network),
        patch.object(socket, "getaddrinfo", new=block_network),
    ):
        first_ref = pipeline.run(
            str(project.id),
            source_file.resource_ref,
            task_key,
        )
        second_ref = pipeline.run(
            str(project.id),
            source_file.resource_ref,
            task_key,
        )

    result = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert result is not None
    assert first_ref == second_ref == f"automatic-result://{result.id}"
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 1
    assert result.source_file_id == source_file.id
    assert result.provider_call_ids == ["fixture-qwen-request-id"]
    assert result.coverage["coverage_checked"] is True
    assert result.coverage["blocking_count"] == 0
    assert result.candidates[0]["payload"]["coarse_type"] == "roughness"
    assert result.candidates[0]["source_location_ids"]
    assert result.candidates[0]["advisor_review"]["validated"] is True
    assert provider_network_connections == 0
    assert storage.resolve_resource_ref(result.inventory_ref).is_file()
    assert db_session.get(Project, project.id).state == ProjectState.READY_FOR_EDIT
    job = db_session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == str(project.id),
            LogicalJob.logical_task_key == task_key,
        )
    )
    assert job is not None
    assert job.status == "succeeded"
    assert job.result_ref == first_ref


def test_coverage_blocking_creates_no_raw_result_and_records_error(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """CAND-005: coverage veto persists a structured error before raw insert."""
    observation = TextObservation(
        observation_id="observation-1",
        source_type="native",
        observation_level="line",
        raw_text="M6",
        normalized_text="M6",
        page_index=0,
        bbox_pdf=(1, 2, 3, 4),
        bbox_normalized=(0.01, 0.02, 0.03, 0.04),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)
    blocking_snapshot = CandidateSnapshot(
        candidates=(),
        coverage_entries=(
            CoverageEntry(
                "observation-1",
                "ambiguous",
                None,
                (1, 2, 3, 4),
            ),
        ),
        expected_observation_ids=("observation-1",),
        duplicate_relations=(),
    )

    with pytest.raises(CoverageBlocking, match="coverage_blocking"):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (_page(observation),),
            candidate_snapshot_builder=lambda _pages: blocking_snapshot,
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:coverage-blocking",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert error.code == "coverage_blocking"
    assert error.stage == "coverage"
    assert error.severity == "blocking"
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED


def _linear_candidate(
    candidate_id: str,
    source_location_id: str,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "payload": {
            "candidate_id": candidate_id,
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "10",
            "coordinates": [1, 2, 11, 12],
            "scope": "local_feature",
            "nominal": "10",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": [source_location_id],
        "source_truth_preserved": True,
    }


def test_pipeline_freezes_mixed_confidence_decisions_after_coverage(
    db_session: Session,
    tmp_path: Path,
) -> None:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)
    candidates = tuple(
        _linear_candidate(f"candidate-{index}", f"source-{index}")
        for index in range(1, 6)
    )
    coverage_entries = tuple(
        CoverageEntry(
            observation_id=f"source-{index}",
            disposition="ambiguous" if index == 4 else "candidate",
            source_location_id=f"source-{index}",
            coordinates=(1, 2, 11, 12),
            candidate_id=f"candidate-{index}",
            requires_confirmation=index == 4,
        )
        for index in range(1, 6)
    )
    snapshot = CandidateSnapshot(
        candidates=candidates,
        coverage_entries=coverage_entries,
        expected_observation_ids=tuple(
            f"source-{index}" for index in range(1, 6)
        ),
        duplicate_relations=(
            DuplicateRelation(
                left_candidate_id="candidate-5",
                right_candidate_id="other-candidate",
            ),
        ),
        source_signals=tuple(
            CandidateSourceSignal(
                source_location_id=f"source-{index}",
                source_type="native",
                normalized_value=value,
            )
            for index, value in enumerate(
                (
                    Decimal("1"),
                    Decimal("0.80"),
                    Decimal("0.50"),
                    Decimal("1"),
                    Decimal("1"),
                ),
                start=1,
            )
        ),
    )
    observation = TextObservation(
        observation_id="inventory-source",
        source_type="native",
        observation_level="line",
        raw_text="10",
        normalized_text="10",
        page_index=0,
        bbox_pdf=(1, 2, 11, 12),
        bbox_normalized=(0.01, 0.02, 0.11, 0.12),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )

    result_ref = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(),
        inventory_builder=lambda _path: (_page(observation),),
        candidate_snapshot_builder=lambda _pages: snapshot,
    ).run(
        str(project.id),
        source_file.resource_ref,
        "process:mixed-confidence",
    )

    result = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert result is not None
    assert result_ref == f"automatic-result://{result.id}"
    assert result.schema_version == "automatic-result/2"
    decisions = [
        candidate["confidence_decision"] for candidate in result.candidates
    ]
    assert [decision["band"] for decision in decisions] == [
        "high",
        "medium",
        "low",
        "low",
        "low",
    ]
    assert all(
        set(candidate).intersection({"confidence_decision"})
        == {"confidence_decision"}
        for candidate in result.candidates
    )
    assert (
        decisions[0]["review_disposition"] == "auto_accepted"
        and decisions[1]["review_disposition"] == "review_required"
    )
    assert "ambiguous_source" in decisions[3]["evidence_codes"]
    assert "possible_duplicate" in decisions[4]["evidence_codes"]


def test_confidence_policy_failure_is_structured_and_atomic(
    db_session: Session,
    tmp_path: Path,
) -> None:
    class ExplodingPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            raise ValueError("private policy implementation detail")

    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            confidence_policy=ExplodingPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:confidence-policy-failure",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert error.code == "confidence_policy_failed"
    assert error.stage == "confidence_policy"
    assert error.cause_category == "processing_defect"
    assert error.message == "Confidence policy evaluation failed"
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED


def test_unknown_confidence_policy_version_is_rejected_before_persistence(
    db_session: Session,
    tmp_path: Path,
) -> None:
    candidate = _linear_candidate("candidate-1", "source-1")

    class UnknownVersionPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            decided = dict(candidate)
            decided["confidence_decision"] = {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/unknown",
                "evidence_codes": ["typed_schema_complete"],
            }
            return (decided,)

    snapshot = CandidateSnapshot(
        candidates=(candidate,),
        coverage_entries=(
            CoverageEntry(
                observation_id="source-1",
                disposition="candidate",
                source_location_id="source-1",
                coordinates=(1, 2, 11, 12),
                candidate_id="candidate-1",
            ),
        ),
        expected_observation_ids=("source-1",),
        duplicate_relations=(),
    )
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError):
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            candidate_snapshot_builder=lambda _pages: snapshot,
            confidence_policy=UnknownVersionPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            "process:unknown-confidence-policy",
        )

    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert (
        error.code,
        error.stage,
        error.cause_category,
    ) == (
        "confidence_policy_failed",
        "confidence_policy",
        "processing_defect",
    )


@pytest.mark.parametrize(
    "invalid_candidates",
    (
        None,
        "candidate-1",
        b"candidate-1",
        bytearray(b"candidate-1"),
        {"candidate_id": "candidate-1"},
    ),
    ids=("none", "string", "bytes", "bytearray", "mapping"),
)
def test_invalid_confidence_candidate_container_is_structured_and_atomic(
    db_session: Session,
    tmp_path: Path,
    invalid_candidates: object,
) -> None:
    class InvalidContainerPolicy:
        def evaluate_candidates(self, *_args, **_kwargs):
            return invalid_candidates

    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    storage = LocalFileStorage(tmp_path)
    source_file = _source(db_session, storage, project)

    with pytest.raises(ConfidencePolicyError) as failure:
        InventoryPipeline(
            db_session,
            storage,
            PassingPreflight(),
            inventory_builder=lambda _path: (),
            confidence_policy=InvalidContainerPolicy(),
        ).run(
            str(project.id),
            source_file.resource_ref,
            f"process:invalid-confidence-container:{type(invalid_candidates).__name__}",
        )

    assert str(failure.value.__cause__) == (
        "automatic-result/2 candidates must be a non-string sequence"
    )
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.project_id == project.id
        )
    ) == 0
    error = db_session.scalar(
        select(ErrorRecord).where(ErrorRecord.project_id == project.id)
    )
    assert error is not None
    assert (
        error.code,
        error.stage,
        error.cause_category,
    ) == (
        "confidence_policy_failed",
        "confidence_policy",
        "processing_defect",
    )
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED
