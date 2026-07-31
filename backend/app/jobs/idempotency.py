from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import String, UniqueConstraint, select, update
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
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processing_stage: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        nullable=False,
    )


class LogicalJobStateError(RuntimeError):
    pass


PROCESSING_STAGES = {
    "queued",
    "parsing",
    "recognizing",
    "local_ready",
    "vlm_enriching",
    "preparing_review",
}


@dataclass(frozen=True)
class LogicalJobFailureClaim:
    owns_failure: bool
    successful_result_ref: str | None


def successful_result_ref(job: LogicalJob) -> str | None:
    if job.status == "succeeded":
        if isinstance(job.result_ref, str) and job.result_ref:
            return job.result_ref
        raise LogicalJobStateError("succeeded logical job is missing result_ref")
    if job.result_ref is not None:
        raise LogicalJobStateError("incomplete logical job already has result_ref")
    if job.status not in {"pending", "processing"}:
        raise LogicalJobStateError(f"logical job cannot run from status {job.status}")
    return None


def existing_successful_result_ref(
    session: Session, *, project_id: str, logical_task_key: str
) -> str | None:
    job = session.scalar(select(LogicalJob).where(
        LogicalJob.project_id == project_id,
        LogicalJob.logical_task_key == logical_task_key,
    ))
    return successful_result_ref(job) if job is not None else None


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


def set_processing_stage(
    session: Session,
    *,
    job_id: uuid.UUID,
    stage: str,
    expected_stages: tuple[str, ...] | None = None,
) -> None:
    if stage not in PROCESSING_STAGES:
        raise ValueError("unknown processing stage")
    if expected_stages is not None and (
        not expected_stages
        or any(expected not in PROCESSING_STAGES for expected in expected_stages)
    ):
        raise ValueError("expected processing stages are invalid")
    statement = (
        update(LogicalJob)
        .where(
            LogicalJob.id == job_id,
            LogicalJob.result_ref.is_(None),
            LogicalJob.status.in_(("pending", "processing")),
        )
        .values(status="processing", processing_stage=stage)
    )
    if expected_stages is not None:
        statement = statement.where(
            LogicalJob.processing_stage.in_(expected_stages)
        )
    outcome = session.execute(statement)
    if outcome.rowcount != 1:
        session.rollback()
        raise LogicalJobStateError("logical job cannot change processing stage")
    session.commit()


def complete_logical_job(
    session: Session,
    *,
    job_id: uuid.UUID,
    result_ref: str,
) -> str:
    if not isinstance(result_ref, str) or not result_ref:
        raise ValueError("result_ref must be non-empty")
    outcome = session.execute(
        update(LogicalJob)
        .where(
            LogicalJob.id == job_id,
            LogicalJob.result_ref.is_(None),
            LogicalJob.status.in_(("pending", "processing")),
        )
        .values(status="succeeded", result_ref=result_ref)
    )
    session.commit()
    if outcome.rowcount == 1:
        return result_ref

    winner = session.get(LogicalJob, job_id, populate_existing=True)
    if winner is None:
        raise LogicalJobStateError("logical job disappeared during completion")
    existing = successful_result_ref(winner)
    if existing is None:
        raise LogicalJobStateError("logical job completion lost without a winner")
    return existing


def claim_logical_job_failure(
    session: Session,
    *,
    job_id: uuid.UUID,
) -> LogicalJobFailureClaim:
    outcome = session.execute(
        update(LogicalJob)
        .where(
            LogicalJob.id == job_id,
            LogicalJob.result_ref.is_(None),
            LogicalJob.status.in_(("pending", "processing")),
        )
        .values(status="failed")
        .execution_options(synchronize_session=False)
    )
    if outcome.rowcount == 1:
        refreshed = session.get(LogicalJob, job_id, populate_existing=True)
        if refreshed is None:
            raise LogicalJobStateError(
                "logical job disappeared after failure claim"
            )
        return LogicalJobFailureClaim(
            owns_failure=True,
            successful_result_ref=None,
        )

    existing = session.get(LogicalJob, job_id, populate_existing=True)
    if existing is None:
        raise LogicalJobStateError("logical job disappeared during failure claim")
    if existing.status == "succeeded":
        return LogicalJobFailureClaim(
            owns_failure=False,
            successful_result_ref=successful_result_ref(existing),
        )
    if existing.status == "failed" and existing.result_ref is None:
        return LogicalJobFailureClaim(
            owns_failure=False,
            successful_result_ref=None,
        )
    raise LogicalJobStateError("logical job failure claim found inconsistent state")
