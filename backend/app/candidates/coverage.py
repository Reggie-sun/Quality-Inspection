from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Disposition = Literal[
    "candidate",
    "reference_context",
    "non_inspection",
    "ambiguous",
]
_DISPOSITIONS = {
    "candidate",
    "reference_context",
    "non_inspection",
    "ambiguous",
}


@dataclass(frozen=True)
class CoverageEntry:
    observation_id: str
    disposition: Disposition | str | None
    source_location_id: str | None
    coordinates: tuple[float, float, float, float] | None
    candidate_id: str | None = None
    requires_confirmation: bool = False
    advisor_review: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "observation_id": self.observation_id,
            "disposition": self.disposition,
            "source_location_id": self.source_location_id,
            "coordinates": self.coordinates,
            "candidate_id": self.candidate_id,
            "requires_confirmation": self.requires_confirmation,
        }
        if self.advisor_review is not None:
            payload["advisor_review"] = dict(self.advisor_review)
        return payload


@dataclass(frozen=True)
class CoverageReport:
    blocking_count: int
    review_required_count: int
    coverage_checked: bool
    entries: tuple[CoverageEntry, ...]
    blocking_observation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "blocking_count": self.blocking_count,
            "review_required_count": self.review_required_count,
            "coverage_checked": self.coverage_checked,
            "blocking_observation_ids": list(self.blocking_observation_ids),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _is_blank(value: str | None) -> bool:
    return not isinstance(value, str) or not value.strip()


def check_coverage(
    entries: list[CoverageEntry] | tuple[CoverageEntry, ...],
    *,
    expected_observation_ids: set[str] | tuple[str, ...] | list[str] | None = None,
) -> CoverageReport:
    frozen_entries = tuple(entries)
    expected = (
        {entry.observation_id for entry in frozen_entries}
        if expected_observation_ids is None
        else set(expected_observation_ids)
    )
    occurrence_count: dict[str, int] = {}
    blocking_ids: set[str] = set()
    review_required_ids: set[str] = set()

    for entry in frozen_entries:
        occurrence_count[entry.observation_id] = (
            occurrence_count.get(entry.observation_id, 0) + 1
        )
        incomplete = (
            _is_blank(entry.observation_id)
            or entry.disposition not in _DISPOSITIONS
            or _is_blank(entry.source_location_id)
            or entry.coordinates is None
            or (
                entry.disposition == "candidate"
                and _is_blank(entry.candidate_id)
            )
        )
        if incomplete:
            blocking_ids.add(entry.observation_id)
        if entry.disposition == "ambiguous" or entry.requires_confirmation:
            review_required_ids.add(entry.observation_id)

    blocking_ids.update(
        observation_id
        for observation_id, count in occurrence_count.items()
        if count != 1
    )
    blocking_ids.update(expected.difference(occurrence_count))

    return CoverageReport(
        blocking_count=len(blocking_ids),
        review_required_count=len(review_required_ids),
        coverage_checked=not blocking_ids,
        entries=frozen_entries,
        blocking_observation_ids=tuple(sorted(blocking_ids)),
    )
