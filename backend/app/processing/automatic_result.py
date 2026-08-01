from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.complex_fallback import CoarseCandidate, coarse_candidate
from app.candidates.confidence import (
    CandidateSourceSignal,
    ConfidenceDecisionContractError,
    normalize_native_signal,
    normalize_tencent_ocr_signal,
    validate_confidence_decision,
)
from app.candidates.coverage import CoverageEntry, CoverageReport
from app.candidates.disposition import (
    WELLI_LAYOUT_RULE_VERSION,
    classify_primary_disposition,
    repeated_page_overlay_observation_ids,
    welli_page_frame_assignment_touches_outer_edge,
)
from app.candidates.duplicates import (
    DuplicateCandidate,
    DuplicateRelation,
    suggest_cross_view_duplicates,
)
from app.candidates.grouping import group_observations
from app.candidates.geometric_tolerance import GeometricToleranceCandidate
from app.candidates.models import AutomaticResult
from app.candidates.schemas import Candidate, stable_candidate_id
from app.candidates.technical_requirements import (
    TechnicalRequirementDecision,
    evaluate_technical_requirements,
    is_standalone_executable_requirement,
    reconstruct_technical_requirement_entries,
    technical_requirement_source_location_ids,
    validate_technical_requirements,
)
from app.jobs.idempotency import LogicalJob, LogicalJobStateError
from app.pdf.layout_profiles import welli_same_page_watermark_observation_ids
from app.pdf.schemas import LayoutProfileMatch, ObservationRegionAssignment
from app.pdf.schemas import TextObservation, VisualObservation
from app.projects.models import Project
from app.projects.state import InvalidTransition, ProjectState, transition


LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/1"
AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/2"
ROUGHNESS_TOKEN = re.compile(r"(?<![A-Za-z])Ra(?=\s*[0-9])", re.IGNORECASE)
SYMBOL_RECOGNITION_SUMMARY_VERSION = "symbol-recognition-summary/1"
_ROUTED_RECOGNITION_MODES = frozenset(
    {"shadow_uncertainty", "production_uncertainty"}
)


class CoverageBlocking(RuntimeError):
    code = "coverage_blocking"

    def __init__(self, blocking_count: int) -> None:
        self.blocking_count = blocking_count
        super().__init__(f"coverage_blocking: {blocking_count} blocking observations")


@dataclass(frozen=True)
class CandidateSnapshot:
    candidates: tuple[dict[str, Any], ...]
    coverage_entries: tuple[CoverageEntry, ...]
    expected_observation_ids: tuple[str, ...]
    duplicate_relations: tuple[DuplicateRelation, ...]
    source_signals: tuple[CandidateSourceSignal, ...] = ()
    provider_call_ids: tuple[str, ...] = ()
    required_visual_observation_ids: tuple[str, ...] = ()
    technical_requirements: tuple[dict[str, Any], ...] = ()
    completeness: str = "complete"
    recognition_mode: str = "legacy_high_recall"
    router_version: str = "legacy"
    recognition_summary: Mapping[str, Any] | None = None
    recognition_evidence_ref: str | None = None


def _validate_terminal_recognition_provenance(
    *,
    project: Project,
    project_id: uuid.UUID,
    completeness: str,
    recognition_mode: str,
    router_version: str,
    recognition_summary: Mapping[str, Any] | None,
    recognition_evidence_ref: str | None,
) -> None:
    if recognition_mode != project.recognition_mode:
        raise ValueError("recognition_mode must match the locked project")
    if router_version != project.recognition_router_version:
        raise ValueError("router_version must match the locked project")
    if (
        recognition_mode in _ROUTED_RECOGNITION_MODES
        or recognition_summary is not None
        or completeness == "partial_review_required"
    ):
        if not isinstance(recognition_summary, Mapping):
            raise ValueError("recognition_summary must be one object")
        summary = dict(recognition_summary)
        if (
            set(summary) != {"schema_version", "unresolved_roi_count"}
            or summary.get("schema_version")
            != SYMBOL_RECOGNITION_SUMMARY_VERSION
            or not isinstance(summary.get("unresolved_roi_count"), int)
            or isinstance(summary.get("unresolved_roi_count"), bool)
            or summary["unresolved_roi_count"] < 0
        ):
            raise ValueError("recognition_summary is invalid")
        if (
            completeness == "partial_review_required"
        ) != (summary["unresolved_roi_count"] > 0):
            raise ValueError(
                "completeness must match unresolved_roi_count"
            )
    expected_evidence_ref = (
        f"symbol-routing-evidence://{project_id}"
        if recognition_mode == "production_uncertainty"
        else None
    )
    if recognition_evidence_ref != expected_evidence_ref:
        raise ValueError("recognition_evidence_ref is invalid")


