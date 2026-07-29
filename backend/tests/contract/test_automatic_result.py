from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.candidates.confidence import (
    CONFIDENCE_EVIDENCE_CODE_ORDER,
    CONFIDENCE_POLICY_VERSION,
    ConfidenceDecisionContractError,
)
from app.processing.automatic_result import (
    AUTOMATIC_RESULT_SCHEMA_VERSION,
    NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
    _validated_candidates_for_schema,
    build_automatic_result,
)


def _decision(**overrides: object) -> dict[str, object]:
    decision: dict[str, object] = {
        "band": "high",
        "disposition": "auto_accepted",
        "policy_version": CONFIDENCE_POLICY_VERSION,
        "evidence_codes": [
            "typed_schema_complete",
            "source_truth_preserved",
            "coverage_clear",
        ],
    }
    decision.update(overrides)
    return decision


def _candidate(decision: object) -> dict[str, object]:
    return {
        "candidate_id": "candidate-1",
        "payload": {"raw_text": "M6", "item_type": "thread"},
        "source_location_ids": ["observation-1"],
        "confidence_decision": decision,
    }


def test_confidence_evidence_code_order_is_frozen() -> None:
    assert CONFIDENCE_EVIDENCE_CODE_ORDER == (
        "typed_schema_complete",
        "typed_schema_incomplete",
        "feature_kind_unknown",
        "coarse_fallback",
        "local_projection_failed",
        "source_truth_preserved",
        "normalized_value_invalid",
        "single_source_owner",
        "source_location_missing",
        "source_owner_conflict",
        "local_association_complete",
        "local_association_missing",
        "coverage_clear",
        "coverage_unchecked",
        "coverage_blocking",
        "ambiguous_source",
        "no_conflict",
        "possible_duplicate",
        "cross_view_conflict",
        "projection_conflict",
        "provider_schema_rejected",
        "semantic_confirmation_clear",
        "semantic_confirmation_required",
        "balloon_requirement_known",
        "balloon_requirement_unknown",
        "source_signal_valid",
        "source_signal_missing",
        "source_signal_invalid",
        "source_signal_high",
        "source_signal_medium",
        "source_signal_low",
    )


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "candidate_id": "candidate-1",
            "payload": {"raw_text": "M6", "item_type": "thread"},
            "source_location_ids": ["observation-1"],
        },
        _candidate(
            {
                "band": "high",
                "disposition": "auto_accepted",
                "policy_version": CONFIDENCE_POLICY_VERSION,
            }
        ),
        _candidate({**_decision(), "reasoning": "provider said so"}),
    ],
)
def test_automatic_result_v2_rejects_candidate_without_confidence_decision(
    candidate: dict[str, object],
) -> None:
    with pytest.raises(ConfidenceDecisionContractError):
        _validated_candidates_for_schema(
            [candidate],
            NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
        )


def test_automatic_result_v2_rejects_unknown_confidence_policy() -> None:
    with pytest.raises(
        ConfidenceDecisionContractError,
        match="policy_version",
    ):
        _validated_candidates_for_schema(
            [_candidate(_decision(policy_version="candidate-confidence/999"))],
            NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
        )


@pytest.mark.parametrize(
    "decision",
    [
        _decision(band="unknown"),
        _decision(band=[]),
        _decision(band="medium", disposition="auto_accepted"),
        _decision(band="low", disposition="auto_accepted"),
        _decision(band="high", disposition="review_required"),
        _decision(evidence_codes=[]),
        _decision(evidence_codes=["coverage_clear", "coverage_clear"]),
        _decision(evidence_codes=["coverage_clear", 7]),
        _decision(evidence_codes=["not-a-known-evidence-code"]),
        _decision(
            evidence_codes=[
                "coverage_clear",
                "typed_schema_complete",
            ]
        ),
    ],
)
def test_automatic_result_v2_rejects_invalid_confidence_decision(
    decision: dict[str, object],
) -> None:
    with pytest.raises(ConfidenceDecisionContractError):
        _validated_candidates_for_schema(
            [_candidate(decision)],
            NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
        )


def test_automatic_result_v2_accepts_complete_confidence_decision() -> None:
    candidates = [_candidate(_decision())]

    validated = _validated_candidates_for_schema(
        candidates,
        NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
    )

    assert validated is candidates
    assert validated[0]["confidence_decision"] == _decision()


def test_automatic_result_v1_remains_readable_without_confidence_decision() -> None:
    candidates = [
        {
            "candidate_id": "legacy-candidate",
            "payload": {"raw_text": "M6", "item_type": "thread"},
            "source_location_ids": ["legacy-observation"],
        }
    ]

    validated = _validated_candidates_for_schema(
        candidates,
        AUTOMATIC_RESULT_SCHEMA_VERSION,
    )

    assert validated is candidates


def test_automatic_result_rejects_unknown_schema() -> None:
    with pytest.raises(
        ConfidenceDecisionContractError,
        match="schema_version",
    ):
        _validated_candidates_for_schema([], "automatic-result/999")


def test_build_rejects_invalid_v2_before_database_access() -> None:
    class NoDatabaseAccess:
        def scalar(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("database access happened before validation")

    with pytest.raises(
        ConfidenceDecisionContractError,
        match="policy_version",
    ):
        build_automatic_result(
            NoDatabaseAccess(),  # type: ignore[arg-type]
            project_id="not-read",
            source_file_id="not-read",
            logical_job_id="not-read",
            inventory_ref="asset://tests/inventory.json",
            candidates=[
                _candidate(
                    _decision(
                        policy_version="candidate-confidence/unknown"
                    )
                )
            ],
            coverage=SimpleNamespace(  # type: ignore[arg-type]
                blocking_count=0,
                coverage_checked=True,
            ),
            provider_call_ids=[],
            schema_version=NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION,
        )
