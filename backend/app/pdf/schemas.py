from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.pdf.coordinates import BBox, Matrix


@dataclass(frozen=True)
class TextObservation:
    observation_id: str
    source_type: str
    observation_level: str
    raw_text: str
    normalized_text: str
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    direction: tuple[float, float]
    direction_angle_degrees: float
    confidence: float | None
    parent_region_id: str | None = None
    font_name: str | None = None


@dataclass(frozen=True)
class VisualObservation:
    observation_id: str
    source_type: Literal["visual"]
    observation_level: Literal["annotation_context"]
    page_index: int
    bbox_pdf: BBox
    bbox_normalized: BBox
    proposal_kind: Literal["text_adjacent_vector_context"]
    geometry_sha256: str
    associated_text_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class PageInventory:
    page_index: int
    width: float
    height: float
    rotation: int
    page_type: str
    processing_route: str
    support_level: str
    review_required: bool
    unsupported_reason: str | None
    classification_confidence: float
    classification_rule_version: str
    classification_evidence: dict[str, float | int]
    pdf_to_render_matrix: Matrix
    render_to_pdf_matrix: Matrix
    observations: tuple[TextObservation, ...]
    visual_observations: tuple[VisualObservation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not self.visual_observations:
            payload.pop("visual_observations")
        return payload
