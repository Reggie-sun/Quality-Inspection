from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.candidates.schemas import stable_candidate_id
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewNotFound, ReviewService, manual_review_count
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


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
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result = AutomaticResult(
        id=uuid.uuid4(),
        project_id=project_id,
        source_file_id=source_file_id,
        logical_job_id=job_id,
        inventory_ref=f"asset://tests/{project_id}/inventory.json",
        candidates=[
            {
                "candidate_id": "i1",
                "payload": {
                    "candidate_id": "i1",
                    "item_type": "thread",
                    "raw_text": "M6",
                    "normalized_text": "M6",
                    "coordinates": [1, 2, 3, 4],
                    "scope": "local_feature",
                    "quantity": 2,
                    "thread_spec": "M6",
                    "balloon_required": True,
                    "requires_confirmation": False,
                },
                "source_location_ids": ["s1"],
            },
            {
                "candidate_id": "i2",
                "payload": {
                    "candidate_id": "i2",
                    "item_type": "thread",
                    "raw_text": "M6 通",
                    "normalized_text": "M6 通",
                    "coordinates": [5, 6, 7, 8],
                    "scope": "local_feature",
                    "quantity": 3,
                    "thread_spec": "M6",
                    "through": True,
                    "balloon_required": True,
                    "requires_confirmation": False,
                },
                "source_location_ids": ["s2", "s1"],
            },
            {
                "candidate_id": "typed-1",
                "payload": {
                    "candidate_id": "typed-1",
                    "item_type": "linear_dimension",
                    "raw_text": "10",
                    "normalized_text": "10",
                    "coordinates": [9, 10, 11, 12],
                    "scope": "local_feature",
                    "nominal": "10",
                    "balloon_required": True,
                    "requires_confirmation": False,
                },
                "source_location_ids": ["s-typed"],
            },
            {
                "candidate_id": "composite-1",
                "payload": {
                    "candidate_id": "composite-1",
                    "item_type": "composite",
                    "raw_text": "Φ10\n深20",
                    "normalized_text": "Φ10 深20",
                    "coordinates": [13, 14, 15, 16],
                    "scope": "local_feature",
                    "balloon_required": True,
                    "requires_confirmation": False,
                },
                "source_location_ids": ["s-composite"],
            },
            {
                "candidate_id": "complex-1",
                "payload": {
                    "raw_text": "Ra 3.2",
                    "coordinates": [17, 18, 19, 20],
                    "coarse_type": "roughness",
                    "requires_confirmation": True,
                },
                "source_location_ids": ["s-complex"],
            },
        ],
        coverage={
            "blocking_count": 0,
            "review_required_count": 1,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [
                {
                    "observation_id": "s-complex",
                    "disposition": "candidate",
                    "source_location_id": "s-complex",
                    "coordinates": [17, 18, 19, 20],
                    "candidate_id": "complex-1",
                    "requires_confirmation": True,
                }
            ],
            "relations": [],
        },
        provider_call_ids=[],
        schema_version="automatic-result/1",
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
                result_ref=f"automatic-result://{result.id}",
            ),
        ]
    )
    db_session.flush()
    db_session.add(result)
    db_session.commit()
    return result


@pytest.fixture
def review_service(db_session: Session) -> ReviewService:
    return ReviewService(db_session)


@pytest.fixture
def working_copy(
    review_service: ReviewService,
    raw_result: AutomaticResult,
) -> ReviewWorkingCopy:
    working = review_service.create_from_raw(raw_result.id)
    acquire_lock(review_service.session, working.project_id, "quality-1")
    return working


def _item(working: ReviewWorkingCopy, item_id: str) -> dict[str, object]:
    return next(item for item in working.items if item["item_id"] == item_id)


def _confidence_decision(band: str) -> dict[str, object]:
    return {
        "band": band,
        "review_disposition": (
            "auto_accepted" if band == "high" else "review_required"
        ),
        "policy_version": "candidate-confidence/1",
        "evidence_codes": [
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


def _set_confidence_state(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    item_id: str,
    band: str,
) -> dict[str, object]:
    items = copy.deepcopy(working_copy.items)
    item = next(value for value in items if value["item_id"] == item_id)
    decision = _confidence_decision(band)
    item["confidence_decision"] = decision
    item["status"] = "auto_accepted" if band == "high" else "pending"
    item["requires_confirmation"] = band != "high"
    item["acceptance_source"] = (
        "confidence_policy" if band == "high" else None
    )
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    return decision


def _set_linked_review_state(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    item_ids: list[str],
) -> None:
    target_ids = set(item_ids)
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] in target_ids
        if item["item_id"] in target_ids:
            item["status"] = "pending"
            item["requires_confirmation"] = True
            item["acceptance_source"] = None
    working_copy.items = items
    working_copy.coverage = {
        "blocking_count": 0,
        "review_required_count": len(item_ids),
        "coverage_checked": True,
        "blocking_observation_ids": [],
        "entries": [
            {
                "observation_id": f"coverage-{item_id}",
                "disposition": "candidate",
                "source_location_id": f"source-{item_id}",
                "coordinates": [1, 2, 3, 4],
                "candidate_id": item_id,
                "requires_confirmation": True,
            }
            for item_id in item_ids
        ],
        "relations": [],
    }
    db_session.commit()
    db_session.refresh(working_copy)


def _set_technical_requirement_state(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    *,
    confirmed: bool = False,
) -> None:
    requirement_id = "requirement-1"
    items = copy.deepcopy(working_copy.items)
    item = next(value for value in items if value["item_id"] == "i1")
    item["technical_requirement_refs"] = [requirement_id]
    item["inspection_standard"] = (
        "MANUAL-CONFIRMED" if confirmed else "GB/T 1804-m"
    )
    item["sip_detail_fields_confirmed"] = confirmed
    item["sip_suggestion_provenance"] = {
        "inspection_standard": requirement_id
    }
    working_copy.items = items
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"].append(
        {
            "observation_id": "requirement-source",
            "disposition": "reference_context",
            "source_location_id": "requirement-source",
            "coordinates": [1, 2, 3, 4],
            "candidate_id": None,
            "requires_confirmation": True,
        }
    )
    coverage["review_required_count"] += 1
    working_copy.coverage = coverage
    working_copy.technical_requirements = [
        {
            "requirement_id": requirement_id,
            "ordinal": 5,
            "raw_text": "未注尺寸公差按GB/T 1804-m执行",
            "normalized_text": "未注尺寸公差按GB/T 1804-m执行",
            "source_location_ids": ["requirement-source"],
            "page_index": 0,
            "coordinates": [[1, 2, 3, 4]],
            "category": "applicability_rule",
            "subtype": "general_dimensional_tolerance",
            "parsed_parameters": {
                "standard_code": "GB/T 1804",
                "tolerance_class": "m",
            },
            "match_outcome": "matched_items",
            "matched_candidate_ids": ["i1"],
            "generated_candidate_id": None,
            "rule_id": "technical-requirement:general_dimensional_tolerance",
            "rule_version": "technical-requirement/1",
            "review_required": True,
            "review_status": "suggested",
            "sip_suggestion": {
                "inspection_item": "未注尺寸公差",
                "inspection_standard": "GB/T 1804-m",
                "key_dimension": None,
                "source_page": 1,
                "remarks": "未注尺寸公差按GB/T 1804-m执行",
            },
        }
    ]
    db_session.commit()
    db_session.refresh(working_copy)


