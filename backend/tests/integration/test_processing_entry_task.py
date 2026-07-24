from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Iterator
from hashlib import sha256
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.config import Settings
from app.db import engine
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.processing import tasks
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


class PassingPreflight:
    def check(self) -> None:
        return None


@pytest.fixture
def database_connection() -> Iterator[Connection]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    try:
        yield connection
    finally:
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def task_session_factory(
    database_connection: Connection,
) -> Callable[[], Session]:
    def factory() -> Session:
        return Session(
            bind=database_connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

    return factory


def _write_candidate_pdf(path: Path) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=200.0, height=200.0)
    page.insert_text((20.0, 30.0), "M6")
    document.save(path)
    document.close()
    return path.read_bytes()


def _project_source(
    session: Session,
    storage: LocalFileStorage,
    tmp_path: Path,
) -> tuple[Project, StoredFile]:
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    content = _write_candidate_pdf(tmp_path / f"{project.id}.pdf")
    stored = storage.write_verified(
        f"projects/{project.id}/source.pdf",
        content,
        sha256(content).hexdigest(),
    )
    source_file = StoredFile(
        resource_ref=stored.resource_ref,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        mime_type="application/pdf",
    )
    session.add_all([project, source_file])
    session.commit()
    return project, source_file


def _configure_task(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory: Callable[[], Session],
    storage_root: Path,
    external_calls: list[str],
) -> None:
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(storage_root=storage_root),
    )
    monkeypatch.setattr(
        tasks,
        "ProcessingPreflight",
        lambda *_args, **_kwargs: PassingPreflight(),
    )
    monkeypatch.setattr(tasks.Redis, "from_url", lambda *_args, **_kwargs: object())

    def forbidden_provider_factory(_settings: Settings):
        external_calls.append("ocr-provider")
        raise AssertionError("vector processing must not construct the OCR Provider")

    monkeypatch.setattr(tasks, "OCR_PROVIDER_FACTORY", forbidden_provider_factory)


def _counts(session: Session, project_id: uuid.UUID) -> dict[str, int]:
    return {
        "raw": session.scalar(
            select(func.count())
            .select_from(AutomaticResult)
            .where(AutomaticResult.project_id == project_id)
        ),
        "job": session.scalar(
            select(func.count())
            .select_from(LogicalJob)
            .where(LogicalJob.project_id == str(project_id))
        ),
        "working": session.scalar(
            select(func.count())
            .select_from(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.project_id == project_id)
        ),
        "error": session.scalar(
            select(func.count())
            .select_from(ErrorRecord)
            .where(ErrorRecord.project_id == project_id)
        ),
    }


def test_canonical_task_creates_one_review_working_copy_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(setup, storage, tmp_path)
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    key = f"product-process:{project.id}"

    first = inventory_project.run(str(project.id), source.resource_ref, key)
    second = inventory_project.run(str(project.id), source.resource_ref, key)

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        working = verify.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project.id
            )
        )
        job = verify.scalar(
            select(LogicalJob).where(LogicalJob.project_id == str(project.id))
        )
        assert raw is not None
        assert working is not None
        assert job is not None
        assert first == second == f"automatic-result://{raw.id}"
        assert working.raw_result_id == raw.id
        assert verify.get(Project, project.id).state == ProjectState.EDITING
        assert job.status == "succeeded"
        assert job.result_ref == first
        assert _counts(verify, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 1,
            "error": 0,
        }
        assert external_calls == []
        assert inventory_project.name == "quality_inspection.inventory_project"
        assert tuple(inspect.signature(inventory_project.run).parameters) == (
            "project_id",
            "source_ref",
            "logical_task_key",
        )
    finally:
        verify.close()


def test_review_bootstrap_failure_is_sanitized_durable_and_retry_safe(
    monkeypatch: pytest.MonkeyPatch,
    task_session_factory: Callable[[], Session],
    tmp_path: Path,
) -> None:
    storage = LocalFileStorage(tmp_path / "storage")
    setup = task_session_factory()
    project, source = _project_source(setup, storage, tmp_path)
    setup.close()
    external_calls: list[str] = []
    _configure_task(
        monkeypatch,
        session_factory=task_session_factory,
        storage_root=storage.root,
        external_calls=external_calls,
    )
    original_create = ReviewService.create_from_raw
    private_detail = "/srv/private/customer.pdf credential=do-not-leak"

    def fail_bootstrap(_service: ReviewService, _raw_id: uuid.UUID):
        raise RuntimeError(private_detail)

    monkeypatch.setattr(ReviewService, "create_from_raw", fail_bootstrap)
    key = f"product-process:{project.id}"

    with pytest.raises(RuntimeError, match="do-not-leak"):
        inventory_project.run(str(project.id), source.resource_ref, key)
    with pytest.raises(RuntimeError, match="do-not-leak"):
        inventory_project.run(str(project.id), source.resource_ref, key)

    verify = task_session_factory()
    try:
        raw = verify.scalar(
            select(AutomaticResult).where(AutomaticResult.project_id == project.id)
        )
        job = verify.scalar(
            select(LogicalJob).where(LogicalJob.project_id == str(project.id))
        )
        error = verify.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        assert raw is not None
        assert job is not None
        assert job.status == "succeeded"
        assert job.result_ref == f"automatic-result://{raw.id}"
        assert verify.get(Project, project.id).state == ProjectState.READY_FOR_EDIT
        assert _counts(verify, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 0,
            "error": 1,
        }
        assert error is not None
        assert error.code == "review_bootstrap_failed"
        assert error.message == "Review working copy could not be prepared"
        assert error.severity == "blocking"
        assert error.stage == "review_bootstrap"
        assert error.location_ref is None
        assert error.cause_category == "processing_defect"
        assert private_detail not in error.message
        assert external_calls == []
    finally:
        verify.close()

    monkeypatch.setattr(ReviewService, "create_from_raw", original_create)
    result_ref = inventory_project.run(str(project.id), source.resource_ref, key)

    recovered = task_session_factory()
    try:
        assert result_ref.startswith("automatic-result://")
        assert recovered.get(Project, project.id).state == ProjectState.EDITING
        assert _counts(recovered, project.id) == {
            "raw": 1,
            "job": 1,
            "working": 1,
            "error": 1,
        }
        assert external_calls == []
    finally:
        recovered.close()
