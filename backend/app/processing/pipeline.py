from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capabilities.service import (
    CapabilityUnavailable,
    ProcessingPreflight,
    deferred_vision_preflight,
)
from app.candidates.advisor import CandidateAdvisorFailure
from app.candidates.confidence import (
    ConfidenceDecisionContractError,
    ConfidencePolicy,
)
from app.candidates.coverage import check_coverage
from app.candidates.models import AutomaticResult
from app.errors.models import ErrorRecord
from app.jobs.idempotency import (
    LogicalJob,
    LogicalJobStateError,
    claim_logical_job_failure,
    claim_logical_job,
    set_processing_stage,
    successful_result_ref,
)
from app.pdf.inventory import build_inventory
from app.pdf.visual_observations import VisualObservationBlockingError
from app.processing.automatic_result import (
    AUTOMATIC_RESULT_SCHEMA_VERSION,
    CandidateSnapshot,
    CoverageBlocking,
    automatic_result_ref,
    build_automatic_result,
    candidate_snapshot_from_inventory,
)
from app.projects.models import Project
from app.projects.state import InvalidTransition, ProjectState, transition
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


class UnsupportedInput(ValueError):
    pass


class ConfidencePolicyError(RuntimeError):
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
        candidate_snapshot_builder: Callable[
            [tuple[Any, ...]], CandidateSnapshot
        ] = candidate_snapshot_from_inventory,
        confidence_policy: ConfidencePolicy | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._preflight = preflight
        self._inventory_builder = inventory_builder
        self._candidate_snapshot_builder = candidate_snapshot_builder
        self._confidence_policy = (
            confidence_policy
            if confidence_policy is not None
            else ConfidencePolicy()
        )

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

    def _validated_automatic_result_ref(
        self,
        *,
        job_id: uuid.UUID,
        result_ref: str | None,
    ) -> str | None:
        if result_ref is None:
            return None
        result = self._session.scalar(
            select(AutomaticResult).where(AutomaticResult.logical_job_id == job_id)
        )
        if result is None or result_ref != automatic_result_ref(result):
            raise LogicalJobStateError(
                "successful process job is missing its automatic result"
            )
        return result_ref

    def _require_processing(
        self,
        project: Project,
        job: LogicalJob,
    ) -> str | None:
        if project.state == ProjectState.PROCESSING:
            return None
        failure = claim_logical_job_failure(self._session, job_id=job.id)
        if failure.successful_result_ref is not None:
            result_ref = self._validated_automatic_result_ref(
                job_id=job.id,
                result_ref=failure.successful_result_ref,
            )
            self._session.rollback()
            return result_ref
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
            result_ref = self._validated_automatic_result_ref(
                job_id=job_id,
                result_ref=failure.successful_result_ref,
            )
            self._session.rollback()
            return result_ref
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
        existing = self._validated_automatic_result_ref(
            job_id=job.id,
            result_ref=successful_result_ref(job),
        )
        if existing is not None:
            return existing

        project = self._project(project_id)
        existing = self._require_processing(project, job)
        if existing is not None:
            return existing
        safe_source_ref: str | None = None
        inventory_ref: str | None = None
        candidate_advisor_started = False
        deferred_vision_check: Callable[[], None] | None = None
        try:
            set_processing_stage(
                self._session,
                job_id=job.id,
                stage="parsing",
            )
            if isinstance(self._preflight, ProcessingPreflight):
                if project.recognition_mode == "production_uncertainty":
                    self._preflight.check(vision_required=False)
                    deferred_vision_check = self._preflight.check_vision
                else:
                    self._preflight.check()
            else:
                self._preflight.check()
            source_path = self._storage.resolve_resource_ref(source_ref)
            safe_source_ref = source_ref
            pages = tuple(self._inventory_builder(source_path))
            inventory_ref = self._store_inventory(project_id, job, pages)
            set_processing_stage(
                self._session,
                job_id=job.id,
                stage="recognizing",
            )
            if any(page.support_level == "unsupported" for page in pages):
                existing = self._record_failure(
                    project,
                    job,
                    state=ProjectState.UNSUPPORTED_INPUT,
                    code="unsupported_input",
                    message="Pure scanned PDF input is unsupported",
                    stage="page_inventory",
                    location_ref=inventory_ref,
                    cause_category="unsupported_input",
                )
                if existing is not None:
                    return existing
                raise UnsupportedInput("pure scanned PDF input is unsupported")
            project = self._project(project_id, for_update=True)
            existing = self._require_processing(project, job)
            if existing is not None:
                return existing
            source_file = self._session.scalar(
                select(StoredFile).where(StoredFile.resource_ref == source_ref)
            )
            if source_file is None:
                raise ValueError("source file metadata does not exist")
            candidate_advisor_started = True
            if deferred_vision_check is None:
                snapshot = self._candidate_snapshot_builder(pages)
            else:
                with deferred_vision_preflight(deferred_vision_check):
                    snapshot = self._candidate_snapshot_builder(pages)
            coverage = check_coverage(
                snapshot.coverage_entries,
                expected_observation_ids=snapshot.expected_observation_ids,
                required_visual_observation_ids=(
                    snapshot.required_visual_observation_ids
                ),
            )
            try:
                decided_candidates = (
                    self._confidence_policy.evaluate_candidates(
                        candidates=snapshot.candidates,
                        coverage=coverage,
                        duplicate_relations=snapshot.duplicate_relations,
                        source_signals=snapshot.source_signals,
                    )
                )
            except Exception as exc:
                raise ConfidencePolicyError(
                    "Confidence policy evaluation failed"
                ) from exc
            try:
                automatic_result = build_automatic_result(
                    self._session,
                    project_id=project.id,
                    source_file_id=source_file.id,
                    logical_job_id=job.id,
                    inventory_ref=inventory_ref,
                    candidates=decided_candidates,
                    coverage=coverage,
                    provider_call_ids=snapshot.provider_call_ids,
                    duplicate_relations=snapshot.duplicate_relations,
                    technical_requirements=snapshot.technical_requirements,
                    schema_version=AUTOMATIC_RESULT_SCHEMA_VERSION,
                    completeness=snapshot.completeness,
                    recognition_mode=snapshot.recognition_mode,
                    router_version=snapshot.router_version,
                    recognition_summary=snapshot.recognition_summary,
                    recognition_evidence_ref=snapshot.recognition_evidence_ref,
                )
            except ConfidenceDecisionContractError as exc:
                raise ConfidencePolicyError(
                    "Confidence policy evaluation failed"
                ) from exc
            return automatic_result_ref(automatic_result)
        except UnsupportedInput:
            raise
        except InvalidTransition:
            raise
        except CoverageBlocking as exc:
            existing = self._record_failure(
                project,
                job,
                state=ProjectState.PROCESSING_FAILED,
                code=exc.code,
                message=str(exc),
                stage="coverage",
                location_ref=inventory_ref,
                cause_category="processing_defect",
            )
            if existing is not None:
                return existing
            raise
        except ConfidencePolicyError:
            existing = self._record_failure(
                project,
                job,
                state=ProjectState.PROCESSING_FAILED,
                code="confidence_policy_failed",
                message="Confidence policy evaluation failed",
                stage="confidence_policy",
                location_ref=None,
                cause_category="processing_defect",
            )
            if existing is not None:
                return existing
            raise
        except CandidateAdvisorFailure:
            existing = self._record_failure(
                project,
                job,
                state=ProjectState.PROCESSING_FAILED,
                code="vision_provider_call_failed",
                message="Vision candidate Advisor call failed",
                stage="candidate_advisor",
                location_ref=None,
                cause_category="processing_defect",
            )
            if existing is not None:
                return existing
            raise
        except VisualObservationBlockingError as exc:
            if exc.code not in {
                "symbol_route_budget_exhausted",
                "visual_crop_oversize",
            }:
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
            existing = self._record_failure(
                project,
                job,
                state=ProjectState.PROCESSING_FAILED,
                code=exc.code,
                message="Visual symbol scheduling failed",
                stage="candidate_advisor",
                location_ref=None,
                cause_category="processing_defect",
            )
            if existing is not None:
                return existing
            raise
        except CapabilityUnavailable as exc:
            if exc.code == "vision_provider_unavailable":
                existing = self._record_failure(
                    project,
                    job,
                    state=None,
                    code=exc.code,
                    message=exc.detail,
                    stage="preflight",
                    location_ref=None,
                    cause_category="invalid_configuration",
                )
                if existing is not None:
                    return existing
                raise
            if candidate_advisor_started:
                existing = self._record_failure(
                    project,
                    job,
                    state=ProjectState.PROCESSING_FAILED,
                    code="vision_provider_call_failed",
                    message="Vision candidate Advisor call failed",
                    stage="candidate_advisor",
                    location_ref=None,
                    cause_category="transient_provider_failure",
                )
                if existing is not None:
                    return existing
                raise
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
