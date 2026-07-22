from __future__ import annotations

from typing import Any


class CapabilityUnavailable(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _configured(value: bool | str | None) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is True


class ProcessingPreflight:
    def __init__(
        self,
        storage: Any,
        redis_client: Any,
        celery_application: Any | None = None,
        *,
        ocr_configured: bool | str | None,
        vision_configured: bool | str | None,
    ) -> None:
        if celery_application is None:
            from app.celery_app import celery_app

            celery_application = celery_app
        self._storage = storage
        self._redis = redis_client
        self._celery = celery_application
        self._ocr_configured = ocr_configured
        self._vision_configured = vision_configured

    def check(self) -> None:
        try:
            self._storage.probe()
        except Exception as exc:
            raise CapabilityUnavailable(
                "storage_unavailable",
                "shared storage probe failed",
            ) from exc

        try:
            if self._redis.ping() is not True:
                raise RuntimeError("Redis ping did not return true")
        except Exception as exc:
            raise CapabilityUnavailable(
                "redis_unavailable",
                "Redis capability check failed",
            ) from exc

        try:
            workers = self._celery.control.inspect(timeout=1).ping()
            if not isinstance(workers, dict) or not workers:
                raise RuntimeError("no Celery worker responded")
        except Exception as exc:
            raise CapabilityUnavailable(
                "celery_worker_unavailable",
                "Celery worker capability check failed",
            ) from exc

        if not _configured(self._ocr_configured):
            raise CapabilityUnavailable(
                "ocr_provider_unavailable",
                "OCR Provider configuration is unavailable",
            )
        if not _configured(self._vision_configured):
            raise CapabilityUnavailable(
                "vision_provider_unavailable",
                "Vision Provider configuration is unavailable",
            )
