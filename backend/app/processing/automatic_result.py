from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.complex_fallback import CoarseCandidate, coarse_candidate
from app.candidates.coverage import CoverageEntry, CoverageReport
from app.candidates.disposition import classify_technical_requirement
from app.candidates.duplicates import (
    DuplicateCandidate,
    DuplicateRelation,
    suggest_cross_view_duplicates,
)
from app.candidates.grouping import group_observations
from app.candidates.models import AutomaticResult
from app.candidates.schemas import Candidate, stable_candidate_id
from app.jobs.idempotency import LogicalJob, LogicalJobStateError
from app.pdf.schemas import TextObservation
from app.projects.models import Project
from app.projects.state import InvalidTransition, ProjectState, transition


AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/1"
ROUGHNESS_TOKEN = re.compile(r"(?<![A-Za-z])Ra(?=\s*[0-9])", re.IGNORECASE)


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
    provider_call_ids: tuple[str, ...] = ()


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


def _coarse_type(raw_text: str) -> str | None:
    if ROUGHNESS_TOKEN.search(raw_text) or "粗糙" in raw_text:
        return "roughness"
    if "焊" in raw_text:
        return "weld"
    if any(symbol in raw_text for symbol in ("⌖", "⌒", "⏥", "∥", "⊥")):
        return "geometric_tolerance"
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


def _candidate_payload(candidate: Candidate | CoarseCandidate) -> dict[str, Any]:
    return candidate.model_dump(mode="json", exclude_none=True)


def _candidate_envelope(
    candidate: Candidate | CoarseCandidate,
    observations: Sequence[TextObservation],
) -> dict[str, Any]:
    candidate_id = (
        candidate.candidate_id
        if isinstance(candidate, Candidate)
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


def candidate_snapshot_from_inventory(
    pages: Sequence[Any],
) -> CandidateSnapshot:
    observations = _selected_observations(pages)
    candidates: list[dict[str, Any]] = []
    coverage_entries: list[CoverageEntry] = []
    duplicate_inputs: list[DuplicateCandidate] = []
    index = 0

    while index < len(observations):
        observation = observations[index]
        candidate: Candidate | CoarseCandidate | None = None
        members: tuple[TextObservation, ...] = (observation,)

        requirement = classify_technical_requirement(
            observation.raw_text,
            observation.bbox_pdf,
            source_id=observation.observation_id,
        )
        if requirement is not None:
            candidate = requirement
        elif composite := _composite_at(observations, index):
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

        if candidate is None:
            coverage_entries.append(
                CoverageEntry(
                    observation_id=observation.observation_id,
                    disposition="ambiguous",
                    source_location_id=observation.observation_id,
                    coordinates=observation.bbox_pdf,
                    requires_confirmation=True,
                )
            )
            index += 1
            continue

        envelope = _candidate_envelope(candidate, members)
        candidate_id = str(envelope["candidate_id"])
        candidates.append(envelope)
        requires_confirmation = bool(
            getattr(candidate, "requires_confirmation", False)
        )
        for member in members:
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

    return CandidateSnapshot(
        candidates=tuple(candidates),
        coverage_entries=tuple(coverage_entries),
        expected_observation_ids=tuple(
            observation.observation_id for observation in observations
        ),
        duplicate_relations=tuple(
            suggest_cross_view_duplicates(duplicate_inputs)
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
    schema_version: str = AUTOMATIC_RESULT_SCHEMA_VERSION,
) -> AutomaticResult:
    if coverage.blocking_count > 0 or not coverage.coverage_checked:
        raise CoverageBlocking(coverage.blocking_count)
    if not isinstance(inventory_ref, str) or not inventory_ref.strip():
        raise ValueError("inventory_ref must be non-blank")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("schema_version must be non-blank")
    if any(
        not isinstance(call_id, str) or not call_id.strip()
        for call_id in provider_call_ids
    ):
        raise ValueError("provider_call_ids must contain non-blank strings")

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
        candidates=_json_safe(list(candidates)),
        coverage=_json_safe(coverage_payload),
        provider_call_ids=list(provider_call_ids),
        schema_version=schema_version,
    )
    session.add(result)
    session.flush()
    project.state = transition(
        ProjectState(project.state),
        ProjectState.READY_FOR_EDIT,
    )
    job.status = "succeeded"
    job.result_ref = automatic_result_ref(result)
    session.commit()
    return result
