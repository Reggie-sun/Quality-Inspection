from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.pdf.coordinates import BBox
from app.pdf.gdt_frames import GdtFrameObservation
from app.candidates.geometric_tolerance import ToleranceType


GdtCellRole = Literal[
    "symbol",
    "tolerance",
    "modifier",
    "datum",
    "separator",
    "unknown",
]


class _FrozenEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GdtCellEvidence(_FrozenEvidence):
    cell_index: int = Field(ge=0)
    cell_role: GdtCellRole
    bbox_normalized: tuple[float, float, float, float]
    raw_token: str
    associated_text_observation_ids: tuple[str, ...] = ()
    confidence_signal: float = Field(ge=0.0, le=1.0)


class GdtFrameEvidence(_FrozenEvidence):
    frame_observation_id: str = Field(min_length=1)
    frame_bbox_normalized: tuple[float, float, float, float]
    tolerance_type_signal: ToleranceType
    cells: tuple[GdtCellEvidence, ...] = Field(min_length=1)
    confidence_signal: float = Field(ge=0.0, le=1.0)


class GdtEvidenceValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _raise(code: str) -> None:
    raise GdtEvidenceValidationError(code)


def _normalized_bbox(value: Sequence[float], code: str) -> BBox:
    if len(value) != 4:
        _raise(code)
    values = tuple(float(item) for item in value)
    if (
        not all(math.isfinite(item) and 0.0 <= item <= 1.0 for item in values)
        or values[2] <= values[0]
        or values[3] <= values[1]
    ):
        _raise(code)
    return values  # type: ignore[return-value]


def _to_pdf(normalized: BBox, crop_bbox_pdf: BBox) -> BBox:
    width = crop_bbox_pdf[2] - crop_bbox_pdf[0]
    height = crop_bbox_pdf[3] - crop_bbox_pdf[1]
    return (
        crop_bbox_pdf[0] + normalized[0] * width,
        crop_bbox_pdf[1] + normalized[1] * height,
        crop_bbox_pdf[0] + normalized[2] * width,
        crop_bbox_pdf[1] + normalized[3] * height,
    )


def _contains(container: BBox, candidate: BBox, *, epsilon: float = 0.01) -> bool:
    return (
        candidate[0] >= container[0] - epsilon
        and candidate[1] >= container[1] - epsilon
        and candidate[2] <= container[2] + epsilon
        and candidate[3] <= container[3] + epsilon
    )


def _parse_frame(provider_frame: Mapping[str, object]) -> GdtFrameEvidence:
    try:
        return GdtFrameEvidence.model_validate(provider_frame)
    except ValidationError:
        _raise("provider_schema_invalid")


def validate_gdt_frame_evidence(
    *,
    provider_frame: Mapping[str, object],
    observation: GdtFrameObservation,
    crop_bbox_pdf: BBox,
) -> GdtFrameEvidence:
    """Validate one Provider frame against the deterministic local proposal."""
    evidence = _parse_frame(provider_frame)
    if evidence.frame_observation_id != observation.observation_id:
        _raise("frame_id_not_found")
    if (
        crop_bbox_pdf[2] <= crop_bbox_pdf[0]
        or crop_bbox_pdf[3] <= crop_bbox_pdf[1]
    ):
        _raise("crop_bbox_invalid")

    frame_normalized = _normalized_bbox(
        evidence.frame_bbox_normalized,
        "frame_bbox_invalid",
    )
    frame_bbox_pdf = _to_pdf(frame_normalized, crop_bbox_pdf)
    if not _contains(crop_bbox_pdf, frame_bbox_pdf) or not _contains(
        observation.bbox_pdf,
        frame_bbox_pdf,
    ):
        _raise("frame_bbox_out_of_bounds")

    indexes = tuple(cell.cell_index for cell in evidence.cells)
    if indexes != tuple(range(len(indexes))):
        _raise("cell_index_not_contiguous")
    if len(evidence.cells) != len(observation.cells):
        _raise("cell_count_mismatch")

    allowlisted_ids = set(observation.associated_text_observation_ids)
    for index, cell in enumerate(evidence.cells):
        cell_bbox = _to_pdf(
            _normalized_bbox(cell.bbox_normalized, "cell_bbox_invalid"),
            crop_bbox_pdf,
        )
        if not _contains(frame_bbox_pdf, cell_bbox):
            _raise("cell_bbox_out_of_frame")
        if not _contains(observation.cells[index].bbox_pdf, cell_bbox):
            _raise("cell_bbox_mismatch")
        if any(text_id not in allowlisted_ids for text_id in cell.associated_text_observation_ids):
            _raise("text_id_not_allowlisted")
        if cell.cell_role in {"datum", "modifier"} and (
            not cell.raw_token.strip()
            or any(character.isspace() for character in cell.raw_token.strip())
        ):
            _raise("cell_token_invalid")

    return evidence


def validate_gdt_frame_evidence_batch(
    *,
    provider_frames: Sequence[Mapping[str, object]],
    observations: Sequence[GdtFrameObservation],
    crop_bbox_pdf: BBox,
) -> tuple[GdtFrameEvidence, ...]:
    if len(provider_frames) > len(observations):
        _raise("provider_frame_count_exceeded")
    observation_by_id = {
        observation.observation_id: observation
        for observation in observations
    }
    if len(observation_by_id) != len(observations):
        _raise("duplicate_observation_id")
    validated: list[GdtFrameEvidence] = []
    for provider_frame in provider_frames:
        frame_id = provider_frame.get("frame_observation_id")
        observation = observation_by_id.get(frame_id)
        if observation is None:
            _raise("frame_id_not_found")
        validated.append(
            validate_gdt_frame_evidence(
                provider_frame=provider_frame,
                observation=observation,
                crop_bbox_pdf=crop_bbox_pdf,
            )
        )
    return tuple(validated)


__all__ = [
    "GdtCellEvidence",
    "GdtCellRole",
    "GdtEvidenceValidationError",
    "GdtFrameEvidence",
    "validate_gdt_frame_evidence",
    "validate_gdt_frame_evidence_batch",
]
