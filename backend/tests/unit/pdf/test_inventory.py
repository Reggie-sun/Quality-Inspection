import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from app.pdf import inventory as inventory_module
from app.pdf.classification import PageSignals, classify_page
from app.pdf.inventory import _image_coverage, append_ocr_observations, build_inventory
from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    TextObservation,
    VisualObservation,
)
from app.processing.automatic_result import candidate_snapshot_from_inventory
from app.processing.pipeline import InventoryPipeline
from app.storage.local import LocalFileStorage


def _write_text_pdf(path: Path, *, rotate_text: bool = False) -> None:
    document = pymupdf.open()
    page = document.new_page(width=595.0, height=842.0)
    if rotate_text:
        page.insert_text((120.0, 220.0), "VERTICAL DIMENSION", rotate=90)
    else:
        page.insert_text((72.0, 96.0), "DIM   25 TOLERANCE")
    document.save(path)
    document.close()


def test_span_and_line_text_round_trip(tmp_path: Path) -> None:
    """P0-REC-006A: native span and line facts preserve raw and normalized text."""
    pdf_path = tmp_path / "text.pdf"
    _write_text_pdf(pdf_path)

    page = build_inventory(pdf_path)[0]
    native = [item for item in page.observations if item.source_type == "native"]

    assert {item.observation_level for item in native} == {"line", "span"}
    assert {item.raw_text for item in native} == {"DIM   25 TOLERANCE"}
    assert {item.normalized_text for item in native} == {"DIM 25 TOLERANCE"}
    assert all(item.font_name for item in native if item.observation_level == "span")
    assert all(item.bbox_pdf[0] <= item.bbox_pdf[2] for item in native)
    assert all(0.0 <= value <= 1.0 for item in native for value in item.bbox_normalized)


def test_observation_has_page_index(tmp_path: Path) -> None:
    """P0-REC-006B: every observation keeps its zero-based page index."""
    pdf_path = tmp_path / "indexed.pdf"
    _write_text_pdf(pdf_path)

    observations = build_inventory(pdf_path)[0].observations

    assert observations
    assert {item.page_index for item in observations} == {0}


def test_rotated_text_preserves_direction(tmp_path: Path) -> None:
    """P0-REC-006D: rotated native text preserves direction and angle."""
    pdf_path = tmp_path / "rotated.pdf"
    _write_text_pdf(pdf_path, rotate_text=True)

    span = next(
        item
        for item in build_inventory(pdf_path)[0].observations
        if item.observation_level == "span"
    )

    assert span.direction != pytest.approx((1.0, 0.0))
    assert abs(span.direction_angle_degrees) == pytest.approx(90.0)


def test_native_observation_remains_authoritative(tmp_path: Path) -> None:
    """P0-REC-003: OCR append does not overwrite native observations."""
    pdf_path = tmp_path / "native.pdf"
    _write_text_pdf(pdf_path)
    page = build_inventory(pdf_path)[0]
    native_before = page.observations
    ocr = TextObservation(
        observation_id="ocr-region-1",
        source_type="ocr",
        observation_level="span",
        raw_text="DIM 25",
        normalized_text="DIM 25",
        page_index=0,
        bbox_pdf=(70.0, 80.0, 140.0, 100.0),
        bbox_normalized=(70.0 / 595.0, 80.0 / 842.0, 140.0 / 595.0, 100.0 / 842.0),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=0.93,
        parent_region_id="region-1",
    )

    extended = append_ocr_observations(page, (ocr,))

    assert page.observations == native_before
    assert extended.observations[: len(native_before)] == native_before
    assert extended.observations[-1] == ocr
    assert all(item.source_type == "native" for item in native_before)


