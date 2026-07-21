import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.capabilities.service import CapabilityUnavailable
from app.db import SessionLocal
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.processing.pipeline import InventoryPipeline, UnsupportedInput
from app.projects.models import Project
from app.projects.state import ProjectState
from app.storage.local import LocalFileStorage


@dataclass(frozen=True)
class UnsupportedPageStub:
    support_level: str = "unsupported"

    def to_dict(self) -> dict[str, str]:
        return {"support_level": self.support_level}


class PassingPreflight:
    def check(self) -> None:
        return None


class FailingPreflight:
    def __init__(self, code: str, detail: str) -> None:
        self._code = code
        self._detail = detail

    def check(self) -> None:
        raise CapabilityUnavailable(self._code, self._detail)


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_structured_error_envelope_round_trip(db_session: Session) -> None:
    """P0-RES-006 persists the stable error envelope and location ref."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    error = ErrorRecord(
        project_id=project.id,
        code="inventory_processing_failed",
        message="Page inventory processing failed",
        severity="blocking",
        stage="page_inventory",
        location_ref="asset://projects/source.pdf",
        cause_category="processing_defect",
    )
    try:
        db_session.add(project)
        db_session.flush()
        db_session.add(error)
        db_session.commit()
        db_session.expire_all()

        persisted = db_session.get(ErrorRecord, error.id)
        assert persisted is not None
        assert {
            "project_id": persisted.project_id,
            "code": persisted.code,
            "message": persisted.message,
            "severity": persisted.severity,
            "stage": persisted.stage,
            "location_ref": persisted.location_ref,
            "cause_category": persisted.cause_category,
        } == {
            "project_id": project.id,
            "code": "inventory_processing_failed",
            "message": "Page inventory processing failed",
            "severity": "blocking",
            "stage": "page_inventory",
            "location_ref": "asset://projects/source.pdf",
            "cause_category": "processing_defect",
        }
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()


def test_error_and_project_failure_commit_together(db_session: Session) -> None:
    """P0-RES-006 stores the error in the same transaction as failure state."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    try:
        db_session.add(project)
        db_session.flush()
        project.state = ProjectState.PROCESSING_FAILED
        db_session.add(
            ErrorRecord(
                project_id=project.id,
                code="inventory_processing_failed",
                message="Page inventory processing failed",
                severity="blocking",
                stage="page_inventory",
                location_ref=None,
                cause_category="processing_defect",
            )
        )
        db_session.commit()
        db_session.expire_all()

        assert db_session.get(Project, project.id).state == "processing_failed"
        assert (
            db_session.query(ErrorRecord)
            .filter(ErrorRecord.project_id == project.id)
            .one()
            .code
            == "inventory_processing_failed"
        )
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()


def test_unsupported_inventory_is_not_recorded_as_processing_failure(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-RES-006 keeps unsupported input distinct from processing failure."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    storage = LocalFileStorage(tmp_path)
    payload = b"fixture-pdf"
    source = storage.write_verified(
        "projects/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )
    try:
        db_session.add(project)
        db_session.commit()

        with pytest.raises(UnsupportedInput):
            InventoryPipeline(
                db_session,
                storage,
                PassingPreflight(),
                inventory_builder=lambda _path: (UnsupportedPageStub(),),
            ).run(project_id, source.resource_ref, "inventory:unsupported")

        persisted_project = db_session.get(Project, project.id)
        error = db_session.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        job = db_session.scalar(
            select(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        assert persisted_project is not None
        assert persisted_project.state == ProjectState.UNSUPPORTED_INPUT
        assert error is not None
        assert error.code == "unsupported_input"
        assert error.cause_category == "unsupported_input"
        assert error.location_ref is not None
        assert storage.resolve_resource_ref(error.location_ref).is_file()
        assert job is not None
        assert job.status == "failed"
        assert job.result_ref is None
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(LogicalJob).where(LogicalJob.project_id == project_id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()


@pytest.mark.parametrize(
    ("code", "detail", "cause_category"),
    (
        (
            "redis_unavailable",
            "Redis capability check failed",
            "transient_dependency_unavailable",
        ),
        (
            "ocr_provider_unavailable",
            "OCR Provider configuration is unavailable",
            "invalid_configuration",
        ),
    ),
)
def test_preflight_failure_is_persisted_before_source_read(
    db_session: Session,
    tmp_path: Path,
    code: str,
    detail: str,
    cause_category: str,
) -> None:
    """P0-RES-006 records a capability veto without reading the source PDF."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    storage = LocalFileStorage(tmp_path)
    try:
        db_session.add(project)
        db_session.commit()

        with pytest.raises(CapabilityUnavailable) as raised:
            InventoryPipeline(
                db_session,
                storage,
                FailingPreflight(code, detail),
                inventory_builder=lambda _path: pytest.fail(
                    "capability veto must precede inventory work"
                ),
            ).run(project_id, "asset://missing/source.pdf", "inventory:preflight")

        error = db_session.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        job = db_session.scalar(
            select(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        assert raised.value.code == code
        assert db_session.get(Project, project.id).state == ProjectState.PROCESSING
        assert error is not None
        assert error.code == code
        assert error.stage == "preflight"
        assert error.location_ref is None
        assert error.cause_category == cause_category
        assert job is not None
        assert job.status == "failed"
        assert job.result_ref is None
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(LogicalJob).where(LogicalJob.project_id == project_id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()


def test_invalid_source_ref_never_enters_the_error_envelope(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-RES-006 persists no host path when source reference validation fails."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    storage = LocalFileStorage(tmp_path)
    host_path = "/srv/private/customer-drawing.pdf"
    try:
        db_session.add(project)
        db_session.commit()

        with pytest.raises(ValueError, match="asset scheme"):
            InventoryPipeline(
                db_session,
                storage,
                PassingPreflight(),
                inventory_builder=lambda _path: pytest.fail(
                    "invalid source reference must not reach inventory"
                ),
            ).run(project_id, host_path, "inventory:invalid-source-ref")

        error = db_session.scalar(
            select(ErrorRecord).where(ErrorRecord.project_id == project.id)
        )
        job = db_session.scalar(
            select(LogicalJob).where(LogicalJob.project_id == project_id)
        )
        assert error is not None
        assert error.location_ref is None
        assert error.cause_category == "processing_defect"
        assert host_path not in error.message
        assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED
        assert job is not None
        assert job.status == "failed"
        assert job.result_ref is None
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(LogicalJob).where(LogicalJob.project_id == project_id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()
