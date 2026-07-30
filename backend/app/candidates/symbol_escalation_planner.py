from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.candidates.symbol_escalation_contracts import (
    MAX_VISUAL_IN_FLIGHT,
    MAX_VISUAL_PAGE_WALL_SECONDS,
    MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE,
    MAX_VISUAL_PRIMARY_GROUPS_PER_PROJECT,
    MAX_VISUAL_PROJECT_WALL_SECONDS,
    BudgetReservationOutcome,
    EscalationBatch,
    EscalationBudgetState,
    batch_budget_sha256,
    batch_lineage_sha256,
    semantic_content_sha256,
    valid_bbox,
    validate_actual_call_capacity,
    validate_budget_state,
    validate_escalation_batch,
)
from app.candidates.local_symbol_resolution import (
    LOCAL_SYMBOL_FAMILIES,
    LocalResolution,
)
from app.candidates.symbol_routing import (
    SYMBOL_ROUTER_VERSION,
    RoutingDecision,
    route_visual_observation,
    validate_routing_decision,
)
from app.pdf.coordinates import BBox
from app.pdf.schemas import VisualObservation


_ESCALATION_REASON_PRIORITY_BY_ROUTER_VERSION = {
    SYMBOL_ROUTER_VERSION: (
        "local_evidence_conflict",
        "local_parse_incomplete",
        "unknown_symbol_pattern",
        "ambiguous_component_grouping",
        "missing_local_discriminator",
        "local_validator_disagreement",
    )
}


@dataclass(frozen=True)
class EscalationRequest:
    decision: RoutingDecision
    observation: VisualObservation
    local_resolution: LocalResolution
    projected_wall_seconds: float

    @property
    def family_hypotheses(self) -> tuple[str, ...]:
        return self.local_resolution.family_hypotheses


@dataclass(frozen=True)
class EscalationBudgetDenial:
    content_sha256: str
    page_index: int
    observation_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EscalationPlan:
    batches: tuple[EscalationBatch, ...]
    denied: tuple[EscalationBudgetDenial, ...]
    budget_state: EscalationBudgetState
    max_in_flight: int = MAX_VISUAL_IN_FLIGHT

    @property
    def primary_group_count(self) -> int:
        return self.budget_state.project_primary_count


def _validate_escalation_request(request: EscalationRequest) -> None:
    decision = validate_routing_decision(request.decision)
    observation = request.observation
    if decision.disposition != "escalate":
        raise ValueError("escalation planner accepts only escalate decisions")
    if not isinstance(observation, VisualObservation):
        raise ValueError("escalation observation does not match decision")
    if (
        not isinstance(request.local_resolution, LocalResolution)
        or route_visual_observation(request.local_resolution) != decision
        or request.local_resolution.visual_observation_id
        != observation.observation_id
        or decision.visual_observation_id != observation.observation_id
    ):
        raise ValueError(
            "escalation request does not bind canonical local evidence"
        )
    if (
        not isinstance(request.family_hypotheses, tuple)
        or any(
            not isinstance(family, str)
            or family not in LOCAL_SYMBOL_FAMILIES
            for family in request.family_hypotheses
        )
    ):
        raise ValueError("escalation family set is not allowlisted")
    if (
        not isinstance(observation.page_index, int)
        or observation.page_index < 0
        or not valid_bbox(observation.bbox_pdf)
        or not isinstance(observation.geometry_sha256, str)
        or not observation.geometry_sha256
        or not isinstance(
            observation.associated_text_observation_ids,
            tuple,
        )
        or not observation.associated_text_observation_ids
        or any(
            not isinstance(source_id, str) or not source_id
            for source_id in observation.associated_text_observation_ids
        )
    ):
        raise ValueError("escalation observation evidence is invalid")
    if (
        not isinstance(request.projected_wall_seconds, (int, float))
        or isinstance(request.projected_wall_seconds, bool)
        or not math.isfinite(float(request.projected_wall_seconds))
        or request.projected_wall_seconds < 0
    ):
        raise ValueError("projected wall duration is invalid")


def _request_content_sha256(request: EscalationRequest) -> str:
    observation = request.observation
    return semantic_content_sha256(
        page_index=observation.page_index,
        bbox_pdf=observation.bbox_pdf,
        geometry_sha256s=(observation.geometry_sha256,),
        associated_text_observation_ids=(
            observation.associated_text_observation_ids
        ),
        escalation_reason_codes=request.decision.escalation_reason_codes,
        family_hypotheses=request.family_hypotheses,
    )


