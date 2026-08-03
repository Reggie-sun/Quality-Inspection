from __future__ import annotations

import importlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.jobs.idempotency import LogicalJob
from app.processing.recognition_preview import RecognitionPreviewService
from app.projects.models import Project, ProjectLifecycleStatus
from app.projects.state import ProjectState
from app.review.models import ReviewLock, ReviewWorkingCopy
from app.storage.models import StoredFile


@dataclass
class LifecycleContext:
    session: Session
    active: Project
    source: StoredFile
    dispatched: list[tuple[str, str, str]]

    def lifecycle(self, *, failing_dispatch: bool = False) -> Any:
        module = _lifecycle_module()

        def dispatch(project_id: str, source_ref: str, task_key: str) -> None:
            if failing_dispatch:
                raise RuntimeError("dispatch unavailable")
            self.dispatched.append((project_id, source_ref, task_key))

        return module.ProjectLifecycleService(self.session, dispatch=dispatch)

    def reload(self, project_id: uuid.UUID) -> Project:
        self.session.expire_all()
        project = self.session.get(Project, project_id)
        assert project is not None
        return project

    def add_working_copy(self, project: Project) -> None:
        job = LogicalJob(
            project_id=str(project.id),
            logical_task_key=f"product-process:{project.id}",
            status="succeeded",
            result_ref=f"result://{project.id}",
            processing_stage="preparing_review",
        )
        self.session.add(job)
        self.session.flush()
        result = AutomaticResult(
            project_id=project.id,
            source_file_id=self.source.id,
            logical_job_id=job.id,
            inventory_ref=f"asset://tests/{project.id}/inventory.json",
            candidates=[],
            coverage={},
            technical_requirements=[],
            provider_call_ids=[],
            schema_version="automatic-result/1",
            completeness="complete",
            recognition_mode=project.recognition_mode,
            router_version=project.recognition_router_version,
            recognition_summary={},
        )
        self.session.add(result)
        self.session.flush()
        self.session.add(
            ReviewWorkingCopy(
                project_id=project.id,
                raw_result_id=result.id,
                version=1,
                items=[],
                coverage={},
                technical_requirements=[],
                sip_metadata={},
                numbering_stale=False,
            )
        )
        self.session.commit()


def _lifecycle_module() -> ModuleType:
    return importlib.import_module("app.projects.lifecycle")


@pytest.fixture
def lifecycle_context() -> Iterator[LifecycleContext]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    project = Project(
        id=uuid.uuid4(),
        state=ProjectState.EDITING,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
        source_filename="drawing.pdf",
        lifecycle_status=ProjectLifecycleStatus.ACTIVE,
    )
    source = StoredFile(
        resource_ref=f"asset://tests/{project.id}/source.pdf",
        sha256="a" * 64,
        size_bytes=10,
        mime_type="application/pdf",
    )
    session.add_all([project, source])
    session.flush()
    RecognitionPreviewService(session, project_id=project.id).publish_local(
        source_file_id=source.id,
        snapshot={
            "schema_version": "recognition-preview/1",
            "stage": "local_ready",
            "candidates": [],
            "sources": [],
            "counts": {
                "local_resolved": 0,
                "cache_resolved": 0,
                "vlm_pending": 0,
                "vlm_resolved": 0,
                "unresolved": 0,
            },
        },
    )
    session.commit()
    context = LifecycleContext(session, project, source, [])
    try:
        yield context
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_start_reprocess_creates_hidden_successor_and_preserves_predecessor(
    lifecycle_context: LifecycleContext,
) -> None:
    successor = lifecycle_context.lifecycle().start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    assert successor.predecessor_project_id == lifecycle_context.active.id
    assert successor.lifecycle_status == ProjectLifecycleStatus.REPROCESSING
    assert successor.source_filename == "drawing.pdf"
    assert lifecycle_context.reload(
        lifecycle_context.active.id
    ).lifecycle_status == ProjectLifecycleStatus.ACTIVE
    assert lifecycle_context.dispatched == [
        (
            str(successor.id),
            lifecycle_context.source.resource_ref,
            f"product-process:{successor.id}",
        )
    ]


