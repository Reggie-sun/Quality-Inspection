from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

import app.candidates.advisor as advisor_module
from app.candidates.advisor import (
    CandidateAdvisor,
    CandidateAdvisorFailure,
    VisualExecutionIdentity,
)
from app.candidates.coverage import CoverageEntry
from app.candidates.duplicates import DuplicateRelation
from app.candidates.local_symbol_resolution import LocalResolution
from app.candidates.symbol_escalation_planner import (
    reserve_escalation_budget_window as real_reserve_escalation_budget_window,
)
from app.candidates.symbol_review import VisualReviewDecision
from app.candidates.symbol_routing import RoutingDecision
from app.candidates.technical_requirements import (
    TechnicalRequirementEntry,
    evaluate_technical_requirements,
)
from app.config import Settings
from app.pdf.inventory import build_inventory
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import (
    VisualBatch,
    reconstruct_visual_geometry_contexts,
)
from app.processing.automatic_result import (
    CandidateSnapshot,
    candidate_snapshot_from_inventory,
)
from app.providers.base import VisionResult
from app.providers.qwen_vl import VisualSymbolProviderError
from app.storage.local import LocalFileStorage


def advisor_payload(
    raw_text: str,
    item_type: str,
    normalized_text: str,
    requires_confirmation: bool,
) -> dict[str, object]:
    return {
        "schema_version": "candidate-review/1",
        "raw_text": raw_text,
        "item_type": item_type,
        "normalized_text": normalized_text,
        "requires_confirmation": requires_confirmation,
    }


class RecordingVisionProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.images: list[bytes] = []
        self.prompts: list[str] = []

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        self.images.append(image)
        self.prompts.append(prompt)
        return VisionResult(
            request_id=f"fixture-qwen-request-{len(self.images)}",
            payload=dict(self.payload),
            usage={"total_tokens": 10},
        )


class SequenceVisionProvider:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls = 0

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        del image, prompt
        payload = self.payloads[self.calls]
        self.calls += 1
        return VisionResult(
            request_id=f"fixture-qwen-request-{self.calls}",
            payload=dict(payload),
            usage={},
        )


class EchoVisionProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        self.calls.append(request)
        return VisionResult(
            request_id=f"fixture-qwen-request-{len(self.calls)}",
            payload=advisor_payload(
                raw_text=str(request["raw_text"]),
                item_type=str(request["expected_type"]),
                normalized_text=str(request["raw_text"]),
                requires_confirmation=True,
            ),
            usage={},
        )


