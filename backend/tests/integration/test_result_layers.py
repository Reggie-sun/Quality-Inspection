from __future__ import annotations

import copy
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
from app.review.service import FreezeBlocked, ReviewConfirmationBlocked, ReviewService
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
                advisor_review={
                    "provider_role": "advisor",
                    "validated": True,
                },
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
                "advisor_review": {
                    "provider_role": "advisor",
                    "validated": True,
                },
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
    assert "advisor_review" in raw_result.candidates[0]
    assert all("advisor_review" not in item for item in working.items)
    assert all(
        "advisor_review" not in entry
        for entry in working.coverage.get("entries", [])
    )


def test_new_symbol_result_does_not_mutate_existing_text_only_raw_result(
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    """A new visual result and working copy cannot rewrite an older raw result."""
    original_candidates = copy.deepcopy(raw_result.candidates)
    original_coverage = copy.deepcopy(raw_result.coverage)
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    source_file = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="1" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key="process:new-symbol-result",
    )
    db_session.add_all([project, source_file, job])
    db_session.commit()
    coverage = check_coverage(
        [
            CoverageEntry(
                "visual-no-detection",
                "ambiguous",
                "visual-no-detection",
                (10, 20, 30, 40),
                requires_confirmation=True,
                advisor_review={
                    "route": "visual_symbol",
                    "schema_version": "visual-symbol-review/1",
                    "symbol_kinds": [],
                    "rejection_code": "visual_no_detection",
                },
            )
        ],
        expected_observation_ids={"visual-no-detection"},
        required_visual_observation_ids={"visual-no-detection"},
    )
    symbol_result = build_automatic_result(
        db_session,
        project_id=project.id,
        source_file_id=source_file.id,
        logical_job_id=job.id,
        inventory_ref=f"asset://tests/{project.id}/inventory.json",
        candidates=[],
        coverage=coverage,
        provider_call_ids=["fixture-symbol-request"],
    )

    working = ReviewService(db_session).create_from_raw(symbol_result.id)
    persisted_old = db_session.get(AutomaticResult, raw_result.id)

    assert persisted_old is not None
    assert persisted_old.candidates == original_candidates
    assert persisted_old.coverage == original_coverage
    assert symbol_result.coverage["entries"][0]["advisor_review"] == {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/1",
        "symbol_kinds": [],
        "rejection_code": "visual_no_detection",
    }
    assert working.items == []
    assert working.coverage["entries"][0]["symbol_kinds"] == []
    assert (
        working.coverage["entries"][0]["rejection_code"]
        == "visual_no_detection"
    )
    assert "advisor_review" not in working.coverage["entries"][0]


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
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": working.items[0]["item_id"],
            "inspection_item": "M6",
            "inspection_standard": "6H",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        },
    )
    working = service.apply(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "LAYERS-001",
            "material": "steel",
            "revision": "A",
        },
    )

    service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )

    assert service.reviewed_result_for(working.project_id) is None
    assert service.get_working_copy(working.id).items_frozen_at is not None


def test_review_remarks_persist_without_mutating_raw_or_export_contract(
    db_session: Session,
    tmp_path: Path,
) -> None:
    context = make_balloon_context(db_session, tmp_path, frozen=False)
    working = context.review_service.apply(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
        command={
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6",
            "inspection_standard": "confirmed M6",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
            "remarks": "现场复核量具",
        },
    )
    working = context.review_service.freeze_items(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    context.balloon_service.generate_formal(
        working.project_id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    reviewed = context.review_service.confirm(
        working.id,
        expected_version=working.version,
        operator_id="quality-1",
    )
    raw = db_session.get(AutomaticResult, working.raw_result_id)

    assert reviewed.items[0]["remarks"] == "现场复核量具"
    assert raw is not None
    assert raw.candidates[0]["payload"].get("remarks") is None


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


@pytest.mark.parametrize(
    "missing",
    ["metadata", "details"],
)
def test_freeze_rejects_incomplete_sip_snapshot_and_remains_recoverable(
    db_session: Session,
    tmp_path: Path,
    missing: str,
) -> None:
    """P0-EXP-007E keeps an incomplete SIP draft editable before freeze."""
    context = make_balloon_context(db_session, tmp_path, frozen=False)
    if missing == "metadata":
        context.working_copy.sip_metadata = {}
    else:
        items = copy.deepcopy(context.working_copy.items)
        items[0].pop("sip_detail_fields_confirmed")
        context.working_copy.items = items
    db_session.commit()

    with pytest.raises(FreezeBlocked) as error:
        context.review_service.freeze_items(
            context.working_copy.id,
            expected_version=context.working_copy.version,
            operator_id="quality-1",
        )

    assert error.value.code == "unresolved_confirmation"
    current = context.review_service.get_working_copy(context.working_copy.id)
    assert current.items_frozen_at is None
    if missing == "metadata":
        command = {
            "type": "set_sip_metadata",
            "material_code": "MAT-001",
            "material_name": "fixture",
            "drawing_number": "D5-FIXTURE",
            "material": "steel",
            "revision": "A",
        }
    else:
        command = {
            "type": "set_sip_detail_fields",
            "item_id": "i1",
            "inspection_item": "M6",
            "inspection_standard": "confirmed M6",
            "inspection_method": "thread gauge",
            "key_dimension": "yes",
            "inspection_role": "IPQC",
            "source_page": 1,
        }
    recovered = context.review_service.apply(
        current.id,
        expected_version=current.version,
        operator_id="quality-1",
        command=command,
    )
    frozen = context.review_service.freeze_items(
        recovered.id,
        expected_version=recovered.version,
        operator_id="quality-1",
    )

    assert frozen.items_frozen_at is not None


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
    assert reviewed.schema_version == "reviewed-result/2"
    assert reviewed.sip_metadata == {
        "material_code": "MAT-001",
        "material_name": "fixture",
        "drawing_number": "D5-FIXTURE",
        "material": "steel",
        "revision": "A",
    }
    assert all(
        item["sip_detail_fields_confirmed"] is True
        for item in reviewed.items
    )
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