def test_visual_observations_are_additive_and_survive_ocr_append(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "visual-additive.pdf"
    _write_text_pdf(pdf_path)
    original = build_inventory(pdf_path)[0]
    visual = VisualObservation(
        observation_id="visual-context-1",
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=(60.0, 70.0, 120.0, 95.0),
        bbox_normalized=(
            60.0 / original.width,
            70.0 / original.height,
            120.0 / original.width,
            95.0 / original.height,
        ),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=("native-line-1",),
    )
    page = replace(original, visual_observations=(visual,))
    ocr = TextObservation(
        observation_id="ocr-region-visual-page",
        source_type="ocr",
        observation_level="region",
        raw_text="DIM 25",
        normalized_text="DIM 25",
        page_index=0,
        bbox_pdf=(70.0, 80.0, 140.0, 100.0),
        bbox_normalized=(70.0 / 595.0, 80.0 / 842.0, 140.0 / 595.0, 100.0 / 842.0),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=0.93,
    )

    assert "visual_observations" not in original.to_dict()
    assert page.to_dict()["visual_observations"] == (
        {
            "observation_id": visual.observation_id,
            "source_type": "visual",
            "observation_level": "annotation_context",
            "page_index": 0,
            "bbox_pdf": visual.bbox_pdf,
            "bbox_normalized": visual.bbox_normalized,
            "proposal_kind": "text_adjacent_vector_context",
            "geometry_sha256": "a" * 64,
            "associated_text_observation_ids": ("native-line-1",),
        },
    )
    extended = append_ocr_observations(page, (ocr,))
    assert extended.visual_observations == (visual,)
    assert extended.observations[-1] == ocr

    snapshot = candidate_snapshot_from_inventory((page,))
    visual_entries = [
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == visual.observation_id
    ]
    assert snapshot.expected_observation_ids[-1] == visual.observation_id
    assert len(visual_entries) == 1
    assert visual_entries[0].disposition == "ambiguous"
    assert visual_entries[0].source_location_id == visual.observation_id
    assert visual_entries[0].coordinates == visual.bbox_pdf
    assert visual_entries[0].requires_confirmation is True
    assert all(
        visual.observation_id not in candidate["source_location_ids"]
        for candidate in snapshot.candidates
    )


def test_page_inventory_omits_absent_layout_profile_match(tmp_path: Path) -> None:
    pdf_path = tmp_path / "layout-absent.pdf"
    _write_text_pdf(pdf_path)

    payload = build_inventory(pdf_path)[0].to_dict()

    assert "layout_profile_match" not in payload
    assert "visual_observations" not in payload


def test_page_inventory_serializes_versioned_layout_assignment(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "layout-match.pdf"
    _write_text_pdf(pdf_path)
    original = build_inventory(pdf_path)[0]
    native_line = next(
        item
        for item in original.observations
        if item.source_type == "native" and item.observation_level == "line"
    )
    assignment = ObservationRegionAssignment(
        observation_id=native_line.observation_id,
        page_index=0,
        profile_id="welli-a3-landscape/1",
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-3",
        assignment_evidence_codes=(
            "bbox_inside_role",
            "center_in_role",
            "horizontal_direction",
            "single_role",
        ),
        boundary_distance_mm=2.1,
        rule_version="p0-a2-welli-layout/1",
    )
    match = LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a3-landscape/1",
        match_state="high_confidence",
        geometry_evidence_codes=("archive_grid", "body_frame", "revision_grid"),
        text_anchor_evidence_codes=(
            "archive_anchor",
            "revision_anchor_quorum",
        ),
        assignments=(assignment,),
        rule_version="p0-a2-welli-layout/1",
    )

    payload = replace(original, layout_profile_match=match).to_dict()

    assert payload["layout_profile_match"]["assignments"][0]["cell_id"] == (
        "revision-description-3"
    )
    assert payload["layout_profile_match"]["geometry_evidence_codes"] == (
        "archive_grid",
        "body_frame",
        "revision_grid",
    )
    assert payload["layout_profile_match"]["assignments"][0][
        "assignment_evidence_codes"
    ] == (
        "bbox_inside_role",
        "center_in_role",
        "horizontal_direction",
        "single_role",
    )


def test_layout_profile_evidence_is_immutable() -> None:
    assignment = ObservationRegionAssignment(
        observation_id="native:p0:b1:l2:line",
        page_index=0,
        profile_id="welli-a3-landscape/1",
        region_id="revision_table",
        cell_role="revision_description",
        cell_id="revision-description-3",
        assignment_evidence_codes=("bbox_inside_role",),
        boundary_distance_mm=2.1,
        rule_version="p0-a2-welli-layout/1",
    )
    match = LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a3-landscape/1",
        match_state="high_confidence",
        geometry_evidence_codes=("revision_grid",),
        text_anchor_evidence_codes=("revision_anchor_quorum",),
        assignments=(assignment,),
        rule_version="p0-a2-welli-layout/1",
    )

    with pytest.raises(FrozenInstanceError):
        assignment.cell_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        match.assignments = ()  # type: ignore[misc]


