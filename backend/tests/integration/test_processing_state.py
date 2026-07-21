import uuid
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.processing.pipeline import InventoryPipeline
from app.projects.models import Project
from app.projects.state import InvalidTransition, ProjectState, transition
from app.storage.local import LocalFileStorage


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class MustNotRun:
    def __getattr__(self, _name):
        raise AssertionError("blocked project performed inventory work")


class SupportedPageStub:
    support_level = "supported"

    def to_dict(self) -> dict[str, str]:
        return {"support_level": self.support_level}


@pytest.mark.parametrize(
    ("current", "target"),
    (
        (ProjectState.PROCESSING, ProjectState.READY_FOR_EDIT),
        (ProjectState.PROCESSING, ProjectState.PROCESSING_FAILED),
        (ProjectState.PROCESSING, ProjectState.UNSUPPORTED_INPUT),
        (ProjectState.READY_FOR_EDIT, ProjectState.EDITING),
        (ProjectState.EDITING, ProjectState.REVIEWED),
        (ProjectState.REVIEWED, ProjectState.EXPORTING),
        (ProjectState.EXPORTING, ProjectState.EXPORT_SUCCEEDED),
        (ProjectState.EXPORTING, ProjectState.EXPORT_FAILED),
        (ProjectState.EXPORT_FAILED, ProjectState.EXPORTING),
    ),
)
def test_only_owned_p0_state_edges_are_allowed(
    current: ProjectState,
    target: ProjectState,
) -> None:
    """P0-RUN-009 allows only the simplified P0 transition graph."""
    assert transition(current, target) is target


@pytest.mark.parametrize(
    "blocked_state",
    (ProjectState.PROCESSING_FAILED, ProjectState.UNSUPPORTED_INPUT),
)
def test_blocking_error_cannot_transition_to_ready_or_success(
    blocked_state: ProjectState,
) -> None:
    """P0-RUN-009 never converts blocking outcomes into formal success."""
    with pytest.raises(InvalidTransition):
        transition(blocked_state, ProjectState.READY_FOR_EDIT)
    with pytest.raises(InvalidTransition):
        transition(blocked_state, ProjectState.EXPORT_SUCCEEDED)


@pytest.mark.parametrize(
    "blocked_state",
    (
        ProjectState.PROCESSING_FAILED,
        ProjectState.UNSUPPORTED_INPUT,
        ProjectState.READY_FOR_EDIT,
    ),
)
def test_inventory_pipeline_cannot_succeed_from_non_processing_state(
    db_session: Session,
    blocked_state: ProjectState,
) -> None:
    """P0-RUN-009 makes the state Owner veto inventory before external work."""
    project = Project(id=uuid.uuid4(), state=blocked_state)
    project_id = str(project.id)
    try:
        db_session.add(project)
        db_session.commit()

        with pytest.raises(InvalidTransition):
            InventoryPipeline(
                db_session,
                MustNotRun(),
                MustNotRun(),
                inventory_builder=MustNotRun(),
            ).run(project_id, "asset://missing.pdf", "inventory:blocked-state")

        db_session.expire_all()
        job = (
            db_session.query(LogicalJob)
            .filter(LogicalJob.project_id == project_id)
            .one()
        )
        assert db_session.get(Project, project.id).state == blocked_state
        assert job.status == "failed"
        assert job.result_ref is None
    finally:
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(LogicalJob).where(LogicalJob.project_id == project_id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()


def test_inventory_pipeline_rechecks_state_before_success(
    db_session: Session,
    tmp_path: Path,
) -> None:
    """P0-RUN-009 prevents a concurrent blocking state from becoming success."""
    project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
    project_id = str(project.id)
    storage = LocalFileStorage(tmp_path)
    payload = b"fixture-pdf"
    source = storage.write_verified(
        "projects/source.pdf",
        payload,
        sha256(payload).hexdigest(),
    )
    competing_session = SessionLocal()

    class PassingPreflight:
        def check(self) -> None:
            return None

    def block_during_inventory(_source_path: Path) -> tuple[SupportedPageStub, ...]:
        competing_project = competing_session.get(Project, project.id)
        assert competing_project is not None
        competing_project.state = ProjectState.PROCESSING_FAILED
        competing_session.commit()
        return (SupportedPageStub(),)

    try:
        db_session.add(project)
        db_session.commit()

        with pytest.raises(InvalidTransition):
            InventoryPipeline(
                db_session,
                storage,
                PassingPreflight(),
                inventory_builder=block_during_inventory,
            ).run(project_id, source.resource_ref, "inventory:state-race")

        db_session.expire_all()
        job = (
            db_session.query(LogicalJob)
            .filter(LogicalJob.project_id == project_id)
            .one()
        )
        assert db_session.get(Project, project.id).state == ProjectState.PROCESSING_FAILED
        assert job.status == "failed"
        assert job.result_ref is None
    finally:
        competing_session.rollback()
        competing_session.close()
        db_session.rollback()
        db_session.execute(delete(ErrorRecord).where(ErrorRecord.project_id == project.id))
        db_session.execute(delete(LogicalJob).where(LogicalJob.project_id == project_id))
        db_session.execute(delete(Project).where(Project.id == project.id))
        db_session.commit()