def _batch_from_request(
    request: EscalationRequest,
    *,
    content_sha256: str,
    observation_ids: tuple[str, ...],
    projected_wall_seconds: float,
) -> EscalationBatch:
    observation = request.observation
    bindings = tuple(
        (observation_id, content_sha256)
        for observation_id in observation_ids
    )
    return EscalationBatch(
        content_sha256=content_sha256,
        lineage_sha256=batch_lineage_sha256(
            content_sha256,
            observation.page_index,
            bindings,
        ),
        budget_sha256=batch_budget_sha256(
            content_sha256,
            observation.page_index,
            projected_wall_seconds,
        ),
        member_content_sha256s=(content_sha256,),
        page_index=observation.page_index,
        observation_ids=observation_ids,
        observation_member_bindings=bindings,
        geometry_sha256s=(observation.geometry_sha256,),
        associated_text_observation_ids=tuple(
            sorted(set(observation.associated_text_observation_ids))
        ),
        escalation_reason_codes=tuple(
            sorted(set(request.decision.escalation_reason_codes))
        ),
        family_hypotheses=tuple(sorted(set(request.family_hypotheses))),
        bbox_pdf=tuple(  # type: ignore[arg-type]
            float(value) for value in observation.bbox_pdf
        ),
        projected_wall_seconds=projected_wall_seconds,
    )


def _bboxes_overlap(left: BBox, right: BBox) -> bool:
    return (
        min(left[2], right[2]) > max(left[0], right[0])
        and min(left[3], right[3]) > max(left[1], right[1])
    )


def _merge_compatible(
    left: EscalationBatch,
    right: EscalationBatch,
) -> bool:
    return (
        left.page_index == right.page_index
        and left.associated_text_observation_ids
        == right.associated_text_observation_ids
        and left.escalation_reason_codes == right.escalation_reason_codes
        and left.family_hypotheses == right.family_hypotheses
        and _bboxes_overlap(left.bbox_pdf, right.bbox_pdf)
    )


def _merge_batches(
    left: EscalationBatch,
    right: EscalationBatch,
) -> EscalationBatch:
    member_hashes = tuple(
        sorted(
            set(
                left.member_content_sha256s
                + right.member_content_sha256s
            )
        )
    )
    bbox = (
        min(left.bbox_pdf[0], right.bbox_pdf[0]),
        min(left.bbox_pdf[1], right.bbox_pdf[1]),
        max(left.bbox_pdf[2], right.bbox_pdf[2]),
        max(left.bbox_pdf[3], right.bbox_pdf[3]),
    )
    geometry_sha256s = tuple(
        sorted(set(left.geometry_sha256s + right.geometry_sha256s))
    )
    observation_member_bindings = tuple(
        sorted(
            left.observation_member_bindings
            + right.observation_member_bindings
        )
    )
    content_sha256 = semantic_content_sha256(
        member_content_sha256s=member_hashes,
        page_index=left.page_index,
        bbox_pdf=bbox,
        geometry_sha256s=geometry_sha256s,
        associated_text_observation_ids=(
            left.associated_text_observation_ids
        ),
        escalation_reason_codes=left.escalation_reason_codes,
        family_hypotheses=left.family_hypotheses,
    )
    projected_wall_seconds = max(
        left.projected_wall_seconds,
        right.projected_wall_seconds,
    )
    return EscalationBatch(
        content_sha256=content_sha256,
        lineage_sha256=batch_lineage_sha256(
            content_sha256,
            left.page_index,
            observation_member_bindings,
        ),
        budget_sha256=batch_budget_sha256(
            content_sha256,
            left.page_index,
            projected_wall_seconds,
        ),
        member_content_sha256s=member_hashes,
        page_index=left.page_index,
        observation_ids=tuple(
            sorted(set(left.observation_ids + right.observation_ids))
        ),
        observation_member_bindings=observation_member_bindings,
        geometry_sha256s=geometry_sha256s,
        associated_text_observation_ids=(
            left.associated_text_observation_ids
        ),
        escalation_reason_codes=left.escalation_reason_codes,
        family_hypotheses=left.family_hypotheses,
        bbox_pdf=bbox,
        projected_wall_seconds=projected_wall_seconds,
    )


