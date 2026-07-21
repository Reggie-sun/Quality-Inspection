from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PageSignals:
    native_char_count: int
    native_span_count: int
    max_image_coverage: float
    vector_drawing_count: int

    def __post_init__(self) -> None:
        if self.native_char_count < 0 or self.native_span_count < 0:
            raise ValueError("native text counts must be non-negative")
        if self.vector_drawing_count < 0:
            raise ValueError("vector drawing count must be non-negative")
        if not 0.0 <= self.max_image_coverage <= 1.0:
            raise ValueError("image coverage must be between zero and one")


@dataclass(frozen=True)
class Classification:
    page_type: str
    processing_route: str
    support_level: str
    confidence: float
    evidence: dict[str, float | int]
    review_required: bool = False
    unsupported_reason: str | None = None
    rule_version: str = "v0.1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_page(signals: PageSignals) -> Classification:
    evidence = asdict(signals)
    if signals.native_char_count >= 20 and signals.max_image_coverage >= 0.8:
        return Classification(
            page_type="hybrid",
            processing_route="hybrid",
            support_level="supported",
            confidence=0.9,
            evidence=evidence,
        )
    if signals.native_char_count >= 20 and (
        signals.vector_drawing_count > 0 or signals.max_image_coverage < 0.8
    ):
        return Classification(
            page_type="vector",
            processing_route="native",
            support_level="supported",
            confidence=0.9,
            evidence=evidence,
        )
    if signals.native_char_count < 20 and signals.max_image_coverage >= 0.8:
        return Classification(
            page_type="scanned",
            processing_route="unsupported",
            support_level="unsupported",
            confidence=0.95,
            evidence=evidence,
            unsupported_reason="pure_scanned_pdf_not_supported",
        )
    return Classification(
        page_type="ambiguous",
        processing_route="hybrid",
        support_level="review_required",
        confidence=0.5,
        evidence=evidence,
        review_required=True,
    )
