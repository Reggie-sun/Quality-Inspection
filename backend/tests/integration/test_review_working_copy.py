from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.candidates.schemas import stable_candidate_id
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.service import FreezeBlocked, ReviewService, manual_review_count
from app.storage.models import StoredFile


def _confidence_decision(
    band: str,
    *,
    evidence_codes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "band": band,
        "review_disposition": (
            "auto_accepted" if band == "high" else "review_required"
        ),
        "policy_version": "candidate-confidence/1",
        "evidence_codes": evidence_codes or [
            "typed_schema_complete",
            "source_truth_preserved",
            "single_source_owner",
            "local_association_complete",
            "coverage_clear",
            "no_conflict",
            "semantic_confirmation_clear",
            "balloon_requirement_known",
            "source_signal_valid",
            f"source_signal_{band}",
        ],
    }


@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def raw_result(db_session: Session) -> AutomaticResult:
    return _make_raw_result(db_session)


def _raw_candidate(
    candidate_id: str = "candidate-1",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "payload": {
            "candidate_id": candidate_id,
            "item_type": "thread",
            "raw_text": "M6",
            "normalized_text": "M6",
            "coordinates": [1, 2, 3, 4],
            "scope": "local_feature",
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": [f"source-{candidate_id}"],
    }


def _make_raw_result(
    db_session: Session,
    *,
    candidates: list[dict[str, object]] | None = None,
    coverage: dict[str, object] | None = None,
    technical_requirements: list[dict[str, object]] | None = None,
    schema_version: str = "automatic-result/1",
) -> AutomaticResult:
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
    result = AutomaticResult(
        id=result_id,
        project_id=project_id,
        source_file_id=source_file_id,
        logical_job_id=job_id,
        inventory_ref=f"asset://tests/{project_id}/inventory.json",
        candidates=candidates if candidates is not None else [_raw_candidate()],
        coverage=coverage if coverage is not None else {
            "blocking_count": 0,
            "review_required_count": 0,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [],
            "relations": [],
        },
        technical_requirements=technical_requirements or [],
        provider_call_ids=[],
        schema_version=schema_version,
    )
    db_session.add_all(
        [
            Project(id=project_id, state=ProjectState.READY_FOR_EDIT),
            StoredFile(
                id=source_file_id,
                resource_ref=f"asset://tests/{project_id}/source.pdf",
                sha256="0" * 64,
                size_bytes=1,
                mime_type="application/pdf",
            ),
            LogicalJob(
                id=job_id,
                project_id=str(project_id),
                logical_task_key=f"review:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    db_session.flush()
    db_session.add(result)
    db_session.commit()
    return result


def _requirement(
    requirement_id: str,
    raw_text: str,
    *,
    subtype: str,
    match_outcome: str,
    matched_candidate_ids: list[str],
    generated_candidate_id: str | None,
    inspection_item: str,
    inspection_standard: str,
) -> dict[str, object]:
    return {
        "requirement_id": requirement_id,
        "ordinal": 1,
        "raw_text": raw_text,
        "normalized_text": raw_text,
        "source_location_ids": [f"source-{requirement_id}"],
        "page_index": 0,
        "coordinates": [[1.0, 2.0, 11.0, 12.0]],
        "category": (
            "standalone_check"
            if subtype == "deburr"
            else "applicability_rule"
        ),
        "subtype": subtype,
        "parsed_parameters": {},
        "match_outcome": match_outcome,
        "matched_candidate_ids": matched_candidate_ids,
        "generated_candidate_id": generated_candidate_id,
        "rule_id": f"technical-requirement:{subtype}",
        "rule_version": "technical-requirement/1",
        "review_required": True,
        "sip_suggestion": {
            "inspection_item": inspection_item,
            "inspection_standard": inspection_standard,
            "key_dimension": None,
            "source_page": 1,
            "remarks": raw_text,
        },
    }


def test_review_bootstrap_projects_requirement_suggestions_without_confirming(
    db_session: Session,
) -> None:
    dimension = _raw_candidate("linear")
    dimension["payload"].update(
        {
            "item_type": "linear_dimension",
            "raw_text": "25",
            "normalized_text": "25",
            "nominal": "25",
        }
    )
    deburr_requirement_id = "requirement-deburr"
    deburr_candidate_id = stable_candidate_id(
        "technical-requirement-candidate",
        deburr_requirement_id,
    )
    deburr_candidate = _raw_candidate(deburr_candidate_id)
    deburr_candidate["payload"].update(
        {
            "item_type": "general_requirement",
            "raw_text": "锐边去毛刺",
            "normalized_text": "锐边去毛刺",
            "scope": "global_requirement",
            "balloon_required": False,
            "requires_confirmation": True,
        }
    )
    dimensional = _requirement(
        "requirement-dimensional",
        "未注尺寸公差按GB/T 1804-m执行",
        subtype="general_dimensional_tolerance",
        match_outcome="matched_items",
        matched_candidate_ids=["linear"],
        generated_candidate_id=None,
        inspection_item="未注尺寸公差",
        inspection_standard="GB/T 1804-m",
    )
    deburr = _requirement(
        deburr_requirement_id,
        "锐边去毛刺",
        subtype="deburr",
        match_outcome="global_scope",
        matched_candidate_ids=[],
        generated_candidate_id=deburr_candidate_id,
        inspection_item="去毛刺与锐边检查",
        inspection_standard="锐边去毛刺",
    )
    raw_result = _make_raw_result(
        db_session,
        candidates=[dimension, deburr_candidate],
        technical_requirements=[dimensional, deburr],
    )

    working = ReviewService(db_session).create_from_raw(raw_result.id)

    assert len(working.technical_requirements) == 2
    items = {item["item_id"]: item for item in working.items}
    deburr_item = items[deburr_candidate_id]
    assert deburr_item["inspection_item"] == "去毛刺与锐边检查"
    assert deburr_item["inspection_standard"] == "锐边去毛刺"
    assert deburr_item["sip_detail_fields_confirmed"] is False
    assert deburr_item["balloon_required"] is False
    dimension_item = items["linear"]
    assert dimension_item["inspection_standard"] == "GB/T 1804-m"
    assert dimension_item.get("upper_tolerance") is None
    assert dimension_item.get("lower_tolerance") is None
    assert dimension_item["sip_detail_fields_confirmed"] is False
    assert dimension_item["sip_suggestion_provenance"][
        "inspection_standard"
    ] == "requirement-dimensional"


def test_original_is_immutable_and_current_is_separate(
    db_session: Session,
    raw_result: AutomaticResult,
) -> None:
    """P0-REV-001: raw candidates and mutable current items are separate layers."""
    original = copy.deepcopy(raw_result.candidates)
    service = ReviewService(db_session)
    working = service.create_from_raw(raw_result.id)
    acquire_lock(db_session, working.project_id, "quality-1")
    service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={"type": "edit", "item_id": "candidate-1", "fields": {"raw_text": "M6 通"}},
    )

    persisted = db_session.get(AutomaticResult, raw_result.id)
    assert persisted is not None
    assert persisted.candidates == original
    assert working.raw_result_id == raw_result.id
    assert working.items is not persisted.candidates


def test_legacy_gdt_reader_projects_typed_unknown_without_inference() -> None:
    item = ReviewService._current_item(
        {
            "candidate_id": "legacy-gdt",
            "payload": {
                "raw_text": "∥ 0.1",
                "coordinates": [1, 2, 3, 4],
                "coarse_type": "geometric_tolerance",
                "requires_confirmation": True,
            },
            "source_location_ids": ["legacy-source"],
        },
        "automatic-result/2",
    )

    assert item["item_type"] == "geometric_tolerance"
    assert item["tolerance_type"] == "unknown"
    assert item["tolerance_symbol"] is None
    assert item["tolerance_value"] is None
    assert item["frames"] == []
    assert item["normalized_text"] == "∥ 0.1"


def test_create_working_copy_moves_ready_project_to_editing(
    db_session: Session,
    raw_result: AutomaticResult,
) -> None:
    working = ReviewService(db_session).create_from_raw(raw_result.id)

    project = db_session.get(Project, raw_result.project_id)
    assert project is not None
    assert project.state == ProjectState.EDITING
    assert working.project_id == project.id


def test_review_bootstrap_defaults_source_only_pending_to_non_inspection(
    db_session: Session,
) -> None:
    raw_coverage = {
        "blocking_count": 0,
        "review_required_count": 2,
        "coverage_checked": True,
        "blocking_observation_ids": [],
        "entries": [
            {
                "observation_id": "source-only",
                "source_location_id": "source-only",
                "candidate_id": None,
                "disposition": "ambiguous",
                "coordinates": [10.0, 20.0, 30.0, 40.0],
                "requires_confirmation": True,
                "disposition_reason": "unclassified_source",
            },
            {
                "observation_id": "candidate-linked",
                "source_location_id": "source-candidate-1",
                "candidate_id": "candidate-1",
                "disposition": "candidate",
                "coordinates": [1.0, 2.0, 3.0, 4.0],
                "requires_confirmation": True,
            },
        ],
        "relations": [],
    }
    raw_result = _make_raw_result(
        db_session,
        coverage=copy.deepcopy(raw_coverage),
    )

    working = ReviewService(db_session).create_from_raw(raw_result.id)

    assert db_session.get(AutomaticResult, raw_result.id).coverage == raw_coverage
    source_only, candidate_linked = working.coverage["entries"]
    assert source_only == {
        **raw_coverage["entries"][0],
        "disposition": "non_inspection",
        "requires_confirmation": False,
        "confirmation_accepted": False,
        "resolution_source": "system_default",
        "resolution_rule_version": "review-source-default/1",
    }
    assert candidate_linked == raw_coverage["entries"][1]
    assert working.coverage["review_required_count"] == 1


def test_review_bootstrap_keeps_unresolved_technical_requirement_pending(
    db_session: Session,
) -> None:
    source_id = "source-technical-unresolved"
    raw_coverage = {
        "blocking_count": 0,
        "review_required_count": 1,
        "coverage_checked": True,
        "blocking_observation_ids": [],
        "entries": [
            {
                "observation_id": source_id,
                "source_location_id": source_id,
                "candidate_id": None,
                "disposition": "ambiguous",
                "coordinates": [10.0, 20.0, 30.0, 40.0],
                "requires_confirmation": True,
                "disposition_reason": "technical_requirement",
                "disposition_rule_version": "technical-requirement/1",
            }
        ],
        "relations": [],
    }
    requirement = _requirement(
        "technical-unresolved",
        "未注公差按 GB/T 1804-m",
        subtype="general_tolerance",
        match_outcome="unresolved",
        matched_candidate_ids=[],
        generated_candidate_id=None,
        inspection_item="未注公差",
        inspection_standard="GB/T 1804-m",
    )
    requirement["source_location_ids"] = [source_id]
    raw_result = _make_raw_result(
        db_session,
        candidates=[],
        coverage=copy.deepcopy(raw_coverage),
        technical_requirements=[requirement],
    )

    working = ReviewService(db_session).create_from_raw(raw_result.id)

    assert working.coverage["entries"] == raw_coverage["entries"]
    assert working.coverage["review_required_count"] == 1
    working.sip_metadata = {
        "material_code": "MAT-001",
        "material_name": "45#",
        "drawing_number": "DWG-001",
        "material": "Steel",
        "revision": "A",
    }
    db_session.commit()
    acquire_lock(db_session, working.project_id, "quality-1")
    with pytest.raises(FreezeBlocked, match="unresolved_confirmation"):
        ReviewService(db_session).freeze_items(
            working.id,
            expected_version=working.version,
            operator_id="quality-1",
        )


def test_v2_bootstrap_routes_only_high_confidence_away_from_manual_review(
    db_session: Session,
) -> None:
    candidates: list[dict[str, object]] = []
    for band in ("high", "medium", "low"):
        candidate_id = f"candidate-{band}"
        candidate = _raw_candidate(candidate_id)
        candidate["confidence_decision"] = _confidence_decision(band)
        candidates.append(candidate)
    raw_result = _make_raw_result(
        db_session,
        candidates=candidates,
        schema_version="automatic-result/2",
    )

    working = ReviewService(db_session).create_from_raw(raw_result.id)
    items = {item["item_id"]: item for item in working.items}

    assert items["candidate-high"] == {
        **items["candidate-high"],
        "status": "auto_accepted",
        "requires_confirmation": False,
        "acceptance_source": "confidence_policy",
        "confidence_decision": _confidence_decision("high"),
    }
    for band in ("medium", "low"):
        assert items[f"candidate-{band}"]["status"] == "pending"
        assert items[f"candidate-{band}"]["requires_confirmation"] is True
        assert items[f"candidate-{band}"]["acceptance_source"] is None
        assert items[f"candidate-{band}"]["confidence_decision"] == (
            _confidence_decision(band)
        )
    assert manual_review_count(working.items, working.coverage) == 2


def test_legacy_bootstrap_ignores_forged_high_confidence_shape(
    db_session: Session,
) -> None:
    candidates = [_raw_candidate()]
    candidates[0]["confidence_decision"] = _confidence_decision("high")
    raw_result = _make_raw_result(db_session, candidates=candidates)

    working = ReviewService(db_session).create_from_raw(raw_result.id)

    assert working.items[0]["status"] == "pending"
    assert working.items[0]["requires_confirmation"] is True
    assert working.items[0]["acceptance_source"] is None
    assert "confidence_decision" not in working.items[0]


@pytest.mark.parametrize(
    ("schema_version", "top_level_decision"),
    [
        ("automatic-result/1", None),
        (
            "automatic-result/2",
            {
                **_confidence_decision("high"),
                "extra": True,
            },
        ),
    ],
    ids=["legacy", "malformed-v2"],
)
@pytest.mark.parametrize(
    "command",
    [
        {"type": "keep", "item_id": "candidate-1"},
        {
            "type": "resolve_confirmation",
            "item_id": "candidate-1",
            "accepted": True,
        },
    ],
    ids=["keep", "accepted-resolve"],
)
def test_payload_forged_high_never_becomes_decision_or_manual_override(
    db_session: Session,
    schema_version: str,
    top_level_decision: object,
    command: dict[str, object],
) -> None:
    candidate = _raw_candidate()
    candidate["payload"]["confidence_decision"] = _confidence_decision("high")
    if top_level_decision is not None:
        candidate["confidence_decision"] = top_level_decision
    raw_result = _make_raw_result(
        db_session,
        candidates=[candidate],
        schema_version=schema_version,
    )
    original = copy.deepcopy(raw_result.candidates)
    service = ReviewService(db_session)
    working = service.create_from_raw(raw_result.id)

    assert working.items[0]["status"] == "pending"
    assert working.items[0]["acceptance_source"] is None
    assert "confidence_decision" not in working.items[0]

    acquire_lock(db_session, working.project_id, "quality-1")
    saved = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command=command,
    )

    assert saved.items[0]["status"] == "kept"
    assert saved.items[0]["requires_confirmation"] is False
    assert saved.items[0]["acceptance_source"] == "manual"
    assert "confidence_decision" not in saved.items[0]
    persisted = db_session.get(AutomaticResult, raw_result.id)
    assert persisted is not None
    assert persisted.candidates == original


@pytest.mark.parametrize(
    "decision",
    [
        None,
        "not-an-object",
        {
            **_confidence_decision("high"),
            "policy_version": "candidate-confidence/999",
        },
        {
            **_confidence_decision("high"),
            "evidence_codes": [
                "typed_schema_complete",
                "typed_schema_complete",
            ],
        },
        {
            **_confidence_decision("high"),
            "evidence_codes": [
                "source_signal_high",
                "typed_schema_complete",
            ],
        },
        {
            **_confidence_decision("high"),
            "evidence_codes": ["unknown"],
        },
        {
            **_confidence_decision("high"),
            "extra": True,
        },
        {
            **_confidence_decision("high"),
            "evidence_codes": "typed_schema_complete",
        },
        {
            **_confidence_decision("high"),
            "band": True,
        },
        {
            **_confidence_decision("high"),
            "review_disposition": "review_required",
        },
    ],
    ids=[
        "missing",
        "malformed",
        "unknown-version",
        "duplicate-evidence",
        "out-of-order-evidence",
        "unknown-evidence",
        "extra-field",
        "wrong-type",
        "wrong-band-type",
        "illegal-pair",
    ],
)
def test_v2_malformed_confidence_decision_fails_closed_without_500(
    db_session: Session,
    decision: object,
) -> None:
    candidates = [_raw_candidate()]
    if decision is not None:
        candidates[0]["confidence_decision"] = decision
    raw_result = _make_raw_result(
        db_session,
        candidates=candidates,
        schema_version="automatic-result/2",
    )

    working = ReviewService(db_session).create_from_raw(raw_result.id)

    assert working.items[0]["status"] == "pending"
    assert working.items[0]["requires_confirmation"] is True
    assert working.items[0]["acceptance_source"] is None
    assert "confidence_decision" not in working.items[0]


def test_manual_review_count_deduplicates_candidate_linked_coverage() -> None:
    items = [
        {
            "item_id": "candidate-review",
            "active": True,
            "requires_confirmation": True,
        },
        {
            "item_id": "candidate-auto",
            "active": True,
            "requires_confirmation": False,
        },
        {
            "item_id": "excluded",
            "active": False,
            "requires_confirmation": True,
        },
    ]
    coverage = {
        "entries": [
            {
                "observation_id": "candidate-linked",
                "candidate_id": "candidate-review",
                "requires_confirmation": True,
            },
            {
                "observation_id": "source-only",
                "candidate_id": None,
                "requires_confirmation": True,
            },
            {
                "observation_id": "source-only",
                "candidate_id": None,
                "requires_confirmation": True,
            },
        ]
    }

    assert manual_review_count(items, coverage) == 2


def test_manual_review_count_skips_malformed_historical_values() -> None:
    assert manual_review_count(
        [
            None,
            "malformed",
            {
                "item_id": "review",
                "active": True,
                "requires_confirmation": True,
            },
        ],
        None,
    ) == 1
    assert manual_review_count([], {"entries": [None, "malformed"]}) == 0


def test_visual_coverage_exposes_only_owner_committed_discriminator() -> None:
    diagnostics = (
        {
            "route": "visual_symbol",
            "schema_version": "visual-symbol-review/1",
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
        },
        {
            "route": "visual_symbol",
            "schema_version": "visual-symbol-review/3",
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
            "confidence_signal": None,
        },
    )
    for diagnostic in diagnostics:
        projected = ReviewService._review_coverage({
            "blocking_count": 0,
            "review_required_count": 1,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [
                {
                    "observation_id": "visual-source",
                    "disposition": "ambiguous",
                    "source_location_id": "visual-source",
                    "coordinates": [1, 2, 3, 4],
                    "candidate_id": None,
                    "requires_confirmation": True,
                    "advisor_review": diagnostic,
                }
            ],
        })

        assert projected["entries"] == [
            {
                "observation_id": "visual-source",
                "disposition": "non_inspection",
                "source_location_id": "visual-source",
                "coordinates": [1, 2, 3, 4],
                "candidate_id": None,
                "requires_confirmation": False,
                "symbol_kinds": [],
                "rejection_code": "visual_no_detection",
                "confirmation_accepted": False,
                "resolution_source": "system_default",
                "resolution_rule_version": "review-source-default/1",
            }
        ]
        assert projected["review_required_count"] == 0