def _selected_observations(pages: Sequence[Any]) -> list[TextObservation]:
    selected: list[TextObservation] = []
    for page in pages:
        observations = list(getattr(page, "observations", ()))
        native_lines = [
            observation
            for observation in observations
            if observation.source_type == "native"
            and observation.observation_level == "line"
        ]
        supplemental = [
            observation
            for observation in observations
            if observation.source_type != "native"
        ]
        selected.extend(
            [*native_lines, *supplemental]
            if native_lines or supplemental
            else observations
        )
    return sorted(
        selected,
        key=lambda observation: (
            observation.page_index,
            observation.direction,
            observation.bbox_pdf[1],
            observation.bbox_pdf[0],
            observation.observation_id,
        ),
    )


def selected_observations(
    pages: Sequence[Any],
) -> tuple[TextObservation, ...]:
    return tuple(_selected_observations(pages))


def selected_visual_observations(
    pages: Sequence[Any],
) -> tuple[VisualObservation, ...]:
    return tuple(
        sorted(
            (
                observation
                for page in pages
                for observation in getattr(page, "visual_observations", ())
            ),
            key=lambda observation: (
                observation.page_index,
                observation.bbox_pdf[1],
                observation.bbox_pdf[0],
                observation.proposal_kind,
                observation.observation_id,
            ),
        )
    )


def _coarse_type(raw_text: str) -> str | None:
    if ROUGHNESS_TOKEN.search(raw_text) or "粗糙" in raw_text:
        return "roughness"
    if "焊" in raw_text:
        return "weld"
    return None


def _composite_at(
    observations: Sequence[TextObservation],
    index: int,
) -> tuple[Candidate, tuple[TextObservation, ...]] | None:
    best: tuple[Candidate, tuple[TextObservation, ...]] | None = None
    for end in range(index + 2, len(observations) + 1):
        group = tuple(observations[index:end])
        if group[-1].page_index != group[0].page_index:
            break
        try:
            candidates = group_observations(group)
        except ValueError:
            break
        if len(candidates) != 1 or candidates[0].item_type != "composite":
            break
        best = candidates[0], group
    return best


def _candidate_payload(
    candidate: Candidate | CoarseCandidate | GeometricToleranceCandidate,
) -> dict[str, Any]:
    return candidate.model_dump(mode="json", exclude_none=True)


def _candidate_envelope(
    candidate: Candidate | CoarseCandidate | GeometricToleranceCandidate,
    observations: Sequence[TextObservation],
) -> dict[str, Any]:
    candidate_id = (
        candidate.candidate_id
        if isinstance(candidate, (Candidate, GeometricToleranceCandidate))
        else stable_candidate_id(
            "coarse-observation",
            *(observation.observation_id for observation in observations),
        )
    )
    return {
        "candidate_id": candidate_id,
        "payload": _candidate_payload(candidate),
        "source_location_ids": [
            observation.observation_id for observation in observations
        ],
    }


