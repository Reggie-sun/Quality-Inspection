from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

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
from app.review.models import ReviewedResult
from app.review.service import ReviewConfirmationBlocked, ReviewService
from app.review.locks import acquire_lock
from app.storage.models import StoredFile
from tests.integration.test_balloon_service import (
    BalloonContext,
    make_balloon_context,
)


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
    acquire_lock(db_session, working.project_id, "quality-1")
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


def test_item_set_freeze_does_not_create_reviewed_result(
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    service = ReviewService(db_session)
    working = service.create_from_raw(raw_result.id)
    acquire_lock(db_session, working.project_id, "quality-1")
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_balloon_required",
            "item_id": working.items[0]["item_id"],
            "balloon_required": True,
        },
    )

    service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )

    assert service.reviewed_result_for(working.project_id) is None
    assert service.get_working_copy(working.id).items_frozen_at is not None


@pytest.fixture
def completed_balloon_review(
    db_session: Session,
    tmp_path: Path,
) -> BalloonContext:
    context = make_balloon_context(db_session, tmp_path, frozen=True)
    context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    return context


def test_reviewed_result_is_immutable(
    completed_balloon_review: BalloonContext,
) -> None:
    """P0-RES-003: confirm creates one immutable reviewed result."""
    context = completed_balloon_review
    balloons = [
        balloon
        for balloon in context.balloon_service.list_for_project(
            context.working_copy.project_id
        )
        if balloon.status == "active"
    ]
    reordered = context.balloon_service.reorder(
        balloons[0].id,
        sort_order=50,
        expected_version=balloons[0].version,
        operator_id="quality-1",
    )
    with pytest.raises(ReviewConfirmationBlocked) as stale_error:
        context.review_service.confirm(
            context.working_copy.id,
            expected_version=context.working_copy.version,
            operator_id="quality-1",
        )
    assert stale_error.value.code == "numbering_stale"

    renumbered = context.balloon_service.renumber(
        context.working_copy.project_id,
        ordered_balloon_ids=[balloons[1].id, reordered.id],
        expected_versions={
            balloons[1].id: balloons[1].version,
            reordered.id: reordered.version,
        },
        operator_id="quality-1",
    )
    reviewed = context.review_service.confirm(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    duplicate = context.review_service.confirm(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )

    assert duplicate.id == reviewed.id
    assert context.session.get(Project, context.working_copy.project_id).state == (
        ProjectState.REVIEWED
    )
    with pytest.raises(RuntimeError, match="immutable reviewed result"):
        context.review_service.replace_items(reviewed.id, [])

    mutation_calls = [
        lambda: context.balloon_service.generate_formal(
            context.working_copy.project_id,
            expected_version=context.working_copy.version,
            operator_id="quality-1",
        ),
        lambda: context.balloon_service.move(
            renumbered[0].id,
            center_pdf=(70, 80),
            expected_version=renumbered[0].version,
            operator_id="quality-1",
        ),
        lambda: context.balloon_service.delete(
            renumbered[0].id,
            expected_version=renumbered[0].version,
            operator_id="quality-1",
        ),
        lambda: context.balloon_service.rebuild(
            renumbered[0].id,
            expected_version=renumbered[0].version,
            operator_id="quality-1",
        ),
        lambda: context.balloon_service.reorder(
            renumbered[0].id,
            sort_order=99,
            expected_version=renumbered[0].version,
            operator_id="quality-1",
        ),
        lambda: context.balloon_service.renumber(
            context.working_copy.project_id,
            ordered_balloon_ids=[value.id for value in renumbered],
            expected_versions={value.id: value.version for value in renumbered},
            operator_id="quality-1",
        ),
    ]
    for mutate in mutation_calls:
        with pytest.raises(RuntimeError, match="finalized"):
            mutate()

    reviewed.items = []
    with pytest.raises(IntegrityError, match="immutable"):
        context.session.commit()
    context.session.rollback()

    persisted = context.session.get(ReviewedResult, reviewed.id)
    assert persisted is not None
    assert persisted.items
