from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


LOCALIZED_PROVIDER_FAILURE_CATEGORIES = frozenset(
    {"timeout", "transport", "schema", "unavailable"}
)


class LocalizedProviderFailure(RuntimeError):
    def __init__(self, failure_category: str) -> None:
        if failure_category not in LOCALIZED_PROVIDER_FAILURE_CATEGORIES:
            raise ValueError("localized Provider failure category is invalid")
        super().__init__("visual symbol Provider request failed")
        self.failure_category = failure_category


@dataclass(frozen=True)
class OcrObservation:
    raw_text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    angle: float


@dataclass(frozen=True)
class OcrResult:
    request_id: str
    observations: tuple[OcrObservation, ...]


@dataclass(frozen=True)
class VisionResult:
    request_id: str
    payload: dict[str, Any]
    usage: dict[str, int]


class OcrProvider(Protocol):
    def recognize_png(self, image: bytes) -> OcrResult: ...


class VisionLlmProvider(Protocol):
    def review_candidate(self, image: bytes, prompt: str) -> VisionResult: ...

    def review_symbols(self, image: bytes, prompt: str) -> VisionResult: ...
