import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.jobs.idempotency import LogicalJob, claim_logical_job


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_duplicate_delivery_returns_the_same_job(db_session: Session) -> None:
    """P0-RUN-010 deduplicates one logical task key within a project."""
    project_id = f"p0-test-{uuid.uuid4()}"
    logical_task_key = "process:sha256"

    try:
        first = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )
        second = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )

        assert second.id == first.id
    finally:
        db_session.rollback()
        db_session.execute(
            delete(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        db_session.commit()
