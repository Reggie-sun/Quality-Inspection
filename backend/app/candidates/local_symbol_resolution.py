from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.candidates.parser import normalize_text, parse_annotation
from app.candidates.symbol_review import (
    SymbolKind,
    VisualReviewDecision,
    project_visual_observation,
)
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import VisualGeometryContext


LOCAL_SYMBOL_FAMILIES = frozenset(
    {
        "diameter",
        "depth",
        "counterbore",
        "surface_roughness",
        "gdt_parallelism",
        "gdt_perpendicularity",
        "gdt_flatness",
        "datum_reference",
        "revision_marker",
    }
)
_ALWAYS_ESCALATE_FAMILIES = frozenset(
    {
        "counterbore",
        "gdt_parallelism",
        "gdt_perpendicularity",
        "gdt_flatness",
    }
)
_TYPED_FAMILIES = frozenset(
    {"diameter", "depth", "surface_roughness"}
)
_REFERENCE_FAMILIES = ("datum_reference", "revision_marker")
_ROUGHNESS = re.compile(r"^Ra\s*([0-9]+(?:\.[0-9]+)?)$", re.IGNORECASE)
_EXPLICIT_DEPTH = re.compile(r"^(?:深|↓)\s*([0-9]+(?:\.[0-9]+)?)$")


@dataclass(frozen=True)
class LocalResolution:
    visual_observation_id: str
    family_hypotheses: tuple[str, ...]
    resolved_family: str | None
    reason_codes: tuple[str, ...]
    projection: VisualReviewDecision | None
    confidence: float | None = None


def _resolution(
    observation: VisualObservation,
    family_hypotheses: Sequence[str],
    *reason_codes: str,
    resolved_family: str | None = None,
    projection: VisualReviewDecision | None = None,
    confidence: float | None = None,
) -> LocalResolution:
    return LocalResolution(
        visual_observation_id=observation.observation_id,
        family_hypotheses=tuple(sorted(set(family_hypotheses))),
        resolved_family=resolved_family,
        reason_codes=tuple(sorted(set(reason_codes))),
        projection=projection,
        confidence=confidence,
    )


def _valid_bbox(bbox: Sequence[float]) -> bool:
    return (
        len(bbox) == 4
        and all(math.isfinite(value) for value in bbox)
        and bbox[2] > bbox[0]
        and bbox[3] > bbox[1]
    )


def _candidate_sources(candidate: Mapping[str, Any]) -> tuple[str, ...] | None:
    source_ids = candidate.get("source_location_ids")
    if not isinstance(source_ids, (list, tuple)) or any(
        not isinstance(source_id, str) or not source_id
        for source_id in source_ids
    ):
        return None
    return tuple(source_ids)


