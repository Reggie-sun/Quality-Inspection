from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.capabilities.service import CapabilityUnavailable
from app.errors.models import ErrorRecord
from app.jobs.idempotency import (
    LogicalJob,
    claim_logical_job_failure,
    claim_logical_job,
    complete_logical_job,
    successful_result_ref,
)
from app.pdf.inventory import build_inventory
from app.projects.models import Project
from app.projects.state import InvalidTransition, ProjectState, transition
from app.storage.local import LocalFileStorage


class UnsupportedInput(ValueError):
    pass


_TRANSIENT_CAPABILITY_CODES = {
    "storage_unavailable",
    "redis_unavailable",
    "celery_worker_unavailable",
}
_INVALID_CONFIGURATION_CODES = {
    "ocr_provider_unavailable",
    "vision_provider_unavailable",
}


def _capability_cause_category(code: str) -> str:
    if code in _TRANSIENT_CAPABILITY_CODES:
        return "transient_dependency_unavailable"
    if code in _INVALID_CONFIGURATION_CODES:
        return "invalid_configuration"
    return "processing_defect"


class InventoryPipeline:
    def __init__(
        self,
        session: Session,
        storage: LocalFileStorage,
        preflight: Any,
        *,
        inventory_builder: Callable[[Path], tuple[Any, ...]] = build_inventory,
    ) -> None:
        self._session = session
        self._storage = storage
        self._preflight = preflight
        self._inventory_builder = inventory_builder

    def _project(self, project_id: str, *, for_update: bool = False) -> Project:
        try:
            identity = uuid.UUID(project_id)
        except ValueError as exc:
            raise ValueError("project_id must be one UUID") from exc
        project = self._session.get(
            Project,
            identity,
            populate_existing=True,
            with_for_update=for_update,
        )
        if project is None:
            raise ValueError("project does not exist")
        return project

    def _require_processing(
        self,
        project: Project,
        job: LogicalJob,
    ) -> str | None:
        if project.state == ProjectState.PROCESSING:
            return None
        failure = claim_logical_job_failure(self._session, job_id=job.id)
        if failure.successful_result_ref is not None:
            self._session.rollback()
            return failure.successful_result_ref
        if failure.owns_failure:
            self._session.commit()
        else:
            self._session.rollback()
        raise InvalidTransition(
            f"{project.state} cannot start or complete page inventory"
        )

    def _store_inventory(
        self,
        project_id: str,
        job: LogicalJob,
        pages: tuple[Any, ...],
    ) -> str:
        document = {
            "schema_version": "page-inventory/1",
            "pages": [page.to_dict() for page in pages],
        }
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        stored = self._storage.write_verified(
            f"projects/{project_id}/inventory/{job.id}.json",
            content,
            hashlib.sha256(content).hexdigest(),
        )
        return stored.resource_ref

    def _record_failure(
        self,
        project: Project,
        job: LogicalJob,
        *,
        state: ProjectState | None,
        code: str,
        message: str,
        stage: str,
        location_ref: str | None,
        cause_category: str,
    ) -> str | None:
        project_id = project.id
        job_id = job.id
        self._session.rollback()
        project = self._session.get(
            Project,
            project_id,
            populate_existing=True,
            with_for_update=True,
        )
        if project is None:
            raise RuntimeError("processing owners disappeared during failure handling")
        failure = claim_logical_job_failure(self._session, job_id=job_id)
        if failure.successful_result_ref is not None:
            self._session.rollback()
            return failure.successful_result_ref
        if not failure.owns_failure:
            self._session.rollback()
            return None
        if state is not None:
            project.state = transition(ProjectState(project.state), state)
        self._session.add(
            ErrorRecord(
                project_id=project.id,
                code=code,
                message=message,
                severity="blocking",
                stage=stage,
                location_ref=location_ref,
                cause_category=cause_category,
            )
        )
        self._session.commit()
        return None

    def run(
        self,
        project_id: str,
        source_ref: str,
        logical_task_key: str,
    ) -> str:
        job = claim_logical_job(
            self._session,
            project_id=project_id,
            logical_task_key=logical_task_key,
        )
        existing = successful_result_ref(job)
        if existing is not None:
            return existing

        project = self._project(project_id)
        existing = self._require_processing(project, job)
        if existing is not None:
            return existing
        safe_source_ref: str | None = None
        try:
            self._preflight.check()
            source_path = self._storage.resolve_resource_ref(source_ref)
            safe_source_ref = source_ref
            pages = tuple(self._inventory_builder(source_path))
            result_ref = self._store_inventory(project_id, job, pages)
            if any(page.support_level == "unsupported" for page in pages):
                existing = self._record_failure(
                    project,
                    job,
                    state=ProjectState.UNSUPPORTED_INPUT,
                    code="unsupported_input",
                    message="Pure scanned PDF input is unsupported",
                    stage="page_inventory",
                    location_ref=result_ref,
                    cause_category="unsupported_input",
                )
                if existing is not None:
                    return existing
                raise UnsupportedInput("pure scanned PDF input is unsupported")
            project = self._project(project_id, for_update=True)
            existing = self._require_processing(project, job)
            if existing is not None:
                return existing
            return complete_logical_job(
                self._session,
                job_id=job.id,
                result_ref=result_ref,
            )
        except UnsupportedInput:
            raise
        except InvalidTransition:
            raise
        except CapabilityUnavailable as exc:
            existing = self._record_failure(
                project,
                job,
                state=None,
                code=exc.code,
                message=exc.detail,
                stage="preflight",
                location_ref=None,
                cause_category=_capability_cause_category(exc.code),
            )
            if existing is not None:
                return existing
            raise
        except Exception:
            existing = self._record_failure(
                project,
                job,
                state=ProjectState.PROCESSING_FAILED,
                code="inventory_processing_failed",
                message="Page inventory processing failed",
                stage="page_inventory",
                location_ref=safe_source_ref,
                cause_category="processing_defect",
            )
            if existing is not None:
                return existing
            raise
