from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.models import ReviewedResult
from app.review.service import FreezeBlocked, ItemsFrozen, ReviewService
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
def working_copy(db_session: Session) -> ReviewWorkingCopy:
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
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
                logical_task_key=f"review-freeze:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    db_session.flush()
    db_session.add(
        AutomaticResult(
            id=result_id,
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
                        "balloon_required": True,
                        "requires_confirmation": False,
                    },
                    "source_location_ids": ["s1"],
                }
            ],
            coverage={
                "blocking_count": 0,
                "review_required_count": 0,
                "coverage_checked": True,
                "blocking_observation_ids": [],
                "entries": [],
                "relations": [],
            },
            provider_call_ids=[],
            schema_version="automatic-result/1",
        )
    )
    db_session.commit()
    service = ReviewService(db_session)
    working = service.create_from_raw(result_id)
    acquire_lock(db_session, project_id, "quality-1")
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
            "remarks": "",
        },
    )
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "FREEZE-001",
            "material": "steel",
            "revision": "A",
        },
    )
    return working


def test_unresolved_confirmation_blocks_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    """PRT-5 unresolved partial evidence, not the label alone, blocks freeze."""
    raw = db_session.get(AutomaticResult, working_copy.raw_result_id)
    assert raw is not None
    setattr(raw, "completeness", "partial_review_required")
    items = copy.deepcopy(working_copy.items)
    items[0]["requires_confirmation"] = True
    working_copy.items = items
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.code == "unresolved_confirmation"
    assert error.value.blockers == ("unresolved_confirmation",)


def test_partial_label_alone_does_not_add_a_freeze_blocker(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    """PRT-5 keeps the confirmation Veto separate from completeness status."""
    raw = db_session.get(AutomaticResult, working_copy.raw_result_id)
    assert raw is not None
    setattr(raw, "completeness", "partial_review_required")
    db_session.commit()

    frozen = ReviewService(db_session).freeze_items(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
    )

    assert frozen.items_frozen_at is not None


def test_source_only_confirmation_blocks_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "source_location_id": "source-only",
            "disposition": "ambiguous",
            "coordinates": [5, 6, 7, 8],
            "requires_confirmation": True,
        }
    ]
    coverage["review_required_count"] = 1
    working_copy.coverage = coverage
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.blockers == ("unresolved_confirmation",)


def test_freeze_reports_only_the_three_exact_blockers(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    items = copy.deepcopy(working_copy.items)
    items[0]["requires_confirmation"] = True
    items[0]["balloon_required"] = None
    coverage = copy.deepcopy(working_copy.coverage)
    coverage["blocking_count"] = 1
    working_copy.items = items
    working_copy.coverage = coverage
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        ReviewService(db_session).freeze_items(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.blockers == (
        "coverage_blocking",
        "unresolved_confirmation",
        "balloon_required_unconfirmed",
    )


def test_item_set_freeze_preserves_editing_without_reviewed_result(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    before_version = working_copy.version
    service = ReviewService(db_session)

    frozen = service.freeze_items(
        working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
    )

    project = db_session.get(Project, working_copy.project_id)
    assert frozen.items_frozen_at is not None
    assert frozen.items_frozen_by == "quality-1"
    assert frozen.items_frozen_version == before_version
    assert frozen.version == before_version
    assert project is not None
    assert project.state == ProjectState.EDITING
    assert service.reviewed_result_for(working_copy.project_id) is None
    assert db_session.scalar(
        select(func.count()).select_from(ReviewedResult).where(
            ReviewedResult.project_id == working_copy.project_id
        )
    ) == 0


def test_item_set_freeze_rejects_later_semantic_commands(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    service = ReviewService(db_session)
    frozen = service.freeze_items(
        working_copy.id,
        expected_version=working_copy.version,
        operator_id="quality-1",
    )

    with pytest.raises(ItemsFrozen):
        service.apply(
            working_copy.id,
            expected_version=frozen.version,
            operator_id="quality-1",
            command={"type": "keep", "item_id": "i1"},
        )
