from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from app.candidates.advisor import CandidateAdvisor, CandidateAdvisorFailure
from app.config import Settings
from app.pdf.inventory import build_inventory
from app.processing.automatic_result import (
    CandidateSnapshot,
    candidate_snapshot_from_inventory,
)
from app.providers.base import VisionResult
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