def test_start_reprocess_rejects_duplicate_active_successor(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()
    service = lifecycle_context.lifecycle()
    service.start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    with pytest.raises(module.ProjectReprocessInProgress):
        service.start_reprocess(
            lifecycle_context.active.id,
            recognition_mode="legacy_high_recall",
            recognition_router_version="legacy",
        )


def test_dispatch_failure_marks_only_successor_failed(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()

    with pytest.raises(module.ProjectLifecycleDispatchFailed) as error:
        lifecycle_context.lifecycle(failing_dispatch=True).start_reprocess(
            lifecycle_context.active.id,
            recognition_mode="legacy_high_recall",
            recognition_router_version="legacy",
        )

    assert lifecycle_context.reload(
        error.value.project_id
    ).lifecycle_status == ProjectLifecycleStatus.REPROCESS_FAILED
    assert lifecycle_context.reload(
        lifecycle_context.active.id
    ).lifecycle_status == ProjectLifecycleStatus.ACTIVE


def test_failed_successor_does_not_block_retry(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()
    with pytest.raises(module.ProjectLifecycleDispatchFailed):
        lifecycle_context.lifecycle(failing_dispatch=True).start_reprocess(
            lifecycle_context.active.id,
            recognition_mode="legacy_high_recall",
            recognition_router_version="legacy",
        )

    successor = lifecycle_context.lifecycle().start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    assert successor.lifecycle_status == ProjectLifecycleStatus.REPROCESSING


def test_promotion_atomically_switches_active_project_and_is_idempotent(
    lifecycle_context: LifecycleContext,
) -> None:
    service = lifecycle_context.lifecycle()
    successor = service.start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )
    lifecycle_context.add_working_copy(successor)

    service.promote_reprocessed_project(successor.id)
    service.promote_reprocessed_project(successor.id)

    assert lifecycle_context.reload(
        lifecycle_context.active.id
    ).lifecycle_status == ProjectLifecycleStatus.SUPERSEDED
    assert lifecycle_context.reload(
        successor.id
    ).lifecycle_status == ProjectLifecycleStatus.ACTIVE


def test_promotion_requires_successor_working_copy(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()
    service = lifecycle_context.lifecycle()
    successor = service.start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    with pytest.raises(module.ProjectPromotionNotReady):
        service.promote_reprocessed_project(successor.id)

    assert lifecycle_context.reload(
        lifecycle_context.active.id
    ).lifecycle_status == ProjectLifecycleStatus.ACTIVE


def test_delete_tombstones_without_deleting_source(
    lifecycle_context: LifecycleContext,
) -> None:
    lifecycle_context.lifecycle().delete_project(lifecycle_context.active.id)

    deleted = lifecycle_context.reload(lifecycle_context.active.id)
    assert deleted.lifecycle_status == ProjectLifecycleStatus.DELETED
    assert deleted.deleted_at is not None
    assert lifecycle_context.session.get(
        StoredFile,
        lifecycle_context.source.id,
    ) is not None


def test_delete_rejects_reprocessing_and_active_review_lock(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()
    service = lifecycle_context.lifecycle()
    service.start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )
    with pytest.raises(module.ProjectReprocessInProgress):
        service.delete_project(lifecycle_context.active.id)

    successor = lifecycle_context.session.query(Project).filter_by(
        predecessor_project_id=lifecycle_context.active.id,
        lifecycle_status=ProjectLifecycleStatus.REPROCESSING,
    ).one()
    service.mark_reprocess_failed(successor.id)
    lifecycle_context.session.add(
        ReviewLock(
            project_id=lifecycle_context.active.id,
            operator_id="operator-a",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    lifecycle_context.session.commit()

    with pytest.raises(module.ProjectLifecycleLocked):
        service.delete_project(lifecycle_context.active.id)


def test_expired_review_lock_does_not_block_delete(
    lifecycle_context: LifecycleContext,
) -> None:
    lifecycle_context.session.add(
        ReviewLock(
            project_id=lifecycle_context.active.id,
            operator_id="operator-a",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    lifecycle_context.session.commit()

    lifecycle_context.lifecycle().delete_project(lifecycle_context.active.id)

    assert lifecycle_context.reload(
        lifecycle_context.active.id
    ).lifecycle_status == ProjectLifecycleStatus.DELETED
    assert lifecycle_context.session.get(
        ReviewLock,
        lifecycle_context.active.id,
    ) is None


def test_access_modes_fail_closed_for_hidden_lifecycle_states(
    lifecycle_context: LifecycleContext,
) -> None:
    module = _lifecycle_module()
    service = lifecycle_context.lifecycle()
    successor = service.start_reprocess(
        lifecycle_context.active.id,
        recognition_mode="legacy_high_recall",
        recognition_router_version="legacy",
    )

    assert service.require_access(
        successor.id,
        module.ProjectAccess.STATUS_READ,
    ).id == successor.id
    assert service.require_access(
        successor.id,
        module.ProjectAccess.PROCESSING_READ,
    ).id == successor.id
    with pytest.raises(module.ProjectLifecycleNotFound):
        service.require_access(successor.id, module.ProjectAccess.ACTIVE)

    service.mark_reprocess_failed(successor.id)
    assert service.require_access(
        successor.id,
        module.ProjectAccess.STATUS_READ,
    ).id == successor.id
    with pytest.raises(module.ProjectLifecycleNotFound):
        service.require_access(
            successor.id,
            module.ProjectAccess.PROCESSING_READ,
        )
