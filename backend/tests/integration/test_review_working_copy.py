from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import acquire_lock
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
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
    result = AutomaticResult(
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
    db_session.add(result)
    db_session.commit()
    return result


def test_original_is_immutable_and_current_is_separate(
    db_session: Session,
    raw_result: AutomaticResult,
) -> None:
    """P0-REV-001: raw candidates and mutable current items are separate layers."""
    original = copy.deepcopy(raw_result.candidates)
    service = ReviewService(db_session)
    working = service.create_from_raw(raw_result.id)
    acquire_lock(db_session, working.project_id, "quality-1")
    service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={"type": "edit", "item_id": "candidate-1", "fields": {"raw_text": "M6 通"}},
    )

    persisted = db_session.get(AutomaticResult, raw_result.id)
    assert persisted is not None
    assert persisted.candidates == original
    assert working.raw_result_id == raw_result.id
    assert working.items is not persisted.candidates


def test_create_working_copy_moves_ready_project_to_editing(
    db_session: Session,
    raw_result: AutomaticResult,
) -> None:
    working = ReviewService(db_session).create_from_raw(raw_result.id)

    project = db_session.get(Project, raw_result.project_id)
    assert project is not None
    assert project.state == ProjectState.EDITING
    assert working.project_id == project.id


def test_visual_coverage_exposes_only_owner_committed_discriminator() -> None:
    diagnostics = (
        {
            "route": "visual_symbol",
            "schema_version": "visual-symbol-review/1",
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
        },
        {
            "route": "visual_symbol",
            "schema_version": "visual-symbol-review/2",
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
            "confidence_signal": None,
        },
    )
    for diagnostic in diagnostics:
        projected = ReviewService._review_coverage({
            "blocking_count": 0,
            "review_required_count": 1,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [
                {
                    "observation_id": "visual-source",
                    "disposition": "ambiguous",
                    "source_location_id": "visual-source",
                    "coordinates": [1, 2, 3, 4],
                    "candidate_id": None,
                    "requires_confirmation": True,
                    "advisor_review": diagnostic,
                }
            ],
        })

        assert projected["entries"] == [
            {
                "observation_id": "visual-source",
                "disposition": "ambiguous",
                "source_location_id": "visual-source",
                "coordinates": [1, 2, 3, 4],
                "candidate_id": None,
                "requires_confirmation": True,
                "symbol_kinds": [],
                "rejection_code": "visual_no_detection",
            }
        ]
