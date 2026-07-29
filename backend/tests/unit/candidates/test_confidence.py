from __future__ import annotations

import copy
import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from app.candidates.confidence import (
    CONFIDENCE_EVIDENCE_CODE_ORDER,
    ConfidenceDecision,
    ConfidencePolicy,
    CandidateSourceSignal,
    confidence_decision_digest,
    normalize_native_signal,
    normalize_tencent_ocr_signal,
    normalize_visual_signal,
    validate_confidence_decision,
)
from app.candidates.coverage import CoverageEntry, CoverageReport
from app.candidates.duplicates import DuplicateRelation


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT
    / "tests/fixtures/confidence/candidate-confidence-v1.json"
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "candidate-1",
        "item_type": "linear_dimension",
        "raw_text": "10",
        "normalized_text": "10",
        "coordinates": [1, 2, 11, 12],
        "scope": "local_feature",
        "nominal": "10",
        "sub_requirements": [],
        "balloon_required": True,
        "requires_confirmation": False,
    }
    payload.update(overrides)
    return payload


def _candidate(**payload_overrides: object) -> dict[str, object]:
    return {
        "candidate_id": "candidate-1",
        "payload": _payload(**payload_overrides),
        "source_location_ids": ["source-1"],
    }


def _signal(
    value: Decimal | None = Decimal("1"),
    *,
    source_location_id: str = "source-1",
    source_type: str = "native",
) -> CandidateSourceSignal:
    return CandidateSourceSignal(
        source_location_id=source_location_id,
        source_type=source_type,  # type: ignore[arg-type]
        normalized_value=value,
    )


def _coverage(
    candidate: dict[str, object],
    *,
    coverage_checked: bool = True,
    blocking_count: int = 0,
    disposition: str = "candidate",
    requires_confirmation: bool = False,
    advisor_review: dict[str, object] | None = None,
    associated: bool = True,
) -> CoverageReport:
    candidate_id = str(candidate["candidate_id"])
    source_ids = [str(item) for item in candidate["source_location_ids"]]  # type: ignore[union-attr]
    entries = tuple(
        CoverageEntry(
            observation_id=source_id,
            disposition=disposition,
            source_location_id=source_id,
            coordinates=(1, 2, 11, 12),
            candidate_id=candidate_id if associated else "other-candidate",
            requires_confirmation=requires_confirmation,
            advisor_review=advisor_review,
        )
        for source_id in source_ids
    )
    return CoverageReport(
        blocking_count=blocking_count,
        review_required_count=sum(
            entry.disposition == "ambiguous" or entry.requires_confirmation
            for entry in entries
        ),
        coverage_checked=coverage_checked,
        entries=entries,
        blocking_observation_ids=(
            ("blocking-source",) if blocking_count else ()
        ),
    )


def _evaluate(
    candidate: dict[str, object] | None = None,
    *,
    coverage: CoverageReport | None = None,
    duplicate_relations: tuple[DuplicateRelation, ...] = (),
    signals: tuple[CandidateSourceSignal, ...] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    envelope = candidate or _candidate()
    frozen = copy.deepcopy(envelope)
    evaluated = ConfidencePolicy().evaluate_candidates(
        (envelope,),
        coverage=coverage or _coverage(envelope),
        duplicate_relations=duplicate_relations,
        source_signals=(_signal(),) if signals is None else signals,
    )
    assert envelope == frozen
    assert evaluated[0] is not envelope
    return evaluated[0], evaluated[0]["confidence_decision"]  # type: ignore[return-value]


def test_native_exact_signal_is_deterministic() -> None:
    assert normalize_native_signal(True) == Decimal("1")
    assert normalize_native_signal(False) == Decimal("0")


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (0, Decimal("0")),
        (70, Decimal("0.70")),
        (95, Decimal("0.95")),
        (100, Decimal("1")),
    ],
)
def test_tencent_ocr_percent_is_normalized_only_by_dividing_by_100(
    percent: object,
    expected: Decimal,
) -> None:
    assert normalize_tencent_ocr_signal(percent) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, Decimal("0")),
        (0.70, Decimal("0.70")),
        (0.95, Decimal("0.95")),
        (1, Decimal("1")),
    ],
)
def test_visual_unit_interval_is_preserved(
    value: object,
    expected: Decimal,
) -> None:
    assert normalize_visual_signal(value) == expected


