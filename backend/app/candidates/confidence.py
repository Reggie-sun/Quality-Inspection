from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import ValidationError

from app.candidates.coverage import CoverageEntry, CoverageReport
from app.candidates.duplicates import DuplicateRelation
from app.candidates.schemas import Candidate


CONFIDENCE_POLICY_VERSION = "candidate-confidence/1"
HIGH_THRESHOLD = Decimal("0.95")
MEDIUM_THRESHOLD = Decimal("0.70")
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
_CANONICAL_THREAD_SPEC = re.compile(
    r"M(?:0|[1-9]\d*)(?:\.\d+)?"
    r"(?:×(?:0|[1-9]\d*)(?:\.\d+)?)?"
)


class ConfidenceDecisionContractError(ValueError):
    """Raised when a frozen confidence decision violates its contract."""


@dataclass(frozen=True)
class CandidateSourceSignal:
    source_location_id: str
    source_type: Literal["native", "ocr", "visual"]
    normalized_value: Decimal | None


@dataclass(frozen=True)
class ConfidenceDecision:
    band: Literal["high", "medium", "low"]
    review_disposition: Literal["auto_accepted", "review_required"]
    policy_version: str
    evidence_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "band": self.band,
            "review_disposition": self.review_disposition,
            "policy_version": self.policy_version,
            "evidence_codes": list(self.evidence_codes),
        }


def validate_confidence_decision(decision: object) -> ConfidenceDecision:
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
    return ConfidenceDecision(
        band=band,
        review_disposition=review_disposition,
        policy_version=CONFIDENCE_POLICY_VERSION,
        evidence_codes=tuple(evidence_codes),
    )


def confidence_decision_digest(decision: ConfidenceDecision) -> str:
    serialized = json.dumps(
        decision.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def normalize_native_signal(exact_match: bool) -> Decimal:
    if not isinstance(exact_match, bool):
        raise ValueError("native exact_match must be one bool")
    return Decimal("1") if exact_match else Decimal("0")


def _normalized_decimal(
    value: object,
    *,
    maximum: Decimal,
    field: str,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be one finite number")
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be one finite number") from exc
    if not normalized.is_finite():
        raise ValueError(f"{field} must be one finite number")
    if normalized < 0 or normalized > maximum:
        raise ValueError(f"{field} is out of range")
    return normalized


def normalize_tencent_ocr_signal(percent: object) -> Decimal:
    return _normalized_decimal(
        percent,
        maximum=Decimal("100"),
        field="Tencent OCR percent",
    ) / Decimal("100")


def normalize_visual_signal(unit_value: object) -> Decimal:
    return _normalized_decimal(
        unit_value,
        maximum=Decimal("1"),
        field="visual unit_value",
    )


def _is_nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_coordinates(value: object) -> bool:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, (str, bytes))
        or len(value) != 4
    ):
        return False
    coordinates: list[float] = []
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(
            coordinate,
            (int, float, Decimal),
        ):
            return False
        number = float(coordinate)
        if not math.isfinite(number):
            return False
        coordinates.append(number)
    return (
        coordinates[2] > coordinates[0]
        and coordinates[3] > coordinates[1]
    )


def _decimal_value(
    value: object,
    *,
    nonnegative: bool,
) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    if nonnegative and decimal_value < 0:
        return None
    return decimal_value


def _optional_finite(payload: Mapping[str, object], field: str) -> bool:
    return field not in payload or payload[field] is None or _decimal_value(
        payload[field],
        nonnegative=False,
    ) is not None


def _family_semantics_complete(
    payload: Mapping[str, object],
    *,
    source_signals: Sequence[CandidateSourceSignal],
) -> tuple[bool, bool]:
    item_type = payload.get("item_type")
    if item_type == "composite":
        return _composite_semantics_complete(payload), False
    return _requirement_semantics_complete(
        item_type,
        payload,
        source_signals=source_signals,
    )


