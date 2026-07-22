from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


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
