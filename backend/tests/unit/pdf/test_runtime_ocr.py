from __future__ import annotations

import uuid
from collections.abc import Mapping
import struct
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from app.config import Settings
from app.pdf.inventory import build_inventory as build_native_inventory
from app.pdf.schemas import (
    LayoutProfileMatch,
    ObservationRegionAssignment,
    PageInventory,
)
from app.processing import runtime_recognition as runtime_recognition_module
from app.processing.automatic_result import CandidateSnapshot
from app.processing.runtime_recognition import RuntimeRecognition
from app.providers.base import OcrObservation, OcrResult


def _png(width: int, height: int) -> bytes:
    pixmap = pymupdf.Pixmap(
        pymupdf.csRGB,
        pymupdf.IRect(0, 0, width, height),
        False,
    )
    pixmap.clear_with(255)
    return pixmap.tobytes("png")


def _write_pdf(
    path: Path,
    *,
    native_text: str | None = None,
    native_point: tuple[float, float] = (10.0, 20.0),
    image_rect: pymupdf.Rect | None = None,
) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    if native_text is not None:
        page.insert_text(native_point, native_text)
    if image_rect is not None:
        page.insert_image(
            image_rect,
            stream=_png(80, 60),
            keep_proportion=False,
        )
    document.save(path)
    document.close()


class RecordingOcrProvider:
    def __init__(
        self,
        *,
        raw_text: str = "M8",
        confidence: float = 98.5,
    ) -> None:
        self.calls: list[tuple[int, int]] = []
        self.raw_text = raw_text
        self.confidence = confidence

    def recognize_png(self, image: bytes) -> OcrResult:
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", image[16:24])
        self.calls.append((width, height))
        return OcrResult(
            request_id="fixture-runtime-ocr-request",
            observations=(
                OcrObservation(
                    raw_text=self.raw_text,
                    confidence=self.confidence,
                    polygon=(
                        (12.0, 8.0),
                        (72.0, 8.0),
                        (72.0, 32.0),
                        (12.0, 32.0),
                    ),
                    angle=0.0,
                ),
            ),
        )


class SourceBoundPreviewSink:
    def __init__(self) -> None:
        self.local_submissions: list[tuple[uuid.UUID, Mapping[str, object]]] = []

    def publish_local(
        self,
        *,
        source_file_id: uuid.UUID,
        snapshot: Mapping[str, object],
    ) -> None:
        assert set(snapshot) == {
            "schema_version",
            "stage",
            "candidates",
            "sources",
            "counts",
        }
        assert set(snapshot["counts"]) == {
            "local_resolved",
            "cache_resolved",
            "vlm_pending",
            "vlm_resolved",
            "unresolved",
        }
        candidates = snapshot["candidates"]
        sources = snapshot["sources"]
        assert isinstance(candidates, list)
        assert isinstance(sources, list)
        assert all(
            set(candidate) == {"candidate_id", "kind", "label"}
            for candidate in candidates
        )
        assert all(
            set(source) == {
                "source_location_id",
                "source_type",
                "page_index",
                "raw_text",
            }
            for source in sources
        )
        self.local_submissions.append((source_file_id, snapshot))


class SourceBoundAdvisor:
    def __init__(self, preview_sink: SourceBoundPreviewSink) -> None:
        self._preview_sink = preview_sink
        self.calls: list[tuple[Path, uuid.UUID, CandidateSnapshot]] = []

    def review(
        self,
        source_path: Path,
        pages: tuple[PageInventory, ...],
        snapshot: CandidateSnapshot,
        *,
        source_file_id: uuid.UUID,
    ) -> CandidateSnapshot:
        assert pages
        observations = {
            observation.observation_id: observation
            for page in pages
            for observation in page.observations
        }
        normalized_snapshot: Mapping[str, object] = {
            "schema_version": "recognition-preview/1",
            "stage": "local_ready",
            "candidates": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "kind": candidate["payload"]["item_type"],
                    "label": candidate["payload"].get("normalized_text")
                    or candidate["payload"]["raw_text"],
                }
                for candidate in snapshot.candidates
            ],
            "sources": [
                {
                    "source_location_id": signal.source_location_id,
                    "source_type": signal.source_type,
                    "page_index": observations[signal.source_location_id].page_index,
                    "raw_text": observations[signal.source_location_id].raw_text,
                }
                for signal in snapshot.source_signals
            ],
            "counts": {
                "local_resolved": len(snapshot.candidates),
                "cache_resolved": 0,
                "vlm_pending": len(snapshot.required_visual_observation_ids),
                "vlm_resolved": 0,
                "unresolved": 0,
            },
        }
        self._preview_sink.publish_local(
            source_file_id=source_file_id,
            snapshot=normalized_snapshot,
        )
        self.calls.append((source_path, source_file_id, snapshot))
        return snapshot


