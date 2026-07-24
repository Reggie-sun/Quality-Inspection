from __future__ import annotations

import uuid

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.advisor import CandidateAdvisor
from app.capabilities.service import ProcessingPreflight
from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.errors.models import ErrorRecord
from app.processing.pipeline import InventoryPipeline
from app.processing.runtime_recognition import RuntimeRecognition
from app.projects.models import Project
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
    settings = get_settings()
    session = SessionLocal()
    try:
        storage = LocalFileStorage(settings.storage_root)
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
        advisor = CandidateAdvisor(
            settings,
            storage,
            project_id=project_id,
            provider_factory=VISION_PROVIDER_FACTORY,
        )
        recognition = RuntimeRecognition(
            settings,
            provider_factory=OCR_PROVIDER_FACTORY,
            advisor=advisor,
        )
        result_ref = InventoryPipeline(
            session,
            storage,
            preflight,
            inventory_builder=recognition.build_inventory,
            candidate_snapshot_builder=recognition.build_candidate_snapshot,
        ).run(
            project_id,
            source_ref,
            logical_task_key,
        )
        try:
            ReviewService(session, storage=storage).create_from_raw(
                _automatic_result_id(result_ref)
            )
        except Exception:
            _record_review_bootstrap_failure(session, project_id)
            raise
        return result_ref
    finally:
        session.close()
