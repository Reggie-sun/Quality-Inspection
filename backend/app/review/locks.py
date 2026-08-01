from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.projects.models import Project
from app.review.models import ReviewLock


class LockConflict(RuntimeError):
    pass


class LockRequired(LockConflict):
    pass


def acquire_lock(
    session: Session,
    project_id: uuid.UUID,
    operator_id: str,
    *,
    ttl_seconds: int = 300,
) -> ReviewLock:
    operator_id = _operator_id(operator_id)
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")

    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise LookupError(f"project {project_id} was not found")
    now = session.scalar(select(func.now()))
    lock = session.scalar(
        select(ReviewLock)
        .where(ReviewLock.project_id == project_id)
        .with_for_update()
    )
    if now is None:
        raise RuntimeError("PostgreSQL database clock was unavailable")
    if lock is not None and lock.expires_at > now and lock.operator_id != operator_id:
        raise LockConflict("project already has an active editor")

    expires_at = now + timedelta(seconds=ttl_seconds)
    if lock is None:
        lock = ReviewLock(
            project_id=project_id,
            operator_id=operator_id,
            expires_at=expires_at,
        )
        session.add(lock)
    else:
        lock.operator_id = operator_id
        lock.expires_at = expires_at
    session.commit()
    session.refresh(lock)
    return lock


def release_lock(
    session: Session,
    project_id: uuid.UUID,
    operator_id: str,
    *,
    expires_at: datetime,
) -> bool:
    operator_id = _operator_id(operator_id)
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise LookupError(f"project {project_id} was not found")
    lock = session.scalar(
        select(ReviewLock)
        .where(ReviewLock.project_id == project_id)
        .with_for_update()
    )
    if (
        lock is None
        or lock.operator_id != operator_id
        or lock.expires_at != expires_at
    ):
        session.commit()
        return False

    session.delete(lock)
    session.commit()
    return True


def require_active_lock(
    session: Session,
    project_id: uuid.UUID,
    operator_id: str,
) -> ReviewLock:
    operator_id = _operator_id(operator_id)
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise LookupError(f"project {project_id} was not found")
    now = session.scalar(select(func.now()))
    lock = session.scalar(
        select(ReviewLock)
        .where(ReviewLock.project_id == project_id)
        .with_for_update()
    )
    if now is None:
        raise RuntimeError("PostgreSQL database clock was unavailable")
    if lock is None or lock.expires_at <= now:
        raise LockRequired("project has no active editor lock")
    if lock.operator_id != operator_id:
        raise LockConflict("operator does not own the active editor lock")
    return lock


def _operator_id(operator_id: str) -> str:
    if not operator_id.strip():
        raise ValueError("operator_id must not be blank")
    return operator_id
