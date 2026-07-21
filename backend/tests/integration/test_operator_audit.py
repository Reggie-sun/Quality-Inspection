import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
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


def test_operation_record_persists_nonempty_operator_id(db_session: Session) -> None:
    """P0-RUN-005 persists a nonempty operator ID for a write command."""
    project_id = uuid.uuid4()
    operation = OperationRecord(
        project_id=project_id,
        operator_id="operator-p0",
        command="review.update",
        target_ids=["candidate-1"],
        before_version=1,
        after_version=2,
    )
    db_session.add(operation)

    try:
        db_session.commit()
        db_session.refresh(operation)

        assert operation.id is not None
        assert operation.operator_id == "operator-p0"
        assert operation.created_at is not None
        assert not OperationRecord.__table__.c.operator_id.nullable
    finally:
        db_session.rollback()
        db_session.execute(
            delete(OperationRecord).where(OperationRecord.project_id == project_id)
        )
        db_session.commit()


@pytest.mark.parametrize("operator_id", ["", "   ", "\t", "\n"])
def test_operation_record_rejects_blank_operator_id(
    db_session: Session,
    operator_id: str,
) -> None:
    """P0-RUN-005 rejects empty and whitespace-only operator IDs."""
    project_id = uuid.uuid4()
    operation = OperationRecord(
        project_id=project_id,
        operator_id=operator_id,
        command="review.update",
        target_ids=["candidate-1"],
        before_version=1,
        after_version=2,
    )
    db_session.add(operation)

    try:
        with pytest.raises(
            IntegrityError,
            match="ck_operation_records_operator_id_nonblank",
        ):
            db_session.commit()
    finally:
        db_session.rollback()
        db_session.execute(
            delete(OperationRecord).where(OperationRecord.project_id == project_id)
        )
        db_session.commit()


def test_review_operation_summary(db_session: Session) -> None:
    """P0-RES-007: review writes one complete operation summary per command."""
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
                logical_task_key=f"review:{project_id}",
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
                    "candidate_id": "candidate-1",
                    "payload": {
                        "candidate_id": "candidate-1",
                        "item_type": "thread",
                        "raw_text": "M6",
                        "normalized_text": "M6",
                        "coordinates": [1, 2, 3, 4],
                        "scope": "local_feature",
                        "balloon_required": True,
                        "requires_confirmation": False,
                    },
                    "source_location_ids": ["source-1"],
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
    before_version = working.version
    service.apply(
        working.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": "candidate-1"},
    )

    records = list(
        db_session.scalars(
            select(OperationRecord).where(OperationRecord.project_id == project_id)
        )
    )
    assert len(records) == 1
    record = records[0]
    assert record.operator_id == "quality-1"
    assert record.command == "keep"
    assert record.target_ids == ["candidate-1"]
    assert record.before_version == before_version
    assert record.after_version == before_version + 1
    assert record.created_at is not None