def test_requirement_match_override_relinks_suggestions_transactionally(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    before_version = working_copy.version

    saved = review_service.apply(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": "requirement-1",
            "outcome": "matched_items",
            "matched_item_ids": ["typed-1"],
        },
    )

    old_target = _item(saved, "i1")
    new_target = _item(saved, "typed-1")
    assert "inspection_standard" not in old_target
    assert old_target["technical_requirement_refs"] == []
    assert new_target["inspection_standard"] == "GB/T 1804-m"
    assert new_target["sip_detail_fields_confirmed"] is False
    assert new_target["sip_suggestion_provenance"][
        "inspection_standard"
    ] == "requirement-1"
    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "matched_items"
    assert requirement["matched_candidate_ids"] == ["typed-1"]
    assert requirement["review_status"] == "confirmed"
    assert saved.version == before_version + 1
    record = db_session.scalar(
        select(OperationRecord).where(
            OperationRecord.project_id == saved.project_id
        )
    )
    assert record is not None
    assert record.command == "set_technical_requirement_match"


def test_requirement_global_and_excluded_preserve_confirmed_values(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(
        working_copy,
        db_session,
        confirmed=True,
    )

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": "requirement-1",
            "outcome": "global_scope",
        },
    )

    assert _item(saved, "i1")["inspection_standard"] == "MANUAL-CONFIRMED"
    global_id = stable_candidate_id(
        "technical-requirement-candidate",
        "requirement-1",
    )
    global_item = _item(saved, global_id)
    assert global_item["active"] is True
    assert global_item["balloon_required"] is False
    assert saved.technical_requirements[0]["generated_candidate_id"] == global_id

    excluded = review_service.apply(
        saved.id,
        expected_version=saved.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": "requirement-1",
            "outcome": "excluded",
        },
    )
    assert _item(excluded, "i1")["inspection_standard"] == "MANUAL-CONFIRMED"
    assert next(
        item for item in excluded.items if item["item_id"] == global_id
    )["active"] is False
    assert excluded.technical_requirements[0]["review_status"] == "excluded"


def _confirm_requirement_target(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    *,
    requirement_id: str = "requirement-1",
    item_ids: list[str] | None = None,
) -> ReviewWorkingCopy:
    return review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": requirement_id,
            "outcome": "matched_items",
            "matched_item_ids": item_ids or ["i1"],
        },
    )


def _confirm_global_requirement(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    *,
    requirement_id: str = "requirement-1",
) -> tuple[ReviewWorkingCopy, str]:
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": requirement_id,
            "outcome": "global_scope",
        },
    )
    generated_id = str(
        saved.technical_requirements[0]["generated_candidate_id"]
    )
    return saved, generated_id


def _add_shared_requirement(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    requirements = copy.deepcopy(working_copy.technical_requirements)
    shared = copy.deepcopy(requirements[0])
    shared["requirement_id"] = "requirement-2"
    shared["raw_text"] = "共享 observation 的第二条技术要求"
    shared["normalized_text"] = shared["raw_text"]
    requirements.append(shared)
    working_copy.technical_requirements = requirements
    db_session.commit()
    db_session.refresh(working_copy)


def _assert_requirement_reopened(saved: ReviewWorkingCopy) -> None:
    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "unresolved"
    assert requirement["matched_candidate_ids"] == []
    assert requirement["generated_candidate_id"] is None
    assert requirement["review_required"] is True
    assert requirement["review_status"] == "suggested"
    requirement_coverage = next(
        entry
        for entry in saved.coverage["entries"]
        if entry["observation_id"] == "requirement-source"
    )
    assert requirement_coverage["requires_confirmation"] is True
    assert "confirmation_accepted" not in requirement_coverage


def test_excluding_only_requirement_target_reopens_requirement_review(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """Retiring the last active target must not silently lose its requirement."""
    _set_technical_requirement_state(working_copy, db_session)
    confirmed = _confirm_requirement_target(review_service, working_copy)

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={"type": "exclude", "item_id": "i1"},
    )

    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "unresolved"
    assert requirement["matched_candidate_ids"] == []
    assert requirement["review_required"] is True
    assert requirement["review_status"] == "suggested"
    requirement_coverage = next(
        entry
        for entry in saved.coverage["entries"]
        if entry["observation_id"] == "requirement-source"
    )
    assert requirement_coverage["requires_confirmation"] is True
    assert "confirmation_accepted" not in requirement_coverage
    assert _item(saved, "i1")["technical_requirement_refs"] == []


def test_retiring_one_of_multiple_requirement_targets_preserves_the_other(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed = _confirm_requirement_target(
        review_service,
        working_copy,
        item_ids=["i1", "typed-1"],
    )

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={"type": "exclude", "item_id": "i1"},
    )

    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "matched_items"
    assert requirement["matched_candidate_ids"] == ["typed-1"]
    assert _item(saved, "typed-1")["technical_requirement_refs"] == [
        "requirement-1"
    ]
    assert _item(saved, "i1")["technical_requirement_refs"] == []


@pytest.mark.parametrize(
    "command",
    [
        {"type": "exclude"},
        {"type": "resolve_confirmation", "accepted": False},
    ],
)
def test_retiring_global_requirement_target_reopens_requirement_review(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    command: dict[str, object],
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={**command, "item_id": generated_id},
    )

    _assert_requirement_reopened(saved)
    assert _item(saved, generated_id)["technical_requirement_refs"] == []


def test_merging_global_requirement_target_relinks_singular_generated_item(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )
    with_peer = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "add",
            "item_type": "general_requirement",
            "raw_text": "另一项全局要求",
            "coordinates": [9, 10, 11, 12],
            "scope": "global_requirement",
            "balloon_required": False,
        },
    )
    peer_id = str(with_peer.items[-1]["item_id"])

    saved = review_service.apply(
        with_peer.id,
        expected_version=with_peer.version,
        operator_id="quality-1",
        command={
            "type": "merge",
            "item_ids": [generated_id, peer_id],
            "raw_text": "合并后的全局要求",
        },
    )

    merged = saved.items[-1]
    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "global_scope"
    assert requirement["generated_candidate_id"] == merged["item_id"]
    assert requirement["matched_candidate_ids"] == []
    assert merged["technical_requirement_refs"] == ["requirement-1"]
    assert merged["balloon_required"] is False


