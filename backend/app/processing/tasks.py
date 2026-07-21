from __future__ import annotations

from redis import Redis

from app.capabilities.service import ProcessingPreflight
from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.processing.pipeline import InventoryPipeline
from app.storage.local import LocalFileStorage


def _all_configured(*values: str | None) -> bool:
    return bool(values) and all(
        isinstance(value, str) and bool(value.strip()) for value in values
    )


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
        return InventoryPipeline(session, storage, preflight).run(
            project_id,
            source_ref,
            logical_task_key,
        )
    finally:
        session.close()