class UnifiedRecordingProvider(EchoVisionProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_order: list[str] = []

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        assert json.loads(prompt)["schema_version"] == "visual-symbol-review/2"
        self.call_order.append("visual")
        return VisionResult(
            request_id="fixture-visual-request-1",
            payload={
                "schema_version": "visual-symbol-review/2",
                "detections": [],
            },
            usage={},
        )

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        self.call_order.append("text")
        return super().review_candidate(image, prompt)


class RetryRecordingProvider(UnifiedRecordingProvider):
    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        assert json.loads(prompt)["schema_version"] == "visual-symbol-review/2"
        self.call_order.append("visual")
        call_count = self.call_order.count("visual")
        if call_count == 1:
            raise VisualSymbolProviderError(
                request_id="fixture-visual-retry-1",
                usage={"total_tokens": 11},
                failure_stage="tool_arguments_schema_invalid",
            )
        return VisionResult(
            request_id="fixture-visual-retry-success",
            payload={
                "schema_version": "visual-symbol-review/2",
                "detections": [],
            },
            usage={"total_tokens": 12},
        )


class VisualDiameterProvider(EchoVisionProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_order: list[str] = []

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        assert request["schema_version"] == "visual-symbol-review/2"
        assert request["prompt_version"] == "visual-symbol-prompt/4"
        assert len(request["visual_contexts"]) == 1
        context = request["visual_contexts"][0]
        assert context["visual_observation_id"] in request[
            "visual_observation_ids"
        ]
        assert all(
            0.0 <= value <= 1.0
            for value in context["context_bbox_normalized"]
        )
        line = next(
            item
            for item in context["associated_text_allowlist"]
            if item["observation_level"] == "line"
        )
        assert line["raw_text"] == "10"
        self.call_order.append("visual")
        return VisionResult(
            request_id="fixture-visual-diameter-request",
            payload={
                "schema_version": "visual-symbol-review/2",
                "detections": [
                    {
                        "visual_observation_id": context[
                            "visual_observation_id"
                        ],
                        "symbol_kind": "diameter",
                        "bbox_normalized": [0.1, 0.1, 0.4, 0.4],
                        "associated_text_observation_ids": [
                            line["observation_id"]
                        ],
                        "confidence_signal": 0.97,
                    }
                ],
            },
            usage={},
        )

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        self.call_order.append("text")
        return super().review_candidate(image, prompt)


class VisualRoughnessProvider(EchoVisionProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_order: list[str] = []

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
        assert image.startswith(b"\x89PNG")
        request = json.loads(prompt)
        context = request["visual_contexts"][0]
        line = next(
            item
            for item in context["associated_text_allowlist"]
            if item["observation_level"] == "line"
        )
        assert str(line["raw_text"]).startswith("Ra ")
        self.call_order.append("visual")
        return VisionResult(
            request_id="fixture-visual-roughness-request",
            payload={
                "schema_version": "visual-symbol-review/2",
                "detections": [
                    {
                        "visual_observation_id": context[
                            "visual_observation_id"
                        ],
                        "symbol_kind": "surface_roughness",
                        "bbox_normalized": [0.1, 0.1, 0.4, 0.4],
                        "associated_text_observation_ids": [
                            line["observation_id"]
                        ],
                        "confidence_signal": 0.97,
                    }
                ],
            },
            usage={},
        )

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        self.call_order.append("text")
        return super().review_candidate(image, prompt)


class FailingIfCalledVisionProvider:
    def __init__(self) -> None:
        self.calls = 0

    def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
        del image, prompt
        self.calls += 1
        raise AssertionError("cache hit constructed one external call")


class RecordingPreviewSink:
    def __init__(self) -> None:
        self.local_submissions: list[
            tuple[Mapping[str, object], uuid.UUID]
        ] = []

    def publish_local(
        self,
        *,
        snapshot: Mapping[str, object],
        source_file_id: uuid.UUID,
    ) -> None:
        assert not isinstance(snapshot, CandidateSnapshot)
        assert set(snapshot) == {
            "schema_version",
            "stage",
            "candidates",
            "sources",
            "counts",
        }
        assert snapshot["schema_version"] == "recognition-preview/1"
        assert snapshot["stage"] == "local_ready"
        assert set(snapshot["counts"]) == {
            "local_resolved",
            "cache_resolved",
            "vlm_pending",
            "vlm_resolved",
            "unresolved",
        }
        self.local_submissions.append((snapshot, source_file_id))


def _normalized_preview_snapshot(
    snapshot: CandidateSnapshot,
) -> Mapping[str, object]:
    return {
        "schema_version": "recognition-preview/1",
        "stage": "local_ready",
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "kind": candidate["payload"]["item_type"],
            }
            for candidate in snapshot.candidates
        ],
        "sources": [
            {
                "source_location_id": signal.source_location_id,
                "source_type": signal.source_type,
            }
            for signal in snapshot.source_signals
        ],
        "counts": {
            "local_resolved": len(snapshot.candidates),
            "cache_resolved": 0,
            "vlm_pending": len(snapshot.candidates),
            "vlm_resolved": 0,
            "unresolved": 0,
        },
    }


def drawing_fixture(
    tmp_path: Path,
    *,
    raw_text: str,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "drawing.pdf"
    document = pymupdf.open()
    page = document.new_page(width=240, height=180)
    page.insert_text((32, 48), raw_text)
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    return source, pages, candidate_snapshot_from_inventory(pages)


def dense_roughness_fixture(
    tmp_path: Path,
    *,
    count: int,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "dense.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=480)
    for index in range(count):
        page.insert_text((24, 24 + index * 24), f"Ra {index + 1}.0")
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    return source, pages, candidate_snapshot_from_inventory(pages)


def dense_visual_roughness_fixture(
    tmp_path: Path,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "dense-visual.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=480)
    for index in range(16):
        page.insert_text((48, 24 + index * 24), f"Ra {index + 1}.0")
    page.draw_rect((34, 10, 42, 18), color=(0, 0, 0), width=1)
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    assert len(pages[0].visual_observations) == 1
    return source, pages, candidate_snapshot_from_inventory(pages)


def visual_diameter_fixture(
    tmp_path: Path,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source = tmp_path / "visual-diameter.pdf"
    document = pymupdf.open()
    page = document.new_page(width=240, height=180)
    page.insert_text((48, 24), "10")
    page.draw_line((34, 14), (42, 14), color=(0, 0, 0), width=1)
    document.save(source)
    document.close()
    pages = tuple(build_inventory(source))
    assert len(pages[0].visual_observations) == 1
    return source, pages, candidate_snapshot_from_inventory(pages)


def three_visual_escalation_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, tuple[object, ...], CandidateSnapshot]:
    source, original_pages, original_snapshot = visual_diameter_fixture(
        tmp_path
    )
    original_visual = original_pages[0].visual_observations[0]
    original_context = reconstruct_visual_geometry_contexts(
        source,
        original_pages,
    )[0]
    boxes = (
        (8.0, 8.0, 28.0, 28.0),
        (88.0, 8.0, 108.0, 28.0),
        (168.0, 8.0, 188.0, 28.0),
    )
    visuals = tuple(
        replace(
            original_visual,
            observation_id=f"fixture-visual-{label}",
            bbox_pdf=bbox,
            bbox_normalized=(
                bbox[0] / original_pages[0].width,
                bbox[1] / original_pages[0].height,
                bbox[2] / original_pages[0].width,
                bbox[3] / original_pages[0].height,
            ),
            geometry_sha256=label * 64,
        )
        for label, bbox in zip(("a", "b", "c"), boxes, strict=True)
    )
    pages = (
        replace(original_pages[0], visual_observations=visuals),
    )
    original_visual_coverage = next(
        entry
        for entry in original_snapshot.coverage_entries
        if entry.observation_id == original_visual.observation_id
    )
    text_coverage = tuple(
        entry
        for entry in original_snapshot.coverage_entries
        if entry.observation_id != original_visual.observation_id
    )
    snapshot = replace(
        original_snapshot,
        coverage_entries=(
            *text_coverage,
            *(
                replace(
                    original_visual_coverage,
                    observation_id=visual.observation_id,
                    source_location_id=visual.observation_id,
                    coordinates=visual.bbox_pdf,
                )
                for visual in visuals
            ),
        ),
        expected_observation_ids=(
            *(
                identity
                for identity in original_snapshot.expected_observation_ids
                if identity != original_visual.observation_id
            ),
            *(visual.observation_id for visual in visuals),
        ),
        required_visual_observation_ids=tuple(
            visual.observation_id for visual in visuals
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _pdf_path, _pages: tuple(
            replace(
                original_context,
                observation_id=visual.observation_id,
                page_index=visual.page_index,
                geometry_sha256=visual.geometry_sha256,
            )
            for visual in visuals
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        lambda **kwargs: LocalResolution(
            visual_observation_id=kwargs["observation"].observation_id,
            family_hypotheses=(),
            resolved_family=None,
            reason_codes=("unknown_symbol_pattern",),
            projection=None,
        ),
    )
    return source, pages, snapshot


def candidate_advisor(
    tmp_path: Path,
    provider: object,
    *,
    symbol_recognition_mode: str | None = "legacy_high_recall",
) -> CandidateAdvisor:
    settings = {"qwen_model": "qwen3-vl-plus"}
    if symbol_recognition_mode is not None:
        settings["symbol_recognition_mode"] = symbol_recognition_mode
    return CandidateAdvisor(
        Settings(**settings),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: provider,
    )


def _canonical_snapshot_bytes(snapshot: CandidateSnapshot) -> bytes:
    return advisor_module._json_bytes(
        {
            "candidates": list(snapshot.candidates),
            "coverage_entries": [
                entry.to_dict() for entry in snapshot.coverage_entries
            ],
            "expected_observation_ids": list(
                snapshot.expected_observation_ids
            ),
            "duplicate_relations": [
                relation.to_dict()
                for relation in snapshot.duplicate_relations
            ],
            "provider_call_ids": list(snapshot.provider_call_ids),
            "required_visual_observation_ids": list(
                snapshot.required_visual_observation_ids
            ),
        }
    )


def test_advisor_publishes_local_snapshot_before_provider_enrichment(
    tmp_path: Path,
) -> None:
    """Catches Advisor enrichment that reaches a Provider before persisting local facts."""
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="M6")
    sink = RecordingPreviewSink()
    source_file_id = uuid.UUID("00000000-0000-0000-0000-000000000601")
    expected_preview = _normalized_preview_snapshot(snapshot)

    class ProviderAfterLocal(RecordingVisionProvider):
        def review_candidate(self, image: bytes, prompt: str) -> VisionResult:
            assert sink.local_submissions == [(expected_preview, source_file_id)]
            return super().review_candidate(image, prompt)

    provider = ProviderAfterLocal(advisor_payload("M6", "thread", "M6", True))
    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: provider,
        preview_sink=sink,
    )

    reviewed = advisor.review(
        source,
        pages,
        snapshot,
        source_file_id=source_file_id,
    )

    assert sink.local_submissions == [(expected_preview, source_file_id)]
    submitted_snapshot = sink.local_submissions[0][0]
    assert submitted_snapshot["candidates"] == expected_preview["candidates"]
    assert submitted_snapshot["sources"] == expected_preview["sources"]
    assert "provider_call_ids" not in submitted_snapshot
    assert "resource_ref" not in submitted_snapshot
    assert len(provider.images) == 1
    assert reviewed.provider_call_ids == ("fixture-qwen-request-1",)


def test_production_locally_resolved_visual_skips_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    local_decision = VisualReviewDecision(
        observation_id=visual.observation_id,
        disposition="non_inspection",
        source_location_ids=(visual.observation_id,),
        coordinates=visual.bbox_pdf,
        candidate_id=None,
        existing_candidate_index=None,
        candidate_envelope=None,
        requires_confirmation=True,
        symbol_kinds=("revision_marker",),
        rejection_code=None,
    )
    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **_kwargs: ("revision_marker",),
        raising=False,
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        lambda **_kwargs: LocalResolution(
            visual_observation_id=visual.observation_id,
            family_hypotheses=("revision_marker",),
            resolved_family="revision_marker",
            reason_codes=(
                "deterministic_geometry_complete",
                "local_projection_complete",
            ),
            projection=local_decision,
        ),
        raising=False,
    )
    constructed: list[str] = []

    def forbidden_factory(_settings: Settings) -> object:
        constructed.append("provider")
        raise AssertionError("locally resolved visual reached Provider")

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, snapshot)

    assert constructed == []
    visual_coverage = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == visual.observation_id
    )
    assert visual_coverage.disposition == "non_inspection"
    assert visual_coverage.advisor_review is not None
    assert {
        key: value
        for key, value in visual_coverage.advisor_review.items()
        if key != "local_resolution_evidence"
    } == {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/2",
        "symbol_kinds": ["revision_marker"],
        "rejection_code": None,
        "confidence_signal": None,
    }
    local_evidence = visual_coverage.advisor_review[
        "local_resolution_evidence"
    ]
    assert isinstance(local_evidence, dict)
    assert local_evidence["reason_codes"] == [
        "deterministic_geometry_complete",
        "local_projection_complete",
    ]


def test_typed_local_resolution_excludes_only_its_text_advisor_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, original_pages, original_snapshot = visual_diameter_fixture(
        tmp_path
    )
    original_context = reconstruct_visual_geometry_contexts(
        source,
        original_pages,
    )[0]
    candidate = dict(original_snapshot.candidates[0])
    payload = dict(candidate["payload"])
    payload.update(
        {
            "item_type": "diameter_dimension",
            "raw_text": "Φ10",
            "normalized_text": "Φ10",
            "nominal": "10",
            "feature_kind": "unknown",
            "requires_confirmation": True,
        }
    )
    candidate["payload"] = payload
    source_ids = tuple(candidate["source_location_ids"])
    observations = tuple(
        replace(
            observation,
            raw_text="Φ10",
            normalized_text="Φ10",
        )
        if observation.observation_id in source_ids
        else observation
        for observation in original_pages[0].observations
    )
    visual = replace(
        original_pages[0].visual_observations[0],
        associated_text_observation_ids=source_ids,
    )
    pages = (
        replace(
            original_pages[0],
            observations=observations,
            visual_observations=(visual,),
        ),
    )
    snapshot = replace(
        original_snapshot,
        candidates=(candidate,),
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _path, _pages: (original_context,),
    )
    constructed: list[str] = []

    def forbidden_factory(_settings: Settings) -> object:
        constructed.append("provider")
        raise AssertionError("typed local route reached Provider")

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="typed-local",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, snapshot)

    assert constructed == []
    assert reviewed.provider_call_ids == ()
    assert reviewed.candidates[0]["candidate_id"] == candidate["candidate_id"]