def test_ocr_append_preserves_native_layout_sidecar(tmp_path: Path) -> None:
    pdf_path = tmp_path / "layout-ocr.pdf"
    _write_text_pdf(pdf_path)
    original = build_inventory(pdf_path)[0]
    native_line = next(
        item
        for item in original.observations
        if item.source_type == "native" and item.observation_level == "line"
    )
    assignment = ObservationRegionAssignment(
        observation_id=native_line.observation_id,
        page_index=0,
        profile_id="welli-a4-portrait/1",
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value-1",
        assignment_evidence_codes=("bbox_inside_role", "center_in_role"),
        boundary_distance_mm=2.0,
        rule_version="p0-a2-welli-layout/1",
    )
    match = LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a4-portrait/1",
        match_state="high_confidence",
        geometry_evidence_codes=("body_frame", "title_grid"),
        text_anchor_evidence_codes=(
            "revision_anchor_quorum",
            "title_anchor_quorum",
        ),
        assignments=(assignment,),
        rule_version="p0-a2-welli-layout/1",
    )
    page = replace(original, layout_profile_match=match)
    ocr = TextObservation(
        observation_id="ocr:layout-append",
        source_type="ocr",
        observation_level="region",
        raw_text="25",
        normalized_text="25",
        page_index=0,
        bbox_pdf=(70.0, 80.0, 140.0, 100.0),
        bbox_normalized=(70.0 / 595.0, 80.0 / 842.0, 140.0 / 595.0, 100.0 / 842.0),
        direction=(1.0, 0.0),
        direction_angle_degrees=0.0,
        confidence=0.93,
    )

    extended = append_ocr_observations(page, (ocr,))

    assert extended.layout_profile_match is match
    assert extended.layout_profile_match.assignments == (assignment,)
    assert all(
        item.observation_id != ocr.observation_id
        for item in extended.layout_profile_match.assignments
    )


def test_build_inventory_calls_layout_matcher_once_per_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "layout-producer.pdf"
    document = pymupdf.open()
    for page_index in range(2):
        page = document.new_page(width=595.0, height=842.0)
        page.insert_text((72.0, 96.0), f"PAGE {page_index + 1}")
        page.draw_rect(pymupdf.Rect(40.0, 50.0, 120.0, 100.0))
    document.save(pdf_path)
    document.close()
    calls: list[dict[str, object]] = []

    def match_spy(**kwargs):
        calls.append(kwargs)
        return LayoutProfileMatch(
            page_index=kwargs["page_index"],
            profile_id="welli-a4-portrait/1",
            match_state="high_confidence",
            geometry_evidence_codes=("body_frame", "revision_grid", "title_grid"),
            text_anchor_evidence_codes=(
                "revision_anchor_quorum",
                "title_anchor_quorum",
            ),
            assignments=(),
            rule_version="p0-a2-welli-layout/1",
        )

    monkeypatch.setattr(
        inventory_module,
        "match_welli_layout_profile",
        match_spy,
        raising=False,
    )

    pages = inventory_module.build_inventory(pdf_path)

    assert len(calls) == 2
    assert [call["page_index"] for call in calls] == [0, 1]
    assert all(call["page_width_pt"] == pytest.approx(595.0) for call in calls)
    assert all(call["page_height_pt"] == pytest.approx(842.0) for call in calls)
    assert all(call["page_rotation"] == 0 for call in calls)
    assert all(call["drawings"] for call in calls)
    assert all(
        all(item.source_type == "native" for item in call["observations"])
        for call in calls
    )
    assert [page.layout_profile_match.page_index for page in pages] == [0, 1]
    assert all("drawings" not in page.to_dict() for page in pages)


