import base64
import hashlib
import json
import shutil
import zlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.providers.call_records import (
    ProviderCallRecord,
    persist_call_record,
    serialize_call_record,
)
from app.candidates.advisor import CandidateAdvisor, CandidateAdvisorFailure
from app.config import Settings
from app.providers.base import VisionResult
from app.providers.qwen_vl import (
    QwenVisionProvider,
    VisualSymbolProviderError,
    canonicalize_visual_png,
)
from app.storage.local import LocalFileStorage


EXPECTED_KEYS = {
    "provider",
    "request_id",
    "model",
    "prompt_version",
    "schema_version",
    "duration_ms",
    "retry_count",
    "input_image_count",
    "estimated_cost",
    "logical_task_reused",
    "request_ref",
    "response_ref",
}


def _png(
    width: int = 32,
    height: int = 24,
    *,
    text: bytes | None = None,
) -> bytes:
    def chunk(kind: bytes, content: bytes) -> bytes:
        return (
            len(content).to_bytes(4, "big")
            + kind
            + content
            + (zlib.crc32(kind + content) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    scanlines = (b"\x00" + b"\x00" * (width * 3)) * height
    document = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
    )
    if text is not None:
        document += chunk(b"tEXt", text)
    return (
        document
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _record() -> ProviderCallRecord:
    return ProviderCallRecord(
        provider="qwen-vl",
        request_id="fixture-qwen-request-id",
        model="qwen3-vl-plus",
        prompt_version="candidate-review-prompt/1",
        schema_version="candidate-review/1",
        duration_ms=125,
        retry_count=1,
        input_image_count=1,
        estimated_cost=0.0125,
        logical_task_reused=False,
        request_ref="fixture://sanitized/qwen-vl/request-v1",
        response_ref="fixture://sanitized/qwen-vl/response-v1",
    )


def test_refs_and_versions_persist_without_secrets(tmp_path: Path) -> None:
    """P0-RES-005: redacted refs and versions survive FileStorage round trip."""
    storage = LocalFileStorage(tmp_path)

    stored = persist_call_record(
        storage,
        "provider-calls/qwen-call.json",
        _record(),
    )
    payload = json.loads(stored.path.read_text(encoding="utf-8"))

    assert set(payload) == EXPECTED_KEYS
    assert payload["request_id"] == "fixture-qwen-request-id"
    assert payload["prompt_version"] == "candidate-review-prompt/1"
    assert payload["schema_version"] == "candidate-review/1"
    assert payload["request_ref"].startswith("fixture://sanitized/")
    assert payload["response_ref"].startswith("fixture://sanitized/")
    encoded = stored.path.read_text(encoding="utf-8").lower()
    assert "authorization" not in encoded
    assert "api_key" not in encoded
    assert "secret" not in encoded
    assert "base64" not in encoded


def test_minimum_call_statistics() -> None:
    """P0-RES-008: one record carries bounded call statistics and reuse state."""
    payload = json.loads(serialize_call_record(_record()))

    assert payload["duration_ms"] == 125
    assert payload["retry_count"] == 1
    assert payload["input_image_count"] == 1
    assert payload["estimated_cost"] == 0.0125
    assert payload["logical_task_reused"] is False

    reused = json.loads(
        serialize_call_record(replace(_record(), logical_task_reused=True))
    )
    assert reused["logical_task_reused"] is True


def test_unknown_pricing_is_serialized_as_null() -> None:
    payload = json.loads(
        serialize_call_record(replace(_record(), estimated_cost=None))
    )

    assert payload["estimated_cost"] is None


@pytest.mark.parametrize(
    "forbidden",
    (
        {"diagnostic": {"authorization": "redacted"}},
        {"diagnostic": {"api-key": "redacted"}},
        {"diagnostic": {"secret": "redacted"}},
        {"diagnostic": {"base64": "redacted"}},
    ),
)
def test_serializer_rejects_secret_bearing_keys(forbidden: dict) -> None:
    """P0-RES-005: recursive secret-bearing keys are rejected before persistence."""
    payload = json.loads(serialize_call_record(_record()))
    payload.update(forbidden)

    with pytest.raises(ValueError, match="forbidden"):
        serialize_call_record(payload)


@pytest.mark.parametrize(
    "unsafe_ref",
    (
        "data:image/png;base64," + "A" * 128,
        "fixture://sanitized/../escaped",
        "asset:///absolute/path",
        "asset://safe/./record",
        "asset://safe/" + "A" * 128,
        "asset:// leading-space",
        123,
    ),
)
def test_serializer_rejects_body_or_non_string_resource_refs(unsafe_ref) -> None:
    """P0-RES-005: refs cannot carry bodies, traversal, or non-string values."""
    with pytest.raises(ValueError, match="resource ref|string fields"):
        serialize_call_record(replace(_record(), request_ref=unsafe_ref))


@pytest.mark.parametrize("unsafe_cost", (float("inf"), float("nan")))
def test_serializer_rejects_non_finite_cost(unsafe_cost: float) -> None:
    """P0-RES-008: persisted estimated cost must be finite."""
    with pytest.raises(ValueError, match="estimated_cost"):
        serialize_call_record(replace(_record(), estimated_cost=unsafe_cost))


def test_qwen_visual_symbol_records_are_redacted_on_success_and_failure(
    tmp_path: Path,
) -> None:
    """PROV-02: persisted success/failure evidence is joined, canonical and redacted."""

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id="fixture-visual-success",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "schema_version": "visual-symbol-review/1",
                                    "detections": [],
                                }
                            )
                        )
                    )
                ],
                usage={"total_tokens": 7},
            )

    class InvalidProvider:
        @staticmethod
        def review_symbols(_image: bytes, _prompt: str) -> VisionResult:
            raise VisualSymbolProviderError(
                request_id="fixture-visual-invalid",
                usage={"total_tokens": 9},
            )

    storage = LocalFileStorage(tmp_path / "storage")
    completions = FakeCompletions()
    success_provider = QwenVisionProvider(
        SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
    )
    advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        storage,
        project_id="project-test",
        provider_factory=lambda _settings: success_provider,
    )
    private_marker = b"private-marker-%PDF"
    image = _png(text=b"review\x00" + private_marker)
    canonical_image = canonicalize_visual_png(image)
    common = {
        "crop_png": image,
        "crop_bbox_pdf": (1.0, 2.0, 30.0, 40.0),
        "source_sha256": "a" * 64,
        "visual_observation_ids": ("visual-001", "visual-002"),
        "model": "qwen3-vl-plus",
    }
    result, _ = advisor._visual_review_result(
        provider=success_provider,
        **common,
    )
    assert result.request_id == "fixture-visual-success"
    sent_data_url = completions.calls[0]["messages"][1]["content"][0][
        "image_url"
    ]["url"]
    sent_image = base64.b64decode(
        sent_data_url.removeprefix("data:image/png;base64,")
    )
    assert sent_image == canonical_image
    assert canonicalize_visual_png(canonical_image) == canonical_image
    assert private_marker not in sent_image
    assert b"%PDF" not in sent_image

    success_record_path = next(
        storage.root.glob("projects/*/provider-calls/qwen-symbol/*.json")
    )
    success_record = json.loads(success_record_path.read_text())
    success_request = json.loads(
        storage.resolve_resource_ref(
            success_record["request_ref"]
        ).read_text()
    )
    success_response = json.loads(
        storage.resolve_resource_ref(success_record["response_ref"]).read_text()
    )
    assert success_request == {
        "schema_version": "visual-symbol-call-request/1",
        "crop_ref": success_request["crop_ref"],
        "crop_sha256": hashlib.sha256(canonical_image).hexdigest(),
        "usage": {"total_tokens": 7},
    }
    success_crop = storage.resolve_resource_ref(success_request["crop_ref"])
    assert success_crop.read_bytes() == sent_image
    assert private_marker not in success_crop.read_bytes()
    assert b"%PDF" not in success_crop.read_bytes()
    assert hashlib.sha256(success_crop.read_bytes()).hexdigest() == (
        success_request["crop_sha256"]
    )
    assert success_response == {
        "schema_version": "visual-symbol-review/1",
        "detections": [],
    }
    assert Path(success_record["response_ref"]).name == (
        hashlib.sha256(
            json.dumps(
                success_response,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        + ".json"
    )
    metadata_variant = _png(
        text=b"alternate\x00different-private-metadata"
    )
    assert canonicalize_visual_png(metadata_variant) == canonical_image
    variant_result, _ = advisor._visual_review_result(
        provider=success_provider,
        **(common | {"crop_png": metadata_variant}),
    )
    assert variant_result == result
    assert len(completions.calls) == 1

    class MustNotCallProvider:
        @staticmethod
        def review_symbols(_image: bytes, _prompt: str) -> VisionResult:
            raise AssertionError("validated visual cache constructed a Provider call")

    cached, _ = advisor._visual_review_result(
        provider=MustNotCallProvider(),
        **common,
    )
    assert cached == result

    cache_cases = (
        "missing_audit",
        "response_hash",
        "identity_source",
        "identity_version",
        "response_schema",
        "audit_extra",
        "audit_mismatch",
        "missing_request",
        "request_usage",
        "missing_crop",
        "tampered_crop",
        "missing_response_artifact",
        "tampered_response_artifact",
        "self_consistent_response",
        "cache_symlink",
    )
    for case in cache_cases:
        case_root = tmp_path / f"invalid-cache-{case}"
        shutil.copytree(storage.root, case_root)
        case_storage = LocalFileStorage(case_root)
        cache_path = next(
            case_root.glob("projects/*/provider-cache/qwen-symbol/*.json")
        )
        audit_path = next(
            case_root.glob("projects/*/provider-calls/qwen-symbol/*.json")
        )
        audit_payload = json.loads(audit_path.read_text())
        request_path = case_storage.resolve_resource_ref(
            audit_payload["request_ref"]
        )
        request_payload = json.loads(request_path.read_text())
        crop_path = case_storage.resolve_resource_ref(
            request_payload["crop_ref"]
        )
        response_path = case_storage.resolve_resource_ref(
            audit_payload["response_ref"]
        )
        if case == "missing_audit":
            audit_path.unlink()
        elif case == "response_hash":
            cache_payload = json.loads(cache_path.read_text())
            cache_payload["response_sha256"] = "0" * 64
            cache_path.write_text(json.dumps(cache_payload))
        elif case == "identity_source":
            cache_payload = json.loads(cache_path.read_text())
            cache_payload["identity"]["source_sha256"] = "b" * 64
            cache_path.write_text(json.dumps(cache_payload))
        elif case == "identity_version":
            cache_payload = json.loads(cache_path.read_text())
            cache_payload["identity"]["prompt_version"] = (
                "visual-symbol-prompt/3"
            )
            cache_path.write_text(json.dumps(cache_payload))
        elif case == "response_schema":
            cache_payload = json.loads(cache_path.read_text())
            cache_payload["response"]["schema_version"] = (
                "visual-symbol-review/2"
            )
            response_bytes = json.dumps(
                cache_payload["response"],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            cache_payload["response_sha256"] = hashlib.sha256(
                response_bytes
            ).hexdigest()
            cache_path.write_text(json.dumps(cache_payload))
        elif case == "audit_extra":
            audit_payload["diagnostic"] = "not-allowlisted"
            audit_path.write_text(json.dumps(audit_payload))
        elif case == "audit_mismatch":
            audit_payload["model"] = "qwen3-vl-max"
            audit_path.write_text(json.dumps(audit_payload))
        elif case == "missing_request":
            request_path.unlink()
        elif case == "request_usage":
            request_payload["usage"]["total_tokens"] = 8
            request_path.write_text(json.dumps(request_payload))
        elif case == "missing_crop":
            crop_path.unlink()
        elif case == "tampered_crop":
            crop_path.write_bytes(_png(width=33))
        elif case == "missing_response_artifact":
            response_path.unlink()
        elif case == "tampered_response_artifact":
            response_path.write_text(
                json.dumps(
                    {
                        "schema_version": "visual-symbol-review/1",
                        "detections": [
                            {
                                "visual_observation_id": "visual-001",
                                "symbol_kind": "diameter",
                                "bbox_normalized": [0.1, 0.1, 0.2, 0.2],
                                "associated_text_observation_ids": [],
                                "requires_confirmation": True,
                            }
                        ],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        elif case == "self_consistent_response":
            cache_payload = json.loads(cache_path.read_text())
            cache_payload["response"]["detections"] = [
                {
                    "visual_observation_id": "visual-001",
                    "symbol_kind": "diameter",
                    "bbox_normalized": [0.1, 0.1, 0.2, 0.2],
                    "associated_text_observation_ids": [],
                    "requires_confirmation": True,
                }
            ]
            response_bytes = json.dumps(
                cache_payload["response"],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            cache_payload["response_sha256"] = hashlib.sha256(
                response_bytes
            ).hexdigest()
            cache_path.write_text(json.dumps(cache_payload))
        elif case == "cache_symlink":
            outside = tmp_path / "outside-cache.json"
            outside.write_bytes(cache_path.read_bytes())
            cache_path.unlink()
            cache_path.symlink_to(outside)

        class CountingProvider:
            def __init__(self) -> None:
                self.calls = 0

            def review_symbols(
                self,
                _image: bytes,
                _prompt: str,
            ) -> VisionResult:
                self.calls += 1
                raise AssertionError("invalid cache reached Provider")

        counting_provider = CountingProvider()
        invalid_advisor = CandidateAdvisor(
            Settings(qwen_model="qwen3-vl-plus"),
            case_storage,
            project_id="project-test",
            provider_factory=lambda _settings: counting_provider,
        )
        with pytest.raises(
            CandidateAdvisorFailure,
            match="^Visual symbol Advisor cache is invalid$",
        ):
            invalid_advisor._visual_review_result(
                provider=counting_provider,
                **common,
            )
        assert counting_provider.calls == 0

    unsafe_metadata_results = (
        VisionResult(
            request_id="secret-request-id",
            payload={
                "schema_version": "visual-symbol-review/1",
                "detections": [],
            },
            usage={"total_tokens": 1},
        ),
        VisionResult(
            request_id="fixture-safe-request-id",
            payload={
                "schema_version": "visual-symbol-review/1",
                "detections": [],
            },
            usage={"api_key": 1},
        ),
    )
    for index, unsafe_result in enumerate(unsafe_metadata_results):
        class UnsafeMetadataProvider:
            @staticmethod
            def review_symbols(_image: bytes, _prompt: str) -> VisionResult:
                return unsafe_result

        metadata_storage = LocalFileStorage(
            tmp_path / f"unsafe-metadata-{index}"
        )
        metadata_advisor = CandidateAdvisor(
            Settings(qwen_model="qwen3-vl-plus"),
            metadata_storage,
            project_id="project-test",
            provider_factory=lambda _settings: UnsafeMetadataProvider(),
        )
        with pytest.raises(
            CandidateAdvisorFailure,
            match="^Visual symbol Advisor call failed$",
        ) as metadata_error:
            metadata_advisor._visual_review_result(
                provider=UnsafeMetadataProvider(),
                **common,
            )
        assert "secret" not in str(metadata_error.value).lower()
        assert "api_key" not in str(metadata_error.value).lower()
        assert not tuple(
            metadata_storage.root.glob(
                "projects/*/provider-calls/qwen-symbol/*.json"
            )
        )

    failure_advisor = CandidateAdvisor(
        Settings(qwen_model="qwen3-vl-plus"),
        LocalFileStorage(tmp_path / "failure-storage"),
        project_id="project-test",
        provider_factory=lambda _settings: InvalidProvider(),
    )
    with pytest.raises(
        CandidateAdvisorFailure,
        match="^Visual symbol Advisor response is invalid$",
    ) as raised:
        failure_advisor._visual_review_result(
            provider=InvalidProvider(),
            **common,
        )
    assert "synthetic-crop" not in str(raised.value)

    failure_record_path = next(
        failure_advisor._storage.root.glob(
            "projects/*/provider-calls/qwen-symbol/*.json"
        )
    )
    failure_record = json.loads(failure_record_path.read_text())
    failure_request = json.loads(
        failure_advisor._storage.resolve_resource_ref(
            failure_record["request_ref"]
        ).read_text()
    )
    failure_response = json.loads(
        failure_advisor._storage.resolve_resource_ref(
            failure_record["response_ref"]
        ).read_text()
    )
    assert set(failure_request) == {
        "crop_ref",
        "crop_sha256",
        "schema_version",
        "usage",
    }
    assert (
        failure_request["schema_version"]
        == "visual-symbol-call-request/1"
    )
    assert failure_request["usage"] == {"total_tokens": 9}
    failure_crop = failure_advisor._storage.resolve_resource_ref(
        failure_request["crop_ref"]
    )
    assert hashlib.sha256(failure_crop.read_bytes()).hexdigest() == (
        failure_request["crop_sha256"]
    )
    assert failure_response == {
        "error_code": "visual_schema_invalid",
        "schema_version": "visual-symbol-call-failure/1",
    }

    encoded = json.dumps(
        [
            success_record,
            success_request,
            success_response,
            failure_record,
            failure_request,
            failure_response,
        ],
        sort_keys=True,
    ).lower()
    for forbidden in (
        "synthetic-crop",
        "data:image",
        "base64",
        "/home/",
        "authorization",
        "api_key",
        "secret",
        "explanation",
        "private-marker",
        "%pdf",
    ):
        assert forbidden not in encoded
