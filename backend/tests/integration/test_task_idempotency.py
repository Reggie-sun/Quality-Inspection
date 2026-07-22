import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.candidates.coverage import check_coverage
from app.candidates.models import AutomaticResult
from app.db import SessionLocal, engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import (
    LogicalJob,
    LogicalJobStateError,
    claim_logical_job,
    complete_logical_job,
)
from app.processing.automatic_result import (
    automatic_result_ref,
    build_automatic_result,
)
from app.processing.pipeline import InventoryPipeline
from app.projects.models import Project
from app.projects.state import ProjectState
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


@dataclass(frozen=True)
class InventoryPageStub:
    support_level: str

    def to_dict(self) -> dict[str, str]:
        return {"support_level": self.support_level}


class PassingPreflight:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def check(self) -> None:
        self._events.append("preflight")


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def transactional_db_session() -> Iterator[Session]:
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


def _freeze_empty_automatic_result(
    session: Session,
    *,
    project: Project,
    source_file: StoredFile,
    job: LogicalJob,
    inventory_ref: str,
) -> AutomaticResult:
    return build_automatic_result(
        session,
        project_id=project.id,
        source_file_id=source_file.id,
        logical_job_id=job.id,
        inventory_ref=inventory_ref,
        candidates=[],
        coverage=check_coverage([], expected_observation_ids=set()),
        provider_call_ids=[],
    )