@pytest.mark.parametrize("adapter", [normalize_tencent_ocr_signal, normalize_visual_signal])
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        math.nan,
        math.inf,
        -math.inf,
        -1,
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_numeric_adapters_reject_missing_bool_nonfinite_and_negative(
    adapter,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        adapter(value)


@pytest.mark.parametrize(
    ("adapter", "value"),
    [
        (normalize_tencent_ocr_signal, 100.0001),
        (normalize_visual_signal, 1.0001),
    ],
)
def test_numeric_adapters_reject_out_of_range(adapter, value: object) -> None:
    with pytest.raises(ValueError):
        adapter(value)


@pytest.mark.parametrize("value", [None, 1, 0, "true"])
def test_native_adapter_rejects_non_bool_and_missing(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_native_signal(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected_band"),
    [
        (Decimal("0.699999999"), "low"),
        (Decimal("0.70"), "medium"),
        (Decimal("0.700000001"), "medium"),
        (Decimal("0.949999999"), "medium"),
        (Decimal("0.95"), "high"),
        (Decimal("0.950000001"), "high"),
    ],
)
def test_exact_threshold_boundaries(
    value: Decimal,
    expected_band: str,
) -> None:
    _, decision = _evaluate(signals=(_signal(value),))
    assert decision["band"] == expected_band


def test_multi_source_uses_minimum_signal() -> None:
    candidate = _candidate()
    candidate["source_location_ids"] = ["source-1", "source-2"]
    _, decision = _evaluate(
        candidate,
        signals=(
            _signal(Decimal("0.99")),
            _signal(
                Decimal("0.70"),
                source_location_id="source-2",
                source_type="visual",
            ),
        ),
    )
    assert decision["band"] == "medium"
    assert "source_signal_medium" in decision["evidence_codes"]


@pytest.mark.parametrize(
    "signals",
    [
        (),
        (_signal(None),),
        (_signal(Decimal("-0.01")),),
        (_signal(Decimal("1.01")),),
        (_signal(Decimal("NaN")),),
    ],
)
def test_missing_or_invalid_source_signal_forces_low(
    signals: tuple[CandidateSourceSignal, ...],
) -> None:
    _, decision = _evaluate(signals=signals)
    assert decision["band"] == "low"
    assert decision["review_disposition"] == "review_required"


def _candidate_veto_cases() -> list[
    tuple[str, dict[str, object], str]
]:
    return [
        ("blank_raw_text", _candidate(raw_text=" "), "typed_schema_incomplete"),
        (
            "blank_normalized_text",
            _candidate(normalized_text=" "),
            "normalized_value_invalid",
        ),
        (
            "invalid_bbox",
            _candidate(coordinates=[1, 2, float("nan"), 12]),
            "typed_schema_incomplete",
        ),
        (
            "semantic_confirmation",
            _candidate(requires_confirmation=True),
            "semantic_confirmation_required",
        ),
        (
            "balloon_requirement_unknown",
            _candidate(balloon_required=None),
            "balloon_requirement_unknown",
        ),
        (
            "coarse_fallback",
            {
                "candidate_id": "candidate-1",
                "payload": {
                    "raw_text": "Ra 3.2",
                    "coordinates": [1, 2, 11, 12],
                    "coarse_type": "roughness",
                    "requires_confirmation": True,
                },
                "source_location_ids": ["source-1"],
            },
            "coarse_fallback",
        ),
        (
            "source_truth_overwrite",
            {
                **_candidate(),
                "source_truth_preserved": False,
            },
            "normalized_value_invalid",
        ),
        (
            "local_projection_failed",
            {
                **_candidate(),
                "advisor_review": {
                    "validated": False,
                    "rejection_code": "local_parse_failed",
                },
            },
            "local_projection_failed",
        ),
        (
            "provider_schema_rejected",
            {
                **_candidate(),
                "advisor_review": {
                    "validated": False,
                    "rejection_code": "type_mismatch",
                },
            },
            "provider_schema_rejected",
        ),
        (
            "source_location_missing",
            {
                **_candidate(),
                "source_location_ids": [],
            },
            "source_location_missing",
        ),
    ]


@pytest.mark.parametrize(
    ("name", "candidate", "expected_evidence"),
    _candidate_veto_cases(),
    ids=[case[0] for case in _candidate_veto_cases()],
)
def test_every_candidate_hard_veto_prevents_high(
    name: str,
    candidate: dict[str, object],
    expected_evidence: str,
) -> None:
    del name
    _, decision = _evaluate(candidate)
    assert decision["band"] != "high"
    assert expected_evidence in decision["evidence_codes"]


@pytest.mark.parametrize(
    ("coverage_kwargs", "expected_evidence"),
    [
        ({"coverage_checked": False}, "coverage_unchecked"),
        ({"blocking_count": 1}, "coverage_blocking"),
        ({"disposition": "ambiguous"}, "ambiguous_source"),
        ({"associated": False}, "local_association_missing"),
        (
            {
                "advisor_review": {
                    "route": "visual_symbol",
                    "schema_version": "visual-symbol-review/1",
                    "symbol_kinds": ["diameter"],
                    "rejection_code": "visual_projection_conflict",
                }
            },
            "projection_conflict",
        ),
    ],
)
def test_every_coverage_hard_veto_prevents_high(
    coverage_kwargs: dict[str, object],
    expected_evidence: str,
) -> None:
    candidate = _candidate()
    _, decision = _evaluate(
        candidate,
        coverage=_coverage(candidate, **coverage_kwargs),  # type: ignore[arg-type]
    )
    assert decision["band"] != "high"
    assert expected_evidence in decision["evidence_codes"]


def test_duplicate_relation_prevents_high() -> None:
    _, decision = _evaluate(
        duplicate_relations=(
            DuplicateRelation(
                left_candidate_id="candidate-1",
                right_candidate_id="candidate-2",
            ),
        )
    )
    assert decision["band"] == "medium"
    assert "possible_duplicate" in decision["evidence_codes"]
    assert "cross_view_conflict" in decision["evidence_codes"]


def test_duplicate_source_owner_prevents_high() -> None:
    candidate = _candidate()
    candidate["source_location_ids"] = ["source-1", "source-1"]
    _, decision = _evaluate(candidate)
    assert decision["band"] != "high"
    assert "source_owner_conflict" in decision["evidence_codes"]


def test_low_is_always_review_required_and_never_auto_excluded() -> None:
    evaluated, decision = _evaluate(signals=(_signal(Decimal("0")),))
    assert decision["band"] == "low"
    assert decision["review_disposition"] == "review_required"
    assert "auto_excluded" not in json.dumps(evaluated, sort_keys=True)


def test_decision_serialization_digest_and_evidence_order_are_deterministic() -> None:
    _, raw = _evaluate(signals=(_signal(Decimal("0.95")),))
    decision = validate_confidence_decision(raw)
    assert isinstance(decision, ConfidenceDecision)
    assert decision.to_dict() == raw
    assert list(decision.evidence_codes) == sorted(
        decision.evidence_codes,
        key=CONFIDENCE_EVIDENCE_CODE_ORDER.index,
    )
    assert confidence_decision_digest(decision) == (
        "ea0a32832c7148cfea3759fe2dc3baf47ae9a0404aa5cd3ca2ac0777c482c22a"
    )
    serialized = json.dumps(
        decision.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert serialized == json.dumps(
        validate_confidence_decision(raw).to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert serialized == (
        '{"band":"high","evidence_codes":["typed_schema_complete",'
        '"source_truth_preserved","single_source_owner",'
        '"local_association_complete","coverage_clear","no_conflict",'
        '"semantic_confirmation_clear","balloon_requirement_known",'
        '"source_signal_valid","source_signal_high"],'
        '"policy_version":"candidate-confidence/1",'
        '"review_disposition":"auto_accepted"}'
    )


def _fixture_coverage(
    candidate: dict[str, object],
    coverage_facts: dict[str, object],
) -> CoverageReport:
    return _coverage(
        candidate,
        coverage_checked=bool(coverage_facts["coverage_checked"]),
        blocking_count=int(coverage_facts["blocking_count"]),
        associated=bool(coverage_facts["local_association_complete"]),
    )


@pytest.mark.parametrize(
    "case",
    json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"],
    ids=lambda case: case["id"],
)
def test_frozen_release_gate_fixture(case: dict[str, object]) -> None:
    candidate = case["candidate"]
    raw_signals = case["source_signals"]
    signals = tuple(
        CandidateSourceSignal(
            source_location_id=str(signal["source_location_id"]),
            source_type=str(signal["source_type"]),  # type: ignore[arg-type]
            normalized_value=Decimal(str(signal["normalized_value"])),
        )
        for signal in raw_signals  # type: ignore[union-attr]
    )
    evaluated = ConfidencePolicy().evaluate_candidates(
        (candidate,),  # type: ignore[arg-type]
        coverage=_fixture_coverage(
            candidate,  # type: ignore[arg-type]
            case["coverage"],  # type: ignore[arg-type]
        ),
        duplicate_relations=(),
        source_signals=signals,
    )
    assert evaluated[0]["confidence_decision"] == case["expected"]
