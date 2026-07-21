import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.db import SessionLocal


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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