@pytest.mark.parametrize("global_first", [True, False])
def test_global_requirement_merge_rejects_local_balloon_peer_in_any_order(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    global_first: bool,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )
    with_peer = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "add",
            "item_type": "general_requirement",
            "raw_text": "需要气泡的局部要求",
            "coordinates": [9, 10, 11, 12],
            "scope": "local_feature",
            "balloon_required": True,
        },
    )
    peer_id = str(with_peer.items[-1]["item_id"])
    item_ids = (
        [generated_id, peer_id]
        if global_first
        else [peer_id, generated_id]
    )

    with pytest.raises(
        ValueError,
        match="global requirement merge requires global unnumbered items",
    ):
        review_service.apply(
            with_peer.id,
            expected_version=with_peer.version,
            operator_id="quality-1",
            command={
                "type": "merge",
                "item_ids": item_ids,
                "raw_text": "非法的局部与全局合并",
            },
        )


@pytest.mark.parametrize(
    "command",
    [
        {"type": "set_balloon_required", "balloon_required": True},
        {"type": "edit", "fields": {"scope": "local_feature"}},
    ],
)
def test_global_requirement_relation_rejects_non_global_or_balloon_commands(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    command: dict[str, object],
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )

    with pytest.raises(
        ValueError,
        match="global requirement target must remain global and unnumbered",
    ):
        review_service.apply(
            confirmed.id,
            expected_version=confirmed.version,
            operator_id="quality-1",
            command={**command, "item_id": generated_id},
        )

    db_session.expire_all()
    unchanged = db_session.get(ReviewWorkingCopy, confirmed.id)
    assert unchanged is not None
    global_item = _item(unchanged, generated_id)
    assert global_item["scope"] == "global_requirement"
    assert global_item["balloon_required"] is False
    assert unchanged.version == confirmed.version


def test_manual_global_requirement_cannot_be_added_with_balloon(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    with pytest.raises(
        ValueError,
        match="global requirement target must remain global and unnumbered",
    ):
        review_service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
            command={
                "type": "add",
                "item_type": "general_requirement",
                "raw_text": "手工全局要求",
                "coordinates": [9, 10, 11, 12],
                "scope": "global_requirement",
                "balloon_required": True,
            },
        )


def test_splitting_global_requirement_target_reopens_singular_relation(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    confirmed, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "split",
            "item_id": generated_id,
            "parts": [
                {"raw_text": "全局要求第一部分"},
                {"raw_text": "全局要求第二部分"},
            ],
        },
    )

    _assert_requirement_reopened(saved)
    assert all(
        item.get("technical_requirement_refs") == []
        for item in saved.items[-2:]
    )


def test_shared_requirement_source_stays_blocked_until_every_relation_resolves(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    _add_shared_requirement(working_copy, db_session)
    first, generated_id = _confirm_global_requirement(
        review_service,
        working_copy,
    )
    both_confirmed = _confirm_requirement_target(
        review_service,
        first,
        requirement_id="requirement-2",
    )
    first_reopened = review_service.apply(
        both_confirmed.id,
        expected_version=both_confirmed.version,
        operator_id="quality-1",
        command={"type": "exclude", "item_id": generated_id},
    )

    saved = _confirm_requirement_target(
        review_service,
        first_reopened,
        requirement_id="requirement-2",
    )

    unresolved = next(
        requirement
        for requirement in saved.technical_requirements
        if requirement["requirement_id"] == "requirement-1"
    )
    assert unresolved["review_required"] is True
    requirement_coverage = next(
        entry
        for entry in saved.coverage["entries"]
        if entry["observation_id"] == "requirement-source"
    )
    assert requirement_coverage["requires_confirmation"] is True
    assert "confirmation_accepted" not in requirement_coverage
    assert "unresolved_confirmation" in _freeze_blockers_with_completed_sip(
        saved
    )

    all_resolved, _ = _confirm_global_requirement(
        review_service,
        saved,
    )
    resolved_coverage = next(
        entry
        for entry in all_resolved.coverage["entries"]
        if entry["observation_id"] == "requirement-source"
    )
    assert resolved_coverage["requires_confirmation"] is False
    assert resolved_coverage["confirmation_accepted"] is True


def test_rejecting_requirement_target_reopens_requirement_review(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """Confirmation rejection retires an item through the same relation boundary."""
    _set_technical_requirement_state(working_copy, db_session)
    confirmed = _confirm_requirement_target(review_service, working_copy)

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "resolve_confirmation",
            "item_id": "i1",
            "accepted": False,
        },
    )

    requirement = saved.technical_requirements[0]
    assert requirement["match_outcome"] == "unresolved"
    assert requirement["matched_candidate_ids"] == []
    assert requirement["review_required"] is True


def test_merging_requirement_target_relinks_to_active_merged_item(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """Replacing a target by merge must rewrite the persisted relation."""
    _set_technical_requirement_state(working_copy, db_session)
    confirmed = _confirm_requirement_target(review_service, working_copy)

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "merge",
            "item_ids": ["i1", "i2"],
            "raw_text": "M6 merged",
        },
    )

    merged = saved.items[-1]
    requirement = saved.technical_requirements[0]
    assert requirement["matched_candidate_ids"] == [merged["item_id"]]
    assert merged["technical_requirement_refs"] == ["requirement-1"]
    assert merged["inspection_standard"] == "GB/T 1804-m"
    assert _item(saved, "i1")["technical_requirement_refs"] == []