def test_local_exclusion_happens_before_dense_text_route_page_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, original_pages, original_snapshot = dense_roughness_fixture(
        tmp_path,
        count=17,
    )
    first_candidate = dict(original_snapshot.candidates[0])
    first_payload = dict(first_candidate["payload"])
    first_payload.update(
        {
            "item_type": "diameter_dimension",
            "raw_text": "Φ10",
            "normalized_text": "Φ10",
            "nominal": "10",
            "feature_kind": "unknown",
            "requires_confirmation": True,
        }
    )
    first_candidate["payload"] = first_payload
    first_source_ids = tuple(first_candidate["source_location_ids"])
    observations = tuple(
        replace(
            observation,
            raw_text="Φ10",
            normalized_text="Φ10",
        )
        if observation.observation_id in first_source_ids
        else observation
        for observation in original_pages[0].observations
    )
    visual = VisualObservation(
        observation_id="dense-local-visual",
        source_type="visual",
        observation_level="annotation_context",
        page_index=0,
        bbox_pdf=(8.0, 8.0, 18.0, 20.0),
        bbox_normalized=(
            8.0 / original_pages[0].width,
            8.0 / original_pages[0].height,
            18.0 / original_pages[0].width,
            20.0 / original_pages[0].height,
        ),
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256="a" * 64,
        associated_text_observation_ids=first_source_ids,
    )
    pages = (
        replace(
            original_pages[0],
            observations=observations,
            visual_observations=(visual,),
        ),
    )
    snapshot = replace(
        original_snapshot,
        candidates=(
            first_candidate,
            *original_snapshot.candidates[1:],
        ),
        coverage_entries=(
            *original_snapshot.coverage_entries,
            CoverageEntry(
                observation_id=visual.observation_id,
                disposition="ambiguous",
                source_location_id=visual.observation_id,
                coordinates=visual.bbox_pdf,
                requires_confirmation=True,
            ),
        ),
        expected_observation_ids=(
            *original_snapshot.expected_observation_ids,
            visual.observation_id,
        ),
        required_visual_observation_ids=(visual.observation_id,),
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _path, _pages: (),
    )
    provider = EchoVisionProvider()

    reviewed = candidate_advisor(
        tmp_path,
        provider,
        symbol_recognition_mode="production_uncertainty",
    ).review(source, pages, snapshot)

    assert len(provider.calls) == 16
    assert all(call["raw_text"] != "Φ10" for call in provider.calls)
    assert [call["raw_text"] for call in provider.calls] == [
        f"Ra {index}.0" for index in range(2, 18)
    ]
    assert len(reviewed.provider_call_ids) == 16
    assert reviewed.candidates[0]["candidate_id"] == (
        first_candidate["candidate_id"]
    )


def test_production_sends_only_escalated_visuals_to_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, original_pages, original_snapshot = visual_diameter_fixture(
        tmp_path
    )
    original_context = reconstruct_visual_geometry_contexts(
        source,
        original_pages,
    )[0]
    local_visual = original_pages[0].visual_observations[0]
    escalated_visual = replace(
        local_visual,
        observation_id="fixture-escalated-visual",
    )
    pages = (
        replace(
            original_pages[0],
            visual_observations=(local_visual, escalated_visual),
        ),
    )
    original_visual_coverage = next(
        entry
        for entry in original_snapshot.coverage_entries
        if entry.observation_id == local_visual.observation_id
    )
    snapshot = replace(
        original_snapshot,
        coverage_entries=(
            *original_snapshot.coverage_entries,
            replace(
                original_visual_coverage,
                observation_id=escalated_visual.observation_id,
                source_location_id=escalated_visual.observation_id,
            ),
        ),
        expected_observation_ids=(
            *original_snapshot.expected_observation_ids,
            escalated_visual.observation_id,
        ),
        required_visual_observation_ids=(
            *original_snapshot.required_visual_observation_ids,
            escalated_visual.observation_id,
        ),
    )
    local_decision = VisualReviewDecision(
        observation_id=local_visual.observation_id,
        disposition="non_inspection",
        source_location_ids=(local_visual.observation_id,),
        coordinates=local_visual.bbox_pdf,
        candidate_id=None,
        existing_candidate_index=None,
        candidate_envelope=None,
        requires_confirmation=True,
        symbol_kinds=("revision_marker",),
        rejection_code=None,
    )

    def fake_resolve(**kwargs: object) -> LocalResolution:
        observation = kwargs["observation"]
        assert hasattr(observation, "observation_id")
        observation_id = str(observation.observation_id)  # type: ignore[union-attr]
        if observation_id == local_visual.observation_id:
            return LocalResolution(
                visual_observation_id=observation_id,
                family_hypotheses=("revision_marker",),
                resolved_family="revision_marker",
                reason_codes=(
                    "deterministic_geometry_complete",
                    "local_projection_complete",
                ),
                projection=local_decision,
            )
        return LocalResolution(
            visual_observation_id=observation_id,
            family_hypotheses=(),
            resolved_family=None,
            reason_codes=("unknown_symbol_pattern",),
            projection=None,
        )

    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **kwargs: (
            ("revision_marker",)
            if kwargs["observation"].observation_id
            == local_visual.observation_id
            else ()
        ),
        raising=False,
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        fake_resolve,
        raising=False,
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _pdf_path, _pages: (
            original_context,
            replace(
                original_context,
                observation_id=escalated_visual.observation_id,
            ),
        ),
    )

    class EscalatedOnlyProvider:
        def __init__(self) -> None:
            self.visual_ids: list[tuple[str, ...]] = []

        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
        ) -> VisionResult:
            request = json.loads(prompt)
            self.visual_ids.append(
                tuple(request["visual_observation_ids"])
            )
            return VisionResult(
                request_id="fixture-escalated-request",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={},
            )

    provider = EscalatedOnlyProvider()
    candidate_advisor(
        tmp_path,
        provider,
        symbol_recognition_mode="production_uncertainty",
    ).review(source, pages, snapshot)

    assert provider.visual_ids == [
        (escalated_visual.observation_id,),
    ]


def test_shadow_uncertainty_uses_legacy_final_write_without_extra_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    legacy_provider = VisualDiameterProvider()
    legacy = candidate_advisor(
        tmp_path / "legacy",
        legacy_provider,
    ).review(source, pages, snapshot)
    calls = {"prepare": 0, "resolve": 0, "route": 0}
    real_prepare = advisor_module.prepare_local_family_hypotheses
    real_resolve = advisor_module.resolve_visual_observation
    real_route = advisor_module.route_visual_observation

    def counted_prepare(**kwargs: object) -> tuple[str, ...]:
        calls["prepare"] += 1
        return real_prepare(**kwargs)  # type: ignore[arg-type]

    def counted_resolve(**kwargs: object) -> LocalResolution:
        calls["resolve"] += 1
        return real_resolve(**kwargs)  # type: ignore[arg-type]

    def counted_route(resolution: object) -> RoutingDecision:
        calls["route"] += 1
        return real_route(resolution)

    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        counted_prepare,
    )
    monkeypatch.setattr(
        advisor_module,
        "resolve_visual_observation",
        counted_resolve,
    )
    monkeypatch.setattr(
        advisor_module,
        "route_visual_observation",
        counted_route,
    )
    shadow_provider = VisualDiameterProvider()

    shadow = candidate_advisor(
        tmp_path / "shadow",
        shadow_provider,
        symbol_recognition_mode="shadow_uncertainty",
    ).review(source, pages, snapshot)

    assert calls == {"prepare": 1, "resolve": 1, "route": 1}
    assert _canonical_snapshot_bytes(shadow) == _canonical_snapshot_bytes(
        legacy
    )
    assert shadow_provider.call_order == legacy_provider.call_order == [
        "visual",
    ]


def test_default_and_explicit_legacy_are_byte_compatible(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    default_provider = VisualDiameterProvider()
    explicit_provider = VisualDiameterProvider()

    default = candidate_advisor(
        tmp_path / "default",
        default_provider,
        symbol_recognition_mode=None,
    ).review(source, pages, snapshot)
    explicit = candidate_advisor(
        tmp_path / "explicit",
        explicit_provider,
        symbol_recognition_mode="legacy_high_recall",
    ).review(source, pages, snapshot)

    assert _canonical_snapshot_bytes(default) == _canonical_snapshot_bytes(
        explicit
    )
    assert default_provider.call_order == explicit_provider.call_order == [
        "visual",
    ]


@pytest.mark.parametrize(
    "invalid_decision",
    ("missing", "malformed", "observation_mismatch"),
)
def test_invalid_production_routing_blocks_before_provider_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_decision: str,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    real_route = advisor_module.route_visual_observation

    def invalid_route(resolution: object) -> object:
        decision = real_route(resolution)
        if invalid_decision == "missing":
            return None
        if invalid_decision == "malformed":
            return object()
        return replace(
            decision,
            visual_observation_id="mismatched-visual-observation",
        )

    monkeypatch.setattr(
        advisor_module,
        "route_visual_observation",
        invalid_route,
    )
    constructed: list[str] = []

    def forbidden_factory(_settings: Settings) -> object:
        constructed.append("provider")
        raise AssertionError("invalid routing constructed Provider")

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / invalid_decision / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol routing contract is invalid$",
    ):
        advisor.review(source, pages, snapshot)

    assert constructed == []


def test_local_preparation_defect_blocks_before_provider_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    monkeypatch.setattr(
        advisor_module,
        "prepare_local_family_hypotheses",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("fixture local helper defect")
        ),
    )
    constructed: list[str] = []

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="helper-defect",
        provider_factory=lambda _settings: (
            constructed.append("provider") or object()
        ),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol routing contract is invalid$",
    ):
        advisor.review(source, pages, snapshot)

    assert constructed == []


