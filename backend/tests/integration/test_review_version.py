from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.main import app
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import LockConflict, LockRequired, acquire_lock
from app.review.models import ReviewWorkingCopy
from app.review.router import get_session
from app.review.service import ReviewService, ReviewVersionConflict
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


def _create_working_copy(db_session: Session) -> ReviewWorkingCopy:
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
                logical_task_key=f"review-version:{project_id}",
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
    return ReviewService(db_session).create_from_raw(result_id)


@pytest.fixture
def working_copy(db_session: Session) -> ReviewWorkingCopy:
    return _create_working_copy(db_session)


def test_stale_write_returns_conflict_without_overwrite(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    """P0-RUN-007: stale writes preserve the committed current value."""
    acquire_lock(db_session, working_copy.project_id, "quality-1")
    service = ReviewService(db_session)
    stale_version = working_copy.version
    saved = service.apply(
        working_copy.id,
        expected_version=stale_version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "i1"},
    )
    saved_items = copy.deepcopy(saved.items)

    with pytest.raises(ReviewVersionConflict):
        service.apply(
            working_copy.id,
            expected_version=stale_version,
            operator_id="quality-1",
            command={"type": "edit", "item_id": "i1", "fields": {"raw_text": "M8"}},
        )

    persisted = db_session.get(ReviewWorkingCopy, working_copy.id)
    assert persisted is not None
    assert persisted.version == stale_version + 1
    assert persisted.items == saved_items
    assert db_session.scalar(
        select(func.count())
        .select_from(OperationRecord)
        .where(OperationRecord.project_id == working_copy.project_id)
    ) == 1


def test_mutation_requires_the_current_active_editor(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    service = ReviewService(db_session)
    with pytest.raises(LockRequired):
        service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-1",
            command={"type": "keep", "item_id": "i1"},
        )

    acquire_lock(db_session, working_copy.project_id, "quality-1")
    with pytest.raises(LockConflict):
        service.apply(
            working_copy.id,
            expected_version=working_copy.version,
            operator_id="quality-2",
            command={"type": "keep", "item_id": "i1"},
        )


def test_guarded_update_rejects_stale_identity_from_second_session() -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    setup = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session_a = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session_b = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    verify = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        working = _create_working_copy(setup)
        acquire_lock(setup, working.project_id, "quality-1")
        stale = session_a.get(ReviewWorkingCopy, working.id)
        assert stale is not None
        stale_version = stale.version
        session_a.commit()

        saved = ReviewService(session_b).apply(
            working.id,
            expected_version=stale_version,
            operator_id="quality-1",
            command={"type": "keep", "item_id": "i1"},
        )
        saved_items = copy.deepcopy(saved.items)

        with pytest.raises(ReviewVersionConflict, match="changed concurrently"):
            ReviewService(session_a).apply(
                working.id,
                expected_version=stale_version,
                operator_id="quality-1",
                command={"type": "edit", "item_id": "i1", "fields": {"raw_text": "M8"}},
            )

        persisted = verify.get(ReviewWorkingCopy, working.id)
        assert persisted is not None
        assert persisted.version == stale_version + 1
        assert persisted.items == saved_items
        assert verify.scalar(
            select(func.count())
            .select_from(OperationRecord)
            .where(OperationRecord.project_id == working.project_id)
        ) == 1
    finally:
        verify.close()
        session_b.close()
        session_a.close()
        setup.close()
        outer_transaction.rollback()
        connection.close()


def test_review_routes_require_operator_and_save_without_freeze(
    db_session: Session,
    working_copy: ReviewWorkingCopy,
) -> None:
    acquire_lock(db_session, working_copy.project_id, "quality-1")
    initial_version = working_copy.version

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        path = f"/api/v1/projects/{working_copy.project_id}/review/commands"
        missing = client.post(
            path,
            json={
                "expected_version": initial_version,
                "command": {"type": "keep", "item_id": "i1"},
            },
        )
        assert missing.status_code == 422
        missing_lock = client.post(
            f"/api/v1/projects/{working_copy.project_id}/review/lock",
            json={},
        )
        missing_freeze = client.post(
            f"/api/v1/projects/{working_copy.project_id}/review/freeze-items",
            json={"expected_version": initial_version},
        )
        assert missing_lock.status_code == 422
        assert missing_freeze.status_code == 422
        blank_freeze = client.post(
            f"/api/v1/projects/{working_copy.project_id}/review/freeze-items",
            headers={"X-QI-Operator": "   "},
            json={"expected_version": initial_version},
        )
        assert blank_freeze.status_code == 422
        assert blank_freeze.json()["error"]["code"] == "review_operator_invalid"

        saved = client.post(
            path,
            headers={"X-QI-Operator": "quality-1"},
            json={
                "expected_version": initial_version,
                "command": {"type": "keep", "item_id": "i1"},
            },
        )
        assert saved.status_code == 200
        assert saved.json()["version"] == initial_version + 1
        assert saved.json()["items_frozen_at"] is None
        assert "freeze" not in saved.request.url.path

        stale = client.post(
            path,
            headers={"X-QI-Operator": "quality-1"},
            json={
                "expected_version": initial_version,
                "command": {"type": "edit", "item_id": "i1", "fields": {"raw_text": "M8"}},
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "review_version_conflict"

        fetched = client.get(
            f"/api/v1/projects/{working_copy.project_id}/review/working-copy"
        )
        assert fetched.status_code == 200
        assert fetched.json()["id"] == str(working_copy.id)
    finally:
        app.dependency_overrides.clear()