def test_splitting_requirement_target_relinks_to_every_active_part(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """Replacing a target by split must preserve the requirement on each part."""
    _set_technical_requirement_state(working_copy, db_session)
    confirmed = _confirm_requirement_target(review_service, working_copy)

    saved = review_service.apply(
        confirmed.id,
        expected_version=confirmed.version,
        operator_id="quality-1",
        command={
            "type": "split",
            "item_id": "i1",
            "parts": [{"raw_text": "M6 first"}, {"raw_text": "M6 second"}],
        },
    )

    split_items = saved.items[-2:]
    split_ids = sorted(str(item["item_id"]) for item in split_items)
    requirement = saved.technical_requirements[0]
    assert requirement["matched_candidate_ids"] == split_ids
    assert all(
        item["technical_requirement_refs"] == ["requirement-1"]
        and item["inspection_standard"] == "GB/T 1804-m"
        for item in split_items
    )
    assert _item(saved, "i1")["technical_requirement_refs"] == []


def _freeze_blockers_with_completed_sip(
    working_copy: ReviewWorkingCopy,
) -> list[str]:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        if not item.get("active", True):
            continue
        item.update(
            {
                "inspection_item": "confirmed item",
                "inspection_standard": "confirmed standard",
                "inspection_method": "confirmed method",
                "key_dimension": "yes",
                "inspection_role": "IPQC",
                "source_page": 1,
                "sip_detail_fields_confirmed": True,
            }
        )
    return ReviewService.freeze_blockers(
        items,
        working_copy.coverage,
        {
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "DRAWING-001",
            "material": "steel",
            "revision": "A",
        },
    )


def _set_source_only_coverage(
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "disposition": "ambiguous",
            "source_location_id": "source-location",
            "coordinates": [21, 22, 23, 24],
            "candidate_id": None,
            "requires_confirmation": True,
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
        }
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()


def test_source_relations_round_trip(working_copy: ReviewWorkingCopy) -> None:
    """P0-REV-003: current items keep every basic source relation."""
    assert _item(working_copy, "i1")["source_location_ids"] == ["s1"]
    assert _item(working_copy, "i2")["source_location_ids"] == ["s2", "s1"]


def test_keep_candidate(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-004: keep is an explicit versioned review command."""
    before_version = working_copy.version
    saved = review_service.apply(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )

    assert _item(saved, "i1")["status"] == "kept"
    assert _item(saved, "i1")["active"] is True
    assert _item(saved, "i1")["requires_confirmation"] is False
    assert _item(saved, "i1")["acceptance_source"] == "manual"
    assert saved.version == before_version + 1


def test_keep_review_required_candidate_is_manual_override_and_complete(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    decision = _set_confidence_state(
        working_copy,
        db_session,
        "i1",
        "medium",
    )

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )

    kept = _item(saved, "i1")
    assert kept["status"] == "kept"
    assert kept["requires_confirmation"] is False
    assert kept["acceptance_source"] == "manual_override"
    assert kept["confidence_decision"] == decision


@pytest.mark.parametrize(
    ("item_ids", "command", "accepted", "source_status"),
    [
        (
            ["i1"],
            {"type": "keep", "item_id": "i1"},
            True,
            "kept",
        ),
        (
            ["i1"],
            {
                "type": "edit",
                "item_id": "i1",
                "fields": {"raw_text": "M6 通"},
            },
            True,
            "kept",
        ),
        (
            ["i1"],
            {
                "type": "set_balloon_required",
                "item_id": "i1",
                "balloon_required": False,
            },
            True,
            "kept",
        ),
        (
            ["i1"],
            {"type": "exclude", "item_id": "i1"},
            False,
            "excluded",
        ),
        (
            ["i1", "i2"],
            {
                "type": "merge",
                "item_ids": ["i1", "i2"],
                "raw_text": "M6 通",
            },
            True,
            "superseded",
        ),
        (
            ["composite-1"],
            {
                "type": "split",
                "item_id": "composite-1",
                "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
            },
            True,
            "superseded",
        ),
    ],
    ids=["keep", "edit", "toggle", "exclude", "merge", "split"],
)
def test_semantic_completion_resolves_candidate_linked_coverage_atomically(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    item_ids: list[str],
    command: dict[str, object],
    accepted: bool,
    source_status: str,
) -> None:
    _set_linked_review_state(working_copy, db_session, item_ids)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command=command,
    )

    assert all(
        entry["requires_confirmation"] is False
        and entry["confirmation_accepted"] is accepted
        for entry in saved.coverage["entries"]
    )
    assert saved.coverage["review_required_count"] == 0
    assert manual_review_count(saved.items, saved.coverage) == 0
    assert all(_item(saved, item_id)["status"] == source_status for item_id in item_ids)
    assert "unresolved_confirmation" not in _freeze_blockers_with_completed_sip(
        saved
    )


def test_exclude_candidate_without_deleting_original(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    """P0-REV-005: exclude is current-only and never deletes raw evidence."""
    original = copy.deepcopy(raw_result.candidates)
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "exclude", "item_id": "i1"},
    )

    assert _item(saved, "i1")["status"] == "excluded"
    assert _item(saved, "i1")["active"] is False
    persisted = db_session.get(AutomaticResult, raw_result.id)
    assert persisted is not None
    assert persisted.candidates == original


@pytest.mark.parametrize(
    "command",
    [
        {
            "type": "edit",
            "item_id": "i1",
            "fields": {"raw_text": "M6 通"},
        },
        {
            "type": "exclude",
            "item_id": "i1",
        },
        {
            "type": "set_balloon_required",
            "item_id": "i1",
            "balloon_required": False,
        },
    ],
    ids=["edit", "exclude", "balloon-toggle"],
)
def test_human_semantic_action_preserves_high_decision_as_manual_override(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    raw_result: AutomaticResult,
    db_session: Session,
    command: dict[str, object],
) -> None:
    decision = _set_confidence_state(
        working_copy,
        db_session,
        "i1",
        "high",
    )
    original = copy.deepcopy(raw_result.candidates)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command=command,
    )

    changed = _item(saved, "i1")
    assert changed["acceptance_source"] == "manual_override"
    assert changed["confidence_decision"] == decision
    assert changed["status"] == (
        "excluded" if command["type"] == "exclude" else "kept"
    )
    assert db_session.get(AutomaticResult, raw_result.id).candidates == original


def test_sip_only_update_does_not_override_auto_disposition(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    decision = _set_confidence_state(
        working_copy,
        db_session,
        "i1",
        "high",
    )

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6 thread",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        },
    )

    item = _item(saved, "i1")
    assert item["status"] == "auto_accepted"
    assert item["acceptance_source"] == "confidence_policy"
    assert item["confidence_decision"] == decision


def test_historical_malformed_decision_uses_ordinary_manual_provenance(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    item = next(value for value in items if value["item_id"] == "i1")
    item["confidence_decision"] = {"band": "high"}
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )

    kept = _item(saved, "i1")
    assert kept["status"] == "kept"
    assert kept["acceptance_source"] == "manual"
    assert "confidence_decision" not in kept


def test_edit_raw_text(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-006: a human edit retains sources and records manual provenance."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "edit", "item_id": "i1", "fields": {"raw_text": "M6 通"}},
    )

    edited = _item(saved, "i1")
    assert edited["raw_text"] == "M6 通"
    assert edited["source_type"] == "manual"
    assert edited["source_location_ids"] == ["s1"]


def test_edit_typed_core_fields(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-007: typed edits retain Decimal semantics and raw text."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "edit",
            "item_id": "typed-1",
            "fields": {
                "nominal": Decimal("12.50"),
                "upper_tolerance": Decimal("0.03"),
            },
        },
    )

    edited = _item(saved, "typed-1")
    assert edited["nominal"] == "12.50"
    assert edited["upper_tolerance"] == "0.03"
    assert edited["raw_text"] == "10"


def test_add_manual_item(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-009: manual additions require explicit geometry and scope."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "add",
            "raw_text": "M8 深12",
            "item_type": "thread",
            "coordinates": (21, 22, 23, 24),
            "scope": "local_feature",
            "balloon_required": True,
        },
    )

    added = saved.items[-1]
    assert added["source_type"] == "manual"
    assert added["scope"] == "local_feature"
    assert added["coordinates"] == [21.0, 22.0, 23.0, 24.0]
    assert added["source_location_ids"] == []
    assert added["status"] == "kept"
    assert added["acceptance_source"] == "manual"


def test_set_balloon_required_marks_numbering_stale(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-010: requirement changes invalidate but never create numbering."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_balloon_required",
            "item_id": "i1",
            "balloon_required": False,
        },
    )

    assert _item(saved, "i1")["balloon_required"] is False
    assert saved.numbering_stale is True
    assert all("balloon_number" not in item for item in saved.items)


def test_set_sip_detail_fields_are_fixed_confirmed_values(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-EXP-007E stores explicit reviewed values and retires stale ones."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": " M6 thread ",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
            "remarks": "现场复核量具",
        },
    )

    item = _item(saved, "i1")
    assert item["inspection_item"] == "M6 thread"
    assert item["inspection_standard"] == "6H"
    assert item["inspection_method"] == "thread gauge"
    assert item["key_dimension"] == "yes"
    assert item["inspection_role"] == "IPQC"
    assert item["source_page"] == 1
    assert item["remarks"] == "现场复核量具"
    assert item["sip_detail_fields_confirmed"] is True

    edited = review_service.apply(
        saved.id,
        expected_version=saved.version,
        operator_id="quality-1",
        command={"type": "edit", "item_id": "i1", "fields": {"raw_text": "M8"}},
    )
    assert "sip_detail_fields_confirmed" not in _item(edited, "i1")
    assert "inspection_item" not in _item(edited, "i1")
    assert "remarks" not in _item(edited, "i1")


def test_generate_sip_table_maps_active_rows_in_one_operation(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] in {"i1", "typed-1"}
        if item["active"]:
            item["page_index"] = 0 if item["item_id"] == "i1" else 1
    inactive_before = copy.deepcopy(
        next(item for item in items if item["item_id"] == "i2")
    )
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    before_version = working_copy.version
    before_operations = db_session.scalar(
        select(func.count()).select_from(OperationRecord)
    )

    saved = review_service.apply(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    assert saved.version == before_version + 1
    assert _item(saved, "i1")["inspection_method"] == "螺纹规"
    assert _item(saved, "typed-1")["inspection_method"] == "游标卡尺"
    assert _item(saved, "i1")["sip_detail_fields_confirmed"] is True
    assert _item(saved, "typed-1")["sip_detail_fields_confirmed"] is True
    assert _item(saved, "i1")["sip_mapping_exceptions"] == []
    assert _item(saved, "i2") == inactive_before
    assert db_session.scalar(
        select(func.count()).select_from(OperationRecord)
    ) == before_operations + 1
    operation = db_session.scalar(
        select(OperationRecord)
        .where(OperationRecord.project_id == saved.project_id)
        .order_by(OperationRecord.created_at.desc())
    )
    assert operation is not None
    assert operation.command == "generate_sip_table"
    assert operation.target_ids == ["i1", "typed-1"]
    assert operation.before_version == before_version
    assert operation.after_version == before_version + 1


def test_generate_sip_table_resolves_page_from_owned_source_observation(
    working_copy: ReviewWorkingCopy,
    raw_result: AutomaticResult,
    db_session: Session,
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    inventory = json.dumps(
        {
            "pages": [
                {
                    "page_index": 2,
                    "observations": [
                        {
                            "observation_id": "s1",
                            "bbox_pdf": [1, 2, 3, 4],
                            "raw_text": "M6",
                        }
                    ],
                }
            ]
        }
    ).encode()
    storage.write_verified(
        f"tests/{raw_result.project_id}/inventory.json",
        inventory,
        hashlib.sha256(inventory).hexdigest(),
    )
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == "i1"
        item.pop("page_index", None)
        item.pop("source_page", None)
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)

    saved = ReviewService(db_session, storage=storage).apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    row = _item(saved, "i1")
    assert row["source_page"] == 3
    assert row["sip_mapping_exceptions"] == []
    assert row["sip_detail_fields_confirmed"] is True

    regenerated = ReviewService(db_session, storage=storage).apply(
        saved.id,
        expected_version=saved.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "OQC",
        },
    )

    regenerated_row = _item(regenerated, "i1")
    assert regenerated_row["source_page"] == 3
    assert regenerated_row["sip_mapping_exceptions"] == []
    assert regenerated_row["sip_detail_fields_confirmed"] is True


def test_generate_sip_table_preserves_manual_resolved_row(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == "i1"
        if item["active"]:
            item["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    manual = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "人工检验项目",
            "inspection_standard": "人工标准",
            "inspection_method": "人工量具",
            "key_dimension": "是",
            "inspection_role": "OQC",
            "source_page": 4,
            "remarks": "人工备注",
        },
    )
    manual_row = copy.deepcopy(_item(manual, "i1"))

    generated = review_service.apply(
        manual.id,
        expected_version=manual.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    assert _item(generated, "i1") == manual_row


def test_generate_sip_table_can_refresh_only_automatic_role(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == "i1"
        if item["active"]:
            item["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)

    first = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )
    first_role = _item(first, "i1")["inspection_role"]
    second = review_service.apply(
        first.id,
        expected_version=first.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "OQC",
        },
    )

    assert first_role == "IPQC"
    assert _item(second, "i1")["inspection_role"] == "OQC"
    assert _item(second, "i1")["sip_detail_fields_confirmed"] is True


def test_confirmed_requirement_invalidates_automatic_sip_readiness(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == "i1"
        if item["active"]:
            item["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    generated = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )
    automatic_row = copy.deepcopy(_item(generated, "i1"))
    _set_technical_requirement_state(generated, db_session)
    remapped_items = copy.deepcopy(generated.items)
    remapped_items[
        next(
            index
            for index, item in enumerate(remapped_items)
            if item["item_id"] == "i1"
        )
    ] = automatic_row
    generated.items = remapped_items
    db_session.commit()
    db_session.refresh(generated)

    saved = review_service.apply(
        generated.id,
        expected_version=generated.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": "requirement-1",
            "outcome": "matched_items",
            "matched_item_ids": ["i1"],
        },
    )

    row = _item(saved, "i1")
    assert row["inspection_standard"] == "GB/T 1804-m"
    assert row["sip_suggestion_provenance"]["inspection_standard"] == (
        "requirement-1"
    )
    assert row["sip_detail_fields_confirmed"] is False
    assert "inspection_method" not in row
    assert "sip_mapping_exceptions" not in row


def test_requirement_retarget_marks_old_automatic_sip_row_for_regeneration(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_technical_requirement_state(working_copy, db_session)
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] in {"i1", "typed-1"}
        if item["active"]:
            item["page_index"] = 0
    working_copy.items = items
    db_session.commit()
    db_session.refresh(working_copy)
    generated = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )
    assert _item(generated, "i1")["sip_detail_fields_confirmed"] is True

    retargeted = review_service.apply(
        generated.id,
        expected_version=generated.version,
        operator_id="quality-1",
        command={
            "type": "set_technical_requirement_match",
            "requirement_id": "requirement-1",
            "outcome": "matched_items",
            "matched_item_ids": ["typed-1"],
        },
    )

    old_target = _item(retargeted, "i1")
    assert "inspection_standard" not in old_target
    assert old_target["sip_detail_fields_confirmed"] is False
    assert old_target["sip_mapping_exceptions"] == [
        "sip_regeneration_required"
    ]


def test_generate_sip_table_maps_coarse_roughness_without_manual_exception(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == "complex-1"
        if item["active"]:
            item["page_index"] = 0
            item["requires_confirmation"] = False
    working_copy.items = items
    working_copy.coverage = {
        "blocking_count": 0,
        "review_required_count": 0,
        "coverage_checked": True,
        "blocking_observation_ids": [],
        "entries": [],
        "relations": [],
    }
    db_session.commit()
    db_session.refresh(working_copy)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    row = _item(saved, "complex-1")
    assert row["inspection_item"] == "粗糙度：Ra 3.2"
    assert row["inspection_method"] == "粗糙度仪"
    assert row["sip_mapping_exceptions"] == []
    assert row["sip_detail_fields_confirmed"] is True


@pytest.mark.parametrize(
    ("item_id", "expected_exception"),
    [("composite-1", "composite_method_required")],
)
def test_generate_sip_table_keeps_unresolved_rows_as_exceptions(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    item_id: str,
    expected_exception: str,
) -> None:
    items = copy.deepcopy(working_copy.items)
    for item in items:
        item["active"] = item["item_id"] == item_id
        if item["active"]:
            item["page_index"] = 0
            item["requires_confirmation"] = False
    working_copy.items = items
    working_copy.coverage = {
        "blocking_count": 0,
        "review_required_count": 0,
        "coverage_checked": True,
        "blocking_observation_ids": [],
        "entries": [],
        "relations": [],
    }
    db_session.commit()
    db_session.refresh(working_copy)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "generate_sip_table",
            "inspection_role": "IPQC",
        },
    )

    row = _item(saved, item_id)
    assert row["sip_mapping_exceptions"] == [expected_exception]
    assert row["sip_detail_fields_confirmed"] is False


def test_set_sip_metadata_replaces_the_fixed_review_snapshot(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-EXP-002 freezes all fixed SIP metadata through the Review Owner."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": " MAT-001 ",
            "material_name": "上座",
            "drawing_number": "JS26032501",
            "material": "SUS304",
            "revision": "A1",
        },
    )

    assert saved.sip_metadata == {
        "material_code": "MAT-001",
        "material_name": "上座",
        "drawing_number": "JS26032501",
        "material": "SUS304",
        "revision": "A1",
    }


def test_set_sip_metadata_keeps_optional_material_blank(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """Catches optional material being restored to the nonblank SIP gate."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "上座",
            "drawing_number": "JS26032501",
            "material": "none",
            "revision": "A1",
        },
    )

    assert saved.sip_metadata == {
        "material_code": "MAT-001",
        "material_name": "上座",
        "drawing_number": "JS26032501",
        "material": "",
        "revision": "A1",
    }


