from __future__ import annotations

import hashlib
import json
import math
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
_VISUAL_REJECTION_CODES = {
    "visual_bbox_invalid",
    "visual_source_mismatch",
    "visual_duplicate_detection",
    "visual_local_parse_failed",
    "visual_projection_conflict",
    "visual_no_detection",
}
_VISUAL_SYMBOL_KINDS = {
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
_VISUAL_INSPECTION_KIND_SETS = {
    ("diameter",),
    ("depth",),
    ("depth", "diameter"),
    ("counterbore", "depth", "diameter"),
    ("surface_roughness",),
    ("gdt_parallelism",),
    ("gdt_perpendicularity",),
    ("gdt_flatness",),
}
_VISUAL_REVIEW_KEYS = {
    "route",
    "schema_version",
    "symbol_kinds",
    "rejection_code",
    "confidence_signal",
}
_LOCAL_RESOLUTION_REASON_CODES = {
    "native_symbol_explicit",
    "deterministic_geometry_complete",
    "local_projection_complete",
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
    disposition_reason: str | None = None
    disposition_rule_version: str | None = None

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
        if self.disposition_reason is not None:
            payload["disposition_reason"] = self.disposition_reason
        if self.disposition_rule_version is not None:
            payload["disposition_rule_version"] = (
                self.disposition_rule_version
            )
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


def _valid_coordinates(
    coordinates: tuple[float, float, float, float] | None,
) -> bool:
    return (
        isinstance(coordinates, tuple)
        and len(coordinates) == 4
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in coordinates
        )
        and coordinates[2] > coordinates[0]
        and coordinates[3] > coordinates[1]
    )


def _valid_visual_semantics(
    entry: CoverageEntry,
    *,
    symbol_kinds: list[str],
    rejection_code: object,
    confidence_signal: object,
    local_resolution_valid: bool,
) -> bool:
    kinds = tuple(symbol_kinds)
    has_candidate = not _is_blank(entry.candidate_id)
    if entry.disposition == "candidate":
        return (
            has_candidate
            and rejection_code is None
            and (
                confidence_signal is not None
                or local_resolution_valid
            )
            and kinds in _VISUAL_INSPECTION_KIND_SETS
        )
    if entry.disposition == "reference_context":
        return (
            not has_candidate
            and not entry.requires_confirmation
            and rejection_code is None
            and (
                confidence_signal is not None
                or local_resolution_valid
            )
            and kinds == ("datum_reference",)
        )
    if entry.disposition == "non_inspection":
        return (
            not has_candidate
            and entry.requires_confirmation
            and rejection_code is None
            and (
                confidence_signal is not None
                or local_resolution_valid
            )
            and kinds == ("revision_marker",)
        )
    if entry.disposition == "ambiguous":
        return (
            not has_candidate
            and entry.requires_confirmation
            and not local_resolution_valid
            and rejection_code in _VISUAL_REJECTION_CODES
            and (
                (rejection_code == "visual_no_detection" and not kinds)
                or rejection_code != "visual_no_detection"
            )
        )
    return False


def _valid_local_resolution_evidence(
    entry: CoverageEntry,
    value: object,
) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "router_version",
        "input_sha256",
        "decision_sha256",
        "reason_codes",
    }:
        return False
    input_sha256 = value.get("input_sha256")
    decision_sha256 = value.get("decision_sha256")
    reason_codes = value.get("reason_codes")
    if (
        value.get("schema_version") != "symbol-routing-decision/1"
        or value.get("router_version") != "symbol-uncertainty-router/1"
        or not isinstance(input_sha256, str)
        or len(input_sha256) != 64
        or any(character not in "0123456789abcdef" for character in input_sha256)
        or not isinstance(decision_sha256, str)
        or len(decision_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in decision_sha256
        )
        or not isinstance(reason_codes, list)
        or not reason_codes
        or any(not isinstance(code, str) for code in reason_codes)
        or reason_codes != sorted(set(reason_codes))
        or not set(reason_codes).issubset(
            _LOCAL_RESOLUTION_REASON_CODES
        )
        or "local_projection_complete" not in reason_codes
        or not set(reason_codes).intersection(
            {
                "native_symbol_explicit",
                "deterministic_geometry_complete",
            }
        )
    ):
        return False
    canonical = json.dumps(
        {
            "schema_version": value["schema_version"],
            "router_version": value["router_version"],
            "visual_observation_id": entry.observation_id,
            "input_sha256": input_sha256,
            "disposition": "locally_resolved",
            "local_resolution_reason_codes": reason_codes,
            "escalation_reason_codes": [],
            "block_reason_codes": [],
            "requires_confirmation": entry.requires_confirmation,
            "escalation_group_id": None,
            "escalation_group_member_index": None,
            "local_resolution_ref": f"sha256:{input_sha256}",
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest() == decision_sha256


def check_coverage(
    entries: list[CoverageEntry] | tuple[CoverageEntry, ...],
    *,
    expected_observation_ids: set[str] | tuple[str, ...] | list[str] | None = None,
    required_visual_observation_ids: (
        set[str] | tuple[str, ...] | list[str] | None
    ) = None,
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
    required_visual = set(required_visual_observation_ids or ())

    for entry in frozen_entries:
        occurrence_count[entry.observation_id] = (
            occurrence_count.get(entry.observation_id, 0) + 1
        )
        incomplete = (
            _is_blank(entry.observation_id)
            or entry.disposition not in _DISPOSITIONS
            or _is_blank(entry.source_location_id)
            or not _valid_coordinates(entry.coordinates)
            or (
                entry.disposition == "candidate"
                and _is_blank(entry.candidate_id)
            )
        )
        if incomplete:
            blocking_ids.add(entry.observation_id)
        if entry.observation_id in required_visual:
            review = entry.advisor_review
            symbol_kinds = (
                review.get("symbol_kinds")
                if isinstance(review, dict)
                else None
            )
            symbol_kinds_valid = (
                isinstance(symbol_kinds, list)
                and all(isinstance(kind, str) for kind in symbol_kinds)
                and symbol_kinds == sorted(set(symbol_kinds))
                and set(symbol_kinds).issubset(_VISUAL_SYMBOL_KINDS)
            )
            local_resolution_present = (
                isinstance(review, dict)
                and "local_resolution_evidence" in review
            )
            local_resolution_valid = (
                isinstance(review, dict)
                and _valid_local_resolution_evidence(
                    entry,
                    review.get("local_resolution_evidence"),
                )
            )
            visual_review_valid = (
                isinstance(review, dict)
                and set(review)
                == (
                    _VISUAL_REVIEW_KEYS
                    | {"local_resolution_evidence"}
                    if local_resolution_present
                    else _VISUAL_REVIEW_KEYS
                )
                and review.get("route") == "visual_symbol"
                and review.get("schema_version") == "visual-symbol-review/3"
                and symbol_kinds_valid
                and (
                    not local_resolution_present
                    or local_resolution_valid
                )
                and (
                    review.get("confidence_signal") is None
                    or (
                        isinstance(
                            review.get("confidence_signal"),
                            (int, float),
                        )
                        and not isinstance(
                            review.get("confidence_signal"),
                            bool,
                        )
                        and math.isfinite(
                            float(review["confidence_signal"])
                        )
                        and 0
                        <= float(review["confidence_signal"])
                        <= 1
                    )
                )
                and (
                    review.get("rejection_code") is None
                    or review.get("rejection_code") in _VISUAL_REJECTION_CODES
                )
            )
            if not visual_review_valid:
                blocking_ids.add(entry.observation_id)
            if (
                entry.source_location_id != entry.observation_id
                or not visual_review_valid
                or not isinstance(symbol_kinds, list)
                or not _valid_visual_semantics(
                    entry,
                    symbol_kinds=symbol_kinds,
                    rejection_code=(
                        review.get("rejection_code")
                        if isinstance(review, dict)
                        else None
                    ),
                    confidence_signal=(
                        review.get("confidence_signal")
                        if isinstance(review, dict)
                        else None
                    ),
                    local_resolution_valid=local_resolution_valid,
                )
            ):
                blocking_ids.add(entry.observation_id)
        if entry.disposition == "ambiguous" or entry.requires_confirmation:
            review_required_ids.add(entry.observation_id)

    blocking_ids.update(
        observation_id
        for observation_id, count in occurrence_count.items()
        if count != 1
    )
    blocking_ids.update(expected.difference(occurrence_count))
    blocking_ids.update(required_visual.difference(occurrence_count))

    return CoverageReport(
        blocking_count=len(blocking_ids),
        review_required_count=len(review_required_ids),
        coverage_checked=not blocking_ids,
        entries=frozen_entries,
        blocking_observation_ids=tuple(sorted(blocking_ids)),
    )