def test_visual_execution_outcome_separates_cache_provenance_from_current_work(
    tmp_path: Path,
) -> None:
    source, pages, _snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    provider = UnifiedRecordingProvider()
    advisor = candidate_advisor(tmp_path, provider)
    document = pymupdf.open(source)
    try:
        crop_bbox_pdf = (0.0, 0.0, 80.0, 80.0)
        crop_png = advisor_module._render_visual_crop(
            document[0],
            crop_bbox_pdf,
        )
    finally:
        document.close()
    arguments = {
        "provider": provider,
        "crop_png": crop_png,
        "crop_bbox_pdf": crop_bbox_pdf,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "visual_observations": (visual,),
        "text_observations": {
            observation.observation_id: observation
            for observation in pages[0].observations
        },
        "model": "qwen3-vl-plus",
    }

    live = advisor._visual_review_result(**arguments)
    cached = advisor._visual_review_result(**arguments)

    assert live.result.request_id == "fixture-visual-request-1"
    assert live.provenance_request_ids == ("fixture-visual-request-1",)
    assert live.current_attempt_request_ids == (
        "fixture-visual-request-1",
    )
    assert live.current_attempt_count == 1
    assert live.retry_count == 0
    assert len(live.attempt_duration_ms) == 1
    assert live.measured_duration_ms == sum(live.attempt_duration_ms)
    assert live.cache_hit is False
    assert live.execution_identity is None
    assert tuple(live) == (
        live.result,
        live.provider,
        live.provenance_request_ids,
    )

    assert cached.result == live.result
    assert cached.provenance_request_ids == live.provenance_request_ids
    assert cached.current_attempt_request_ids == ()
    assert cached.current_attempt_count == 0
    assert cached.retry_count == 0
    assert cached.attempt_duration_ms == ()
    assert cached.measured_duration_ms == 0
    assert cached.cache_hit is True
    assert cached.execution_identity is None
    assert provider.call_order == ["visual"]


def test_visual_retry_outcome_sums_both_attempts_after_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, _snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    provider = RetryRecordingProvider()
    advisor = candidate_advisor(tmp_path, provider)
    clock = iter((0, 5_000_000, 10_000_000, 17_000_000))
    monkeypatch.setattr(
        advisor_module.time,
        "perf_counter_ns",
        lambda: next(clock),
    )
    authorization: list[object] = []
    document = pymupdf.open(source)
    try:
        outcome = advisor._visual_review_result(
            provider=provider,
            crop_png=advisor_module._render_visual_crop(
                document[0],
                (0.0, 0.0, 80.0, 80.0),
            ),
            crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            visual_observations=(visual,),
            text_observations={
                observation.observation_id: observation
                for observation in pages[0].observations
            },
            model="qwen3-vl-plus",
            allow_schema_retry=True,
            retry_authorizer=lambda identity, _duration_ms: (
                authorization.append(identity) or True
            ),
        )
    finally:
        document.close()

    assert authorization == [None]
    assert outcome.current_attempt_request_ids == (
        "fixture-visual-retry-1",
        "fixture-visual-retry-success",
    )
    assert outcome.current_attempt_count == 2
    assert outcome.retry_count == 1
    assert outcome.attempt_duration_ms == (5, 7)
    assert outcome.measured_duration_ms == 12
    assert outcome.cache_hit is False


def test_visual_retry_authorizer_denial_prevents_second_call(
    tmp_path: Path,
) -> None:
    source, pages, _snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    provider = RetryRecordingProvider()
    advisor = candidate_advisor(tmp_path, provider)
    authorization: list[object] = []
    document = pymupdf.open(source)
    try:
        with pytest.raises(
            CandidateAdvisorFailure,
            match="^Visual symbol Advisor response is invalid$",
        ):
            advisor._visual_review_result(
                provider=provider,
                crop_png=advisor_module._render_visual_crop(
                    document[0],
                    (0.0, 0.0, 80.0, 80.0),
                ),
                crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
                source_sha256=hashlib.sha256(
                    source.read_bytes()
                ).hexdigest(),
                visual_observations=(visual,),
                text_observations={
                    observation.observation_id: observation
                    for observation in pages[0].observations
                },
                model="qwen3-vl-plus",
                allow_schema_retry=True,
                retry_authorizer=lambda identity, _duration_ms: (
                    authorization.append(identity) or False
                ),
            )
    finally:
        document.close()

    assert authorization == [None]
    assert provider.call_order == ["visual"]


def test_production_visual_outcome_preserves_planner_batch_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    provider = UnifiedRecordingProvider()
    real_review = CandidateAdvisor._visual_review_result
    seen: list[
        tuple[
            object,
            tuple[float, float, float, float],
            bytes,
        ]
    ] = []

    def capture_outcome(
        self: CandidateAdvisor,
        **kwargs: object,
    ) -> object:
        outcome = real_review(self, **kwargs)  # type: ignore[arg-type]
        assert outcome.execution_identity is kwargs["execution_identity"]
        seen.append(
            (
                outcome.execution_identity,
                kwargs["crop_bbox_pdf"],  # type: ignore[arg-type]
                kwargs["crop_png"],  # type: ignore[arg-type]
            )
        )
        return outcome

    monkeypatch.setattr(
        CandidateAdvisor,
        "_visual_review_result",
        capture_outcome,
    )

    candidate_advisor(
        tmp_path,
        provider,
        symbol_recognition_mode="production_uncertainty",
    ).review(source, pages, snapshot)

    assert len(seen) == 1
    identity, crop_bbox_pdf, crop_png = seen[0]
    assert identity.page_index == 0  # type: ignore[union-attr]
    assert len(identity.content_sha256) == 64  # type: ignore[union-attr]
    assert len(identity.lineage_sha256) == 64  # type: ignore[union-attr]
    assert len(identity.budget_sha256) == 64  # type: ignore[union-attr]
    assert identity.observation_member_bindings == (  # type: ignore[union-attr]
        (visual.observation_id, identity.content_sha256),  # type: ignore[union-attr]
    )
    assert crop_bbox_pdf[0] <= visual.bbox_pdf[0]
    assert crop_bbox_pdf[1] <= visual.bbox_pdf[1]
    assert crop_bbox_pdf[2] >= visual.bbox_pdf[2]
    assert crop_bbox_pdf[3] >= visual.bbox_pdf[3]
    assert crop_bbox_pdf != visual.bbox_pdf
    assert 0.0 <= crop_bbox_pdf[0] < crop_bbox_pdf[2] <= pages[0].width
    assert 0.0 <= crop_bbox_pdf[1] < crop_bbox_pdf[3] <= pages[0].height
    assert identity.crop_sha256 == hashlib.sha256(  # type: ignore[union-attr]
        advisor_module.canonicalize_visual_png(crop_png)
    ).hexdigest()


def test_visual_execution_identity_crop_hash_mismatch_blocks_provider(
    tmp_path: Path,
) -> None:
    source, pages, _snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    constructed: list[str] = []
    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="crop-hash-mismatch",
        provider_factory=lambda _settings: (
            constructed.append("provider") or object()
        ),
    )
    document = pymupdf.open(source)
    try:
        crop_png = advisor_module._render_visual_crop(
            document[0],
            (0.0, 0.0, 80.0, 80.0),
        )
    finally:
        document.close()

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol execution identity is invalid$",
    ):
        advisor._visual_review_result(
            provider=None,
            crop_png=crop_png,
            crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            visual_observations=(visual,),
            text_observations={
                observation.observation_id: observation
                for observation in pages[0].observations
            },
            model="qwen3-vl-plus",
            execution_identity=VisualExecutionIdentity(
                page_index=0,
                content_sha256="a" * 64,
                lineage_sha256="b" * 64,
                budget_sha256="c" * 64,
                observation_member_bindings=(
                    (visual.observation_id, "a" * 64),
                ),
                crop_sha256="d" * 64,
            ),
            legacy_cache_enabled=False,
        )

    assert constructed == []


def test_production_does_not_read_or_write_legacy_visual_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    provider = UnifiedRecordingProvider()
    advisor = candidate_advisor(
        tmp_path,
        provider,
        symbol_recognition_mode="production_uncertainty",
    )
    monkeypatch.setattr(
        advisor,
        "_visual_cache_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("production read legacy visual cache")
        ),
    )

    reviewed = advisor.review(source, pages, snapshot)

    assert provider.call_order == ["visual"]
    assert reviewed.provider_call_ids == ("fixture-visual-request-1",)
    assert (
        list(
            (tmp_path / "storage").glob(
                "projects/project-test/provider-cache/qwen-symbol/*.json"
            )
        )
        == []
    )


def test_production_requires_exact_single_bounded_crop_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    monkeypatch.setattr(
        advisor_module,
        "pack_visual_batches",
        lambda _page, _observations: (),
    )
    constructed: list[str] = []

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="invalid-crop-owner",
        provider_factory=lambda _settings: (
            constructed.append("provider") or object()
        ),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol execution crop is invalid$",
    ):
        advisor.review(source, pages, snapshot)

    assert constructed == []