def _exact_source_candidates(
    candidates: Sequence[Mapping[str, Any]],
    associated_ids: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    expected = set(associated_ids)
    return tuple(
        candidate
        for candidate in candidates
        if (
            (sources := _candidate_sources(candidate)) is not None
            and set(sources) == expected
            and len(sources) == len(expected)
        )
    )


def _overlapping_source_candidates(
    candidates: Sequence[Mapping[str, Any]],
    associated_ids: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    expected = set(associated_ids)
    return tuple(
        candidate
        for candidate in candidates
        if (
            (sources := _candidate_sources(candidate)) is not None
            and expected.intersection(sources)
        )
    )


def _source_bbox(
    source_ids: Sequence[str],
    text_by_id: Mapping[str, TextObservation],
) -> tuple[float, float, float, float] | None:
    try:
        bboxes = tuple(text_by_id[source_id].bbox_pdf for source_id in source_ids)
    except KeyError:
        return None
    if not bboxes or any(not _valid_bbox(bbox) for bbox in bboxes):
        return None
    return (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )


def _candidate_coordinates_agree(
    candidate: Mapping[str, Any],
    text_by_id: Mapping[str, TextObservation],
) -> bool:
    source_ids = _candidate_sources(candidate)
    payload = candidate.get("payload")
    if source_ids is None or not isinstance(payload, Mapping):
        return False
    coordinates = payload.get("coordinates")
    if (
        not isinstance(coordinates, (list, tuple))
        or len(coordinates) != 4
    ):
        return False
    try:
        candidate_bbox = tuple(float(value) for value in coordinates)
    except (TypeError, ValueError):
        return False
    source_bbox = _source_bbox(source_ids, text_by_id)
    return (
        source_bbox is not None
        and _valid_bbox(candidate_bbox)
        and candidate_bbox == source_bbox
    )


def _requirements(
    payload: Mapping[str, Any],
    kind: str,
) -> tuple[Mapping[str, Any], ...]:
    requirements = payload.get("sub_requirements")
    if not isinstance(requirements, list):
        return ()
    return tuple(
        requirement
        for requirement in requirements
        if isinstance(requirement, Mapping)
        and requirement.get("kind") == kind
    )


def _is_typed_candidate(
    candidate: Mapping[str, Any],
    family: str,
) -> bool:
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        return False
    item_type = payload.get("item_type")
    if family == "diameter":
        if item_type == "diameter_dimension":
            return payload.get("nominal") is not None
        diameter_requirements = _requirements(payload, "diameter_dimension")
        return (
            item_type == "composite"
            and len(diameter_requirements) == 1
            and diameter_requirements[0].get("nominal") is not None
        )
    if family == "depth":
        if item_type == "diameter_dimension":
            return payload.get("depth") is not None
        if item_type == "thread":
            return payload.get("thread_depth") is not None
        depth_requirements = _requirements(payload, "depth")
        return (
            item_type == "composite"
            and len(depth_requirements) == 1
            and depth_requirements[0].get("value") is not None
        )
    if family == "surface_roughness":
        return (
            payload.get("coarse_type") == "roughness"
            and _roughness_value(payload.get("raw_text")) is not None
        )
    return False


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _diameter_value(texts: Sequence[TextObservation]) -> Decimal | None:
    if len(texts) != 1 or texts[0].source_type != "native":
        return None
    normalized = normalize_text(texts[0].raw_text)
    if not normalized.startswith("Φ"):
        return None
    try:
        parsed = parse_annotation(normalized)
    except ValueError:
        return None
    if parsed.item_type != "diameter_dimension" or parsed.nominal is None:
        return None
    return parsed.nominal


def _candidate_diameter_value(
    candidate: Mapping[str, Any],
) -> Decimal | None:
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        return None
    if payload.get("item_type") == "diameter_dimension":
        return _decimal(payload.get("nominal"))
    requirements = _requirements(payload, "diameter_dimension")
    if len(requirements) != 1:
        return None
    return _decimal(requirements[0].get("nominal"))


def _depth_value(texts: Sequence[TextObservation]) -> Decimal | None:
    if not texts or any(text.source_type != "native" for text in texts):
        return None
    values: list[Decimal] = []
    for text in texts:
        try:
            parsed = parse_annotation(text.raw_text)
        except ValueError:
            parsed = None
        if parsed is not None:
            value = (
                parsed.depth
                if parsed.item_type == "diameter_dimension"
                else parsed.thread_depth
                if parsed.item_type == "thread"
                else None
            )
            if value is not None:
                values.append(value)
                continue
        match = _EXPLICIT_DEPTH.fullmatch(normalize_text(text.raw_text))
        if match is not None:
            value = _decimal(match.group(1))
            if value is not None:
                values.append(value)
    return values[0] if len(values) == 1 else None


def _candidate_depth_value(
    candidate: Mapping[str, Any],
) -> Decimal | None:
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        return None
    if payload.get("item_type") == "diameter_dimension":
        return _decimal(payload.get("depth"))
    if payload.get("item_type") == "thread":
        return _decimal(payload.get("thread_depth"))
    requirements = _requirements(payload, "depth")
    if len(requirements) != 1:
        return None
    return _decimal(requirements[0].get("value"))


def _roughness_value(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    match = _ROUGHNESS.fullmatch(normalize_text(value))
    return None if match is None else _decimal(match.group(1))


def _source_roughness_value(
    texts: Sequence[TextObservation],
) -> Decimal | None:
    if len(texts) != 1 or texts[0].source_type != "native":
        return None
    return _roughness_value(texts[0].raw_text)


def _candidate_roughness_value(
    candidate: Mapping[str, Any],
) -> Decimal | None:
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        return None
    return _roughness_value(payload.get("raw_text"))


def _projection_kinds(
    family: str,
    candidate: Mapping[str, Any],
) -> tuple[SymbolKind, ...]:
    if family != "diameter":
        return (family,)  # type: ignore[return-value]
    payload = candidate.get("payload")
    if (
        isinstance(payload, Mapping)
        and payload.get("item_type") == "composite"
        and len(_requirements(payload, "depth")) == 1
    ):
        return ("diameter", "depth")
    return ("diameter",)


def _project(
    *,
    observation: VisualObservation,
    family: str,
    text_observations: Sequence[TextObservation],
    candidates: Sequence[Mapping[str, Any]],
    geometry_context: VisualGeometryContext | None,
) -> VisualReviewDecision:
    kinds = _projection_kinds(
        family,
        candidates[0] if candidates else {},
    )
    detections = tuple(
        {
            "visual_observation_id": observation.observation_id,
            "symbol_kind": kind,
            "bbox_pdf": observation.bbox_pdf,
            "associated_text_observation_ids": (
                observation.associated_text_observation_ids
            ),
        }
        for kind in kinds
    )
    return project_visual_observation(
        observation=observation,
        detections=detections,
        text_observations=text_observations,
        candidates=candidates,
        geometry_context=geometry_context,
    )


def _resolve_reference_family(
    *,
    observation: VisualObservation,
    family: str,
    family_hypotheses: Sequence[str],
    text_observations: Sequence[TextObservation],
    candidates: Sequence[Mapping[str, Any]],
    geometry_context: VisualGeometryContext | None,
    confidence: float | None,
) -> LocalResolution:
    projections = {
        hypothesis: _project(
            observation=observation,
            family=hypothesis,
            text_observations=text_observations,
            candidates=candidates,
            geometry_context=geometry_context,
        )
        for hypothesis in _REFERENCE_FAMILIES
    }
    accepted = tuple(
        hypothesis
        for hypothesis, projection in projections.items()
        if projection.disposition != "ambiguous"
    )
    if accepted == (family,):
        return _resolution(
            observation,
            family_hypotheses,
            "deterministic_geometry_complete",
            "local_projection_complete",
            resolved_family=family,
            projection=projections[family],
            confidence=confidence,
        )
    if accepted:
        return _resolution(
            observation,
            family_hypotheses,
            "local_evidence_conflict",
            confidence=confidence,
        )
    return _resolution(
        observation,
        family_hypotheses,
        "local_parse_incomplete",
        confidence=confidence,
    )


def resolve_visual_observation(
    *,
    observation: VisualObservation,
    family_hypotheses: Sequence[str],
    text_observations: Sequence[TextObservation],
    candidates: Sequence[Mapping[str, Any]],
    geometry_context: VisualGeometryContext | None,
    confidence: float | None = None,
) -> LocalResolution:
    """Resolve one admitted visual observation from deterministic local evidence."""
    hypotheses = tuple(sorted(set(family_hypotheses)))
    if not _valid_bbox(observation.bbox_pdf):
        return _resolution(
            observation,
            hypotheses,
            "visual_geometry_invalid",
            confidence=confidence,
        )
    if geometry_context is not None and (
        geometry_context.observation_id != observation.observation_id
        or geometry_context.page_index != observation.page_index
        or geometry_context.geometry_sha256 != observation.geometry_sha256
    ):
        return _resolution(
            observation,
            hypotheses,
            "source_reconstruction_mismatch",
            confidence=confidence,
        )

    associated_ids = observation.associated_text_observation_ids
    text_by_id: dict[str, TextObservation] = {}
    duplicate_text_ids: set[str] = set()
    for text in text_observations:
        if text.observation_id in text_by_id:
            duplicate_text_ids.add(text.observation_id)
        text_by_id[text.observation_id] = text
    if (
        not associated_ids
        or len(set(associated_ids)) != len(associated_ids)
        or any(source_id not in text_by_id for source_id in associated_ids)
        or any(source_id in duplicate_text_ids for source_id in associated_ids)
    ):
        return _resolution(
            observation,
            hypotheses,
            "coverage_lineage_incomplete",
            confidence=confidence,
        )
    if any(
        text_by_id[source_id].page_index != observation.page_index
        for source_id in associated_ids
    ):
        return _resolution(
            observation,
            hypotheses,
            "local_evidence_conflict",
            confidence=confidence,
        )
    if not hypotheses or any(
        family not in LOCAL_SYMBOL_FAMILIES for family in hypotheses
    ):
        return _resolution(
            observation,
            hypotheses,
            "unknown_symbol_pattern",
            confidence=confidence,
        )
    if len(hypotheses) != 1:
        return _resolution(
            observation,
            hypotheses,
            "local_evidence_conflict",
            confidence=confidence,
        )

    family = hypotheses[0]
    exact_candidates = _exact_source_candidates(candidates, associated_ids)
    if family in _ALWAYS_ESCALATE_FAMILIES:
        coarse_candidates = tuple(
            candidate
            for candidate in exact_candidates
            if isinstance(candidate.get("payload"), Mapping)
            and candidate["payload"].get("coarse_type") is not None
        )
        reason = (
            "local_evidence_conflict"
            if len(coarse_candidates) > 1
            else "missing_local_discriminator"
        )
        return _resolution(
            observation,
            hypotheses,
            reason,
            confidence=confidence,
        )
    if family in _REFERENCE_FAMILIES:
        return _resolve_reference_family(
            observation=observation,
            family=family,
            family_hypotheses=hypotheses,
            text_observations=text_observations,
            candidates=candidates,
            geometry_context=geometry_context,
            confidence=confidence,
        )
    if family not in _TYPED_FAMILIES:
        return _resolution(
            observation,
            hypotheses,
            "unknown_symbol_pattern",
            confidence=confidence,
        )

    overlapping_candidates = _overlapping_source_candidates(
        candidates,
        associated_ids,
    )
    if len(overlapping_candidates) > 1:
        return _resolution(
            observation,
            hypotheses,
            "local_evidence_conflict",
            confidence=confidence,
        )
    if len(exact_candidates) != 1 or not _is_typed_candidate(
        exact_candidates[0],
        family,
    ):
        return _resolution(
            observation,
            hypotheses,
            "local_parse_incomplete",
            confidence=confidence,
        )

    candidate = exact_candidates[0]
    if not _candidate_coordinates_agree(candidate, text_by_id):
        return _resolution(
            observation,
            hypotheses,
            "local_evidence_conflict",
            confidence=confidence,
        )
    source_texts = tuple(text_by_id[source_id] for source_id in associated_ids)
    if family == "diameter":
        source_value = _diameter_value(source_texts)
        candidate_value = _candidate_diameter_value(candidate)
        if source_value is None:
            return _resolution(
                observation,
                hypotheses,
                "local_parse_incomplete",
                confidence=confidence,
            )
        if candidate_value is None or source_value != candidate_value:
            return _resolution(
                observation,
                hypotheses,
                "local_evidence_conflict",
                confidence=confidence,
            )
    if family == "depth":
        source_value = _depth_value(source_texts)
        candidate_value = _candidate_depth_value(candidate)
        if source_value is None:
            return _resolution(
                observation,
                hypotheses,
                "local_parse_incomplete",
                confidence=confidence,
            )
        if candidate_value is None or source_value != candidate_value:
            return _resolution(
                observation,
                hypotheses,
                "local_evidence_conflict",
                confidence=confidence,
            )
    if family == "surface_roughness":
        source_value = _source_roughness_value(source_texts)
        candidate_value = _candidate_roughness_value(candidate)
        if source_value is None:
            return _resolution(
                observation,
                hypotheses,
                "local_parse_incomplete",
                confidence=confidence,
            )
        if candidate_value is None or source_value != candidate_value:
            return _resolution(
                observation,
                hypotheses,
                "local_evidence_conflict",
                confidence=confidence,
            )

    projection = _project(
        observation=observation,
        family=family,
        text_observations=text_observations,
        candidates=exact_candidates,
        geometry_context=geometry_context,
    )
    if projection.disposition == "ambiguous":
        reason = (
            "local_evidence_conflict"
            if projection.rejection_code == "visual_projection_conflict"
            else "local_parse_incomplete"
        )
        return _resolution(
            observation,
            hypotheses,
            reason,
            confidence=confidence,
        )
    return _resolution(
        observation,
        hypotheses,
        "local_projection_complete",
        "native_symbol_explicit",
        resolved_family=family,
        projection=projection,
        confidence=confidence,
    )
