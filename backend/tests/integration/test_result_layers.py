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
from app.processing.automatic_result import (
    LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION,
    build_automatic_result,
)
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
        schema_version=LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION,
    )


def _insert_partial_raw_result(db_session: Session) -> AutomaticResult:
    assert "completeness" in AutomaticResult.__table__.c
    project_id = uuid.uuid4()
    source_file_id = uuid.uuid4()
    job_id = uuid.uuid4()
    result_id = uuid.uuid4()
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
                logical_task_key=f"process:partial-result:{project_id}",
                status="succeeded",
                result_ref=f"automatic-result://{result_id}",
            ),
        ]
    )
    db_session.flush()
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
                    "raw_text": "M6",
                    "item_type": "thread",
                },
                "source_location_ids": ["page-0:observation-1"],
                "advisor_review": {
                    "provider_role": "advisor",
                    "validated": True,
                },
            }
        ],
        coverage={
            "blocking_count": 0,
            "review_required_count": 1,
            "coverage_checked": True,
            "blocking_observation_ids": [],
            "entries": [
                {
                    "observation_id": "observation-1",
                    "disposition": "candidate",
                    "source_location_id": "page-0:observation-1",
                    "coordinates": [1, 2, 3, 4],
                    "candidate_id": "candidate-1",
                    "requires_confirmation": True,
                    "advisor_review": {
                        "provider_role": "advisor",
                        "validated": True,
                    },
                }
            ],
            "relations": [],
        },
        provider_call_ids=[],
        schema_version=LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION,
        completeness="partial_review_required",
    )
    db_session.add(result)
    db_session.commit()
    return result


def _fresh_process_inputs(
    db_session: Session,
    *,
    recognition_mode: str,
    recognition_router_version: str,
) -> tuple[Project, StoredFile, LogicalJob, object]:
    project = Project(
        id=uuid.uuid4(),
        state=ProjectState.PROCESSING,
        recognition_mode=recognition_mode,
        recognition_router_version=recognition_router_version,
    )
    source_file = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="0" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )
    job = LogicalJob(
        project_id=str(project.id),
        logical_task_key=f"process:terminal-provenance:{project.id}",
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
                advisor_review={"provider_role": "advisor", "validated": True},
            )
        ],
        expected_observation_ids={"observation-1"},
    )
    return project, source_file, job, coverage


def _terminal_provenance_result(
    db_session: Session,
    *,
    project: Project,
    source_file: StoredFile,
    job: LogicalJob,
    coverage: object,
    recognition_mode: str,
    router_version: str,
    recognition_summary: dict[str, object] | None,
    recognition_evidence_ref: str | None,
    completeness: str = "complete",
) -> AutomaticResult:
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
                "advisor_review": {"provider_role": "advisor", "validated": True},
            }
        ],
        coverage=coverage,  # type: ignore[arg-type]
        provider_call_ids=[],
        schema_version=LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION,
        completeness=completeness,
        recognition_mode=recognition_mode,
        router_version=router_version,
        recognition_summary=recognition_summary,
        recognition_evidence_ref=recognition_evidence_ref,
    )


def test_terminal_result_refuses_locked_project_provenance_mismatch(
    db_session: Session,
) -> None:
    project, source_file, job, coverage = _fresh_process_inputs(
        db_session,
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )

    with pytest.raises(ValueError, match="recognition_mode"):
        _terminal_provenance_result(
            db_session,
            project=project,
            source_file=source_file,
            job=job,
            coverage=coverage,
            recognition_mode="shadow_uncertainty",
            router_version="symbol-uncertainty-router/1",
            recognition_summary={
                "schema_version": "symbol-recognition-summary/1",
                "unresolved_roi_count": 0,
            },
            recognition_evidence_ref=(
                f"symbol-routing-evidence://{project.id}"
            ),
        )

    assert db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.logical_job_id == job.id)
    ) is None
    assert db_session.get(LogicalJob, job.id).status == "pending"  # type: ignore[union-attr]
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("completeness", "unresolved_roi_count"),
    (
        ("complete", 1),
        ("partial_review_required", 0),
    ),
)
def test_terminal_result_rejects_inconsistent_completeness_summary(
    db_session: Session,
    completeness: str,
    unresolved_roi_count: int,
) -> None:
    project, source_file, job, coverage = _fresh_process_inputs(
        db_session,
        recognition_mode="production_uncertainty",
        recognition_router_version="symbol-uncertainty-router/1",
    )

    with pytest.raises(ValueError, match="completeness"):
        _terminal_provenance_result(
            db_session,
            project=project,
            source_file=source_file,
            job=job,
            coverage=coverage,
            completeness=completeness,
            recognition_mode="production_uncertainty",
            router_version="symbol-uncertainty-router/1",
            recognition_summary={
                "schema_version": "symbol-recognition-summary/1",
                "unresolved_roi_count": unresolved_roi_count,
            },
            recognition_evidence_ref=(
                f"symbol-routing-evidence://{project.id}"
            ),
        )

    assert db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.logical_job_id == job.id)
    ) is None
    assert db_session.get(LogicalJob, job.id).status == "pending"  # type: ignore[union-attr]
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING  # type: ignore[union-attr]