def test_production_visual_executor_is_bounded_and_prepares_crops_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    main_thread = threading.get_ident()
    render_threads: list[int] = []
    real_render = advisor_module._render_visual_crop

    def tracked_render(
        page: pymupdf.Page,
        bbox: tuple[float, float, float, float],
    ) -> bytes:
        render_threads.append(threading.get_ident())
        return real_render(page, bbox)

    monkeypatch.setattr(
        advisor_module,
        "_render_visual_crop",
        tracked_render,
    )
    lock = threading.Lock()
    first_pair = threading.Barrier(2)
    active = 0
    max_active = 0
    calls = 0
    first_terminal = threading.Event()

    class BoundedProvider:
        def review_symbols(
            self,
            _image: bytes,
            _prompt: str,
        ) -> VisionResult:
            nonlocal active, max_active, calls
            assert len(render_threads) == 3
            with lock:
                active += 1
                calls += 1
                call_index = calls
                max_active = max(max_active, active)
            try:
                if call_index == 3:
                    assert first_terminal.is_set()
                if call_index <= 2:
                    first_pair.wait(timeout=2)
                return VisionResult(
                    request_id=f"fixture-bounded-{call_index}",
                    payload={
                        "schema_version": "visual-symbol-review/2",
                        "detections": [],
                    },
                    usage={},
                )
            finally:
                if call_index <= 2:
                    first_terminal.set()
                with lock:
                    active -= 1

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: BoundedProvider(),
    )

    advisor.review(source, pages, snapshot)

    assert calls == 3
    assert max_active == 2
    assert render_threads == [main_thread, main_thread, main_thread]


def test_success_terminal_refills_sliding_window_while_peer_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    observation_ids = tuple(
        visual.observation_id for visual in pages[0].visual_observations
    )
    first_pair = threading.Barrier(2)
    release_second = threading.Event()
    second_completed = threading.Event()
    third_started = threading.Event()

    class SlidingProvider:
        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
        ) -> VisionResult:
            identity = json.loads(prompt)[
                "visual_observation_ids"
            ][0]
            if identity in observation_ids[:2]:
                first_pair.wait(timeout=3)
            if identity == observation_ids[1]:
                assert release_second.wait(timeout=3)
                second_completed.set()
            if identity == observation_ids[2]:
                third_started.set()
            return VisionResult(
                request_id=f"sliding-{identity}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={},
            )

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="success-sliding",
        provider_factory=lambda _settings: SlidingProvider(),
    )
    results: list[CandidateSnapshot] = []
    failures: list[BaseException] = []

    def execute() -> None:
        try:
            results.append(advisor.review(source, pages, snapshot))
        except BaseException as exc:
            failures.append(exc)

    review_thread = threading.Thread(target=execute)
    review_thread.start()
    assert third_started.wait(timeout=3)
    assert not second_completed.is_set()
    release_second.set()
    review_thread.join(timeout=3)

    assert not review_thread.is_alive()
    assert failures == []
    assert len(results) == 1
    assert results[0].provider_call_ids == tuple(
        f"sliding-{identity}" for identity in observation_ids
    )


def test_production_failure_stops_before_queued_job_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    observation_ids = tuple(
        visual.observation_id for visual in pages[0].visual_observations
    )
    first_pair = threading.Barrier(2)
    release_second = threading.Event()
    failure_returned = threading.Event()
    third_started = threading.Event()
    calls: list[str] = []
    lock = threading.Lock()
    real_review = CandidateAdvisor._visual_review_result

    def tracked_review(
        self: CandidateAdvisor,
        **kwargs: object,
    ) -> object:
        try:
            return real_review(self, **kwargs)  # type: ignore[arg-type]
        except CandidateAdvisorFailure:
            failure_returned.set()
            raise

    monkeypatch.setattr(
        CandidateAdvisor,
        "_visual_review_result",
        tracked_review,
    )

    class FailingWindowProvider:
        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
        ) -> VisionResult:
            identity = json.loads(prompt)[
                "visual_observation_ids"
            ][0]
            with lock:
                calls.append(identity)
            if identity == observation_ids[0]:
                first_pair.wait(timeout=3)
                raise VisualSymbolProviderError(
                    request_id="fixture-window-failure",
                    usage={},
                    failure_stage="message_shape_invalid",
                )
            if identity == observation_ids[1]:
                first_pair.wait(timeout=3)
                assert release_second.wait(timeout=3)
            if identity == observation_ids[2]:
                third_started.set()
            return VisionResult(
                request_id=f"success-{identity}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={},
            )

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="failure-window",
        provider_factory=lambda _settings: FailingWindowProvider(),
    )

    failures: list[BaseException] = []

    def execute() -> None:
        try:
            advisor.review(source, pages, snapshot)
        except BaseException as exc:
            failures.append(exc)

    review_thread = threading.Thread(target=execute)
    review_thread.start()
    assert failure_returned.wait(timeout=3)
    assert not third_started.is_set()
    release_second.set()
    review_thread.join(timeout=3)

    assert not review_thread.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], CandidateAdvisorFailure)
    assert str(failures[0]) == "Visual symbol Advisor response is invalid"
    assert set(calls) == set(observation_ids[:2])
    assert len(calls) == 2
    assert observation_ids[2] not in calls


def test_actual_wall_budget_stops_queued_job_with_fake_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    observation_ids = tuple(
        visual.observation_id for visual in pages[0].visual_observations
    )
    calls: list[str] = []
    clock_counts: dict[int, int] = {}
    lock = threading.Lock()

    def fake_clock() -> int:
        identity = threading.get_ident()
        with lock:
            count = clock_counts.get(identity, 0)
            clock_counts[identity] = count + 1
        return 0 if count % 2 == 0 else 30_000_000_000

    monkeypatch.setattr(
        advisor_module.time,
        "perf_counter_ns",
        fake_clock,
    )

    class SlowMeasuredProvider:
        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
        ) -> VisionResult:
            identity = json.loads(prompt)[
                "visual_observation_ids"
            ][0]
            with lock:
                calls.append(identity)
            return VisionResult(
                request_id=f"slow-{identity}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={},
            )

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="actual-wall",
        provider_factory=lambda _settings: SlowMeasuredProvider(),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol actual wall budget exceeded$",
    ):
        advisor.review(source, pages, snapshot)

    assert set(calls) == set(observation_ids[:2])
    assert len(calls) == 2
    assert observation_ids[2] not in calls


def test_actual_primary_wall_blocks_retry_before_second_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    clock = iter((0, 40_000_000_000))
    monkeypatch.setattr(
        advisor_module.time,
        "perf_counter_ns",
        lambda: next(clock),
    )
    calls = 0

    class SlowSchemaFailureProvider:
        def review_symbols(
            self,
            _image: bytes,
            _prompt: str,
        ) -> VisionResult:
            nonlocal calls
            calls += 1
            raise VisualSymbolProviderError(
                request_id="slow-schema-primary",
                usage={},
                failure_stage="tool_arguments_schema_invalid",
            )

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="retry-actual-wall",
        provider_factory=lambda _settings: SlowSchemaFailureProvider(),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor response is invalid$",
    ):
        advisor.review(source, pages, snapshot)

    assert calls == 1


def test_production_completion_permutations_keep_planner_ordered_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    observation_ids = tuple(
        visual.observation_id for visual in pages[0].visual_observations
    )

    def run_with_completion_order(
        root: Path,
        completion_order: tuple[str, ...],
    ) -> tuple[CandidateSnapshot, tuple[str, ...]]:
        started = {
            identity: threading.Event() for identity in observation_ids
        }
        released = {
            identity: threading.Event() for identity in observation_ids
        }
        completed = {
            identity: threading.Event() for identity in observation_ids
        }
        actual_completion: list[str] = []
        completion_lock = threading.Lock()

        class ScriptedProvider:
            def review_symbols(
                self,
                _image: bytes,
                prompt: str,
            ) -> VisionResult:
                identity = json.loads(prompt)[
                    "visual_observation_ids"
                ][0]
                started[identity].set()
                assert released[identity].wait(timeout=3)
                with completion_lock:
                    actual_completion.append(identity)
                completed[identity].set()
                return VisionResult(
                    request_id=f"request-{identity}",
                    payload={
                        "schema_version": "visual-symbol-review/2",
                        "detections": [],
                    },
                    usage={},
                )

        advisor = CandidateAdvisor(
            Settings(
                qwen_model="qwen3-vl-plus",
                symbol_recognition_mode="production_uncertainty",
            ),
            LocalFileStorage(root / "storage"),
            project_id="project-test",
            provider_factory=lambda _settings: ScriptedProvider(),
        )
        result_box: list[CandidateSnapshot] = []
        failure_box: list[BaseException] = []

        def execute() -> None:
            try:
                result_box.append(advisor.review(source, pages, snapshot))
            except BaseException as exc:
                failure_box.append(exc)

        review_thread = threading.Thread(target=execute)
        review_thread.start()
        assert started[observation_ids[0]].wait(timeout=3)
        assert started[observation_ids[1]].wait(timeout=3)
        for identity in completion_order:
            if identity == observation_ids[2]:
                assert started[identity].wait(timeout=3)
            released[identity].set()
            assert completed[identity].wait(timeout=3)
        review_thread.join(timeout=3)
        assert not review_thread.is_alive()
        assert failure_box == []
        assert actual_completion == list(completion_order)
        return result_box[0], tuple(actual_completion)

    first, first_completion = run_with_completion_order(
        tmp_path / "first",
        (
            observation_ids[0],
            observation_ids[1],
            observation_ids[2],
        ),
    )
    second, second_completion = run_with_completion_order(
        tmp_path / "second",
        (
            observation_ids[1],
            observation_ids[0],
            observation_ids[2],
        ),
    )

    assert first_completion != second_completion
    assert _canonical_snapshot_bytes(first) == _canonical_snapshot_bytes(
        second
    )
    assert first.provider_call_ids == second.provider_call_ids == tuple(
        f"request-{identity}" for identity in observation_ids
    )