def _recognition(
    provider: RecordingOcrProvider,
    factory_calls: list[str],
) -> RuntimeRecognition:
    def provider_factory(_settings: Settings) -> RecordingOcrProvider:
        factory_calls.append("factory")
        return provider

    return RuntimeRecognition(
        Settings(storage_root=Path("/tmp/not-used")),
        provider_factory=provider_factory,
    )


def test_vector_page_with_complete_native_text_makes_zero_ocr_calls(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "vector.pdf"
    _write_pdf(
        pdf_path,
        native_text="COMPLETE NATIVE ENGINEERING DIMENSION TEXT",
    )
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []
    recognition = _recognition(provider, factory_calls)

    enhanced = recognition.build_inventory(pdf_path)

    assert enhanced[0].processing_route == "native"
    assert enhanced[0].observations == native[0].observations
    assert provider.calls == []
    assert factory_calls == []


def test_hybrid_image_region_appends_separate_coordinate_safe_ocr_observation(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "hybrid.pdf"
    image_rect = pymupdf.Rect(100.0, 100.0, 160.0, 140.0)
    _write_pdf(pdf_path, native_text="M6", image_rect=image_rect)
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []
    recognition = _recognition(provider, factory_calls)

    enhanced = recognition.build_inventory(pdf_path)
    snapshot = recognition.build_candidate_snapshot(enhanced)

    assert enhanced[0].processing_route == "hybrid"
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    appended = enhanced[0].observations[len(native[0].observations) :]
    assert len(appended) == 1
    assert appended[0].source_type == "ocr"
    assert appended[0].bbox_pdf == pytest.approx(
        (106.0, 104.0, 136.0, 116.0),
        abs=0.5,
    )
    assert all(0.0 <= value <= 1.0 for value in appended[0].bbox_normalized)
    assert snapshot.provider_call_ids == ("fixture-runtime-ocr-request",)
    ocr_signal = next(
        signal
        for signal in snapshot.source_signals
        if signal.source_location_id == appended[0].observation_id
    )
    assert str(ocr_signal.normalized_value) == "0.985"
    ocr_candidate = next(
        candidate
        for candidate in snapshot.candidates
        if appended[0].observation_id in candidate["source_location_ids"]
    )
    assert ocr_candidate["source_truth_preserved"] is True
    assert provider.calls == [(120, 80)]
    assert factory_calls == ["factory"]


def test_runtime_ocr_preserves_native_layout_assignments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "hybrid-layout-sidecar.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        image_rect=pymupdf.Rect(100.0, 100.0, 160.0, 140.0),
    )
    native = build_native_inventory(pdf_path)[0]
    native_line = next(
        observation
        for observation in native.observations
        if observation.source_type == "native"
        and observation.observation_level == "line"
    )
    assignment = ObservationRegionAssignment(
        observation_id=native_line.observation_id,
        page_index=0,
        profile_id="welli-a4-portrait/1",
        region_id="title_block",
        cell_role="title_metadata_value",
        cell_id="title-metadata-value",
        assignment_evidence_codes=(
            "bbox_inside_role",
            "center_in_role",
            "horizontal_direction",
            "single_role",
        ),
        boundary_distance_mm=2.0,
        rule_version="p0-a2-welli-layout/1",
    )
    match = LayoutProfileMatch(
        page_index=0,
        profile_id="welli-a4-portrait/1",
        match_state="high_confidence",
        geometry_evidence_codes=("body_frame", "revision_grid", "title_grid"),
        text_anchor_evidence_codes=(
            "revision_anchor_quorum",
            "title_anchor_quorum",
        ),
        assignments=(assignment,),
        rule_version="p0-a2-welli-layout/1",
    )
    matched_native = replace(native, layout_profile_match=match)
    monkeypatch.setattr(
        runtime_recognition_module,
        "build_native_inventory",
        lambda *_args, **_kwargs: (matched_native,),
    )
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    enhanced = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert enhanced[0].layout_profile_match is match
    assert enhanced[0].layout_profile_match.assignments == (assignment,)
    appended_ocr_ids = {
        observation.observation_id
        for observation in enhanced[0].observations
        if observation.source_type == "ocr"
    }
    assert appended_ocr_ids
    assert all(
        item.observation_id not in appended_ocr_ids
        for item in enhanced[0].layout_profile_match.assignments
    )


@pytest.mark.parametrize(
    ("confidence", "expected_signal"),
    ((73.25, "0.7325"), (float("nan"), None)),
)
def test_ambiguous_ocr_observation_still_emits_one_source_signal(
    tmp_path: Path,
    confidence: float,
    expected_signal: str | None,
) -> None:
    pdf_path = tmp_path / "ambiguous-ocr.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        image_rect=pymupdf.Rect(100.0, 100.0, 160.0, 140.0),
    )
    provider = RecordingOcrProvider(
        raw_text="NOTE",
        confidence=confidence,
    )
    factory_calls: list[str] = []
    recognition = _recognition(provider, factory_calls)

    enhanced = recognition.build_inventory(pdf_path)
    snapshot = recognition.build_candidate_snapshot(enhanced)

    ocr_observation = next(
        observation
        for observation in enhanced[0].observations
        if observation.source_type == "ocr"
    )
    ocr_entry = next(
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == ocr_observation.observation_id
    )
    ocr_signals = [
        signal
        for signal in snapshot.source_signals
        if signal.source_location_id == ocr_observation.observation_id
    ]
    assert ocr_entry.disposition == "ambiguous"
    assert len(ocr_signals) == 1
    assert ocr_signals[0].source_type == "ocr"
    if expected_signal is None:
        assert ocr_signals[0].normalized_value is None
    else:
        assert str(ocr_signals[0].normalized_value) == expected_signal
    assert len(snapshot.source_signals) == len(
        {entry.observation_id for entry in snapshot.coverage_entries}
    )
    assert len(
        {signal.source_location_id for signal in snapshot.source_signals}
    ) == len(snapshot.source_signals)