def _technical_requirement_coverage_entries(
    observations: Sequence[TextObservation],
    *,
    source_location_ids: frozenset[str],
    decisions: Sequence[TechnicalRequirementDecision],
) -> tuple[CoverageEntry, ...]:
    decisions_by_source: dict[str, list[TechnicalRequirementDecision]] = {}
    for decision in decisions:
        for source_location_id in decision.source_location_ids:
            decisions_by_source.setdefault(source_location_id, []).append(decision)

    entries: list[CoverageEntry] = []
    for observation in observations:
        if observation.observation_id not in source_location_ids:
            continue
        source_decisions = decisions_by_source.get(
            observation.observation_id,
            [],
        )
        if any(
            decision.match_outcome == "unresolved"
            for decision in source_decisions
        ):
            disposition = "ambiguous"
            candidate_id = None
            requires_confirmation = True
        else:
            generated_candidate_ids = [
                decision.generated_candidate_id
                for decision in source_decisions
                if decision.generated_candidate_id is not None
            ]
            if generated_candidate_ids:
                disposition = "candidate"
                candidate_id = generated_candidate_ids[0]
                requires_confirmation = True
            else:
                disposition = "reference_context"
                candidate_id = None
                requires_confirmation = False
        standalone = bool(source_decisions) and all(
            decision.ordinal is None for decision in source_decisions
        )
        entries.append(
            CoverageEntry(
                observation_id=observation.observation_id,
                disposition=disposition,
                source_location_id=observation.observation_id,
                coordinates=observation.bbox_pdf,
                candidate_id=candidate_id,
                requires_confirmation=requires_confirmation,
                disposition_reason=(
                    None if standalone else "technical_requirement"
                ),
                disposition_rule_version=(
                    None if standalone else "technical-requirement/1"
                ),
            )
        )
    return tuple(entries)


@dataclass(frozen=True)
class _LayoutSnapshotContext:
    matches_by_page: Mapping[int, LayoutProfileMatch]
    assignments_by_observation_id: Mapping[str, ObservationRegionAssignment]
    watermark_observation_ids: frozenset[str]
    engineering_preservation_observation_ids: frozenset[str]


def _revision_description_is_engineering(
    observation: TextObservation,
) -> bool:
    if is_standalone_executable_requirement(observation.raw_text):
        return True
    try:
        return bool(group_observations((observation,)))
    except ValueError:
        return False


def _layout_snapshot_context(
    pages: Sequence[Any],
    *,
    selected_text_observations: Sequence[TextObservation],
    visual_observations: Sequence[VisualObservation],
) -> _LayoutSnapshotContext:
    selected_by_id = {
        observation.observation_id: observation
        for observation in selected_text_observations
    }
    visual_text_ids = {
        observation_id
        for visual in visual_observations
        for observation_id in visual.associated_text_observation_ids
    }
    matches_by_page: dict[int, LayoutProfileMatch] = {}
    assignment_groups: dict[
        str,
        list[ObservationRegionAssignment],
    ] = defaultdict(list)
    watermark_ids: set[str] = set()
    for page in pages:
        match = getattr(page, "layout_profile_match", None)
        if (
            not isinstance(match, LayoutProfileMatch)
            or match.match_state != "high_confidence"
            or match.page_index != page.page_index
            or match.rule_version != WELLI_LAYOUT_RULE_VERSION
        ):
            continue
        matches_by_page[page.page_index] = match
        for assignment in match.assignments:
            assignment_groups[assignment.observation_id].append(assignment)
        watermark_ids.update(
            welli_same_page_watermark_observation_ids(
                profile_match=match,
                observations=getattr(page, "observations", ()),
            )
        )

    assignments_by_id: dict[str, ObservationRegionAssignment] = {}
    preservation_ids: set[str] = set()
    for observation_id, grouped_assignments in assignment_groups.items():
        observation = selected_by_id.get(observation_id)
        if len(grouped_assignments) != 1:
            preservation_ids.add(observation_id)
            continue
        assignment = grouped_assignments[0]
        match = matches_by_page.get(assignment.page_index)
        if (
            observation is None
            or observation.source_type != "native"
            or observation.observation_level != "line"
            or match is None
            or assignment.profile_id != match.profile_id
            or assignment.rule_version != match.rule_version
        ):
            preservation_ids.add(observation_id)
            continue
        assignments_by_id[observation_id] = assignment
        if (
            assignment.boundary_distance_mm < 1.0
            and not welli_page_frame_assignment_touches_outer_edge(assignment)
        ):
            preservation_ids.add(observation_id)
        elif (
            assignment.cell_role == "revision_description"
            and _revision_description_is_engineering(observation)
        ):
            preservation_ids.add(observation_id)
        elif (
            assignment.cell_role == "revision_description"
            and observation_id in visual_text_ids
        ):
            preservation_ids.add(observation_id)

    revision_rows: dict[str, set[str]] = defaultdict(set)
    for observation_id, assignment in assignments_by_id.items():
        if assignment.cell_role == "revision_description":
            revision_rows[assignment.cell_id].add(observation_id)
    for row_observation_ids in revision_rows.values():
        if row_observation_ids & preservation_ids:
            preservation_ids.update(row_observation_ids)

    return _LayoutSnapshotContext(
        matches_by_page=dict(sorted(matches_by_page.items())),
        assignments_by_observation_id=dict(
            sorted(assignments_by_id.items())
        ),
        watermark_observation_ids=frozenset(watermark_ids),
        engineering_preservation_observation_ids=frozenset(
            preservation_ids
        ),
    )