def test_concurrent_schema_failures_reserve_exactly_one_project_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = three_visual_escalation_fixture(
        tmp_path,
        monkeypatch,
    )
    competing_ids = {
        visual.observation_id
        for visual in pages[0].visual_observations[:2]
    }
    first_failures = threading.Barrier(2)
    lock = threading.Lock()
    attempts: dict[str, int] = {}
    reservations: list[object] = []

    def tracked_reserve(*args: object, **kwargs: object) -> object:
        outcome = real_reserve_escalation_budget_window(
            *args,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
        if kwargs.get("retry") is True:
            reservations.append(outcome)
        return outcome

    monkeypatch.setattr(
        advisor_module,
        "reserve_escalation_budget_window",
        tracked_reserve,
        raising=False,
    )

    class CompetingRetryProvider:
        def review_symbols(
            self,
            _image: bytes,
            prompt: str,
        ) -> VisionResult:
            identity = json.loads(prompt)[
                "visual_observation_ids"
            ][0]
            with lock:
                attempts[identity] = attempts.get(identity, 0) + 1
                attempt = attempts[identity]
            if identity in competing_ids and attempt == 1:
                first_failures.wait(timeout=3)
                raise VisualSymbolProviderError(
                    request_id=f"failure-{identity}",
                    usage={},
                    failure_stage="tool_arguments_schema_invalid",
                )
            return VisionResult(
                request_id=f"success-{identity}-{attempt}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={},
            )

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode="production_uncertainty",
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: CompetingRetryProvider(),
    )

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor response is invalid$",
    ):
        advisor.review(source, pages, snapshot)

    assert sorted(attempts[identity] for identity in competing_ids) == [1, 2]
    assert len(reservations) == 2
    allowed = [item for item in reservations if item.allowed]
    denied = [item for item in reservations if not item.allowed]
    assert len(allowed) == len(denied) == 1
    retry_state = allowed[0].state
    assert retry_state.project_retry_count == 1
    assert retry_state.project_primary_count == 3
    assert sum(
        count for _, count in retry_state.page_actual_call_counts
    ) == 4
    assert retry_state.project_wall_seconds == (
        4 * advisor_module.PROJECTED_VISUAL_PRIMARY_WALL_SECONDS
    )
    assert set(retry_state.retried_group_identities).issubset(
        set(retry_state.primary_group_identities)
    )
    assert denied[0].state == retry_state


def test_clear_native_candidate_does_not_construct_provider(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="M6")
    constructed: list[str] = []

    def forbidden_factory(_settings: Settings):
        constructed.append("provider")
        raise AssertionError("clear candidate constructed the Provider")

    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, snapshot)

    assert reviewed == replace(
        snapshot,
        recognition_summary={
            "schema_version": "symbol-recognition-summary/1",
            "unresolved_roi_count": 0,
        },
    )
    assert constructed == []
    assert len(reviewed.source_signals) == 1
    assert reviewed.source_signals[0].source_type == "native"
    assert str(reviewed.source_signals[0].normalized_value) == "1"
    assert reviewed.candidates[0]["source_truth_preserved"] is True


def test_advisor_preserves_technical_requirement_decisions(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    requirement = {
        "requirement_id": "technical-requirement-1",
        "rule_version": "technical-requirement/1",
    }
    snapshot = replace(
        snapshot,
        technical_requirements=(requirement,),
    )

    reviewed = candidate_advisor(
        tmp_path,
        EchoVisionProvider(),
    ).review(source, pages, snapshot)

    assert reviewed.technical_requirements == (requirement,)


def test_advisor_retargets_requirement_when_visual_review_retires_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    requirement = TechnicalRequirementEntry(
        ordinal=1,
        raw_text="未注尺寸公差按GB/T 1804-m执行",
        normalized_text="未注尺寸公差按GB/T 1804-m执行",
        source_location_ids=("requirement-source",),
        source_segment_ids=("requirement-source#0",),
        page_index=0,
        coordinates=((10.0, 10.0, 80.0, 20.0),),
    )
    evaluated = evaluate_technical_requirements(
        (requirement,),
        snapshot.candidates,
    )
    snapshot = replace(
        snapshot,
        candidates=evaluated.candidates,
        technical_requirements=tuple(
            decision.model_dump(mode="json")
            for decision in evaluated.decisions
        ),
    )
    original_candidate_id = str(snapshot.candidates[0]["candidate_id"])
    visual = pages[0].visual_observations[0]

    def retire_candidate(**_kwargs: object) -> tuple[VisualReviewDecision, ...]:
        return (
            VisualReviewDecision(
                observation_id=visual.observation_id,
                disposition="reference_context",
                source_location_ids=(visual.observation_id,),
                coordinates=visual.bbox_pdf,
                candidate_id=None,
                existing_candidate_index=0,
                candidate_envelope=None,
                requires_confirmation=False,
                symbol_kinds=(),
                rejection_code=None,
            ),
        )

    monkeypatch.setattr(
        advisor_module,
        "project_visual_page",
        retire_candidate,
    )

    reviewed = candidate_advisor(
        tmp_path,
        UnifiedRecordingProvider(),
    ).review(source, pages, snapshot)

    decision = reviewed.technical_requirements[0]
    assert original_candidate_id not in {
        candidate["candidate_id"] for candidate in reviewed.candidates
    }
    assert decision["match_outcome"] == "global_scope"
    assert decision["matched_candidate_ids"] == []
    assert decision["generated_candidate_id"] in {
        candidate["candidate_id"] for candidate in reviewed.candidates
    }


@pytest.mark.parametrize(
    "symbol_recognition_mode",
    (
        "legacy_high_recall",
        "shadow_uncertainty",
        "production_uncertainty",
    ),
)
def test_resolved_visual_does_not_construct_provider_or_mutate_snapshot(
    tmp_path: Path,
    symbol_recognition_mode: str,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual_id = pages[0].visual_observations[0].observation_id
    coverage_entries = tuple(
        replace(
            entry,
            disposition="reference_context",
            requires_confirmation=False,
            disposition_reason=(
                "welli_layout_visual_context"
                if entry.observation_id == visual_id
                else "fixture_resolved_text"
            ),
            disposition_rule_version="welli-layout-disposition/1",
        )
        for entry in snapshot.coverage_entries
    )
    resolved_snapshot = replace(
        snapshot,
        coverage_entries=coverage_entries,
        required_visual_observation_ids=(),
    )
    constructed: list[str] = []

    def forbidden_factory(_settings: Settings):
        constructed.append("provider")
        raise AssertionError("resolved visual constructed the Provider")

    advisor = CandidateAdvisor(
        Settings(
            qwen_model="qwen3-vl-plus",
            symbol_recognition_mode=symbol_recognition_mode,
        ),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, resolved_snapshot)

    assert reviewed == replace(
        resolved_snapshot,
        recognition_mode=(
            "production_uncertainty"
            if symbol_recognition_mode == "production_uncertainty"
            else symbol_recognition_mode
        ),
        router_version=(
            advisor_module.SYMBOL_ROUTER_VERSION
            if symbol_recognition_mode
            in {"shadow_uncertainty", "production_uncertainty"}
            else "legacy"
        ),
        recognition_summary={
            "schema_version": "symbol-recognition-summary/1",
            "unresolved_roi_count": 0,
        },
        recognition_evidence_ref=(
            "symbol-routing-evidence://project-test"
            if symbol_recognition_mode == "production_uncertainty"
            else None
        ),
    )
    assert constructed == []
    assert reviewed.candidates == resolved_snapshot.candidates
    assert reviewed.source_signals == resolved_snapshot.source_signals
    assert reviewed.provider_call_ids == resolved_snapshot.provider_call_ids
    visual_coverage = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == visual_id
    )
    assert visual_coverage.advisor_review is None
    assert visual_coverage.disposition_reason == (
        "welli_layout_visual_context"
    )


def test_mixed_visual_review_only_projects_required_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, original_pages, _snapshot = visual_diameter_fixture(tmp_path)
    original_context = advisor_module.reconstruct_visual_geometry_contexts(
        source,
        original_pages,
    )[0]
    original_visual = original_pages[0].visual_observations[0]
    resolved_visual = replace(
        original_visual,
        observation_id="resolved-a",
    )
    unresolved_visual = replace(
        original_visual,
        observation_id="unresolved-b",
        bbox_pdf=tuple(value + 12 for value in original_visual.bbox_pdf),
        bbox_normalized=tuple(
            value + 0.05 for value in original_visual.bbox_normalized
        ),
    )
    pages = (
        replace(
            original_pages[0],
            visual_observations=(resolved_visual, unresolved_visual),
        ),
    )
    snapshot = candidate_snapshot_from_inventory(pages)
    coverage_entries = tuple(
        replace(
            entry,
            disposition="reference_context",
            requires_confirmation=False,
            disposition_reason=(
                "welli_layout_visual_context"
                if entry.observation_id == resolved_visual.observation_id
                else "fixture_resolved_text"
            ),
            disposition_rule_version="welli-layout-disposition/1",
        )
        if entry.observation_id != unresolved_visual.observation_id
        else entry
        for entry in snapshot.coverage_entries
    )
    snapshot = replace(
        snapshot,
        coverage_entries=coverage_entries,
        required_visual_observation_ids=(
            unresolved_visual.observation_id,
        ),
    )
    resolved_before = next(
        entry
        for entry in snapshot.coverage_entries
        if entry.observation_id == resolved_visual.observation_id
    )
    resolved_bytes = json.dumps(
        resolved_before.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    projected_ids: list[str] = []
    original_project = advisor_module.project_visual_page

    def recording_project(**kwargs):
        projected_ids.extend(
            item.observation_id
            for item in kwargs["visual_observations"]
        )
        return original_project(**kwargs)

    monkeypatch.setattr(
        advisor_module,
        "project_visual_page",
        recording_project,
    )
    monkeypatch.setattr(
        advisor_module,
        "reconstruct_visual_geometry_contexts",
        lambda _source, _pages: (
            replace(
                original_context,
                observation_id=resolved_visual.observation_id,
            ),
            replace(
                original_context,
                observation_id=unresolved_visual.observation_id,
                line_bbox_pdf=tuple(
                    value + 12
                    for value in original_context.line_bbox_pdf
                ),
            ),
        ),
    )

    class RequiredVisualProvider(UnifiedRecordingProvider):
        def __init__(self) -> None:
            super().__init__()
            self.visual_request_ids: list[tuple[str, ...]] = []

        def review_symbols(self, image: bytes, prompt: str) -> VisionResult:
            request = json.loads(prompt)
            self.visual_request_ids.append(
                tuple(request["visual_observation_ids"])
            )
            return super().review_symbols(image, prompt)

    provider = RequiredVisualProvider()
    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert provider.call_order == ["visual"]
    assert provider.visual_request_ids == [("unresolved-b",)]
    assert projected_ids == ["unresolved-b"]
    resolved_after = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == resolved_visual.observation_id
    )
    assert json.dumps(
        resolved_after.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode() == resolved_bytes
    unresolved_after = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == unresolved_visual.observation_id
    )
    assert unresolved_after.advisor_review is not None
    assert unresolved_after.advisor_review["rejection_code"] == (
        "visual_no_detection"
    )


def test_ambiguous_native_observation_still_emits_one_source_signal(
    tmp_path: Path,
) -> None:
    _source, _pages, snapshot = drawing_fixture(tmp_path, raw_text="NOTE")

    assert snapshot.candidates == ()
    assert len(snapshot.coverage_entries) == 1
    assert snapshot.coverage_entries[0].disposition == "ambiguous"
    assert len(snapshot.source_signals) == 1
    signal = snapshot.source_signals[0]
    assert (
        signal.source_location_id
        == snapshot.coverage_entries[0].observation_id
    )
    assert signal.source_type == "native"
    assert signal.normalized_value is None


def test_composite_members_each_emit_exactly_one_native_source_signal() -> None:
    def observation(
        observation_id: str,
        raw_text: str,
        y0: float,
    ) -> TextObservation:
        return TextObservation(
            observation_id=observation_id,
            source_type="native",
            observation_level="line",
            raw_text=raw_text,
            normalized_text=raw_text,
            page_index=0,
            bbox_pdf=(10.0, y0, 40.0, y0 + 8.0),
            bbox_normalized=(0.05, y0 / 100.0, 0.2, (y0 + 8.0) / 100.0),
            direction=(1.0, 0.0),
            direction_angle_degrees=0.0,
            confidence=None,
        )

    members = (
        observation("native-thread", "M6", 10.0),
        observation("native-through", "贯穿", 20.0),
    )
    snapshot = candidate_snapshot_from_inventory(
        (
            SimpleNamespace(
                observations=members,
                visual_observations=(),
            ),
        )
    )

    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0]["payload"]["item_type"] == "composite"
    assert [signal.source_location_id for signal in snapshot.source_signals] == [
        member.observation_id for member in members
    ]
    assert all(
        str(signal.normalized_value) == "1"
        for signal in snapshot.source_signals
    )