def test_duplicate_delivery_returns_the_same_job(db_session: Session) -> None:
    """P0-RUN-010 deduplicates one logical task key within a project."""
    project_id = f"p0-test-{uuid.uuid4()}"
    logical_task_key = "process:sha256"

    try:
        first = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )
        second = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )

        assert second.id == first.id
    finally:
        db_session.rollback()
        db_session.execute(
            delete(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        db_session.commit()


def test_first_successful_result_ref_wins(db_session: Session) -> None:
    """P0-RUN-010 compare-safe completion never overwrites the first raw result."""
    project_id = f"p0-test-{uuid.uuid4()}"
    logical_task_key = "inventory:sha256"
    try:
        job = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )

        first_ref = complete_logical_job(
            db_session,
            job_id=job.id,
            result_ref="asset://projects/winner/inventory.json",
        )
        second_ref = complete_logical_job(
            db_session,
            job_id=job.id,
            result_ref="asset://projects/loser/inventory.json",
        )

        assert first_ref == "asset://projects/winner/inventory.json"
        assert second_ref == first_ref
        assert db_session.scalar(
            select(func.count()).select_from(LogicalJob).where(
                LogicalJob.project_id == project_id,
                LogicalJob.logical_task_key == logical_task_key,
            )
        ) == 1
    finally:
        db_session.rollback()
        db_session.execute(
            delete(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        db_session.commit()


def test_losing_session_refreshes_the_successful_result_ref(
    db_session: Session,
) -> None:
    """P0-RUN-010 returns the winner even when the loser cached pending state."""
    project_id = f"p0-test-{uuid.uuid4()}"
    logical_task_key = "inventory:two-sessions"
    losing_session = SessionLocal()
    try:
        job = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )
        cached_loser = losing_session.get(LogicalJob, job.id)
        assert cached_loser is not None
        assert cached_loser.status == "pending"

        winner = complete_logical_job(
            db_session,
            job_id=job.id,
            result_ref="asset://projects/winner/inventory.json",
        )
        observed = complete_logical_job(
            losing_session,
            job_id=job.id,
            result_ref="asset://projects/loser/inventory.json",
        )

        assert observed == winner
    finally:
        losing_session.rollback()
        losing_session.close()
        db_session.rollback()
        db_session.execute(
            delete(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        db_session.commit()


def test_completed_duplicate_skips_preflight_and_pdf_read(
    transactional_db_session: Session,
) -> None:
    """P0-RUN-010 duplicate success returns before capability or source work."""
    db_session = transactional_db_session
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    logical_task_key = "inventory:completed"
    source_file = StoredFile(
        resource_ref=f"asset://projects/{project.id}/source.pdf",
        sha256="0" * 64,
        size_bytes=1,
        mime_type="application/pdf",
    )

    class MustNotRun:
        def __getattr__(self, _name):
            raise AssertionError("completed duplicate performed new work")

    job = LogicalJob(
        project_id=project_id,
        logical_task_key=logical_task_key,
    )
    db_session.add_all([project, source_file, job])
    db_session.commit()
    winner = _freeze_empty_automatic_result(
        db_session,
        project=project,
        source_file=source_file,
        job=job,
        inventory_ref=f"asset://projects/{project.id}/inventory.json",
    )
    pipeline = InventoryPipeline(
        db_session,
        MustNotRun(),
        MustNotRun(),
        inventory_builder=MustNotRun(),
    )

    assert pipeline.run(
        project_id,
        source_file.resource_ref,
        logical_task_key,
    ) == automatic_result_ref(winner)


def test_inventory_only_completion_is_not_a_pipeline_winner(
    db_session: Session,
) -> None:
    """D3-T2 rejects the retired D2 inventory ref as a formal process result."""
    project_id = f"p0-test-{uuid.uuid4()}"
    logical_task_key = "inventory:retired-winner"
    try:
        job = claim_logical_job(
            db_session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )
        complete_logical_job(
            db_session,
            job_id=job.id,
            result_ref="asset://projects/retired/inventory.json",
        )

        with pytest.raises(LogicalJobStateError, match="automatic result"):
            InventoryPipeline(
                db_session,
                object(),
                object(),
            ).run(
                project_id,
                "asset://source.pdf",
                logical_task_key,
            )
    finally:
        db_session.rollback()
        db_session.execute(
            delete(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        db_session.commit()


def test_inventory_pipeline_persists_one_successful_raw_result(
    transactional_db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-RUN-010 persists one raw result and advances to ready-for-edit."""
    db_session = transactional_db_session
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    logical_task_key = "inventory:active-path"
    storage = LocalFileStorage(tmp_path)
    payload = b"fixture-pdf"
    source = storage.write_verified(
        "projects/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=source.resource_ref,
        sha256=source.sha256,
        size_bytes=source.size_bytes,
        mime_type="application/pdf",
    )
    events: list[str] = []

    def build_inventory(source_path: Path) -> tuple[InventoryPageStub, ...]:
        assert events == ["preflight"]
        assert source_path == source.path
        events.append("inventory")
        return (InventoryPageStub(support_level="supported"),)

    db_session.add_all([project, source_file])
    db_session.commit()
    result_ref = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight(events),
        inventory_builder=build_inventory,
    ).run(str(project.id), source.resource_ref, logical_task_key)

    job = db_session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == str(project.id),
            LogicalJob.logical_task_key == logical_task_key,
        )
    )
    raw_result = db_session.scalar(
        select(AutomaticResult).where(AutomaticResult.project_id == project.id)
    )
    assert job is not None
    assert raw_result is not None
    assert job.status == "succeeded"
    assert job.result_ref == result_ref == f"automatic-result://{raw_result.id}"
    assert raw_result.source_file_id == source_file.id
    assert raw_result.candidates == []
    assert raw_result.coverage["coverage_checked"] is True
    assert events == ["preflight", "inventory"]
    assert json.loads(storage.read_bytes(raw_result.inventory_ref)) == {
        "pages": [{"support_level": "supported"}],
        "schema_version": "page-inventory/1",
    }
    assert db_session.get(Project, project.id).state == ProjectState.READY_FOR_EDIT


def test_losing_failure_cannot_overwrite_a_successful_result(
    transactional_db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-RUN-010 preserves a winner committed during duplicate processing."""
    db_session = transactional_db_session
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    logical_task_key = "inventory:success-vs-failure"
    storage = LocalFileStorage(tmp_path)
    source_payload = b"fixture-pdf"
    source = storage.write_verified(
        "projects/source.pdf",
        source_payload,
        sha256(source_payload).hexdigest(),
    )
    winner_payload = b'{"schema_version":"page-inventory/1","pages":[]}'
    winner = storage.write_verified(
        "projects/winner/inventory.json",
        winner_payload,
        sha256(winner_payload).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=source.resource_ref,
        sha256=source.sha256,
        size_bytes=source.size_bytes,
        mime_type="application/pdf",
    )
    winner_ref: list[str] = []

    def lose_after_winner_commits(_source_path: Path) -> tuple[InventoryPageStub, ...]:
        winner_job = db_session.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == project_id,
                LogicalJob.logical_task_key == logical_task_key,
            )
        )
        assert winner_job is not None
        raw_result = _freeze_empty_automatic_result(
            db_session,
            project=project,
            source_file=source_file,
            job=winner_job,
            inventory_ref=winner.resource_ref,
        )
        winner_ref.append(automatic_result_ref(raw_result))
        raise RuntimeError("duplicate worker failed after winner commit")

    db_session.add_all([project, source_file])
    db_session.commit()

    observed = InventoryPipeline(
        db_session,
        storage,
        PassingPreflight([]),
        inventory_builder=lose_after_winner_commits,
    ).run(project_id, source.resource_ref, logical_task_key)

    db_session.expire_all()
    job = db_session.scalar(
        select(LogicalJob).where(
            LogicalJob.project_id == project_id,
            LogicalJob.logical_task_key == logical_task_key,
        )
    )
    assert winner_ref
    assert observed == winner_ref[0]
    assert job is not None
    assert job.status == "succeeded"
    assert job.result_ref == winner_ref[0]
    assert db_session.get(Project, project.id).state == ProjectState.READY_FOR_EDIT
    assert db_session.scalar(
        select(func.count()).select_from(AutomaticResult).where(
            AutomaticResult.logical_job_id == job.id
        )
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ErrorRecord).where(
            ErrorRecord.project_id == project.id
        )
    ) == 0
