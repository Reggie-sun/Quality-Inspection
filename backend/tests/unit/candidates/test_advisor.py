from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

import app.candidates.advisor as advisor_module
from app.candidates.advisor import CandidateAdvisor, CandidateAdvisorFailure
from app.candidates.duplicates import DuplicateRelation
from app.config import Settings
from app.pdf.inventory import build_inventory
from app.pdf.schemas import TextObservation
from app.pdf.visual_observations import VisualBatch
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


def candidate_advisor(
    tmp_path: Path,
    provider: object,
) -> CandidateAdvisor:
    return CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=lambda _settings: provider,
    )


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

    assert reviewed == snapshot
    assert constructed == []
    assert len(reviewed.source_signals) == 1
    assert reviewed.source_signals[0].source_type == "native"
    assert str(reviewed.source_signals[0].normalized_value) == "1"
    assert reviewed.candidates[0]["source_truth_preserved"] is True


def test_resolved_visual_does_not_construct_provider_or_mutate_snapshot(
    tmp_path: Path,
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
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "storage"),
        project_id="project-test",
        provider_factory=forbidden_factory,
    )

    reviewed = advisor.review(source, pages, resolved_snapshot)

    assert reviewed == resolved_snapshot
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
