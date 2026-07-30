from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.candidates.symbol_cache import (
    CACHE_IDENTITY_SCHEMA_VERSION,
    CacheWriteRejected,
    SymbolCacheIdentity,
    SymbolCacheProvenance,
    VisualSymbolCacheEntry,
    build_cache_entry,
    evaluate_cache_entry,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _identity(**overrides: object) -> SymbolCacheIdentity:
    values: dict[str, object] = {
        "schema_version": CACHE_IDENTITY_SCHEMA_VERSION,
        "canonical_crop_sha256": SHA_A,
        "associated_text_sha256": SHA_B,
        "local_evidence_sha256s": (SHA_A, SHA_C),
        "router_version": "symbol-uncertainty-router/1",
        "proposal_version": "visual-observation-proposal/1",
        "prompt_version": "visual-symbol-prompt/4",
        "response_schema_version": "visual-symbol-review/2",
        "adapter_version": "qwen-visual-symbol-adapter/5",
        "model_identity": "qwen3-vl-plus",
        "pymupdf_version": "1.26.3",
        "crop_canonicalization_version": "symbol-roi-crop/1",
    }
    values.update(overrides)
    return SymbolCacheIdentity(**values)


def _provenance(
    identity: SymbolCacheIdentity,
    **overrides: object,
) -> SymbolCacheProvenance:
    values: dict[str, object] = {
        "identity_sha256": identity.sha256,
        "producer_project_id": "11111111-1111-4111-8111-111111111111",
        "producer_request_id": "provider-request-1",
        "producer_call_record_ref": (
            "asset://projects/11111111-1111-4111-8111-111111111111/"
            "provider-calls/qwen-symbol/provider-request-1.json"
        ),
        "response_sha256": _response_sha256(),
        "created_at": datetime(2026, 7, 30, tzinfo=UTC),
        "model_identity": identity.model_identity,
        "response_schema_version": identity.response_schema_version,
        "router_version": identity.router_version,
        "validation_outcome": "schema_valid",
    }
    values.update(overrides)
    return SymbolCacheProvenance(**values)


def _entry(
    identity: SymbolCacheIdentity,
    **overrides: object,
) -> VisualSymbolCacheEntry:
    values: dict[str, object] = {
        "identity": identity,
        "response": _response(),
        "response_sha256": _response_sha256(),
        "provenance": _provenance(identity),
    }
    values.update(overrides)
    return VisualSymbolCacheEntry(**values)


def _response() -> dict[str, object]:
    return {
        "schema_version": "visual-symbol-review/2",
        "detections": [],
    }


def _response_sha256() -> str:
    canonical = json.dumps(
        _response(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize(
    ("field", "changed_value"),
    (
        ("schema_version", "symbol-cache-identity/2"),
        ("canonical_crop_sha256", SHA_B),
        ("associated_text_sha256", SHA_C),
        ("local_evidence_sha256s", (SHA_B, SHA_C)),
        ("router_version", "symbol-uncertainty-router/2"),
        ("proposal_version", "visual-observation-proposal/2"),
        ("prompt_version", "visual-symbol-prompt/5"),
        ("response_schema_version", "visual-symbol-review/3"),
        ("adapter_version", "qwen-visual-symbol-adapter/6"),
        ("model_identity", "qwen3-vl-next"),
        ("pymupdf_version", "1.27.0"),
        ("crop_canonicalization_version", "symbol-roi-crop/2"),
    ),
)
def test_cache_identity_binds_every_versioned_content_input(
    field: str,
    changed_value: object,
) -> None:
    identity = _identity()

    changed = replace(identity, **{field: changed_value})

    assert changed.sha256 != identity.sha256


def test_content_identity_is_project_independent() -> None:
    identity = _identity()

    assert not hasattr(identity, "project_id")
    assert identity.sha256 == _identity().sha256


def test_local_evidence_order_is_part_of_content_identity() -> None:
    identity = _identity()

    reordered = replace(
        identity,
        local_evidence_sha256s=tuple(
            reversed(identity.local_evidence_sha256s)
        ),
    )

    assert reordered.sha256 != identity.sha256


def test_identity_mismatch_is_reason_coded_miss_without_compatibility_repair() -> None:
    producer_identity = _identity()
    consumer_identity = _identity(router_version="symbol-uncertainty-router/2")

    result = evaluate_cache_entry(
        expected_identity=consumer_identity,
        entry=_entry(producer_identity),
    )

    assert result.hit is False
    assert result.reason_code == "cache_identity_mismatch"
    assert result.quarantine is False
    assert result.response is None


def test_unsupported_identity_version_cannot_be_a_current_hit() -> None:
    legacy_identity = _identity(
        schema_version="visual-symbol-cache-identity/0"
    )

    result = evaluate_cache_entry(
        expected_identity=legacy_identity,
        entry=_entry(legacy_identity),
    )

    assert result.hit is False
    assert result.reason_code == "cache_identity_mismatch"


@pytest.mark.parametrize(
    "entry",
    (
        _entry(_identity(), provenance=None),
        _entry(
            _identity(),
            provenance=_provenance(_identity(), identity_sha256=SHA_B),
        ),
        _entry(
            _identity(),
            provenance=_provenance(_identity(), response_sha256=SHA_B),
        ),
        _entry(
            _identity(),
            provenance=_provenance(
                _identity(),
                validation_outcome="schema_invalid",
            ),
        ),
        _entry(
            _identity(),
            provenance=_provenance(
                _identity(),
                producer_call_record_ref="asset://../private",
            ),
        ),
        _entry(
            _identity(),
            provenance=_provenance(
                _identity(),
                producer_call_record_ref=(
                    "asset://projects/"
                    "22222222-2222-4222-8222-222222222222/"
                    "provider-calls/qwen-symbol/request.json"
                ),
            ),
        ),
    ),
)
def test_missing_or_invalid_provenance_is_quarantined_reason_coded_miss(
    entry: VisualSymbolCacheEntry,
) -> None:
    result = evaluate_cache_entry(
        expected_identity=_identity(),
        entry=entry,
    )

    assert result.hit is False
    assert result.reason_code == "cache_provenance_invalid"
    assert result.quarantine is True
    assert result.response is None


@pytest.mark.parametrize(
    ("provider_event_code", "schema_valid"),
    (
        ("provider_schema_invalid", False),
        ("provider_timeout", False),
        ("provider_transport_failure", False),
        ("provider_unavailable", False),
        ("not_started_budget_exhausted", False),
        ("provider_response_valid", False),
    ),
)
def test_failed_or_schema_invalid_provider_result_is_never_cacheable(
    provider_event_code: str,
    schema_valid: bool,
) -> None:
    identity = _identity()

    with pytest.raises(CacheWriteRejected):
        build_cache_entry(
            identity=identity,
            response=_response(),
            provenance=_provenance(identity),
            provider_event_code=provider_event_code,
            schema_valid=schema_valid,
        )


def test_schema_valid_provider_response_builds_a_revalidatable_entry() -> None:
    identity = _identity()

    entry = build_cache_entry(
        identity=identity,
        response=_response(),
        provenance=_provenance(identity),
        provider_event_code="provider_response_valid",
        schema_valid=True,
    )
    result = evaluate_cache_entry(
        expected_identity=identity,
        entry=entry,
    )

    assert result.hit is True
    assert result.reason_code == "cache_hit_valid"
    assert result.quarantine is False
    assert result.response == entry.response
