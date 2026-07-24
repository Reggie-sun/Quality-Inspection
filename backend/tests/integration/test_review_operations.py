from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewService
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
    assert saved.version == before_version + 1


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
) -> None:
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


def test_resolve_source_only_coverage_decrements_review_required_count(
    review_service: ReviewService,
    working_copy: ReviewWorkingCopy,
    db_session: Session,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "disposition": "ambiguous",
            "source_location_id": "source-only",
            "coordinates": [21, 22, 23, 24],
            "candidate_id": None,
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
            "type": "resolve_confirmation",
            "item_id": "source-only",
            "accepted": True,
        },
    )

    assert saved.coverage["review_required_count"] == 0
    assert saved.coverage["entries"][0]["requires_confirmation"] is False
    assert saved.coverage["entries"][0]["confirmation_accepted"] is True


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
