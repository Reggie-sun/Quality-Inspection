from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.candidates.parser import NUMBER, normalize_text, parse_annotation
from app.candidates.schemas import Candidate, stable_candidate_id
from app.pdf.schemas import TextObservation


DEPTH_MODIFIER = re.compile(rf"^(?:深|↓)\s*(?P<value>{NUMBER})$")
THROUGH_MODIFIER = re.compile(r"^(?:通|贯穿)$")
MODIFIER_PRIMARY_TYPES = {"diameter_dimension", "thread"}


def _sort_key(
    observation: TextObservation,
) -> tuple[int, tuple[float, float], float, float, str]:
    return (
        observation.page_index,
        observation.direction,
        observation.bbox_pdf[1],
        observation.bbox_pdf[0],
        observation.observation_id,
    )


def _modifier(observation: TextObservation) -> dict[str, Any] | None:
    normalized = normalize_text(observation.raw_text)
    if match := DEPTH_MODIFIER.fullmatch(normalized):
        return {
            "kind": "depth",
            "raw_text": observation.raw_text,
            "value": Decimal(match.group("value")),
        }
    if THROUGH_MODIFIER.fullmatch(normalized):
        return {
            "kind": "through",
            "raw_text": observation.raw_text,
            "value": True,
        }
    return None


def _directions_match(
    left: tuple[float, float], right: tuple[float, float]
) -> bool:
    return all(abs(first - second) <= 1e-6 for first, second in zip(left, right))


def _is_adjacent(left: TextObservation, right: TextObservation) -> bool:
    if left.page_index != right.page_index:
        return False
    if not _directions_match(left.direction, right.direction):
        return False
    left_height = max(left.bbox_pdf[3] - left.bbox_pdf[1], 1.0)
    right_height = max(right.bbox_pdf[3] - right.bbox_pdf[1], 1.0)
    scale = max(left_height, right_height)
    line_gap = right.bbox_pdf[1] - left.bbox_pdf[3]
    x_offset = abs(right.bbox_pdf[0] - left.bbox_pdf[0])
    return -0.5 * scale <= line_gap <= 1.5 * scale and x_offset <= 2.0 * scale


def _single_candidate(
    observation: TextObservation, candidate: Candidate
) -> Candidate:
    return candidate.model_copy(
        update={
            "candidate_id": stable_candidate_id(
                "observation", observation.observation_id
            ),
            "coordinates": observation.bbox_pdf,
        }
    )


def _primary_requirement(candidate: Candidate) -> dict[str, Any]:
    payload = candidate.model_dump(
        exclude_none=True,
        exclude={
            "balloon_required",
            "candidate_id",
            "coordinates",
            "item_type",
            "normalized_text",
            "quantity",
            "raw_text",
            "requires_confirmation",
            "scope",
            "sub_requirements",
        },
    )
    return {
        "order": 0,
        "kind": candidate.item_type,
        "raw_text": candidate.raw_text,
        **payload,
    }


def _union_bbox(
    observations: Sequence[TextObservation],
) -> tuple[float, float, float, float]:
    return (
        min(observation.bbox_pdf[0] for observation in observations),
        min(observation.bbox_pdf[1] for observation in observations),
        max(observation.bbox_pdf[2] for observation in observations),
        max(observation.bbox_pdf[3] for observation in observations),
    )


def _composite_candidate(
    observations: Sequence[TextObservation],
    primary: Candidate,
    modifiers: Sequence[dict[str, Any]],
) -> Candidate:
    sub_requirements = [_primary_requirement(primary)]
    sub_requirements.extend(
        {"order": order, **modifier}
        for order, modifier in enumerate(modifiers, start=1)
    )
    return Candidate(
        candidate_id=stable_candidate_id(
            "observation-group",
            *(observation.observation_id for observation in observations),
        ),
        item_type="composite",
        raw_text="\n".join(observation.raw_text for observation in observations),
        normalized_text="\n".join(
            normalize_text(observation.raw_text) for observation in observations
        ),
        coordinates=_union_bbox(observations),
        quantity=primary.quantity,
        sub_requirements=sub_requirements,
        balloon_required=primary.balloon_required,
        requires_confirmation=primary.requires_confirmation,
    )


def group_observations(
    observations: Sequence[TextObservation],
) -> list[Candidate]:
    ordered = sorted(observations, key=_sort_key)
    candidates: list[Candidate] = []
    index = 0
    while index < len(ordered):
        observation = ordered[index]
        if _modifier(observation) is not None:
            raise ValueError(
                f"orphan candidate modifier: {observation.observation_id}"
            )
        primary = parse_annotation(observation.raw_text)
        group = [observation]
        modifiers: list[dict[str, Any]] = []
        next_index = index + 1
        if primary.item_type in MODIFIER_PRIMARY_TYPES:
            previous = observation
            while next_index < len(ordered):
                following = ordered[next_index]
                modifier = _modifier(following)
                if modifier is None or not _is_adjacent(previous, following):
                    break
                group.append(following)
                modifiers.append(modifier)
                previous = following
                next_index += 1
        if modifiers:
            candidates.append(_composite_candidate(group, primary, modifiers))
            index = next_index
        else:
            candidates.append(_single_candidate(observation, primary))
            index += 1
    return candidates
