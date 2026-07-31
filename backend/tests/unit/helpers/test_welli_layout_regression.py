from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import tests.helpers.welli_layout_regression as regression
from app.candidates.coverage import CoverageEntry
from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    PageInventory,
    TextObservation,
    VisualObservation,
)
from app.pdf.visual_observations import VisualBatch
from app.processing.automatic_result import CandidateSnapshot


def _text(observation_id: str, raw_text: str) -> TextObservation:
    return TextObservation(
        observation_id=observation_id,
        source_type="native",
        observation_level="line",
        raw_text=raw_text,
        normalized_text=raw_text,
        page_index=0,
        bbox_pdf=(10.0, 10.0, 20.0, 20.0),
        bbox_normalized=(0.1, 0.1, 0.2, 0.2),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=None,
    )


def _visual(observation_id: str) -> VisualObservation:
    return VisualObservation(
        observation_id=observation_id,
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=(30.0, 10.0, 40.0, 20.0),
        bbox_normalized=(0.3, 0.1, 0.4, 0.2),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=("revision-marker",),
    )


def _page() -> PageInventory:
    assignments = (
        ObservationRegionAssignment(
            observation_id="revision-marker",
            page_index=0,
            profile_id="welli-a4-portrait/1",
            region_id="revision_table",
            cell_role="revision_marker",
            cell_id="revision-marker-1",
            assignment_evidence_codes=("fixture",),
            boundary_distance_mm=2.0,
            rule_version="p0-a2-welli-layout/1",
        ),
        ObservationRegionAssignment(
            observation_id="engineering-preserved",
            page_index=0,
            profile_id="welli-a4-portrait/1",
            region_id="revision_table",
            cell_role="revision_description",
            cell_id="revision-description-3",
            assignment_evidence_codes=("fixture",),
            boundary_distance_mm=2.0,
            rule_version="p0-a2-welli-layout/1",
        ),
    )
    return PageInventory(
        page_index=0,
        width=210.0,
        height=297.0,
        rotation=0,
        page_type="vector",
        processing_route="native",
        support_level="supported",
        review_required=False,
        unsupported_reason=None,
        classification_confidence=1.0,
        classification_rule_version="fixture/1",
        classification_evidence={},
        pdf_to_render_matrix=(1, 0, 0, 1, 0, 0),
        render_to_pdf_matrix=(1, 0, 0, 1, 0, 0),
        observations=(
            _text("revision-marker", "1"),
            _text("engineering-preserved", "3.2"),
            _text("watermark-line", "private raw watermark"),
            replace(
                _text("revision-marker-span", "1"),
                observation_level="span",
                parent_region_id="revision-marker",
            ),
        ),
        visual_observations=(
            _visual("visual-resolved"),
            _visual("visual-required"),
        ),
        layout_profile_match=LayoutProfileMatch(
            page_index=0,
            profile_id="welli-a4-portrait/1",
            match_state="high_confidence",
            geometry_evidence_codes=("fixture",),
            text_anchor_evidence_codes=("fixture",),
            assignments=assignments,
            rule_version="p0-a2-welli-layout/1",
        ),
    )


def _coverage(
    observation_id: str,
    disposition: str,
    *,
    candidate_id: str | None = None,
    reason: str | None = None,
) -> CoverageEntry:
    return CoverageEntry(
        observation_id=observation_id,
        disposition=disposition,
        source_location_id=observation_id,
        coordinates=(10.0, 10.0, 20.0, 20.0),
        candidate_id=candidate_id,
        requires_confirmation=disposition == "ambiguous",
        disposition_reason=reason,
        disposition_rule_version=(
            "p0-a2-welli-layout/1" if reason else None
        ),
    )


def _snapshot(*, current: bool) -> CandidateSnapshot:
    candidates = (
        {
            "candidate_id": "candidate-engineering",
            "source_location_ids": ["engineering-preserved"],
        },
    )
    if not current:
        candidates += (
            {
                "candidate_id": "candidate-marker",
                "source_location_ids": ["revision-marker"],
            },
        )
    coverage = (
        _coverage(
            "revision-marker",
            "reference_context" if current else "candidate",
            candidate_id=None if current else "candidate-marker",
            reason="welli_revision_marker" if current else None,
        ),
        _coverage(
            "engineering-preserved",
            "candidate",
            candidate_id="candidate-engineering",
        ),
        _coverage(
            "watermark-line",
            "non_inspection" if current else "ambiguous",
            reason="welli_same_page_watermark" if current else None,
        ),
        _coverage(
            "visual-resolved",
            "reference_context" if current else "ambiguous",
            reason="welli_layout_visual_context" if current else None,
        ),
        _coverage("visual-required", "ambiguous"),
    )
    return CandidateSnapshot(
        candidates=candidates,
        coverage_entries=coverage,
        expected_observation_ids=(
            "engineering-preserved",
            "revision-marker",
            "watermark-line",
            "visual-required",
            "visual-resolved",
        ),
        duplicate_relations=(),
        required_visual_observation_ids=(
            ("visual-required",)
            if current
            else ("visual-resolved", "visual-required")
        ),
    )