def _unique_text_observations_by_id(
    pages: Sequence[Any],
) -> Mapping[str, TextObservation]:
    grouped: dict[str, list[TextObservation]] = defaultdict(list)
    for page in pages:
        for observation in getattr(page, "observations", ()):
            grouped[observation.observation_id].append(observation)
    return {
        observation_id: observations[0]
        for observation_id, observations in grouped.items()
        if len(observations) == 1
    }


def _canonical_visual_line_ids(
    visual: VisualObservation,
    *,
    all_text_by_id: Mapping[str, TextObservation],
    selected_native_line_ids: frozenset[str],
) -> tuple[str, ...] | None:
    associated_ids = frozenset(visual.associated_text_observation_ids)
    if not associated_ids:
        return None
    canonical_line_ids: set[str] = set()
    for observation_id in associated_ids:
        observation = all_text_by_id.get(observation_id)
        if observation is None or observation.page_index != visual.page_index:
            return None
        if (
            observation.source_type == "native"
            and observation.observation_level == "line"
        ):
            if observation_id not in selected_native_line_ids:
                return None
            canonical_line_ids.add(observation_id)
            continue
        if (
            observation.source_type != "native"
            or observation.observation_level != "span"
            or not observation.parent_region_id
            or observation.parent_region_id not in associated_ids
        ):
            return None
        parent = all_text_by_id.get(observation.parent_region_id)
        if (
            parent is None
            or parent.page_index != visual.page_index
            or parent.source_type != "native"
            or parent.observation_level != "line"
            or parent.observation_id not in selected_native_line_ids
        ):
            return None
        canonical_line_ids.add(parent.observation_id)
    return tuple(sorted(canonical_line_ids)) or None


