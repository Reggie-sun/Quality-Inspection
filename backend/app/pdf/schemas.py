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
class ObservationRegionAssignment:
    observation_id: str
    page_index: int
    profile_id: str
    region_id: Literal[
        "title_block",
        "revision_table",
        "archive_strip",
        "page_frame",
    ]
    cell_role: str
    cell_id: str
    assignment_evidence_codes: tuple[str, ...]
    boundary_distance_mm: float
    rule_version: str


@dataclass(frozen=True)
class LayoutProfileMatch:
    page_index: int
    profile_id: str
    match_state: Literal["high_confidence"]
    geometry_evidence_codes: tuple[str, ...]
    text_anchor_evidence_codes: tuple[str, ...]
    assignments: tuple[ObservationRegionAssignment, ...]
    rule_version: str


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
    layout_profile_match: LayoutProfileMatch | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not self.visual_observations:
            payload.pop("visual_observations")
        if self.layout_profile_match is None:
            payload.pop("layout_profile_match")
        return payload