def test_runtime_recognition_forwards_exact_source_identity_to_advisor(
    tmp_path: Path,
) -> None:
    """Catches a runtime path that loses preview source identity or publishes itself."""
    pdf_path = tmp_path / "source-bound.pdf"
    _write_pdf(pdf_path, native_text="M6")
    provider = RecordingOcrProvider()
    source_file_id = uuid.UUID("00000000-0000-0000-0000-000000000601")
    sink = SourceBoundPreviewSink()
    advisor = SourceBoundAdvisor(sink)
    recognition = RuntimeRecognition(
        Settings(storage_root=Path("/tmp/not-used")),
        provider_factory=lambda _settings: provider,
        advisor=advisor,
    )

    pages = recognition.build_inventory(pdf_path)
    snapshot = recognition.build_candidate_snapshot(
        pages,
        source_file_id=source_file_id,
    )

    assert advisor.calls == [(pdf_path, source_file_id, snapshot)]
    expected_snapshot: Mapping[str, object] = {
        "schema_version": "recognition-preview/1",
        "stage": "local_ready",
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "kind": candidate["payload"]["item_type"],
                "label": candidate["payload"].get("normalized_text")
                or candidate["payload"]["raw_text"],
            }
            for candidate in snapshot.candidates
        ],
        "sources": [
            {
                "source_location_id": signal.source_location_id,
                "source_type": signal.source_type,
                "page_index": next(
                    observation.page_index
                    for page in pages
                    for observation in page.observations
                    if observation.observation_id == signal.source_location_id
                ),
                "raw_text": next(
                    observation.raw_text
                    for page in pages
                    for observation in page.observations
                    if observation.observation_id == signal.source_location_id
                ),
            }
            for signal in snapshot.source_signals
        ],
        "counts": {
            "local_resolved": len(snapshot.candidates),
            "cache_resolved": 0,
            "vlm_pending": len(snapshot.required_visual_observation_ids),
            "vlm_resolved": 0,
            "unresolved": 0,
        },
    }
    assert sink.local_submissions == [
        (
            source_file_id,
            expected_snapshot,
        )
    ]
    assert expected_snapshot["counts"] == {
        "local_resolved": 1,
        "cache_resolved": 0,
        "vlm_pending": 0,
        "vlm_resolved": 0,
        "unresolved": 0,
    }
    assert provider.calls == []