def _requirement_semantics_complete(
    item_type: object,
    payload: Mapping[str, object],
    *,
    source_signals: Sequence[CandidateSourceSignal] = (),
) -> tuple[bool, bool]:
    feature_unknown = False
    if item_type == "linear_dimension":
        return _decimal_value(
            payload.get("nominal"),
            nonnegative=True,
        ) is not None, feature_unknown
    if item_type == "diameter_dimension":
        feature_kind = payload.get("feature_kind")
        feature_unknown = feature_kind not in {
            "hole",
            "shaft",
            "cylindrical_feature",
        }
        return (
            _decimal_value(
                payload.get("nominal"),
                nonnegative=True,
            )
            is not None
            and not feature_unknown
        ), feature_unknown
    if item_type == "thread":
        thread_depth = payload.get("thread_depth")
        return (
            isinstance(payload.get("thread_spec"), str)
            and _CANONICAL_THREAD_SPEC.fullmatch(
                payload["thread_spec"]
            )
            is not None
            and isinstance(payload.get("through"), bool)
            and (
                thread_depth is None
                or _decimal_value(thread_depth, nonnegative=True) is not None
            )
        ), feature_unknown
    if item_type == "radius":
        return _decimal_value(
            payload.get("radius_value"),
            nonnegative=True,
        ) is not None, feature_unknown
    if item_type == "angle":
        angle = _decimal_value(
            payload.get("angle_value"),
            nonnegative=True,
        )
        return (
            angle is not None
            and angle <= Decimal("360")
            and _optional_finite(payload, "upper_tolerance")
            and _optional_finite(payload, "lower_tolerance")
        ), feature_unknown
    if item_type == "general_requirement":
        has_classifier_proxy = any(
            signal.source_type == "native"
            and signal.normalized_value == Decimal("1")
            for signal in source_signals
        )
        return (
            payload.get("scope") == "global_requirement"
            and payload.get("balloon_required") is False
            and has_classifier_proxy
        ), feature_unknown
    return False, feature_unknown


def _composite_semantics_complete(payload: Mapping[str, object]) -> bool:
    requirements = payload.get("sub_requirements")
    if not isinstance(requirements, list) or not requirements:
        return False
    if any(not isinstance(requirement, Mapping) for requirement in requirements):
        return False
    if [
        requirement.get("order")
        for requirement in requirements
    ] != list(range(len(requirements))):
        return False
    primary = requirements[0]
    if not isinstance(primary, Mapping):
        return False
    primary_complete, _ = _requirement_semantics_complete(
        primary.get("kind"),
        primary,
    )
    if not primary_complete:
        return False
    for modifier in requirements[1:]:
        if not isinstance(modifier, Mapping):
            return False
        if modifier.get("kind") == "depth":
            if _decimal_value(
                modifier.get("value"),
                nonnegative=True,
            ) is None:
                return False
        elif modifier.get("kind") == "through":
            if modifier.get("value") is not True:
                return False
        else:
            return False
    return True


def _contains_coarse_fallback(payload: Mapping[str, object]) -> bool:
    if "coarse_type" in payload:
        return True
    requirements = payload.get("sub_requirements")
    return isinstance(requirements, list) and any(
        isinstance(requirement, Mapping)
        and "coarse_type" in requirement
        for requirement in requirements
    )


def _ordered_evidence(codes: set[str]) -> tuple[str, ...]:
    return tuple(
        code for code in CONFIDENCE_EVIDENCE_CODE_ORDER if code in codes
    )


def _source_ids(candidate: Mapping[str, object]) -> tuple[str, ...]:
    values = candidate.get("source_location_ids")
    if not isinstance(values, (list, tuple)) or isinstance(
        values,
        (str, bytes),
    ):
        return ()
    if any(not isinstance(value, str) for value in values):
        return ()
    return tuple(values)


def _linked_coverage_entries(
    candidate_id: str,
    source_ids: Sequence[str],
    coverage: CoverageReport,
) -> tuple[CoverageEntry, ...]:
    source_set = set(source_ids)
    return tuple(
        entry
        for entry in coverage.entries
        if entry.candidate_id == candidate_id
        or entry.source_location_id in source_set
        or entry.observation_id in source_set
    )