def test_coarse_candidate_uses_one_bounded_local_crop(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            raw_text="Ra 3.2",
            item_type="roughness",
            normalized_text="Ra 3.2",
            requires_confirmation=True,
        )
    )
    advisor = candidate_advisor(tmp_path, provider)

    reviewed = advisor.review(source, pages, snapshot)

    assert len(provider.images) == 1
    assert provider.images[0].startswith(b"\x89PNG")
    provenance = reviewed.candidates[0]["advisor_review"]
    assert provenance["review_reason"] == "coarse_type"
    assert provenance["validated"] is True
    assert len(provenance["crop_sha256"]) == 64
    assert 6.0 <= provenance["padding_pdf"] <= 24.0
    assert provenance["crop_bbox_pdf"][0] >= 0
    assert provenance["crop_bbox_pdf"][2] <= pages[0].width


def test_advisor_prompt_carries_the_frozen_output_schema(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            raw_text="Ra 3.2",
            item_type="roughness",
            normalized_text="Ra 3.2",
            requires_confirmation=True,
        )
    )

    candidate_advisor(tmp_path, provider).review(source, pages, snapshot)

    prompt = json.loads(provider.prompts[0])
    output_schema = prompt["output_schema"]
    assert output_schema["type"] == "object"
    assert output_schema["additionalProperties"] is False
    assert output_schema["required"] == [
        "schema_version",
        "raw_text",
        "item_type",
        "normalized_text",
        "requires_confirmation",
    ]
    assert output_schema["properties"]["schema_version"] == {
        "const": "candidate-review/1",
    }
    assert output_schema["properties"]["raw_text"] == {"const": "Ra 3.2"}
    assert output_schema["properties"]["item_type"] == {"const": "roughness"}
    assert output_schema["properties"]["requires_confirmation"] == {"const": True}


def test_page_call_cap_keeps_remaining_objects_unreviewed(tmp_path: Path) -> None:
    source, pages, snapshot = dense_roughness_fixture(tmp_path, count=17)
    provider = EchoVisionProvider()

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert len(provider.calls) == 16
    assert sum("advisor_review" in item for item in reviewed.candidates) == 16
    assert reviewed.candidates[-1]["payload"]["requires_confirmation"] is True


def test_visual_calls_precede_the_text_budget_remainder(tmp_path: Path) -> None:
    """ADV-09: one visual batch leaves exactly fifteen stable text calls."""
    source, pages, snapshot = dense_visual_roughness_fixture(tmp_path)
    provider = UnifiedRecordingProvider()

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert provider.call_order == ["visual", *(["text"] * 15)]
    assert len(reviewed.provider_call_ids) == 16
    visual_id = pages[0].visual_observations[0].observation_id
    visual_coverage = next(
        entry
        for entry in reviewed.coverage_entries
        if entry.observation_id == visual_id
    )
    assert visual_coverage.advisor_review == {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/2",
        "symbol_kinds": [],
        "rejection_code": "visual_no_detection",
        "confidence_signal": None,
    }


