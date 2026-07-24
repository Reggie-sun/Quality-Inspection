import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.providers.call_records import (
    ProviderCallRecord,
    persist_call_record,
    serialize_call_record,
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
