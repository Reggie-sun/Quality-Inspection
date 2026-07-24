from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.projects.schemas import (
    ProjectError,
    ProjectPhase,
    ProjectStatusResponse,
)
from app.projects.state import ProjectState
from app.review.models import ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


ProjectDispatcher = Callable[[str, str, str], object]


class InvalidPdf(ValueError):
    pass


class ProjectNotFound(LookupError):
    pass


class ProjectDispatchFailed(RuntimeError):
    def __init__(self, status: ProjectStatusResponse) -> None:
        super().__init__("project processing dispatch failed")
        self.status = status


_TRANSIENT_CAUSE_CATEGORIES = {
    "transient_dependency_unavailable",
    "transient_dispatch_failure",
}

_SAFE_ERROR_STAGES = {
    "project_dispatch_failed": "dispatch",
    "storage_unavailable": "preflight",
    "redis_unavailable": "preflight",
    "celery_worker_unavailable": "preflight",
    "ocr_provider_unavailable": "preflight",
    "vision_provider_unavailable": "preflight",
    "unsupported_input": "page_inventory",
    "inventory_processing_failed": "page_inventory",
    "coverage_blocking": "coverage",
    "review_bootstrap_failed": "review_bootstrap",
}


def validate_pdf(content: bytes, content_type: str) -> None:
    media_type = content_type.partition(";")[0].strip().lower()
    if not content or media_type != "application/pdf":
        raise InvalidPdf("uploaded file is not a valid PDF")
    if not content.startswith(b"%PDF-"):
        raise InvalidPdf("uploaded file is not a valid PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or document.page_count < 1:
                raise InvalidPdf("uploaded file is not a readable PDF")
    except InvalidPdf:
        raise
    except Exception as error:
        raise InvalidPdf("uploaded file is not a valid PDF") from error


class ProjectIntakeService:
    def __init__(
        self,
        session: Session,
        storage: LocalFileStorage,
        dispatch: ProjectDispatcher,
    ) -> None:
        self.session = session
        self.storage = storage
        self.dispatch = dispatch

    def create_pdf(
        self,
        *,
        content: bytes,
        content_type: str,
    ) -> ProjectStatusResponse:
        validate_pdf(content, content_type)
        project = Project(id=uuid.uuid4(), state=ProjectState.PROCESSING)
        stored = self.storage.write_verified(
            f"projects/{project.id}/source.pdf",
            content,
            hashlib.sha256(content).hexdigest(),
        )
        source = StoredFile(
            resource_ref=stored.resource_ref,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            mime_type="application/pdf",
        )
        self.session.add_all([project, source])
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.storage.delete(stored.resource_ref)
            raise

        try:
            self.dispatch(
                str(project.id),
                source.resource_ref,
                f"product-process:{project.id}",
            )
        except Exception as error:
            failed_status = self._record_dispatch_failure(project.id)
            raise ProjectDispatchFailed(failed_status) from error
        return self.status(project.id, include_project_id=True)

    def status(
        self,
        project_id: uuid.UUID,
        *,
        include_project_id: bool = False,
    ) -> ProjectStatusResponse:
        project = self.session.get(Project, project_id, populate_existing=True)
        if project is None:
            raise ProjectNotFound("project was not found")

        working_copy = self.session.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project_id
            )
        )
        if working_copy is not None:
            return self._status_response(
                project_id,
                include_project_id=include_project_id,
                phase=ProjectPhase.READY_FOR_REVIEW,
                workbench_ready=True,
            )

        task_key = f"product-process:{project_id}"
        job = self.session.scalar(
            select(LogicalJob).where(
                LogicalJob.project_id == str(project_id),
                LogicalJob.logical_task_key == task_key,
            )
        )
        blocking_error = self.session.scalar(
            select(ErrorRecord)
            .where(
                ErrorRecord.project_id == project_id,
                ErrorRecord.severity == "blocking",
            )
            .order_by(ErrorRecord.id.desc())
            .limit(1)
        )
        if blocking_error is not None:
            return self._failed_status(
                project_id,
                blocking_error,
                include_project_id=include_project_id,
            )
        if project.state in {
            ProjectState.PROCESSING_FAILED,
            ProjectState.UNSUPPORTED_INPUT,
        }:
            return self._generic_failed_status(
                project_id,
                include_project_id=include_project_id,
            )
        if job is not None and job.status == "failed":
            return self._generic_failed_status(
                project_id,
                include_project_id=include_project_id,
            )
        if job is None:
            return self._status_response(
                project_id,
                include_project_id=include_project_id,
                phase=ProjectPhase.QUEUED,
            )
        if job.status not in {"pending", "processing", "succeeded"}:
            return self._generic_failed_status(
                project_id,
                include_project_id=include_project_id,
            )
        return self._status_response(
            project_id,
            include_project_id=include_project_id,
            phase=ProjectPhase.PROCESSING,
        )

    def _record_dispatch_failure(
        self,
        project_id: uuid.UUID,
    ) -> ProjectStatusResponse:
        project = self.session.get(Project, project_id, populate_existing=True)
        if project is None:
            raise RuntimeError("project disappeared during dispatch failure handling")
        project.state = ProjectState.PROCESSING_FAILED
        self.session.add(
            ErrorRecord(
                project_id=project_id,
                code="project_dispatch_failed",
                message="Project processing dispatch failed",
                severity="blocking",
                stage="dispatch",
                location_ref=None,
                cause_category="transient_dispatch_failure",
            )
        )
        self.session.commit()
        return self.status(project_id, include_project_id=True)

    def _failed_status(
        self,
        project_id: uuid.UUID,
        error: ErrorRecord,
        *,
        include_project_id: bool,
    ) -> ProjectStatusResponse:
        code = error.code
        stage = _SAFE_ERROR_STAGES.get(code)
        if stage is None:
            code = "project_processing_failed"
            stage = "processing"
        return self._status_response(
            project_id,
            include_project_id=include_project_id,
            phase=ProjectPhase.FAILED,
            retryable=error.cause_category in _TRANSIENT_CAUSE_CATEGORIES,
            error=ProjectError(code=code, stage=stage),
        )

    def _generic_failed_status(
        self,
        project_id: uuid.UUID,
        *,
        include_project_id: bool,
    ) -> ProjectStatusResponse:
        return self._status_response(
            project_id,
            include_project_id=include_project_id,
            phase=ProjectPhase.FAILED,
            error=ProjectError(
                code="project_processing_failed",
                stage="processing",
            ),
        )

    @staticmethod
    def _status_response(
        project_id: uuid.UUID,
        *,
        include_project_id: bool,
        phase: ProjectPhase,
        workbench_ready: bool = False,
        retryable: bool = False,
        error: ProjectError | None = None,
    ) -> ProjectStatusResponse:
        return ProjectStatusResponse(
            project_id=project_id if include_project_id else None,
            phase=phase,
            workbench_ready=workbench_ready,
            retryable=retryable,
            error=error,
        )