def _resolved_visual_coverage(
    visual: VisualObservation,
    *,
    canonical_line_ids: tuple[str, ...] | None,
    layout_context: _LayoutSnapshotContext,
    text_coverage_by_id: Mapping[str, CoverageEntry],
) -> CoverageEntry | None:
    if canonical_line_ids is None:
        return None
    match = layout_context.matches_by_page.get(visual.page_index)
    if match is None:
        return None
    dispositions: list[str] = []
    for line_id in canonical_line_ids:
        assignment = layout_context.assignments_by_observation_id.get(line_id)
        coverage = text_coverage_by_id.get(line_id)
        if (
            assignment is None
            or assignment.page_index != visual.page_index
            or assignment.profile_id != match.profile_id
            or line_id
            in layout_context.engineering_preservation_observation_ids
            or coverage is None
            or coverage.disposition
            not in {"reference_context", "non_inspection"}
            or coverage.disposition_rule_version
            != WELLI_LAYOUT_RULE_VERSION
            or not (coverage.disposition_reason or "").startswith("welli_")
        ):
            return None
        dispositions.append(str(coverage.disposition))
    disposition = (
        "non_inspection"
        if set(dispositions) == {"non_inspection"}
        else "reference_context"
    )
    return CoverageEntry(
        observation_id=visual.observation_id,
        disposition=disposition,
        source_location_id=visual.observation_id,
        coordinates=visual.bbox_pdf,
        requires_confirmation=False,
        disposition_reason="welli_layout_visual_context",
        disposition_rule_version=WELLI_LAYOUT_RULE_VERSION,
    )