def _review_evidence(
    review: object,
    evidence: set[str],
) -> bool:
    if not isinstance(review, Mapping):
        return False
    rejection_code = review.get("rejection_code")
    rejected = review.get("validated") is False or _is_nonblank(rejection_code)
    if not rejected:
        return False
    code = str(rejection_code or "")
    if "local_parse" in code:
        evidence.add("local_projection_failed")
    if "projection_conflict" in code:
        evidence.add("projection_conflict")
    if "cross_view" in code:
        evidence.add("cross_view_conflict")
    evidence.add("provider_schema_rejected")
    return True


def _candidate_source_signals(
    source_ids: Sequence[str],
    source_signals: Sequence[CandidateSourceSignal],
    evidence: set[str],
) -> tuple[tuple[CandidateSourceSignal, ...], bool]:
    relevant = tuple(
        signal
        for signal in source_signals
        if signal.source_location_id in set(source_ids)
    )
    counts = Counter(signal.source_location_id for signal in relevant)
    if any(count != 1 for count in counts.values()):
        evidence.add("source_owner_conflict")
    missing = [source_id for source_id in source_ids if counts[source_id] == 0]
    if missing:
        evidence.add("source_signal_missing")
        return relevant, False
    valid = (
        bool(source_ids)
        and len(relevant) == len(source_ids)
        and all(count == 1 for count in counts.values())
        and all(
            signal.source_type in {"native", "ocr", "visual"}
            and isinstance(signal.normalized_value, Decimal)
            and signal.normalized_value.is_finite()
            and Decimal("0") <= signal.normalized_value <= Decimal("1")
            for signal in relevant
        )
    )
    if not valid:
        evidence.add("source_signal_invalid")
        return relevant, False
    evidence.add("source_signal_valid")
    return relevant, True