def _batch_order(batch: EscalationBatch) -> tuple[object, ...]:
    priority = _ESCALATION_REASON_PRIORITY_BY_ROUTER_VERSION[
        SYMBOL_ROUTER_VERSION
    ]
    reason_priority = min(
        priority.index(reason)
        for reason in batch.escalation_reason_codes
    )
    return (
        batch.page_index,
        reason_priority,
        batch.bbox_pdf[1],
        batch.bbox_pdf[0],
        batch.content_sha256,
        batch.bbox_pdf[3],
        batch.bbox_pdf[2],
    )


def _escalation_batches(
    requests: Sequence[EscalationRequest],
) -> tuple[EscalationBatch, ...]:
    content_requests: dict[str, EscalationRequest] = {}
    content_observation_ids: dict[str, set[str]] = {}
    content_wall_seconds: dict[str, float] = {}
    observation_content: dict[str, str] = {}
    for request in requests:
        _validate_escalation_request(request)
        content_sha256 = _request_content_sha256(request)
        observation_id = request.observation.observation_id
        existing_content = observation_content.get(observation_id)
        if (
            existing_content is not None
            and existing_content != content_sha256
        ):
            raise ValueError(
                "observation id maps to conflicting escalation content"
            )
        observation_content[observation_id] = content_sha256
        content_requests.setdefault(content_sha256, request)
        content_observation_ids.setdefault(content_sha256, set()).add(
            observation_id
        )
        content_wall_seconds[content_sha256] = max(
            content_wall_seconds.get(content_sha256, 0.0),
            float(request.projected_wall_seconds),
        )

    exact_batches = sorted(
        (
            _batch_from_request(
                content_requests[content_sha256],
                content_sha256=content_sha256,
                observation_ids=tuple(
                    sorted(content_observation_ids[content_sha256])
                ),
                projected_wall_seconds=content_wall_seconds[
                    content_sha256
                ],
            )
            for content_sha256 in content_requests
        ),
        key=_batch_order,
    )
    merged: list[EscalationBatch] = []
    unvisited = set(range(len(exact_batches)))
    while unvisited:
        seed = min(unvisited, key=lambda index: _batch_order(exact_batches[index]))
        component = {seed}
        frontier = [seed]
        unvisited.remove(seed)
        while frontier:
            current = frontier.pop()
            connected = sorted(
                (
                    candidate
                    for candidate in unvisited
                    if _merge_compatible(
                        exact_batches[current],
                        exact_batches[candidate],
                    )
                ),
                key=lambda index: _batch_order(exact_batches[index]),
            )
            for candidate in connected:
                unvisited.remove(candidate)
                component.add(candidate)
                frontier.append(candidate)
        ordered_component = sorted(
            component,
            key=lambda index: _batch_order(exact_batches[index]),
        )
        combined = exact_batches[ordered_component[0]]
        for index in ordered_component[1:]:
            combined = _merge_batches(combined, exact_batches[index])
        merged.append(combined)
    return tuple(sorted(merged, key=_batch_order))


_BUDGET_REASON_ORDER = (
    "primary_page_budget_exceeded",
    "primary_project_budget_exceeded",
    "unified_page_actual_call_budget_exceeded",
    "page_wall_budget_exceeded",
    "project_wall_budget_exceeded",
    "project_retry_budget_exceeded",
)


