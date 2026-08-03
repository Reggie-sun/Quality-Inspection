from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.advisor import CandidateAdvisor
from app.candidates.symbol_routing import (
    validate_frozen_symbol_routing_identity,
)
from app.capabilities.service import ProcessingPreflight
from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.jobs.idempotency import (
    LogicalJob,
    LogicalJobStateError,
    existing_successful_result_ref,
    set_processing_stage,
)
from app.errors.models import ErrorRecord
from app.processing.pipeline import InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.providers.usage_ledger import ProviderUsageLedger
from app.processing.recognition_preview import RecognitionPreviewService
from app.projects.models import Project
from app.projects.lifecycle import (
    ProjectLifecycleNotFound,
    ProjectLifecycleService,
)
from app.providers.runtime import (
    OcrProviderFactory,
    VisionProviderFactory,
    build_ocr_provider,
    build_vision_provider,
)
from app.review.service import ReviewService
from app.storage.local import LocalFileStorage


OCR_PROVIDER_FACTORY: OcrProviderFactory = build_ocr_provider
VISION_PROVIDER_FACTORY: VisionProviderFactory = build_vision_provider
_AUTOMATIC_RESULT_PREFIX = "automatic-result://"


class _VisibleRecognitionPreviewSink:
    """Task-owned transaction boundary for previews observed by later stages."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        project_id: uuid.UUID,
        logical_task_key: str,
    ) -> None:
        self._session_factory = session_factory
        self._project_id = project_id
        self._logical_task_key = logical_task_key

    def _persist(self, operation: str, *, stage: str, **kwargs: object) -> object:
        session = self._session_factory()
        try:
            job = session.scalar(
                select(LogicalJob).where(
                    LogicalJob.project_id == str(self._project_id),
                    LogicalJob.logical_task_key == self._logical_task_key,
                )
            )
            if job is None:
                raise LogicalJobStateError("logical job is unavailable")
            service = RecognitionPreviewService(session, project_id=self._project_id)
            result = getattr(service, operation)(**kwargs)
            predecessor_stage = {
                "local_ready": ("recognizing", "local_ready"),
                "vlm_enriching": ("local_ready", "vlm_enriching"),
            }[stage]
            set_processing_stage(
                session,
                job_id=job.id,
                stage=stage,
                expected_stages=predecessor_stage,
            )
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def publish_local(
        self,
        *,
        source_file_id: uuid.UUID,
        snapshot: Mapping[str, object],
    ) -> object:
        return self._persist(
            "publish_local",
            stage="local_ready",
            source_file_id=source_file_id,
            snapshot=snapshot,
        )

    def append_enrichment(
        self,
        *,
        expected_head_version: int,
        parent_revision_id: uuid.UUID,
        snapshot: Mapping[str, object],
    ) -> object:
        return self._persist(
            "append_enrichment",
            stage="vlm_enriching",
            expected_head_version=expected_head_version,
            parent_revision_id=parent_revision_id,
            snapshot=snapshot,
        )


def _all_configured(*values: str | None) -> bool:
    return bool(values) and all(
        isinstance(value, str) and bool(value.strip()) for value in values
    )


def _automatic_result_id(result_ref: str) -> uuid.UUID:
    if not result_ref.startswith(_AUTOMATIC_RESULT_PREFIX):
        raise ValueError("processing result is not an automatic result")
    return uuid.UUID(result_ref.removeprefix(_AUTOMATIC_RESULT_PREFIX))


def _record_review_bootstrap_failure(session: Session, project_id: str) -> None:
    session.rollback()
    project = session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .with_for_update()
    )
    if project is None:
        raise RuntimeError("project disappeared during review bootstrap failure")
    existing = session.scalar(
        select(ErrorRecord.id).where(
            ErrorRecord.project_id == project.id,
            ErrorRecord.code == "review_bootstrap_failed",
            ErrorRecord.stage == "review_bootstrap",
        )
    )
    if existing is None:
        session.add(
            ErrorRecord(
                project_id=project.id,
                code="review_bootstrap_failed",
                message="Review working copy could not be prepared",
                severity="blocking",
                stage="review_bootstrap",
                location_ref=None,
                cause_category="processing_defect",
            )
        )
    session.commit()


@celery_app.task(name="quality_inspection.inventory_project")
def inventory_project(
    project_id: str,
    source_ref: str,
    logical_task_key: str,
) -> str:
    """Run inventory through coverage closure and return the raw-result ref."""
    session = SessionLocal()
    try:
        identity = uuid.UUID(project_id)
        lifecycle = ProjectLifecycleService(session)
        project = lifecycle.require_processing_task(identity)
        recognition_mode, _ = validate_frozen_symbol_routing_identity(
            getattr(project, "recognition_mode", None),
            getattr(project, "recognition_router_version", None),
        )
        settings = get_settings().model_copy(
            update={"symbol_recognition_mode": recognition_mode}
        )
        if (
            settings.provider_cycle_authorization_id is not None
            and recognition_mode != "production_uncertainty"
        ):
            raise ValueError("Provider cycle project routing identity is invalid")
        storage = LocalFileStorage(settings.storage_root)
        existing = existing_successful_result_ref(
            session, project_id=project_id, logical_task_key=logical_task_key
        )
        if existing is not None:
            try:
                lifecycle.require_processing_task(identity, for_update=True)
                ReviewService(session, storage=storage).create_from_raw(
                    _automatic_result_id(existing)
                )
                lifecycle.promote_reprocessed_project(identity)
            except ProjectLifecycleNotFound:
                session.rollback()
                raise
            except Exception:
                _record_review_bootstrap_failure(session, project_id)
                raise
            return existing
        usage_ledger = None
        if settings.provider_cycle_authorization_id is not None:
            if settings.provider_cycle_authorization_root is None:
                raise ValueError("Provider cycle authorization root is missing")
            usage_ledger = ProviderUsageLedger.open(
                cycle_id=settings.provider_cycle_authorization_id,
                storage_root=settings.storage_root,
                authorization_root=(
                    settings.provider_cycle_authorization_root
                ),
                project_id=project_id,
            )
        preflight = ProcessingPreflight(
            storage,
            Redis.from_url(settings.redis_url),
            celery_app,
            ocr_configured=_all_configured(
                settings.tencent_secret_id,
                settings.tencent_secret_key,
                settings.tencent_region,
            ),
            vision_configured=_all_configured(
                settings.qwen_api_key,
                settings.qwen_workspace_id,
                settings.qwen_model,
            ),
        )
        preview_sink = _VisibleRecognitionPreviewSink(
            SessionLocal,
            project_id=uuid.UUID(project_id),
            logical_task_key=logical_task_key,
        )
        preview_superseder = RecognitionPreviewService(
            session,
            project_id=uuid.UUID(project_id),
        )
        advisor = CandidateAdvisor(
            settings,
            storage,
            project_id=project_id,
            provider_factory=VISION_PROVIDER_FACTORY,
            symbol_session_factory=SessionLocal,
            require_symbol_persistence=True,
            preview_sink=preview_sink,
            usage_ledger=usage_ledger,
        )
        recognition = RuntimeRecognition(
            settings,
            provider_factory=OCR_PROVIDER_FACTORY,
            advisor=advisor,
            usage_ledger=usage_ledger,
        )
        result_ref = InventoryPipeline(
            session,
            storage,
            preflight,
            inventory_builder=recognition.build_inventory,
            candidate_snapshot_builder=recognition.build_candidate_snapshot,
            preview_superseder=preview_superseder,
        ).run(
            project_id,
            source_ref,
            logical_task_key,
        )
        try:
            lifecycle.require_processing_task(identity, for_update=True)
            ReviewService(session, storage=storage).create_from_raw(
                _automatic_result_id(result_ref)
            )
            lifecycle.promote_reprocessed_project(identity)
        except ProjectLifecycleNotFound:
            session.rollback()
            raise
        except Exception:
            _record_review_bootstrap_failure(session, project_id)
            raise
        return result_ref
    except Exception:
        session.rollback()
        try:
            ProjectLifecycleService(session).mark_reprocess_failed(
                uuid.UUID(project_id)
            )
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
