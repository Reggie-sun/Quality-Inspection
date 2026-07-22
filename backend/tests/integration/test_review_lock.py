from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import func, text, update
from sqlalchemy.orm import Session

from app.db import engine
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import LockConflict, acquire_lock
from app.review.models import ReviewLock


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
def project(db_session: Session) -> Project:
    project = Project(id=uuid.uuid4(), state=ProjectState.EDITING)
    db_session.add(project)
    db_session.commit()
    return project


def test_second_editor_is_rejected(
    db_session: Session,
    project: Project,
) -> None:
    """P0-RUN-006: one project has at most one active editor."""
    acquire_lock(db_session, project.id, "quality-1")

    with pytest.raises(LockConflict, match="active editor"):
        acquire_lock(db_session, project.id, "quality-2")

    lock = db_session.get(ReviewLock, project.id)
    assert lock is not None
    assert lock.operator_id == "quality-1"


def test_expired_lock_can_be_acquired_by_next_operator(
    db_session: Session,
    project: Project,
) -> None:
    acquire_lock(db_session, project.id, "quality-1")
    db_session.execute(
        update(ReviewLock)
        .where(ReviewLock.project_id == project.id)
        .values(expires_at=func.now() - text("interval '1 second'"))
    )
    db_session.commit()

    lock = acquire_lock(db_session, project.id, "quality-2")

    assert lock.operator_id == "quality-2"


def test_same_operator_can_renew_active_lock(
    db_session: Session,
    project: Project,
) -> None:
    first = acquire_lock(db_session, project.id, "quality-1", ttl_seconds=30)
    renewed = acquire_lock(db_session, project.id, "quality-1", ttl_seconds=60)

    assert renewed.project_id == first.project_id
    assert renewed.expires_at >= first.expires_at
