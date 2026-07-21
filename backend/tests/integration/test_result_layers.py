from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.candidates.coverage import CoverageEntry, check_coverage
from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.processing.automatic_result import build_automatic_result
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


@pytest.fixture
def raw_result(db_session: Session) -> AutomaticResult:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source_file = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="0" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key="process:immutable-result",
    )
    db_session.add_all([project, source_file, job])
    db_session.commit()
    coverage = check_coverage(
        [
            CoverageEntry(
                "observation-1",
                "candidate",
                "page-0:observation-1",
                (1, 2, 3, 4),
                candidate_id="candidate-1",
            )
        ],
        expected_observation_ids={"observation-1"},
    )

    return build_automatic_result(
        db_session,
        project_id=project.id,
        source_file_id=source_file.id,
        logical_job_id=job.id,
        inventory_ref=f"asset://tests/{project.id}/inventory.json",
        candidates=[
            {
                "candidate_id": "candidate-1",
                "payload": {"raw_text": "M6", "item_type": "thread"},
                "source_location_ids": ["page-0:observation-1"],
            }
        ],
        coverage=coverage,
        provider_call_ids=[],
    )


def test_raw_result_is_immutable(
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    """P0-RES-001: database vetoes UPDATE and DELETE of raw automatic facts."""
    raw_result.candidates = []
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    persisted = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.id == raw_result.id)
    )
    assert persisted is not None
    db_session.delete(persisted)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.id == raw_result.id)
    ) is not None


def test_working_copy_is_versioned(
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    """P0-RES-002: review is a separate, saveable, versioned result layer."""
    service = ReviewService(db_session)
    working = service.create_from_raw(raw_result.id)
    before_version = working.version
    saved = service.apply(
        working.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={"type": "keep", "item_id": working.items[0]["item_id"]},
    )

    assert saved.id == working.id
    assert saved.raw_result_id == raw_result.id
    assert saved.version == before_version + 1
