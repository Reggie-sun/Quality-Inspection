from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Literal


@dataclass(frozen=True)
class DuplicateCandidate:
    candidate_id: str
    normalized_text: str
    view_id: str
    disposition: str

    def __post_init__(self) -> None:
        values = (
            self.candidate_id,
            self.normalized_text,
            self.view_id,
            self.disposition,
        )
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("duplicate candidate fields must be non-blank")


@dataclass(frozen=True)
class DuplicateRelation:
    left_candidate_id: str
    right_candidate_id: str
    relation_type: Literal["possible_duplicate"] = "possible_duplicate"
    requires_confirmation: Literal[True] = True

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "relation_type": self.relation_type,
            "requires_confirmation": self.requires_confirmation,
        }


def suggest_cross_view_duplicates(
    candidates: list[DuplicateCandidate],
) -> list[DuplicateRelation]:
    ordered = sorted(candidates, key=lambda candidate: candidate.candidate_id)
    identities = [candidate.candidate_id for candidate in ordered]
    if len(identities) != len(set(identities)):
        raise ValueError("candidate_id must be unique before duplicate advice")

    relations = []
    for left, right in combinations(ordered, 2):
        if (
            left.view_id != right.view_id
            and left.normalized_text == right.normalized_text
        ):
            relations.append(
                DuplicateRelation(
                    left_candidate_id=left.candidate_id,
                    right_candidate_id=right.candidate_id,
                )
            )
    return relations
