from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.capabilities.service import CapabilityUnavailable, ProcessingPreflight
from app.celery_app import celery_app
from app.processing.tasks import _all_configured


@dataclass
class RecordingStorage:
    events: list[str]
    failure: Exception | None = None

    def probe(self) -> None:
        self.events.append("storage")
        if self.failure is not None:
            raise self.failure


@dataclass
class RecordingRedis:
    events: list[str]
    available: bool = True

    def ping(self) -> bool:
        self.events.append("redis")
        return self.available


class RecordingInspect:
    def __init__(self, events: list[str], workers: dict | None) -> None:
        self.events = events
        self.workers = workers

    def ping(self) -> dict | None:
        self.events.append("celery-ping")
        return self.workers


class RecordingControl:
    def __init__(self, events: list[str], workers: dict | None) -> None:
        self.events = events
        self.workers = workers

    def inspect(self, *, timeout: int) -> RecordingInspect:
        assert timeout == 1
        self.events.append("celery-inspect")
        return RecordingInspect(self.events, self.workers)


class RecordingCelery:
    def __init__(self, events: list[str], workers: dict | None = None) -> None:
        self.control = RecordingControl(
            events,
            workers if workers is not None else {"worker-1": {"ok": "pong"}},
        )


def test_missing_qwen_config_blocks_new_processing() -> None:
    """P0-RUN-003 checks capabilities in order and blocks missing Vision config."""
    events: list[str] = []
    preflight = ProcessingPreflight(
        RecordingStorage(events),
        RecordingRedis(events),
        RecordingCelery(events),
        ocr_configured=True,
        vision_configured=False,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "vision_provider_unavailable"
    assert events == ["storage", "redis", "celery-inspect", "celery-ping"]


def test_first_failed_capability_short_circuits_without_provider_calls() -> None:
    """P0-RUN-003 fails closed at the first unavailable capability."""
    events: list[str] = []
    preflight = ProcessingPreflight(
        RecordingStorage(events, failure=OSError("host path must stay private")),
        RecordingRedis(events),
        RecordingCelery(events),
        ocr_configured=True,
        vision_configured=True,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "storage_unavailable"
    assert error.value.detail == "shared storage probe failed"
    assert events == ["storage"]


def test_empty_celery_worker_map_is_unavailable() -> None:
    """P0-RUN-003 requires at least one Celery worker response."""
    events: list[str] = []
    preflight = ProcessingPreflight(
        RecordingStorage(events),
        RecordingRedis(events),
        RecordingCelery(events, workers={}),
        ocr_configured=True,
        vision_configured=True,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "celery_worker_unavailable"


def test_missing_celery_ping_response_is_unavailable() -> None:
    """P0-RUN-003 treats a Celery inspect timeout as unavailable."""
    events: list[str] = []
    celery = RecordingCelery(events)
    celery.control = RecordingControl(events, workers=None)
    preflight = ProcessingPreflight(
        RecordingStorage(events),
        RecordingRedis(events),
        celery,
        ocr_configured=True,
        vision_configured=True,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "celery_worker_unavailable"


def test_redis_failure_short_circuits_before_celery() -> None:
    """P0-RUN-003 stops at Redis when its ping is not successful."""
    events: list[str] = []
    preflight = ProcessingPreflight(
        RecordingStorage(events),
        RecordingRedis(events, available=False),
        RecordingCelery(events),
        ocr_configured=True,
        vision_configured=True,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "redis_unavailable"
    assert events == ["storage", "redis"]


def test_missing_ocr_config_precedes_missing_vision_config() -> None:
    """P0-RUN-003 reports the first missing Provider configuration."""
    events: list[str] = []
    preflight = ProcessingPreflight(
        RecordingStorage(events),
        RecordingRedis(events),
        RecordingCelery(events),
        ocr_configured=False,
        vision_configured=False,
    )

    with pytest.raises(CapabilityUnavailable) as error:
        preflight.check()

    assert error.value.code == "ocr_provider_unavailable"


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        (("configured", "configured"), True),
        (("configured", " "), False),
        ((None, "configured"), False),
        ((), False),
    ),
)
def test_provider_configuration_requires_every_non_blank_component(
    values: tuple[str | None, ...],
    expected: bool,
) -> None:
    """P0-RUN-003 does not collapse whitespace credentials to configured."""
    assert _all_configured(*values) is expected


def test_celery_explicitly_includes_processing_task_module() -> None:
    """P0-RUN-003 worker discovery includes the owned inventory task module."""
    assert "app.processing.tasks" in celery_app.conf.include