def test_non_source_command_normalizes_legacy_source_only_coverage(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """Catches ordinary review progress preserving obsolete source blockers."""
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "legacy-source",
            "source_location_id": "legacy-source",
            "candidate_id": None,
            "disposition": "ambiguous",
            "coordinates": [1, 2, 3, 4],
            "requires_confirmation": True,
        }
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "上座",
            "drawing_number": "JS26032501",
            "material": "",
            "revision": "A1",
        },
    )

    assert saved.coverage["review_required_count"] == 0
    assert saved.coverage["entries"][0]["resolution_source"] == "system_default"


def test_simple_merge_preserves_sources_without_quantity_sum(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-011: merge keeps ordered source union and never sums quantity."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={"type": "merge", "item_ids": ["i1", "i2"], "raw_text": "M6 通"},
    )

    merged = saved.items[-1]
    assert merged["source_location_ids"] == ["s1", "s2"]
    assert merged["quantity"] is None
    assert merged["merged_from_item_ids"] == ["i1", "i2"]
    assert {_item(saved, item_id)["status"] for item_id in ("i1", "i2")} == {
        "superseded"
    }


def test_merge_and_split_outputs_are_manual_overrides_without_inherited_decision(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    first_decision = _set_confidence_state(
        working_copy,
        db_session,
        "i1",
        "high",
    )
    _set_confidence_state(working_copy, db_session, "i2", "high")

    merged = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "merge",
            "item_ids": ["i1", "i2"],
            "raw_text": "M6 通",
        },
    )
    merged_item = merged.items[-1]

    assert merged_item["status"] == "kept"
    assert merged_item["acceptance_source"] == "manual_override"
    assert "confidence_decision" not in merged_item
    assert _item(merged, "i1")["acceptance_source"] == "manual_override"
    assert _item(merged, "i1")["confidence_decision"] == first_decision

    split_decision = _set_confidence_state(
        merged,
        db_session,
        "composite-1",
        "high",
    )
    split = review_service.apply(
        merged.id,
        expected_version=merged.version,
        operator_id="quality-1",
        command={
            "type": "split",
            "item_id": "composite-1",
            "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
        },
    )

    assert all(item["status"] == "kept" for item in split.items[-2:])
    assert all(
        item["acceptance_source"] == "manual_override"
        for item in split.items[-2:]
    )
    assert all("confidence_decision" not in item for item in split.items[-2:])
    source = _item(split, "composite-1")
    assert source["acceptance_source"] == "manual_override"
    assert source["confidence_decision"] == split_decision


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ({"type": "merge", "item_ids": ["i1", "i1"], "raw_text": "M6"}, "distinct"),
        (
            {"type": "merge", "item_ids": ["i1", "typed-1"], "raw_text": "mixed"},
            "same simple item type",
        ),
        (
            {"type": "merge", "item_ids": ["i1", "complex-1"], "raw_text": "mixed"},
            "same simple item type",
        ),
        (
            {"type": "split", "item_id": "complex-1", "parts": [{"raw_text": "a"}, {"raw_text": "b"}]},
            "simple items",
        ),
    ],
)
def test_merge_and_split_reject_non_simple_inputs(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    command: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        review_service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
            command=command,
        )