class ConfidencePolicy:
    def evaluate_candidates(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        coverage: CoverageReport,
        duplicate_relations: Sequence[DuplicateRelation],
        source_signals: Sequence[CandidateSourceSignal],
    ) -> tuple[dict[str, Any], ...]:
        source_owners: dict[str, set[int]] = {}
        for index, candidate in enumerate(candidates):
            for source_id in set(_source_ids(candidate)):
                source_owners.setdefault(source_id, set()).add(index)
        conflicted_source_ids = {
            source_id
            for source_id, owners in source_owners.items()
            if len(owners) > 1
        }

        evaluated: list[dict[str, Any]] = []
        for candidate in candidates:
            envelope = copy.deepcopy(dict(candidate))
            decision = self._evaluate_candidate(
                candidate,
                coverage=coverage,
                duplicate_relations=duplicate_relations,
                source_signals=source_signals,
                conflicted_source_ids=conflicted_source_ids,
            )
            envelope["confidence_decision"] = decision.to_dict()
            evaluated.append(envelope)
        return tuple(evaluated)

    def _evaluate_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        coverage: CoverageReport,
        duplicate_relations: Sequence[DuplicateRelation],
        source_signals: Sequence[CandidateSourceSignal],
        conflicted_source_ids: set[str],
    ) -> ConfidenceDecision:
        evidence: set[str] = set()
        eligible_for_high = True
        candidate_id = (
            str(candidate.get("candidate_id"))
            if _is_nonblank(candidate.get("candidate_id"))
            else ""
        )
        payload = candidate.get("payload")
        payload_mapping = payload if isinstance(payload, Mapping) else {}
        source_ids = _source_ids(candidate)

        source_shape_valid = (
            bool(source_ids)
            and all(_is_nonblank(source_id) for source_id in source_ids)
            and len(source_ids) == len(set(source_ids))
        )
        if not source_ids or any(not _is_nonblank(item) for item in source_ids):
            evidence.add("source_location_missing")
        elif len(source_ids) != len(set(source_ids)):
            evidence.add("source_owner_conflict")
        else:
            evidence.add("single_source_owner")
        if conflicted_source_ids.intersection(source_ids):
            evidence.discard("single_source_owner")
            evidence.add("source_owner_conflict")
            source_shape_valid = False
        eligible_for_high &= source_shape_valid

        relevant_signals, signals_valid = _candidate_source_signals(
            source_ids,
            source_signals,
            evidence,
        )

        typed_complete = False
        feature_unknown = False
        if _contains_coarse_fallback(payload_mapping):
            evidence.add("coarse_fallback")
        else:
            try:
                Candidate.model_validate(payload_mapping)
            except ValidationError:
                pass
            else:
                semantics_complete, feature_unknown = (
                    _family_semantics_complete(
                        payload_mapping,
                        source_signals=relevant_signals,
                    )
                )
                typed_complete = (
                    semantics_complete
                    and _is_nonblank(payload_mapping.get("raw_text"))
                    and _is_nonblank(payload_mapping.get("normalized_text"))
                    and _valid_coordinates(
                        payload_mapping.get("coordinates")
                    )
                )
        evidence.add(
            "typed_schema_complete"
            if typed_complete
            else "typed_schema_incomplete"
        )
        if feature_unknown:
            evidence.add("feature_kind_unknown")
        eligible_for_high &= typed_complete

        source_truth_preserved = candidate.get(
            "source_truth_preserved",
            True,
        ) is True
        normalized_valid = (
            _is_nonblank(payload_mapping.get("normalized_text"))
            and source_truth_preserved
        )
        if normalized_valid:
            evidence.add("source_truth_preserved")
        else:
            evidence.add("normalized_value_invalid")
        eligible_for_high &= normalized_valid

        linked_entries = _linked_coverage_entries(
            candidate_id,
            source_ids,
            coverage,
        )
        association_complete = (
            bool(source_ids)
            and all(
                sum(
                    entry.source_location_id == source_id
                    and entry.candidate_id == candidate_id
                    and entry.disposition == "candidate"
                    for entry in linked_entries
                )
                == 1
                for source_id in source_ids
            )
        )
        evidence.add(
            "local_association_complete"
            if association_complete
            else "local_association_missing"
        )
        eligible_for_high &= association_complete

        coverage_clear = (
            coverage.coverage_checked and coverage.blocking_count == 0
        )
        if not coverage.coverage_checked:
            evidence.add("coverage_unchecked")
        if coverage.blocking_count:
            evidence.add("coverage_blocking")
        if coverage_clear:
            evidence.add("coverage_clear")
        eligible_for_high &= coverage_clear

        conflict = False
        if any(
            entry.disposition == "ambiguous"
            for entry in linked_entries
        ):
            evidence.add("ambiguous_source")
            conflict = True
        for entry in linked_entries:
            conflict = (
                _review_evidence(entry.advisor_review, evidence)
                or conflict
            )
        conflict = (
            _review_evidence(candidate.get("advisor_review"), evidence)
            or conflict
        )
        duplicate = any(
            candidate_id
            in {relation.left_candidate_id, relation.right_candidate_id}
            for relation in duplicate_relations
        )
        if duplicate:
            evidence.update(
                {"possible_duplicate", "cross_view_conflict"}
            )
            conflict = True
        if not conflict:
            evidence.add("no_conflict")
        eligible_for_high &= not conflict

        requires_confirmation = (
            payload_mapping.get("requires_confirmation") is not False
            or any(entry.requires_confirmation for entry in linked_entries)
        )
        evidence.add(
            "semantic_confirmation_required"
            if requires_confirmation
            else "semantic_confirmation_clear"
        )
        eligible_for_high &= not requires_confirmation

        balloon_known = isinstance(
            payload_mapping.get("balloon_required"),
            bool,
        )
        evidence.add(
            "balloon_requirement_known"
            if balloon_known
            else "balloon_requirement_unknown"
        )
        eligible_for_high &= balloon_known

        if not signals_valid:
            band: Literal["high", "medium", "low"] = "low"
        else:
            minimum = min(
                signal.normalized_value
                for signal in relevant_signals
                if signal.normalized_value is not None
            )
            if minimum >= HIGH_THRESHOLD:
                evidence.add("source_signal_high")
                band = "high"
            elif minimum >= MEDIUM_THRESHOLD:
                evidence.add("source_signal_medium")
                band = "medium"
            else:
                evidence.add("source_signal_low")
                band = "low"
            if not eligible_for_high:
                band = "low"

        review_disposition: Literal[
            "auto_accepted",
            "review_required",
        ] = "auto_accepted" if band == "high" else "review_required"
        return ConfidenceDecision(
            band=band,
            review_disposition=review_disposition,
            policy_version=CONFIDENCE_POLICY_VERSION,
            evidence_codes=_ordered_evidence(evidence),
        )