def candidate_snapshot_from_inventory(
    pages: Sequence[Any],
) -> CandidateSnapshot:
    observations = _selected_observations(pages)
    requirement_entries = reconstruct_technical_requirement_entries(observations)
    technical_source_ids = technical_requirement_source_location_ids(
        observations,
        requirement_entries,
    )
    local_observations = [
        observation
        for observation in observations
        if observation.observation_id not in technical_source_ids
    ]
    repeated_overlay_ids = repeated_page_overlay_observation_ids(
        local_observations
    )
    visual_observations = selected_visual_observations(pages)
    visually_contextualized_text_ids = {
        observation_id
        for visual_observation in visual_observations
        for observation_id in visual_observation.associated_text_observation_ids
    }
    layout_context = _layout_snapshot_context(
        pages,
        selected_text_observations=observations,
        visual_observations=visual_observations,
    )
    candidates: list[dict[str, Any]] = []
    coverage_entries: list[CoverageEntry] = []
    duplicate_inputs: list[DuplicateCandidate] = []
    source_signals: list[CandidateSourceSignal] = []
    source_signal_indexes: dict[str, list[int]] = {}
    for observation in observations:
        if observation.source_type == "native":
            signal = CandidateSourceSignal(
                source_location_id=observation.observation_id,
                source_type="native",
                normalized_value=None,
            )
        elif observation.source_type == "ocr":
            try:
                normalized_signal = normalize_tencent_ocr_signal(
                    observation.confidence
                )
            except ValueError:
                normalized_signal = None
            signal = CandidateSourceSignal(
                source_location_id=observation.observation_id,
                source_type="ocr",
                normalized_value=normalized_signal,
            )
        else:
            continue
        source_signal_indexes.setdefault(
            observation.observation_id,
            [],
        ).append(len(source_signals))
        source_signals.append(signal)
    index = 0

    while index < len(local_observations):
        observation = local_observations[index]
        candidate: (
            Candidate | CoarseCandidate | GeometricToleranceCandidate | None
        ) = None
        members: tuple[TextObservation, ...] = (observation,)

        has_visual_context = (
            observation.observation_id
            in visually_contextualized_text_ids
        )
        decision = classify_primary_disposition(
            observation,
            has_visual_context=has_visual_context,
            layout_assignment=(
                layout_context.assignments_by_observation_id.get(
                    observation.observation_id
                )
            ),
            welli_watermark_observation_ids=(
                layout_context.watermark_observation_ids
            ),
            engineering_preservation_observation_ids=(
                layout_context.engineering_preservation_observation_ids
            ),
        )
        if decision is None:
            if composite := _composite_at(local_observations, index):
                candidate, members = composite
            else:
                try:
                    candidate = group_observations([observation])[0]
                except ValueError:
                    coarse_type = _coarse_type(observation.raw_text)
                    if coarse_type is not None:
                        candidate = coarse_candidate(
                            observation.raw_text,
                            coarse_type,
                            observation.bbox_pdf,
                        )
                    elif any(
                        symbol in observation.raw_text
                        for symbol in (
                            "⏤",
                            "▱",
                            "⏥",
                            "○",
                            "⌭",
                            "⌒",
                            "⌓",
                            "∠",
                            "⊥",
                            "∥",
                            "⌖",
                            "◎",
                            "⌯",
                            "↗",
                            "⌰",
                        )
                    ):
                        candidate = GeometricToleranceCandidate.from_legacy_unknown(
                            candidate_id=stable_candidate_id(
                                "geometric-tolerance-unknown",
                                observation.observation_id,
                            ),
                            raw_text=observation.raw_text,
                            coordinates=observation.bbox_pdf,
                            source_location_ids=(observation.observation_id,),
                        )

        if candidate is None:
            if decision is None:
                decision = classify_primary_disposition(
                    observation,
                    has_visual_context=has_visual_context,
                    repeated_overlay_observation_ids=repeated_overlay_ids,
                    layout_assignment=(
                        layout_context.assignments_by_observation_id.get(
                            observation.observation_id
                        )
                    ),
                    welli_watermark_observation_ids=(
                        layout_context.watermark_observation_ids
                    ),
                    engineering_preservation_observation_ids=(
                        layout_context.engineering_preservation_observation_ids
                    ),
                )
            coverage_entries.append(
                CoverageEntry(
                    observation_id=observation.observation_id,
                    disposition=(
                        decision.disposition if decision else "ambiguous"
                    ),
                    source_location_id=observation.observation_id,
                    coordinates=observation.bbox_pdf,
                    requires_confirmation=(
                        decision.requires_confirmation if decision else True
                    ),
                    disposition_reason=(
                        decision.reason if decision else None
                    ),
                    disposition_rule_version=(
                        decision.rule_version if decision else None
                    ),
                )
            )
            index += 1
            continue

        envelope = _candidate_envelope(candidate, members)
        source_truth_preserved = (
            isinstance(candidate, Candidate)
            and not bool(candidate.requires_confirmation)
        )
        envelope["source_truth_preserved"] = source_truth_preserved
        candidate_id = str(envelope["candidate_id"])
        candidates.append(envelope)
        requires_confirmation = bool(
            getattr(candidate, "requires_confirmation", False)
        )
        for member in members:
            if member.source_type == "native" and source_truth_preserved:
                for signal_index in source_signal_indexes.get(
                    member.observation_id,
                    (),
                ):
                    source_signals[signal_index] = CandidateSourceSignal(
                        source_location_id=member.observation_id,
                        source_type="native",
                        normalized_value=normalize_native_signal(True),
                    )
            coverage_entries.append(
                CoverageEntry(
                    observation_id=member.observation_id,
                    disposition="candidate",
                    source_location_id=member.observation_id,
                    coordinates=member.bbox_pdf,
                    candidate_id=candidate_id,
                    requires_confirmation=requires_confirmation,
                )
            )
        payload = envelope["payload"]
        duplicate_inputs.append(
            DuplicateCandidate(
                candidate_id=candidate_id,
                normalized_text=str(
                    payload.get("normalized_text", payload["raw_text"])
                ),
                view_id=f"page:{members[0].page_index}",
                disposition="candidate",
            )
        )
        index += len(members)

    requirement_evaluation = evaluate_technical_requirements(
        requirement_entries,
        candidates,
    )
    candidates = list(requirement_evaluation.candidates)
    coverage_entries.extend(
        _technical_requirement_coverage_entries(
            observations,
            source_location_ids=technical_source_ids,
            decisions=requirement_evaluation.decisions,
        )
    )

    text_coverage_by_id = {
        entry.observation_id: entry for entry in coverage_entries
    }
    all_text_by_id = _unique_text_observations_by_id(pages)
    selected_native_line_ids = frozenset(
        observation.observation_id
        for observation in observations
        if observation.source_type == "native"
        and observation.observation_level == "line"
    )
    required_visual_ids: list[str] = []
    for observation in visual_observations:
        resolved = _resolved_visual_coverage(
            observation,
            canonical_line_ids=_canonical_visual_line_ids(
                observation,
                all_text_by_id=all_text_by_id,
                selected_native_line_ids=selected_native_line_ids,
            ),
            layout_context=layout_context,
            text_coverage_by_id=text_coverage_by_id,
        )
        if resolved is not None:
            coverage_entries.append(resolved)
            continue
        coverage_entries.append(
            CoverageEntry(
                observation_id=observation.observation_id,
                disposition="ambiguous",
                source_location_id=observation.observation_id,
                coordinates=observation.bbox_pdf,
                requires_confirmation=True,
            )
        )
        required_visual_ids.append(observation.observation_id)

    return CandidateSnapshot(
        candidates=tuple(candidates),
        coverage_entries=tuple(coverage_entries),
        expected_observation_ids=tuple(
            observation.observation_id for observation in observations
        )
        + tuple(
            observation.observation_id
            for observation in visual_observations
        ),
        duplicate_relations=tuple(
            suggest_cross_view_duplicates(duplicate_inputs)
        ),
        source_signals=tuple(source_signals),
        required_visual_observation_ids=tuple(required_visual_ids),
        technical_requirements=tuple(
            decision.model_dump(mode="json")
            for decision in requirement_evaluation.decisions
        ),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"automatic result value is not JSON-safe: {type(value).__name__}")