def test_simple_split_preserves_source_relations(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-REV-012: every split part retains the input source relations."""
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "split",
            "item_id": "composite-1",
            "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
        },
    )

    assert [item["source_location_ids"] for item in saved.items[-2:]] == [
        ["s-composite"],
        ["s-composite"],
    ]
    assert all(
        item["split_from_item_id"] == "composite-1"
        for item in saved.items[-2:]
    )
    assert _item(saved, "composite-1")["status"] == "superseded"


def test_resolve_confirmation_records_explicit_outcome(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    decision = _set_confidence_state(
        working_copy,
        db_session,
        "complex-1",
        "low",
    )
    before_version = working_copy.version
    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "resolve_confirmation",
            "item_id": "complex-1",
            "accepted": False,
        },
    )

    resolved = _item(saved, "complex-1")
    assert resolved["requires_confirmation"] is False
    assert resolved["confirmation_accepted"] is False
    assert resolved["status"] == "excluded"
    assert resolved["active"] is False
    assert resolved["acceptance_source"] == "manual_override"
    assert resolved["confidence_decision"] == decision
    assert saved.coverage["entries"][0]["candidate_id"] == "complex-1"
    assert saved.coverage["entries"][0]["requires_confirmation"] is False
    assert saved.coverage["entries"][0]["confirmation_accepted"] is False
    assert saved.coverage["review_required_count"] == 0
    assert saved.version == before_version + 1
    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert len(records) == 1
    assert records[0].command == "resolve_confirmation"
    assert records[0].before_version == before_version
    assert records[0].after_version == before_version + 1


def test_promote_source_creates_item_and_resolves_coverage_atomically(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)
    before_items = copy.deepcopy(working_copy.items)
    before_coverage = copy.deepcopy(working_copy.coverage)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "promote_source",
            "observation_id": "source-only",
            "raw_text": " M16 ",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 1,
        },
    )

    assert saved.items[:-1] == before_items
    assert len(saved.items) == len(before_items) + 1
    added = saved.items[-1]
    new_item_id = added["item_id"]
    uuid.UUID(new_item_id)
    assert added == {
        "item_id": new_item_id,
        "item_type": "thread",
        "raw_text": "M16",
        "normalized_text": "M16",
        "coordinates": [21, 22, 23, 24],
        "scope": "local_feature",
        "balloon_required": True,
        "requires_confirmation": False,
        "source_location_ids": ["source-location"],
        "page_index": 1,
        "source_type": "manual",
        "status": "kept",
        "acceptance_source": "manual",
        "active": True,
    }
    assert sum(
        item.get("active", True) and item["item_id"] == new_item_id
        for item in saved.items
    ) == 1
    assert saved.coverage == {
        **before_coverage,
        "entries": [
            {
                "observation_id": "source-only",
                "disposition": "candidate",
                "source_location_id": "source-location",
                "coordinates": [21, 22, 23, 24],
                "candidate_id": new_item_id,
                "requires_confirmation": False,
                "symbol_kinds": [],
                "rejection_code": "visual_no_detection",
                "confirmation_accepted": True,
            }
        ],
        "review_required_count": 0,
    }
    assert saved.numbering_stale is True

    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert len(records) == 1
    assert records[0].command == "promote_source"
    assert records[0].target_ids == ["source-only", new_item_id]


def test_ignore_source_resolves_coverage_without_changing_items_or_numbering(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)
    before_items = copy.deepcopy(working_copy.items)
    before_coverage = copy.deepcopy(working_copy.coverage)

    saved = review_service.apply(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
        command={
            "type": "ignore_source",
            "observation_id": "source-only",
        },
    )

    assert saved.items == before_items
    assert saved.coverage == {
        **before_coverage,
        "entries": [
            {
                "observation_id": "source-only",
                "disposition": "non_inspection",
                "source_location_id": "source-location",
                "coordinates": [21, 22, 23, 24],
                "candidate_id": None,
                "requires_confirmation": False,
                "symbol_kinds": [],
                "rejection_code": "visual_no_detection",
                "confirmation_accepted": False,
            }
        ],
        "review_required_count": 0,
    }
    assert saved.numbering_stale is False

    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert len(records) == 1
    assert records[0].command == "ignore_source"
    assert records[0].target_ids == ["source-only"]


def test_ignore_sources_resolves_all_targets_in_one_version_and_audit_record(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-1",
            "disposition": "ambiguous",
            "source_location_id": "source-location-1",
            "coordinates": [21, 22, 23, 24],
            "candidate_id": None,
            "requires_confirmation": True,
        },
        {
            "observation_id": "source-2",
            "disposition": "ambiguous",
            "source_location_id": "source-location-2",
            "coordinates": [31, 32, 33, 34],
            "candidate_id": None,
            "requires_confirmation": True,
        },
    ]
    coverage["review_required_count"] = 2
    working_copy.coverage = coverage
    db_session.commit()
    db_session.refresh(working_copy)
    before_version = working_copy.version
    before_items = copy.deepcopy(working_copy.items)
    before_numbering_stale = working_copy.numbering_stale

    saved = review_service.apply(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={
            "type": "ignore_sources",
            "observation_ids": ["source-1", "source-2"],
        },
    )

    assert saved.version == before_version + 1
    assert saved.items == before_items
    assert saved.numbering_stale is before_numbering_stale
    assert saved.coverage["review_required_count"] == 0
    assert [
        {
            key: entry.get(key)
            for key in (
                "observation_id",
                "disposition",
                "candidate_id",
                "requires_confirmation",
                "confirmation_accepted",
            )
        }
        for entry in saved.coverage["entries"]
    ] == [
        {
            "observation_id": "source-1",
            "disposition": "non_inspection",
            "candidate_id": None,
            "requires_confirmation": False,
            "confirmation_accepted": False,
        },
        {
            "observation_id": "source-2",
            "disposition": "non_inspection",
            "candidate_id": None,
            "requires_confirmation": False,
            "confirmation_accepted": False,
        },
    ]
    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert len(records) == 1
    assert records[0].command == "ignore_sources"
    assert records[0].target_ids == ["source-1", "source-2"]
    assert records[0].before_version == before_version
    assert records[0].after_version == before_version + 1


def test_ignore_sources_rejects_the_entire_batch_when_one_target_is_resolved(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-1",
            "disposition": "ambiguous",
            "source_location_id": "source-location-1",
            "coordinates": [21, 22, 23, 24],
            "candidate_id": None,
            "requires_confirmation": True,
        },
        {
            "observation_id": "source-2",
            "disposition": "non_inspection",
            "source_location_id": "source-location-2",
            "coordinates": [31, 32, 33, 34],
            "candidate_id": None,
            "requires_confirmation": False,
            "confirmation_accepted": False,
        },
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()
    db_session.refresh(working_copy)
    before_version = working_copy.version
    before_items = copy.deepcopy(working_copy.items)
    before_coverage = copy.deepcopy(working_copy.coverage)

    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=before_version,
            operator_id="quality-1",
            command={
                "type": "ignore_sources",
                "observation_ids": ["source-1", "source-2"],
            },
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.items == before_items
    assert persisted.coverage == before_coverage
    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert records == []


def test_resolve_confirmation_rejects_source_only_observation_atomically(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    _set_source_only_coverage(working_copy, db_session)
    before_version = working_copy.version
    before_coverage = copy.deepcopy(working_copy.coverage)
    before_items = copy.deepcopy(working_copy.items)

    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=before_version,
            operator_id="quality-1",
            command={
                "type": "resolve_confirmation",
                "item_id": "source-only",
                "accepted": True,
            },
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.coverage == before_coverage
    assert persisted.items == before_items


@pytest.mark.parametrize(
    "command",
    [
        {
            "type": "promote_source",
            "observation_id": "s-complex",
            "raw_text": "M16",
            "item_type": "thread",
            "scope": "local_feature",
            "balloon_required": True,
            "page_index": 1,
        },
        {
            "type": "ignore_source",
            "observation_id": "s-complex",
        },
    ],
)
def test_source_review_rejects_candidate_backed_entry_atomically(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    command: dict[str, object],
) -> None:
    before_version = working_copy.version
    before_coverage = copy.deepcopy(working_copy.coverage)
    before_items = copy.deepcopy(working_copy.items)

    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=before_version,
            operator_id="quality-1",
            command=command,
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.coverage == before_coverage
    assert persisted.items == before_items


@pytest.mark.parametrize(
    ("malformed_entries", "command_type"),
    [
        pytest.param(entries, command_type, id=f"{entries!r}-{command_type}")
        for entries in (None, 1, [None])
        for command_type in ("promote_source", "ignore_source")
    ],
)
def test_source_review_rejects_malformed_coverage_entries_atomically(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    malformed_entries: object,
    command_type: str,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = malformed_entries
    working_copy.coverage = coverage
    db_session.commit()
    db_session.refresh(working_copy)
    before_version = working_copy.version
    before_coverage = copy.deepcopy(working_copy.coverage)
    before_items = copy.deepcopy(working_copy.items)
    command: dict[str, object] = {
        "type": command_type,
        "observation_id": "source-only",
    }
    if command_type == "promote_source":
        command.update(
            {
                "raw_text": "M16",
                "item_type": "thread",
                "scope": "local_feature",
                "balloon_required": True,
                "page_index": 1,
            }
        )

    with pytest.raises(ReviewNotFound):
        review_service.apply(
            working_copy.id,
            expected_version=before_version,
            operator_id="quality-1",
            command=command,
        )

    db_session.expire_all()
    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.coverage == before_coverage
    assert persisted.items == before_items


def test_modification_log_records_command_sequence(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    """P0-REV-002: each command writes one ordered operation summary."""
    first_version = working_copy.version
    kept = review_service.apply(
        working_copy.id,
        expected_version=first_version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )
    review_service.apply(
        working_copy.id,
        expected_version=kept.version,
        operator_id="quality-1",
        command={"type": "edit", "item_id": "i1", "fields": {"raw_text": "M6 通"}},
    )

    records = list(
        db_session.scalars(
            select(OperationRecord)
            .where(OperationRecord.project_id == working_copy.project_id)
            .order_by(OperationRecord.before_version)
        )
    )
    assert [record.command for record in records] == ["keep", "edit"]
    assert [(record.before_version, record.after_version) for record in records] == [
        (first_version, first_version + 1),
        (first_version + 1, first_version + 2),
    ]


@pytest.mark.parametrize(
    "command",
    [
        {"type": "keep", "item_id": "i1"},
        {"type": "exclude", "item_id": "i1"},
        {"type": "edit", "item_id": "i1", "fields": {"raw_text": "M6 通"}},
        {
            "type": "add",
            "raw_text": "M8",
            "item_type": "thread",
            "coordinates": (21, 22, 23, 24),
            "scope": "local_feature",
            "balloon_required": True,
        },
        {"type": "merge", "item_ids": ["i1", "i2"], "raw_text": "M6 通"},
        {
            "type": "split",
            "item_id": "composite-1",
            "parts": [{"raw_text": "Φ10"}, {"raw_text": "深20"}],
        },
        {"type": "resolve_confirmation", "item_id": "complex-1", "accepted": True},
        {
            "type": "set_balloon_required",
            "item_id": "i1",
            "balloon_required": False,
        },
        {
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        },
        {
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "DRAWING-001",
            "material": "steel",
            "revision": "A",
        },
    ],
)
def test_each_command_increments_once_and_writes_one_operation(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
    command: dict[str, object],
) -> None:
    before_version = working_copy.version

    saved = review_service.apply(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command=command,
    )

    records = list(
        db_session.scalars(
            select(OperationRecord).where(
                OperationRecord.project_id == working_copy.project_id
            )
        )
    )
    assert saved.version == before_version + 1
    assert len(records) == 1
    assert records[0].before_version == before_version
    assert records[0].after_version == before_version + 1


def test_operation_failure_rolls_back_working_copy_and_audit(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    before_version = working_copy.version
    before_items = copy.deepcopy(working_copy.items)

    def fail_operation_insert(*_: object) -> None:
        raise RuntimeError("injected audit failure")

    event.listen(OperationRecord, "before_insert", fail_operation_insert)
    try:
        with pytest.raises(RuntimeError, match="injected audit failure"):
            review_service.apply(
                working_copy.id,
                expected_version=before_version,
                operator_id="quality-1",
                command={"type": "keep", "item_id": "i1"},
            )
    finally:
        event.remove(OperationRecord, "before_insert", fail_operation_insert)
        db_session.rollback()

    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == before_version
    assert persisted.items == before_items
    assert db_session.scalar(
        select(func.count())
        .select_from(OperationRecord)
        .where(OperationRecord.project_id == working_copy.project_id)
    ) == 0