def test_discover_unique_pdfs_deduplicates_and_orders_by_sha(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "private-first-root"
    second_root = tmp_path / "private-second-root"
    first_root.mkdir()
    second_root.mkdir()
    duplicate_bytes = b"%PDF-private-duplicate"
    unique_bytes = b"%PDF-private-unique"
    (first_root / "private-name-a.pdf").write_bytes(duplicate_bytes)
    (second_root / "private-name-b.PDF").write_bytes(duplicate_bytes)
    (second_root / "private-name-c.pdf").write_bytes(unique_bytes)
    (second_root / "not-a-pdf.txt").write_text("ignored")

    discovered = regression.discover_unique_pdfs(
        (first_root, second_root)
    )

    assert len(discovered) == 2
    assert [
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in discovered
    ] == sorted(
        {
            hashlib.sha256(duplicate_bytes).hexdigest(),
            hashlib.sha256(unique_bytes).hexdigest(),
        }
    )


def test_discovery_and_report_reject_invalid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="at least one corpus root"):
        regression.discover_unique_pdfs(())

    text_path = tmp_path / "private-input.txt"
    text_path.write_text("not pdf")
    with pytest.raises(ValueError, match="input must be one PDF"):
        regression.build_welli_layout_report((text_path,))

    monkeypatch.delenv("QI_CURRENT_FOUR_SOURCE_ROOT", raising=False)
    monkeypatch.delenv("QI_WELLI_REGRESSION_SOURCE_ROOT", raising=False)
    with pytest.raises(ValueError, match="corpus root environment"):
        regression.main(["--output", str(tmp_path / "report.json")])


def test_report_is_canonical_private_safe_and_compares_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "private-document-name.pdf"
    pdf_path.write_bytes(b"%PDF-private-source-bytes")
    page = _page()
    snapshot_calls: list[bool] = []

    monkeypatch.setattr(
        regression,
        "build_inventory",
        lambda _path: (page,),
    )

    def fake_snapshot(pages):
        has_sidecar = pages[0].layout_profile_match is not None
        snapshot_calls.append(has_sidecar)
        return _snapshot(current=has_sidecar)

    monkeypatch.setattr(
        regression,
        "candidate_snapshot_from_inventory",
        fake_snapshot,
    )
    monkeypatch.setattr(
        regression,
        "plan_visual_batches",
        lambda _pages, snapshot: (
            (
                VisualBatch(
                    page_index=0,
                    call_index=0,
                    observation_ids=(
                        snapshot.required_visual_observation_ids
                    ),
                    crop_bbox_pdf=(0.0, 0.0, 50.0, 50.0),
                    pixel_width=100,
                    pixel_height=100,
                ),
            ),
        ),
    )

    first = regression.build_welli_layout_report((pdf_path,))
    second = regression.build_welli_layout_report((pdf_path,))
    first_bytes = regression.canonical_report_bytes(first)
    second_bytes = regression.canonical_report_bytes(second)

    assert first_bytes == second_bytes
    assert snapshot_calls == [True, False, True, False]
    assert set(first) == {"schema_version", "report", "report_sha256"}
    assert first["schema_version"] == "welli-layout-regression/1"
    expected_hash = hashlib.sha256(
        regression.canonical_report_bytes(first["report"])
    ).hexdigest()
    assert first["report_sha256"] == expected_hash
    aggregate = first["report"]["aggregate"]
    assert aggregate == {
        "control_candidate_source_count": 2,
        "current_candidate_source_count": 1,
        "candidate_source_ids_rerouted": 1,
        "revision_marker_reroutes": 1,
        "revision_description_reroutes": 0,
        "title_metadata_reroutes": 0,
        "page_frame_reroutes": 0,
        "watermark_native_line_count": 1,
        "revision_engineering_preserved_line_count": 1,
        "resolved_visual_observation_count": 1,
        "required_visual_observation_count": 1,
        "resolved_visual_ids_in_planned_batches": 0,
        "coverage_blocking_count": 0,
    }
    serialized = first_bytes.decode()
    for private_value in (
        str(tmp_path),
        pdf_path.name,
        "private raw watermark",
        "%PDF-private-source-bytes",
    ):
        assert private_value not in serialized


def test_report_rejects_duplicate_observation_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "duplicate.pdf"
    pdf_path.write_bytes(b"%PDF-duplicate-observation")
    page = _page()
    duplicate_page = replace(
        page,
        observations=(
            page.observations[0],
            replace(page.observations[1], observation_id="revision-marker"),
        ),
    )
    monkeypatch.setattr(
        regression,
        "build_inventory",
        lambda _path: (duplicate_page,),
    )

    with pytest.raises(ValueError, match="duplicate observation identity"):
        regression.build_welli_layout_report((pdf_path,))


def test_title_reroute_metric_includes_metadata_and_approval_context() -> None:
    aggregate = regression._empty_aggregate()
    current_coverage = {
        "metadata": _coverage(
            "metadata",
            "reference_context",
            reason="welli_title_metadata_value",
        ),
        "approval": _coverage(
            "approval",
            "reference_context",
            reason="welli_title_approval_context",
        ),
    }

    regression._increment_reason_counts(
        aggregate,
        rerouted_ids=frozenset(current_coverage),
        current_coverage=current_coverage,
    )

    assert aggregate["title_metadata_reroutes"] == 2