def test_build_inventory_no_match_keeps_previous_serialized_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "layout-no-match.pdf"
    _write_text_pdf(pdf_path)
    monkeypatch.setattr(
        inventory_module,
        "match_welli_layout_profile",
        lambda **_kwargs: None,
        raising=False,
    )

    page = inventory_module.build_inventory(pdf_path)[0]

    assert page.layout_profile_match is None
    assert "layout_profile_match" not in page.to_dict()


def test_inventory_storage_persists_additive_layout_sidecar(tmp_path: Path) -> None:
    pdf_path = tmp_path / "layout-storage.pdf"
    _write_text_pdf(pdf_path)
    page = build_inventory(pdf_path)[0]
    match = LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a4-portrait/1",
        match_state="high_confidence",
        geometry_evidence_codes=("body_frame", "revision_grid", "title_grid"),
        text_anchor_evidence_codes=(
            "revision_anchor_quorum",
            "title_anchor_quorum",
        ),
        assignments=(),
        rule_version="p0-a2-welli-layout/1",
    )
    storage = LocalFileStorage(tmp_path / "storage")
    pipeline = InventoryPipeline(None, storage, None)  # type: ignore[arg-type]

    resource_ref = pipeline._store_inventory(  # noqa: SLF001
        "project-layout",
        SimpleNamespace(id="job-layout"),  # type: ignore[arg-type]
        (replace(page, layout_profile_match=match),),
    )
    payload = json.loads(storage.read_bytes(resource_ref))

    assert payload["schema_version"] == "page-inventory/1"
    assert payload["pages"][0]["layout_profile_match"]["profile_id"] == (
        "welli-a4-portrait/1"
    )
    assert "drawings" not in payload["pages"][0]


def test_inventory_preserves_pymupdf_cropbox_local_bbox(tmp_path: Path) -> None:
    """P0-REC-006C: PyMuPDF CropBox-local text is not offset a second time."""
    pdf_path = tmp_path / "cropped.pdf"
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    page.insert_text((60.0, 70.0), "CROPPED DIMENSION")
    page.set_cropbox(pymupdf.Rect(50.0, 50.0, 150.0, 150.0))
    document.save(pdf_path)
    document.close()

    with pymupdf.open(pdf_path) as source:
        raw_span = source[0].get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
        x0, y0, x1, y1 = (float(value) for value in raw_span["bbox"])
        expected_bbox = (
            max(0.0, min(x0, 100.0)),
            max(0.0, min(y0, 100.0)),
            max(0.0, min(x1, 100.0)),
            max(0.0, min(y1, 100.0)),
        )

    span = next(
        item
        for item in build_inventory(pdf_path)[0].observations
        if item.observation_level == "span"
    )

    assert span.bbox_pdf == pytest.approx(expected_bbox)
    assert span.bbox_pdf[0] > 0.0
    assert span.bbox_pdf[1] > 0.0


def test_image_coverage_clips_to_visible_page() -> None:
    """P0-REC-001: off-page image area cannot force scanned routing."""

    class PageWithMostlyHiddenImage:
        rect = pymupdf.Rect(0.0, 0.0, 100.0, 100.0)

        @staticmethod
        def get_images(*, full: bool) -> list[tuple[str]]:
            assert full is True
            return [("image",)]

        @staticmethod
        def get_image_rects(_image: tuple[str]) -> list[pymupdf.Rect]:
            return [pymupdf.Rect(-990.0, 0.0, 10.0, 100.0)]

    coverage = _image_coverage(PageWithMostlyHiddenImage(), 10_000.0)
    classification = classify_page(PageSignals(0, 0, coverage, 0))

    assert coverage == pytest.approx(0.1)
    assert classification.page_type == "ambiguous"
