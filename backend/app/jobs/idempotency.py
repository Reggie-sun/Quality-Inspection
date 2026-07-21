from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base


class LogicalJob(Base):
    __tablename__ = "logical_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "logical_task_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_task_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )


def claim_logical_job(
    session: Session,
    *,
    project_id: str,
    logical_task_key: str,
) -> LogicalJob:
    existing = session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == project_id,
            LogicalJob.logical_task_key == logical_task_key,
        )
    )
    if existing is not None:
        return existing

    job = LogicalJob(
        project_id=project_id,
        logical_task_key=logical_task_key,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == project_id,
                LogicalJob.logical_task_key == logical_task_key,
            )
        )
        if existing is None:
            raise
        return existing
    return job