def test_one_visual_schema_retry_consumes_page_and_document_budget(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = dense_visual_roughness_fixture(tmp_path)
    provider = RetryRecordingProvider()

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert provider.call_order == ["visual", "visual", *(["text"] * 14)]
    assert len(reviewed.provider_call_ids) == 16
    assert reviewed.provider_call_ids[:2] == (
        "fixture-visual-retry-1",
        "fixture-visual-retry-success",
    )


def test_warm_legacy_cache_preserves_visual_accounting_and_text_slots(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = dense_visual_roughness_fixture(tmp_path)
    provider = UnifiedRecordingProvider()
    advisor = candidate_advisor(tmp_path, provider)

    cold = advisor.review(source, pages, snapshot)
    cold_call_order = tuple(provider.call_order)
    warm = advisor.review(source, pages, snapshot)

    assert cold_call_order == ("visual", *(["text"] * 15))
    assert tuple(provider.call_order) == cold_call_order
    assert _canonical_snapshot_bytes(warm) == _canonical_snapshot_bytes(
        cold
    )
    assert len(warm.provider_call_ids) == 16


def test_second_visual_schema_failure_in_document_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual_id = pages[0].visual_observations[0].observation_id
    monkeypatch.setattr(
        advisor_module,
        "plan_visual_batches",
        lambda _pages, _snapshot: (
            (
                VisualBatch(
                    page_index=0,
                    call_index=0,
                    observation_ids=(visual_id,),
                    crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
                    pixel_width=334,
                    pixel_height=334,
                ),
                VisualBatch(
                    page_index=0,
                    call_index=1,
                    observation_ids=(visual_id,),
                    crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
                    pixel_width=417,
                    pixel_height=417,
                ),
            ),
        ),
    )

    class TwoFailureProvider:
        def __init__(self) -> None:
            self.calls = 0

        def review_symbols(self, _image: bytes, _prompt: str) -> VisionResult:
            self.calls += 1
            if self.calls in (1, 3):
                raise VisualSymbolProviderError(
                    request_id=f"fixture-schema-failure-{self.calls}",
                    usage={"total_tokens": self.calls},
                    failure_stage="tool_arguments_schema_invalid",
                )
            return VisionResult(
                request_id=f"fixture-schema-success-{self.calls}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={"total_tokens": self.calls},
            )

    provider = TwoFailureProvider()
    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor response is invalid$",
    ):
        candidate_advisor(tmp_path, provider).review(source, pages, snapshot)

    assert provider.calls == 3


def test_second_cached_visual_retry_chain_in_document_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual = pages[0].visual_observations[0]
    batches = (
        VisualBatch(
            page_index=0,
            call_index=0,
            observation_ids=(visual.observation_id,),
            crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
            pixel_width=334,
            pixel_height=334,
        ),
        VisualBatch(
            page_index=0,
            call_index=1,
            observation_ids=(visual.observation_id,),
            crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
            pixel_width=417,
            pixel_height=417,
        ),
    )
    monkeypatch.setattr(
        advisor_module,
        "plan_visual_batches",
        lambda _pages, _snapshot: (batches,),
    )

    class TwoRetryCacheProvider:
        def __init__(self) -> None:
            self.calls = 0

        def review_symbols(self, _image: bytes, _prompt: str) -> VisionResult:
            self.calls += 1
            if self.calls % 2 == 1:
                raise VisualSymbolProviderError(
                    request_id=f"fixture-cached-retry-{self.calls}",
                    usage={"total_tokens": self.calls},
                    failure_stage="tool_arguments_schema_invalid",
                )
            return VisionResult(
                request_id=f"fixture-cached-success-{self.calls}",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={"total_tokens": self.calls},
            )

    provider = TwoRetryCacheProvider()
    builder = candidate_advisor(tmp_path, provider)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    text_observations = {
        observation.observation_id: observation
        for observation in pages[0].observations
    }
    document = pymupdf.open(source)
    try:
        for batch in batches:
            builder._visual_review_result(
                provider=provider,
                crop_png=advisor_module._render_visual_crop(
                    document[0],
                    batch.crop_bbox_pdf,
                ),
                crop_bbox_pdf=batch.crop_bbox_pdf,
                source_sha256=source_sha256,
                visual_observations=(visual,),
                text_observations=text_observations,
                model="qwen3-vl-plus",
                allow_schema_retry=True,
            )
    finally:
        document.close()
    assert provider.calls == 4

    class MustNotCallProvider:
        calls = 0

        @classmethod
        def review_symbols(
            cls,
            _image: bytes,
            _prompt: str,
        ) -> VisionResult:
            cls.calls += 1
            raise AssertionError("invalid retry cache reached Provider")

    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor retry budget is invalid$",
    ):
        candidate_advisor(tmp_path, MustNotCallProvider()).review(
            source,
            pages,
            snapshot,
        )

    assert MustNotCallProvider.calls == 0


def test_full_visual_page_has_no_retry_spare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    visual_id = pages[0].visual_observations[0].observation_id
    batch = VisualBatch(
        page_index=0,
        call_index=0,
        observation_ids=(visual_id,),
        crop_bbox_pdf=(0.0, 0.0, 80.0, 80.0),
        pixel_width=334,
        pixel_height=334,
    )
    monkeypatch.setattr(
        advisor_module,
        "plan_visual_batches",
        lambda _pages, _snapshot: (tuple(replace(batch, call_index=i) for i in range(16)),),
    )

    class FailThenSucceedProvider:
        def __init__(self) -> None:
            self.calls = 0

        def review_symbols(self, _image: bytes, _prompt: str) -> VisionResult:
            self.calls += 1
            if self.calls == 1:
                raise VisualSymbolProviderError(
                    request_id="fixture-no-spare-failure",
                    usage={"total_tokens": 1},
                    failure_stage="tool_arguments_schema_invalid",
                )
            return VisionResult(
                request_id="fixture-no-spare-success",
                payload={
                    "schema_version": "visual-symbol-review/2",
                    "detections": [],
                },
                usage={"total_tokens": 1},
            )

    provider = FailThenSucceedProvider()
    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor response is invalid$",
    ):
        candidate_advisor(tmp_path, provider).review(source, pages, snapshot)

    assert provider.calls == 1


def test_visual_projection_does_not_create_same_review_text_route(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = visual_diameter_fixture(tmp_path)
    provider = VisualDiameterProvider()

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert provider.call_order == ["visual"]
    assert reviewed.candidates[0]["payload"]["item_type"] == (
        "diameter_dimension"
    )
    assert reviewed.candidates[0]["payload"]["requires_confirmation"] is True
    assert reviewed.source_signals[: len(snapshot.source_signals)] == (
        snapshot.source_signals
    )
    visual_signals = tuple(
        signal
        for signal in reviewed.source_signals
        if signal.source_type == "visual"
    )
    assert len(visual_signals) == 1
    assert str(visual_signals[0].normalized_value) == "0.97"


def test_visual_promotion_preserves_ambiguous_text_signal_and_appends_visual(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = dense_visual_roughness_fixture(tmp_path)
    provider = VisualRoughnessProvider()
    text_signal = next(
        signal
        for signal in snapshot.source_signals
        if signal.source_type == "native"
    )
    assert text_signal.normalized_value is None

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.source_signals[: len(snapshot.source_signals)] == (
        snapshot.source_signals
    )
    assert len(reviewed.source_signals) == len(snapshot.source_signals) + 1
    assert len(
        {signal.source_location_id for signal in reviewed.source_signals}
    ) == len(reviewed.source_signals)
    assert reviewed.source_signals[-1].source_type == "visual"
    assert str(reviewed.source_signals[-1].normalized_value) == "0.97"


def test_validator_rejects_raw_text_or_type_drift(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = SequenceVisionProvider(
        [
            advisor_payload("Ra 6.3", "roughness", "Ra 6.3", True),
            advisor_payload("Ra 3.2", "thread", "Ra 3.2", True),
        ]
    )

    first = candidate_advisor(tmp_path, provider).review(source, pages, snapshot)
    second = candidate_advisor(
        tmp_path / "second",
        SequenceVisionProvider([provider.payloads[1]]),
    ).review(source, pages, snapshot)

    assert first.candidates[0]["payload"] == snapshot.candidates[0]["payload"]
    assert (
        first.candidates[0]["advisor_review"]["rejection_code"]
        == "raw_text_mismatch"
    )
    assert second.candidates[0]["advisor_review"]["rejection_code"] == "type_mismatch"


def test_advisor_cannot_clear_required_confirmation(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    provider = RecordingVisionProvider(
        payload=advisor_payload("Ra 3.2", "roughness", "Ra 3.2", False)
    )

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.candidates[0]["payload"]["requires_confirmation"] is True
    assert reviewed.candidates[0]["advisor_review"]["validated"] is False
    assert (
        reviewed.candidates[0]["advisor_review"]["rejection_code"]
        == "confirmation_downgrade"
    )


def test_ambiguous_promotion_requires_local_parser_success(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="M6 depth 10")
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            "M6 depth 10",
            "thread",
            "M6深10",
            True,
        )
    )

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.coverage_entries[0].disposition == "candidate"
    assert reviewed.coverage_entries[0].requires_confirmation is True
    assert reviewed.candidates[0]["payload"]["raw_text"] == "M6 depth 10"
    assert reviewed.candidates[0]["payload"]["thread_spec"] == "M6"


def test_existing_text_payload_update_recomputes_duplicate_suggestions(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="10±0.1")
    candidate = dict(snapshot.candidates[0])
    candidate["payload"] = {
        **candidate["payload"],
        "requires_confirmation": True,
    }
    stale = DuplicateRelation("stale-left", "stale-right")
    snapshot = replace(
        snapshot,
        candidates=(candidate,),
        duplicate_relations=(stale,),
    )
    provider = RecordingVisionProvider(
        payload=advisor_payload(
            "10±0.1",
            "linear_dimension",
            "11",
            True,
        )
    )

    reviewed = candidate_advisor(tmp_path, provider).review(
        source,
        pages,
        snapshot,
    )

    assert reviewed.candidates[0]["payload"]["normalized_text"] == "11"
    assert reviewed.duplicate_relations == ()


def test_cache_hit_reuses_validated_result_without_provider_call(
    tmp_path: Path,
) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    first_provider = EchoVisionProvider()
    first = candidate_advisor(tmp_path, first_provider)
    second_provider = FailingIfCalledVisionProvider()
    second = candidate_advisor(tmp_path, second_provider)

    first_result = first.review(source, pages, snapshot)
    second_result = second.review(source, pages, snapshot)

    assert len(first_provider.calls) == 1
    assert second_provider.calls == 0
    assert second_result.provider_call_ids == first_result.provider_call_ids


def test_cache_without_call_record_fails_closed(tmp_path: Path) -> None:
    source, pages, snapshot = drawing_fixture(tmp_path, raw_text="Ra 3.2")
    first_provider = EchoVisionProvider()
    candidate_advisor(tmp_path, first_provider).review(source, pages, snapshot)
    call_record = next(
        (tmp_path / "storage").glob("projects/*/provider-calls/qwen/*.json")
    )
    call_record.unlink()
    second_provider = FailingIfCalledVisionProvider()

    with pytest.raises(
        CandidateAdvisorFailure,
        match="audit record is missing",
    ):
        candidate_advisor(tmp_path, second_provider).review(source, pages, snapshot)

    assert len(first_provider.calls) == 1
    assert second_provider.calls == 0
