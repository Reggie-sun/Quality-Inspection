from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text, update
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import LockConflict, acquire_lock, release_lock
from app.review.models import ReviewLock
from app.review.router import get_session


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


def test_exact_owner_and_lease_version_can_release_lock(
    db_session: Session,
    project: Project,
) -> None:
    lock = acquire_lock(db_session, project.id, "quality-1")

    released = release_lock(
        db_session,
        project.id,
        "quality-1",
        expires_at=lock.expires_at,
    )

    assert released is True
    assert db_session.get(ReviewLock, project.id) is None
    assert acquire_lock(db_session, project.id, "quality-2").operator_id == "quality-2"


def test_stale_lease_version_cannot_release_renewed_lock(
    db_session: Session,
    project: Project,
) -> None:
    original = acquire_lock(db_session, project.id, "quality-1", ttl_seconds=30)
    original_expires_at = original.expires_at
    renewed = acquire_lock(db_session, project.id, "quality-1", ttl_seconds=60)

    released = release_lock(
        db_session,
        project.id,
        "quality-1",
        expires_at=original_expires_at,
    )

    assert released is False
    persisted = db_session.get(ReviewLock, project.id)
    assert persisted is not None
    assert persisted.expires_at == renewed.expires_at


def test_other_operator_and_repeated_release_are_idempotent_noops(
    db_session: Session,
    project: Project,
) -> None:
    lock = acquire_lock(db_session, project.id, "quality-1")

    assert release_lock(
        db_session,
        project.id,
        "quality-2",
        expires_at=lock.expires_at,
    ) is False
    assert db_session.get(ReviewLock, project.id) is not None
    assert release_lock(
        db_session,
        project.id,
        "quality-1",
        expires_at=lock.expires_at,
    ) is True
    assert release_lock(
        db_session,
        project.id,
        "quality-1",
        expires_at=lock.expires_at,
    ) is False


def test_review_lock_release_route_projects_exact_lease_result(
    db_session: Session,
    project: Project,
) -> None:
    lock = acquire_lock(db_session, project.id, "quality-1")

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app).post(
            f"/api/v1/projects/{project.id}/review/lock/release",
            headers={"X-QI-Operator": "quality-1"},
            json={"expires_at": lock.expires_at.isoformat()},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "project_id": str(project.id),
        "released": True,
    }