def _uuid(value: uuid.UUID | str, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be one UUID") from exc


def automatic_result_ref(result: AutomaticResult | uuid.UUID) -> str:
    identity = result.id if isinstance(result, AutomaticResult) else result
    return f"automatic-result://{identity}"


def _validated_candidates_for_schema(
    candidates: Sequence[Mapping[str, Any]],
    schema_version: str,
) -> Sequence[Mapping[str, Any]]:
    if schema_version == LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION:
        return candidates
    if schema_version != AUTOMATIC_RESULT_SCHEMA_VERSION:
        raise ConfidenceDecisionContractError(
            f"automatic result schema_version is unknown: {schema_version}"
        )
    if (
        not isinstance(candidates, Sequence)
        or isinstance(candidates, (str, bytes, bytearray))
        or isinstance(candidates, Mapping)
    ):
        raise ConfidenceDecisionContractError(
            "automatic-result/2 candidates must be a non-string sequence"
        )
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ConfidenceDecisionContractError(
                f"candidate at index {index} must be one object"
            )
        if "confidence_decision" not in candidate:
            raise ConfidenceDecisionContractError(
                f"candidate at index {index} requires confidence_decision"
            )
        validate_confidence_decision(candidate["confidence_decision"])
    return candidates


def build_automatic_result(
    session: Session,
    *,
    project_id: uuid.UUID | str,
    source_file_id: uuid.UUID | str,
    logical_job_id: uuid.UUID | str,
    inventory_ref: str,
    candidates: Sequence[Mapping[str, Any]],
    coverage: CoverageReport,
    provider_call_ids: Sequence[str],
    duplicate_relations: Sequence[DuplicateRelation] = (),
    technical_requirements: Sequence[Mapping[str, Any]] = (),
    schema_version: str = AUTOMATIC_RESULT_SCHEMA_VERSION,
    completeness: str = "complete",
    recognition_mode: str = "legacy_high_recall",
    router_version: str = "legacy",
    recognition_summary: Mapping[str, Any] | None = None,
    recognition_evidence_ref: str | None = None,
    preview_superseder: object | None = None,
) -> AutomaticResult:
    if coverage.blocking_count > 0 or not coverage.coverage_checked:
        raise CoverageBlocking(coverage.blocking_count)
    if not isinstance(inventory_ref, str) or not inventory_ref.strip():
        raise ValueError("inventory_ref must be non-blank")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("schema_version must be non-blank")
    if completeness not in {"complete", "partial_review_required"}:
        raise ValueError("completeness is invalid")
    if not isinstance(recognition_mode, str) or not recognition_mode.strip():
        raise ValueError("recognition_mode must be non-blank")
    if not isinstance(router_version, str) or not router_version.strip():
        raise ValueError("router_version must be non-blank")
    if recognition_evidence_ref is not None and (
        not isinstance(recognition_evidence_ref, str)
        or not recognition_evidence_ref.strip()
    ):
        raise ValueError("recognition_evidence_ref must be non-blank when set")
    if any(
        not isinstance(call_id, str) or not call_id.strip()
        for call_id in provider_call_ids
    ):
        raise ValueError("provider_call_ids must contain non-blank strings")
    validated_candidates = _validated_candidates_for_schema(
        candidates,
        schema_version,
    )
    candidate_ids = {
        str(candidate["candidate_id"])
        for candidate in validated_candidates
        if isinstance(candidate.get("candidate_id"), str)
        and str(candidate["candidate_id"]).strip()
    }
    if len(candidate_ids) != len(validated_candidates):
        raise ConfidenceDecisionContractError(
            "automatic result candidates require unique non-blank candidate_id"
        )
    validated_requirements = validate_technical_requirements(
        technical_requirements,
        candidate_ids=candidate_ids,
    )

    project_identity = _uuid(project_id, "project_id")
    source_identity = _uuid(source_file_id, "source_file_id")
    job_identity = _uuid(logical_job_id, "logical_job_id")
    project = session.scalar(
        select(Project)
        .where(Project.id == project_identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if project is None:
        raise ValueError("project does not exist")
    _validate_terminal_recognition_provenance(
        project=project,
        project_id=project_identity,
        completeness=completeness,
        recognition_mode=recognition_mode,
        router_version=router_version,
        recognition_summary=recognition_summary,
        recognition_evidence_ref=recognition_evidence_ref,
    )
    job = session.scalar(
        select(LogicalJob)
        .where(LogicalJob.id == job_identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise ValueError("logical job does not exist")
    if job.project_id != str(project_identity):
        raise ValueError("logical job does not belong to project")
    if job.status == "succeeded":
        existing = session.scalar(
            select(AutomaticResult).where(
                AutomaticResult.logical_job_id == job.id
            )
        )
        if existing is None or job.result_ref != automatic_result_ref(existing):
            raise LogicalJobStateError(
                "successful process job is missing its automatic result"
            )
        session.commit()
        return existing
    if job.status not in {"pending", "processing"} or job.result_ref is not None:
        raise LogicalJobStateError(
            f"logical job cannot freeze result from status {job.status}"
        )
    if project.state != ProjectState.PROCESSING:
        raise InvalidTransition(
            f"{project.state} cannot freeze an automatic result"
        )

    coverage_payload = coverage.to_dict()
    coverage_payload["relations"] = [
        relation.to_dict() for relation in duplicate_relations
    ]
    result = AutomaticResult(
        id=uuid.uuid4(),
        project_id=project.id,
        source_file_id=source_identity,
        logical_job_id=job.id,
        inventory_ref=inventory_ref,
        candidates=_json_safe(list(validated_candidates)),
        coverage=_json_safe(coverage_payload),
        technical_requirements=_json_safe(validated_requirements),
        provider_call_ids=list(provider_call_ids),
        schema_version=schema_version,
        completeness=completeness,
        recognition_mode=recognition_mode,
        router_version=router_version,
        recognition_summary=_json_safe(
            dict(recognition_summary) if recognition_summary is not None else {}
        ),
        recognition_evidence_ref=recognition_evidence_ref,
    )
    session.add(result)
    session.flush()
    project.state = transition(
        ProjectState(project.state),
        ProjectState.READY_FOR_EDIT,
    )
    job.processing_stage = "preparing_review"
    job.status = "succeeded"
    job.result_ref = automatic_result_ref(result)
    session.flush()
    if preview_superseder is not None:
        preview_superseder.supersede_with_terminal(automatic_result_id=result.id)
    session.commit()
    return result