def test_supported_full_page_hybrid_uses_bounded_local_ocr_crops(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "supported-hybrid.pdf"
    _write_pdf(
        pdf_path,
        native_text="NATIVE DIMENSION TEXT REMAINS AUTHORITATIVE",
        image_rect=pymupdf.Rect(0.0, 0.0, 200.0, 200.0),
    )
    native = build_native_inventory(pdf_path)
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    enhanced = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert enhanced[0].page_type == "hybrid"
    assert enhanced[0].support_level == "supported"
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    assert 1 <= len(provider.calls) <= 16
    assert all(dimensions != (400, 400) for dimensions in provider.calls)
    assert sum(
        observation.source_type == "ocr"
        for observation in enhanced[0].observations
    ) == len(provider.calls)
    assert factory_calls == ["factory"]


def test_small_native_bbox_does_not_suppress_remaining_large_image_region(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "partially-native-image.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        native_point=(40.0, 45.0),
        image_rect=pymupdf.Rect(20.0, 20.0, 180.0, 160.0),
    )
    native = build_native_inventory(pdf_path)
    native_bbox = next(
        observation.bbox_pdf
        for observation in native[0].observations
        if observation.observation_level == "line"
    )
    image_rect = pymupdf.Rect(20.0, 20.0, 180.0, 160.0)
    assert image_rect.contains(pymupdf.Rect(native_bbox))
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    enhanced = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert enhanced[0].processing_route == "hybrid"
    assert provider.calls
    assert any(
        observation.source_type == "ocr"
        for observation in enhanced[0].observations
    )
    assert enhanced[0].observations[: len(native[0].observations)] == (
        native[0].observations
    )
    assert factory_calls == ["factory"]


def test_runtime_ocr_is_capped_at_sixteen_local_crops(tmp_path: Path) -> None:
    pdf_path = tmp_path / "many-regions.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300.0, height=240.0)
    page.insert_text((5.0, 12.0), "M6")
    image = _png(40, 30)
    for row in range(4):
        for column in range(5):
            x0 = 20.0 + column * 52.0
            y0 = 24.0 + row * 48.0
            page.insert_image(
                pymupdf.Rect(x0, y0, x0 + 40.0, y0 + 30.0),
                stream=image,
                keep_proportion=False,
            )
    document.save(pdf_path)
    document.close()
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert len(provider.calls) == 16
    assert factory_calls == ["factory"]


def test_ocr_never_receives_whole_page_when_only_one_image_region_is_missing(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "bounded-region.pdf"
    _write_pdf(
        pdf_path,
        native_text="M6",
        image_rect=pymupdf.Rect(100.0, 100.0, 160.0, 140.0),
    )
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert provider.calls == [(120, 80)]
    assert provider.calls[0][0] < 400
    assert provider.calls[0][1] < 400
    assert factory_calls == ["factory"]


def test_pure_scanned_page_stays_unsupported_without_ocr_promotion(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _write_pdf(
        pdf_path,
        image_rect=pymupdf.Rect(0.0, 0.0, 200.0, 200.0),
    )
    provider = RecordingOcrProvider()
    factory_calls: list[str] = []

    pages = _recognition(provider, factory_calls).build_inventory(pdf_path)

    assert pages[0].support_level == "unsupported"
    assert pages[0].processing_route == "unsupported"
    assert pages[0].review_required is True
    assert pages[0].observations
    assert len(provider.calls) == 4
    assert factory_calls == ["factory"]
