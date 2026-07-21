from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CandidateType = Literal[
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
    "general_requirement",
    "composite",
]


def stable_candidate_id(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()[:24]


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    item_type: CandidateType
    raw_text: str
    normalized_text: str
    coordinates: tuple[float, float, float, float] | None = None
    scope: Literal["local_feature", "global_requirement"] = "local_feature"
    quantity: int | None = Field(default=None, ge=1)
    nominal: Decimal | None = None
    upper_tolerance: Decimal | None = None
    lower_tolerance: Decimal | None = None
    feature_kind: Literal[
        "hole", "shaft", "cylindrical_feature", "unknown"
    ] | None = None
    depth: Decimal | None = None
    through: bool | None = None
    thread_spec: str | None = None
    thread_depth: Decimal | None = None
    radius_value: Decimal | None = None
    angle_value: Decimal | None = None
    sub_requirements: list[dict[str, Any]] = Field(default_factory=list)
    balloon_required: bool = True
    requires_confirmation: bool = False
