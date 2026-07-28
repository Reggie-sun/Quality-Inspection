#!/usr/bin/env python3
"""Compare one immutable symbol manifest with one persisted automatic result."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


OVERLAP_THRESHOLD = 0.5
_NEGATIVE_KINDS = frozenset({"frozen_negative"})
_SEMANTIC_DISPOSITIONS = frozenset({"reference_context", "non_inspection"})

BBox = tuple[float, float, float, float]


def _bbox(value: Any) -> BBox:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 4
        or any(not isinstance(item, (int, float)) for item in value)
    ):
        raise ValueError("symbol eval bbox must contain four numbers")
    bbox = tuple(float(item) for item in value)
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        raise ValueError("symbol eval bbox must have positive area")
    return bbox  # type: ignore[return-value]


def _union(boxes: Sequence[BBox]) -> BBox:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _overlap(left: BBox, right: BBox) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(
        0.0,
        min(left[3], right[3]) - max(left[1], right[1]),
    )
    intersection_area = intersection_width * intersection_height
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    return intersection_area / min(left_area, right_area)


def _labels(
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("symbol eval manifest pages are unavailable")
    for page in pages:
        if not isinstance(page, Mapping) or not isinstance(page.get("labels"), list):
            raise ValueError("symbol eval manifest page is invalid")
        page_index = page.get("page_index")
        if not isinstance(page_index, int):
            raise ValueError("symbol eval manifest page index is invalid")
        for source in page["labels"]:
            if not isinstance(source, Mapping):
                raise ValueError("symbol eval manifest label is invalid")
            label_id = source.get("label_id")
            kinds = source.get("symbol_kinds")
            if (
                not isinstance(label_id, str)
                or not label_id
                or not isinstance(kinds, list)
                or any(not isinstance(kind, str) for kind in kinds)
            ):
                raise ValueError("symbol eval manifest label identity is invalid")
            label = {
                "label_id": label_id,
                "page_index": page_index,
                "bbox_pdf": _bbox(source.get("bbox_pdf")),
                "symbol_kinds": frozenset(kinds),
                "expected_disposition": source.get("expected_disposition"),
                "expected_projection": source.get("expected_projection"),
                "negative_family": source.get("negative_family"),
            }
            (negative if label["symbol_kinds"] == _NEGATIVE_KINDS else positive).append(
                label
            )
    return positive, negative


def _visual_index(
    visual_observations: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for source in visual_observations:
        observation_id = source.get("observation_id")
        page_index = source.get("page_index")
        if not isinstance(observation_id, str) or not observation_id:
            raise ValueError("visual observation identity is invalid")
        if observation_id in indexed:
            raise ValueError("visual observation identity is duplicated")
        if not isinstance(page_index, int):
            raise ValueError("visual observation page index is invalid")
        indexed[observation_id] = {
            "page_index": page_index,
            "bbox_pdf": _bbox(source.get("bbox_pdf")),
        }
    return indexed


def _coverage_index(
    raw_coverage: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for entry in raw_coverage:
        observation_id = entry.get("observation_id")
        if isinstance(observation_id, str) and observation_id:
            indexed.setdefault(observation_id, []).append(entry)
    return indexed


def _detected_kinds(
    visual_ids: Sequence[str],
    coverage: Mapping[str, Sequence[Mapping[str, Any]]],
) -> frozenset[str]:
    kinds: set[str] = set()
    for visual_id in visual_ids:
        for entry in coverage.get(visual_id, ()):
            advisor_review = entry.get("advisor_review")
            if not isinstance(advisor_review, Mapping):
                continue
            values = advisor_review.get("symbol_kinds")
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                continue
            kinds.update(value for value in values if isinstance(value, str))
    return frozenset(kinds)


def _projection(candidate: Mapping[str, Any]) -> str | None:
    payload = candidate.get("payload")
    if not isinstance(payload, Mapping):
        return None
    for field in ("item_type", "coarse_type"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _failure(
    reason: str,
    *,
    label_id: str | None = None,
    candidate_id: str | None = None,
    overlap_ratio: float | None = None,
) -> dict[str, Any]:
    failure: dict[str, Any] = {"reason": reason}
    if label_id is not None:
        failure["label_id"] = label_id
    if candidate_id is not None:
        failure["candidate_id"] = candidate_id
    if overlap_ratio is not None:
        failure["overlap_ratio"] = round(overlap_ratio, 6)
    return failure


def _participant_candidates(
    raw_candidates: Sequence[Mapping[str, Any]],
    visuals: Mapping[str, Mapping[str, Any]],
    coverage: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    participants: list[dict[str, Any]] = []
    excluded: list[str] = []
    failures: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for candidate in raw_candidates:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("symbol eval candidate identity is invalid")
        if candidate_id in candidate_ids:
            failures.append(
                _failure("candidate_id_duplicated", candidate_id=candidate_id)
            )
            continue
        candidate_ids.add(candidate_id)
        source_ids = candidate.get("source_location_ids")
        if not isinstance(source_ids, Sequence) or isinstance(
            source_ids,
            (str, bytes),
        ):
            raise ValueError("symbol eval candidate sources are invalid")
        visual_ids = sorted(
            {
                source_id
                for source_id in source_ids
                if isinstance(source_id, str) and source_id in visuals
            }
        )
        if not visual_ids:
            excluded.append(candidate_id)
            continue
        page_indexes = {
            int(visuals[source_id]["page_index"]) for source_id in visual_ids
        }
        if len(page_indexes) != 1:
            failures.append(
                _failure(
                    "visual_candidate_page_conflict",
                    candidate_id=candidate_id,
                )
            )
            participants.append(
                {
                    "candidate_id": candidate_id,
                    "page_index": None,
                    "bbox_pdf": None,
                    "symbol_kinds": _detected_kinds(visual_ids, coverage),
                    "projection": _projection(candidate),
                }
            )
            continue
        participants.append(
            {
                "candidate_id": candidate_id,
                "page_index": next(iter(page_indexes)),
                "bbox_pdf": _union(
                    [visuals[source_id]["bbox_pdf"] for source_id in visual_ids]
                ),
                "symbol_kinds": _detected_kinds(visual_ids, coverage),
                "projection": _projection(candidate),
            }
        )
    return participants, sorted(excluded), failures


def evaluate_symbol_result(
    *,
    manifest: Mapping[str, Any],
    visual_observations: Sequence[Mapping[str, Any]],
    raw_candidates: Sequence[Mapping[str, Any]],
    raw_coverage: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a sanitized, deterministic report without influencing recognition."""
    positive_labels, negative_labels = _labels(manifest)
    candidate_labels = [
        label
        for label in positive_labels
        if label["expected_disposition"] == "candidate"
    ]
    semantic_labels = [
        label
        for label in positive_labels
        if label["expected_disposition"] in _SEMANTIC_DISPOSITIONS
    ]
    visuals = _visual_index(visual_observations)
    coverage = _coverage_index(raw_coverage)
    participants, excluded, failures = _participant_candidates(
        raw_candidates,
        visuals,
        coverage,
    )

    candidate_edges: list[dict[str, Any]] = []
    for candidate in participants:
        if candidate["bbox_pdf"] is None:
            continue
        for label in candidate_labels:
            if (
                candidate["page_index"] != label["page_index"]
                or candidate["symbol_kinds"] != label["symbol_kinds"]
                or candidate["projection"] != label["expected_projection"]
            ):
                continue
            ratio = _overlap(candidate["bbox_pdf"], label["bbox_pdf"])
            if ratio >= OVERLAP_THRESHOLD:
                candidate_edges.append(
                    {
                        "label_id": label["label_id"],
                        "candidate_id": candidate["candidate_id"],
                        "disposition": "candidate",
                        "overlap_ratio": round(ratio, 6),
                    }
                )

    label_matches: list[dict[str, Any]] = []
    for label in candidate_labels:
        edges = [
            edge for edge in candidate_edges if edge["label_id"] == label["label_id"]
        ]
        if len(edges) != 1:
            failures.append(
                _failure(
                    "positive_label_degree_not_one",
                    label_id=label["label_id"],
                )
            )
        else:
            label_matches.append(edges[0])
    for candidate in participants:
        edges = [
            edge
            for edge in candidate_edges
            if edge["candidate_id"] == candidate["candidate_id"]
        ]
        if len(edges) != 1:
            failures.append(
                _failure(
                    "visual_candidate_degree_not_one",
                    candidate_id=candidate["candidate_id"],
                )
            )

    semantic_match_counts = Counter()
    semantic_entries: list[dict[str, Any]] = []
    for observation_id, entries in coverage.items():
        visual = visuals.get(observation_id)
        if visual is None:
            continue
        for entry in entries:
            disposition = entry.get("disposition")
            if disposition not in _SEMANTIC_DISPOSITIONS:
                continue
            semantic_entries.append(
                {
                    "observation_id": observation_id,
                    "page_index": visual["page_index"],
                    "bbox_pdf": visual["bbox_pdf"],
                    "symbol_kinds": _detected_kinds((observation_id,), coverage),
                    "disposition": disposition,
                    "candidate_id": entry.get("candidate_id"),
                    "requires_confirmation": entry.get("requires_confirmation"),
                }
            )
    for label in semantic_labels:
        edges: list[dict[str, Any]] = []
        for entry in semantic_entries:
            if (
                entry["page_index"] != label["page_index"]
                or entry["symbol_kinds"] != label["symbol_kinds"]
                or entry["disposition"] != label["expected_disposition"]
                or entry["candidate_id"] is not None
            ):
                continue
            if (
                label["symbol_kinds"] == frozenset({"revision_marker"})
                and entry["requires_confirmation"] is not True
            ):
                continue
            ratio = _overlap(entry["bbox_pdf"], label["bbox_pdf"])
            if ratio >= OVERLAP_THRESHOLD:
                edges.append(
                    {
                        "label_id": label["label_id"],
                        "candidate_id": None,
                        "observation_id": entry["observation_id"],
                        "disposition": entry["disposition"],
                        "overlap_ratio": round(ratio, 6),
                    }
                )
        if len(edges) != 1:
            failures.append(
                _failure(
                    "semantic_label_match_not_one",
                    label_id=label["label_id"],
                )
            )
        else:
            label_matches.append(edges[0])
            semantic_match_counts[str(label["expected_disposition"])] += 1

    negative_false_positive_count = 0
    for candidate in participants:
        if candidate["bbox_pdf"] is None:
            continue
        for label in negative_labels:
            if candidate["page_index"] != label["page_index"]:
                continue
            ratio = _overlap(candidate["bbox_pdf"], label["bbox_pdf"])
            if ratio < OVERLAP_THRESHOLD:
                continue
            negative_false_positive_count += 1
            failures.append(
                _failure(
                    "negative_candidate_overlap",
                    label_id=label["label_id"],
                    candidate_id=candidate["candidate_id"],
                    overlap_ratio=ratio,
                )
            )

    positive_family_counts = Counter(
        kind for label in positive_labels for kind in label["symbol_kinds"]
    )
    negative_family_counts = Counter(
        str(label["negative_family"]) for label in negative_labels
    )
    label_matches.sort(
        key=lambda item: (
            str(item["label_id"]),
            str(item.get("candidate_id") or ""),
            str(item.get("observation_id") or ""),
        )
    )
    failures.sort(
        key=lambda item: (
            str(item["reason"]),
            str(item.get("label_id") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    report = {
        "schema_version": "symbol-eval-report/1",
        "passed": not failures,
        "overlap_threshold": OVERLAP_THRESHOLD,
        "counts": {
            "positive_label_count": len(positive_labels),
            "candidate_label_count": len(candidate_labels),
            "participating_candidate_count": len(participants),
            "candidate_match_count": len(candidate_edges),
            "reference_match_count": semantic_match_counts["reference_context"],
            "non_inspection_match_count": semantic_match_counts["non_inspection"],
            "negative_label_count": len(negative_labels),
            "negative_false_positive_count": negative_false_positive_count,
            "excluded_candidate_count": len(excluded),
        },
        "positive_family_counts": dict(sorted(positive_family_counts.items())),
        "negative_family_counts": dict(sorted(negative_family_counts.items())),
        "label_matches": label_matches,
        "excluded_candidate_ids": excluded,
        "failures": failures,
    }
    return report
