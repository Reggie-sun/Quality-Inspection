from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


CoarseType = Literal[
    "roughness",
    "weld",
    "cross_view_duplicate",
]


class CoarseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    coordinates: tuple[float, float, float, float]
    coarse_type: CoarseType
    requires_confirmation: Literal[True] = True


def coarse_candidate(
    raw_text: str,
    coarse_type: CoarseType,
    coordinates: tuple[float, float, float, float],
) -> CoarseCandidate:
    return CoarseCandidate(
        raw_text=raw_text,
        coordinates=coordinates,
        coarse_type=coarse_type,
    )