def test_terminal_result_requires_summary_for_partial_completeness(
    db_session: Session,
) -> None:
    project, source_file, job, coverage = _fresh_process_inputs(
        db_session,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    with pytest.raises(ValueError, match="recognition_summary"):
        _terminal_provenance_result(
            db_session,
            project=project,
            source_file=source_file,
            job=job,
            coverage=coverage,
            completeness="partial_review_required",
            recognition_mode="legacy_high_recall",
            router_version="legacy",
            recognition_summary=None,
            recognition_evidence_ref=None,
        )

    assert db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.logical_job_id == job.id)
    ) is None
    assert db_session.get(LogicalJob, job.id).status == "pending"  # type: ignore[union-attr]
    assert db_session.get(Project, project.id).state == ProjectState.PROCESSING  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("recognition_mode", "summary", "evidence_ref", "message"),
    (
        (
            "production_uncertainty",
            {
                "schema_version": "symbol-recognition-summary/1",
                "unresolved_roi_count": 0,
                "extra": True,
            },
            "expected",
            "recognition_summary",
        ),
        (
            "production_uncertainty",
            {
                "schema_version": "symbol-recognition-summary/1",
                "unresolved_roi_count": 0,
            },
            "unexpected",
            "recognition_evidence_ref",
        ),
        (
            "shadow_uncertainty",
            {
                "schema_version": "symbol-recognition-summary/1",
                "unresolved_roi_count": 0,
            },
            "unexpected",
            "recognition_evidence_ref",
        ),
    ),
)
def test_terminal_result_rejects_invalid_routed_provenance(
    db_session: Session,
    recognition_mode: str,
    summary: dict[str, object],
    evidence_ref: str,
    message: str,
) -> None:
    project, source_file, job, coverage = _fresh_process_inputs(
        db_session,
        recognition_mode=recognition_mode,
        recognition_router_version="symbol-uncertainty-router/1",
    )
    expected_evidence_ref = f"symbol-routing-evidence://{project.id}"

    with pytest.raises(ValueError, match=message):
        _terminal_provenance_result(
            db_session,
            project=project,
            source_file=source_file,
            job=job,
            coverage=coverage,
            recognition_mode=recognition_mode,
            router_version="symbol-uncertainty-router/1",
            recognition_summary=summary,
            recognition_evidence_ref=(
                expected_evidence_ref
                if evidence_ref == "expected"
                else "symbol-routing-evidence://another-project"
            ),
        )

    assert db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.logical_job_id == job.id)
    ) is None
    assert db_session.get(LogicalJob, job.id).status == "pending"  # type: ignore[union-attr]


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


def test_legacy_result_reads_as_complete(
    raw_result: AutomaticResult,
    db_session: Session,
) -> None:
    """PRT-5 keeps reader-first compatibility for pre-completeness rows."""
    result_id = raw_result.id
    db_session.expunge(raw_result)

    persisted = db_session.get(AutomaticResult, result_id)

    assert persisted is not None
    assert getattr(persisted, "completeness", None) == "complete"


def test_partial_result_is_immutable_and_creates_exactly_one_working_copy(
    db_session: Session,
) -> None:
    """PRT-5 persists one reviewable partial result without a second copy."""
    raw_result = _insert_partial_raw_result(db_session)
    service = ReviewService(db_session)

    first = service.create_from_raw(raw_result.id)
    second = service.create_from_raw(raw_result.id)

    assert second.id == first.id
    result_id = raw_result.id
    db_session.expunge(raw_result)
    persisted = db_session.get(AutomaticResult, result_id)
    assert persisted is not None
    assert getattr(persisted, "completeness", None) == (
        "partial_review_required"
    )


def test_partial_result_completeness_is_immutable(
    db_session: Session,
) -> None:
    """PRT-5 completeness is part of the immutable automatic-result fact."""
    raw_result = _insert_partial_raw_result(db_session)
    setattr(raw_result, "completeness", "complete")

    with pytest.raises(IntegrityError):
        db_session.commit()


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
                    "schema_version": "visual-symbol-review/3",
                    "symbol_kinds": [],
                    "rejection_code": "visual_no_detection",
                    "confidence_signal": None,
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
        schema_version=LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION,
    )

    working = ReviewService(db_session).create_from_raw(symbol_result.id)
    persisted_old = db_session.get(AutomaticResult, raw_result.id)

    assert persisted_old is not None
    assert persisted_old.candidates == original_candidates
    assert persisted_old.coverage == original_coverage
    assert symbol_result.coverage["entries"][0]["advisor_review"] == {
        "route": "visual_symbol",
        "schema_version": "visual-symbol-review/3",
        "symbol_kinds": [],
        "rejection_code": "visual_no_detection",
        "confidence_signal": None,
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


def test_rejected_confirmation_never_enters_reviewed_export_source(
    db_session: Session,
    tmp_path: Path,
) -> None:
    context = make_balloon_context(db_session, tmp_path, frozen=False)
    before_version = context.working_copy.version

    rejected = context.review_service.apply(
        context.working_copy.id,
        expected_version=before_version,
        operator_id="quality-1",
        command={
            "type": "resolve_confirmation",
            "item_id": "i1",
            "accepted": False,
        },
    )

    assert rejected.version == before_version + 1
    assert rejected.numbering_stale is True
    rejected_item = next(
        item for item in rejected.items if item["item_id"] == "i1"
    )
    assert rejected_item["status"] == "excluded"
    assert rejected_item["active"] is False

    frozen = context.review_service.freeze_items(
        rejected.id,
        expected_version=rejected.version,
        operator_id="quality-1",
    )
    generated = context.balloon_service.generate_formal(
        frozen.project_id,
        expected_version=frozen.version,
        operator_id="quality-1",
    )
    reviewed = context.review_service.confirm(
        frozen.id,
        expected_version=frozen.version,
        operator_id="quality-1",
    )

    assert [item["item_id"] for item in reviewed.items] == ["i2"]
    assert [balloon.inspection_item_id for balloon in generated] == ["i2"]
    assert [
        balloon["inspection_item_id"] for balloon in reviewed.balloons
    ] == ["i2"]


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
    assert reviewed.schema_version == "reviewed-result/3"
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
