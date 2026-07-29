from __future__ import annotations

from collections.abc import Mapping


CONFIDENCE_POLICY_VERSION = "candidate-confidence/1"
CONFIDENCE_EVIDENCE_CODE_ORDER = (
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

_CONFIDENCE_DECISION_FIELDS = {
    "band",
    "review_disposition",
    "policy_version",
    "evidence_codes",
}
_EVIDENCE_CODE_INDEX = {
    code: index for index, code in enumerate(CONFIDENCE_EVIDENCE_CODE_ORDER)
}
_DISPOSITION_BY_BAND = {
    "high": "auto_accepted",
    "medium": "review_required",
    "low": "review_required",
}


class ConfidenceDecisionContractError(ValueError):
    """Raised when a frozen confidence decision violates its contract."""


def validate_confidence_decision(decision: object) -> None:
    if not isinstance(decision, Mapping):
        raise ConfidenceDecisionContractError(
            "confidence_decision must be one object"
        )

    fields = set(decision)
    if fields != _CONFIDENCE_DECISION_FIELDS:
        missing = sorted(_CONFIDENCE_DECISION_FIELDS - fields, key=str)
        extra = sorted(fields - _CONFIDENCE_DECISION_FIELDS, key=str)
        raise ConfidenceDecisionContractError(
            "confidence_decision fields must be exact: "
            f"missing={missing}, extra={extra}"
        )

    band = decision["band"]
    if not isinstance(band, str) or band not in _DISPOSITION_BY_BAND:
        raise ConfidenceDecisionContractError(
            "confidence_decision.band must be high, medium, or low"
        )

    review_disposition = decision["review_disposition"]
    expected_disposition = _DISPOSITION_BY_BAND[band]
    if review_disposition != expected_disposition:
        raise ConfidenceDecisionContractError(
            "confidence_decision.review_disposition does not match band"
        )

    if decision["policy_version"] != CONFIDENCE_POLICY_VERSION:
        raise ConfidenceDecisionContractError(
            "confidence_decision.policy_version is unknown"
        )

    evidence_codes = decision["evidence_codes"]
    if (
        not isinstance(evidence_codes, list)
        or not evidence_codes
        or any(not isinstance(code, str) for code in evidence_codes)
    ):
        raise ConfidenceDecisionContractError(
            "confidence_decision.evidence_codes must be a non-empty list[str]"
        )
    if len(set(evidence_codes)) != len(evidence_codes):
        raise ConfidenceDecisionContractError(
            "confidence_decision.evidence_codes must be unique"
        )
    if any(code not in _EVIDENCE_CODE_INDEX for code in evidence_codes):
        raise ConfidenceDecisionContractError(
            "confidence_decision.evidence_codes contains an unknown code"
        )
    indexes = [_EVIDENCE_CODE_INDEX[code] for code in evidence_codes]
    if indexes != sorted(indexes):
        raise ConfidenceDecisionContractError(
            "confidence_decision.evidence_codes must use canonical order"
        )