def reserve_escalation_budget_window(
    state: EscalationBudgetState,
    batches: Sequence[EscalationBatch],
    *,
    actual_call_capacity_by_page: Mapping[int, int],
    retry: bool = False,
) -> BudgetReservationOutcome:
    """Reserve a whole projected window or leave every counter unchanged."""
    state = validate_budget_state(state)
    capacities = validate_actual_call_capacity(
        actual_call_capacity_by_page
    )
    if any(
        page not in capacities or count > capacities[page]
        for page, count in state.page_actual_call_counts
    ):
        raise ValueError("escalation budget state invalid")
    window = tuple(
        validate_escalation_batch(batch) for batch in batches
    )
    if not window:
        return BudgetReservationOutcome(True, (), state, ())
    if len(window) > MAX_VISUAL_IN_FLIGHT:
        raise ValueError("escalation window exceeds max_in_flight")
    page_primary = dict(state.page_primary_counts)
    page_actual = dict(state.page_actual_call_counts)
    page_wall = dict(state.page_wall_seconds)
    project_primary = state.project_primary_count
    project_wall = state.project_wall_seconds
    primary_identities = set(state.primary_group_identities)
    retried_identities = set(state.retried_group_identities)
    window_identities = {
        (batch.page_index, batch.content_sha256) for batch in window
    }
    if retry and not window_identities.issubset(primary_identities):
        raise ValueError("retry identity has no matching primary group")
    if not retry and (
        len(window_identities) != len(window)
        or primary_identities.intersection(window_identities)
    ):
        raise ValueError("duplicate primary group identity")
    exceeded: set[str] = set()

    if retry:
        if (
            len(window_identities) != len(window)
            or retried_identities.intersection(window_identities)
            or len(retried_identities.union(window_identities)) > 1
        ):
            exceeded.add("project_retry_budget_exceeded")
        else:
            retried_identities.update(window_identities)
    else:
        primary_identities.update(window_identities)

    for batch in window:
        page = batch.page_index
        capacity = capacities.get(page)
        if capacity is None:
            raise ValueError(
                "caller must supply non-negative actual call capacity per page"
            )
        if not retry:
            page_primary[page] = page_primary.get(page, 0) + 1
            project_primary += 1
        page_actual[page] = page_actual.get(page, 0) + 1
        page_wall[page] = (
            page_wall.get(page, 0.0) + batch.projected_wall_seconds
        )
        project_wall += batch.projected_wall_seconds
        if page_primary.get(page, 0) > MAX_VISUAL_PRIMARY_GROUPS_PER_PAGE:
            exceeded.add("primary_page_budget_exceeded")
        if project_primary > MAX_VISUAL_PRIMARY_GROUPS_PER_PROJECT:
            exceeded.add("primary_project_budget_exceeded")
        if page_actual[page] > capacity:
            exceeded.add("unified_page_actual_call_budget_exceeded")
        if page_wall[page] > MAX_VISUAL_PAGE_WALL_SECONDS:
            exceeded.add("page_wall_budget_exceeded")
        if project_wall > MAX_VISUAL_PROJECT_WALL_SECONDS:
            exceeded.add("project_wall_budget_exceeded")

    if exceeded:
        return BudgetReservationOutcome(
            allowed=False,
            reserved_batches=(),
            state=state,
            reason_codes=tuple(
                reason
                for reason in _BUDGET_REASON_ORDER
                if reason in exceeded
            ),
        )
    next_state = EscalationBudgetState(
        page_primary_counts=tuple(sorted(page_primary.items())),
        project_primary_count=project_primary,
        page_actual_call_counts=tuple(sorted(page_actual.items())),
        page_wall_seconds=tuple(sorted(page_wall.items())),
        project_wall_seconds=project_wall,
        primary_group_identities=tuple(sorted(primary_identities)),
        retried_group_identities=tuple(sorted(retried_identities)),
    )
    return BudgetReservationOutcome(
        allowed=True,
        reserved_batches=window,
        state=next_state,
        reason_codes=(),
    )


def plan_symbol_escalation_batches(
    requests: Sequence[EscalationRequest],
    *,
    actual_call_capacity_by_page: Mapping[int, int],
    window_size: int = MAX_VISUAL_IN_FLIGHT,
) -> EscalationPlan:
    """Plan stable ROIs; window_size probes equivalence, not PRT-3 execution."""
    if window_size not in {1, MAX_VISUAL_IN_FLIGHT}:
        raise ValueError("window_size must be 1 or max_in_flight")
    state = EscalationBudgetState((), 0, (), (), 0.0, (), ())
    admitted: list[EscalationBatch] = []
    denied: list[EscalationBudgetDenial] = []
    for batch in _escalation_batches(requests):
        outcome = reserve_escalation_budget_window(
            state,
            (batch,),
            actual_call_capacity_by_page=actual_call_capacity_by_page,
        )
        if outcome.allowed:
            admitted.extend(outcome.reserved_batches)
            state = outcome.state
        else:
            denied.append(
                EscalationBudgetDenial(
                    content_sha256=batch.content_sha256,
                    page_index=batch.page_index,
                    observation_ids=batch.observation_ids,
                    reason_codes=outcome.reason_codes,
                )
            )
    return EscalationPlan(
        batches=tuple(admitted),
        denied=tuple(denied),
        budget_state=state,
    )
