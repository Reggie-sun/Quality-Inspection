from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import replace

import pytest

from app.candidates.local_symbol_resolution import LocalResolution
from app.candidates.symbol_review import VisualReviewDecision
from app.candidates.symbol_escalation_contracts import (
    batch_budget_sha256,
    batch_lineage_sha256,
    semantic_content_sha256,
)
from app.candidates.symbol_escalation_planner import (
    EscalationBudgetState,
    EscalationRequest,
    plan_symbol_escalation_batches,
    reserve_escalation_budget_window,
)
from app.candidates.symbol_routing import (
    route_visual_observation,
    symbol_routing_identity,
    validate_frozen_symbol_routing_identity,
    validate_routing_decision,
)
from app.pdf.schemas import VisualObservation


class _RaisingMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("mapping access failed")

    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("mapping iteration failed")

    def __len__(self) -> int:
        raise RuntimeError("mapping length failed")

    def items(self):
        raise RuntimeError("mapping items failed")


class _SnapshotThenRaisingMapping(Mapping[int, int]):
    def __getitem__(self, key: int) -> int:
        raise RuntimeError("mapping accessed after snapshot")

    def __iter__(self) -> Iterator[int]:
        raise RuntimeError("mapping iterated after snapshot")

    def __len__(self) -> int:
        raise RuntimeError("mapping sized after snapshot")

    def items(self):
        return ((0, 16),)


class _RaisingTuple(tuple):
    def __iter__(self):
        raise RuntimeError("tuple iteration failed")


class _HostileStr(str):
    def __hash__(self) -> int:
        raise RuntimeError("hostile str hash")

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("hostile str equality")

    def __ne__(self, other: object) -> bool:
        raise RuntimeError("hostile str inequality")


def _resolution(
    *reason_codes: str,
    resolved_family: str | None = None,
) -> LocalResolution:
    projection = (
        VisualReviewDecision(
            "visual-1",
            "candidate",
            ("visual-1", "text-1"),
            (0, 0, 1, 1),
            "candidate-1",
            None,
            {"candidate_id": "candidate-1"},
            True,
            ("diameter",),
            None,
        )
        if resolved_family is not None
        else None
    )
    return LocalResolution(
        visual_observation_id="visual-1",
        family_hypotheses=("diameter",),
        resolved_family=resolved_family,
        reason_codes=tuple(reason_codes),
        projection=projection,
        confidence=None,
    )


def test_unknown_reason_fails_closed() -> None:
    decision = route_visual_observation(
        _resolution("future_unregistered_reason"),
    )

    assert decision.disposition == "block"
    assert decision.local_resolution_reason_codes == ()
    assert decision.escalation_reason_codes == ()
    assert decision.block_reason_codes == ("routing_contract_invalid",)


@pytest.mark.parametrize(
    ("resolution", "expected"),
    (
        (
            _resolution(
                "native_symbol_explicit",
                "local_projection_complete",
                resolved_family="diameter",
            ),
            "locally_resolved",
        ),
        (_resolution("local_parse_incomplete"), "escalate"),
        (_resolution("coverage_lineage_incomplete"), "block"),
    ),
)
def test_every_admitted_observation_has_exactly_one_disposition(
    resolution: LocalResolution,
    expected: str,
) -> None:
    decision = route_visual_observation(resolution)
    reason_arrays = (
        decision.local_resolution_reason_codes,
        decision.escalation_reason_codes,
        decision.block_reason_codes,
    )

    assert decision.disposition == expected
    assert sum(bool(reasons) for reasons in reason_arrays) == 1


def test_reason_codes_are_sorted_unique_and_replay_stable() -> None:
    resolution = _resolution(
        "local_parse_incomplete",
        "ambiguous_component_grouping",
        "local_parse_incomplete",
    )

    first = route_visual_observation(resolution)
    replay = route_visual_observation(
        replace(
            resolution,
            reason_codes=tuple(reversed(resolution.reason_codes)),
        )
    )

    assert first == replay
    assert first.escalation_reason_codes == (
        "ambiguous_component_grouping",
        "local_parse_incomplete",
    )


def test_projection_evidence_changes_input_hash() -> None:
    resolution = _resolution(
        "native_symbol_explicit",
        "local_projection_complete",
        resolved_family="diameter",
    )
    assert resolution.projection is not None
    projection = resolution.projection
    variants = (
        replace(
            resolution,
            projection=replace(
                projection,
                requires_confirmation=not projection.requires_confirmation,
            ),
        ),
        replace(
            resolution,
            projection=replace(projection, coordinates=(0, 0, 2, 2)),
        ),
        replace(
            resolution,
            projection=replace(
                projection,
                source_location_ids=("visual-1", "text-2"),
            ),
        ),
        replace(
            resolution,
            projection=replace(projection, symbol_kinds=("depth", "diameter")),
        ),
        replace(
            resolution,
            projection=replace(
                projection,
                candidate_envelope={
                    "candidate_id": "candidate-1",
                    "payload": {"nominal": "10"},
                },
            ),
        ),
    )
    original = route_visual_observation(resolution)

    assert original.disposition == "locally_resolved"
    for variant in variants:
        decision = route_visual_observation(variant)
        assert decision.disposition == "locally_resolved"
        assert decision.input_sha256 != original.input_sha256


def test_confidence_is_excluded_from_decision_and_hash() -> None:
    resolution = _resolution("local_parse_incomplete")

    first = route_visual_observation(resolution)
    changed = route_visual_observation(replace(resolution, confidence=0.99))

    assert first == changed


def _invalid_local_resolution_shapes() -> tuple[LocalResolution, ...]:
    valid = _resolution(
        "native_symbol_explicit",
        "local_projection_complete",
        resolved_family="diameter",
    )
    assert valid.projection is not None
    projection = valid.projection
    return (
        replace(valid, visual_observation_id=""),
        replace(
            valid,
            reason_codes=("local_projection_complete", 1),  # type: ignore[arg-type]
        ),
        replace(
            valid,
            family_hypotheses=("diameter", 1),  # type: ignore[arg-type]
        ),
        replace(valid, family_hypotheses=("diameter", "")),
        replace(valid, resolved_family="future_family"),
        replace(valid, family_hypotheses=("depth",)),
        replace(
            valid,
            projection=replace(projection, observation_id="visual-2"),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                disposition="ambiguous",
                rejection_code="visual_projection_conflict",
            ),
        ),
        replace(
            valid,
            projection=replace(projection, symbol_kinds=("depth",)),
        ),
        replace(
            valid,
            projection=replace(projection, disposition="reference_context"),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                symbol_kinds=("diameter", "future_family"),  # type: ignore[arg-type]
            ),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                symbol_kinds=None,  # type: ignore[arg-type]
            ),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                symbol_kinds=("diameter", 1),  # type: ignore[arg-type]
            ),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                source_location_ids=None,  # type: ignore[arg-type]
            ),
        ),
        replace(
            valid,
            projection=replace(
                projection,
                source_location_ids=("visual-1", 1),  # type: ignore[arg-type]
            ),
        ),
        replace(
            valid,
            family_hypotheses=("depth",),
            resolved_family="depth",
            projection=replace(
                projection,
                symbol_kinds=("depth", "diameter"),
            ),
        ),
        replace(
            valid,
            family_hypotheses=("surface_roughness",),
            resolved_family="surface_roughness",
            projection=replace(
                projection,
                disposition="non_inspection",
                symbol_kinds=("surface_roughness",),
            ),
        ),
        replace(
            valid,
            family_hypotheses=("datum_reference",),
            resolved_family="datum_reference",
            reason_codes=(
                "deterministic_geometry_complete",
                "local_projection_complete",
            ),
            projection=replace(
                projection,
                disposition="candidate",
                symbol_kinds=("datum_reference",),
            ),
        ),
        replace(
            valid,
            family_hypotheses=("revision_marker",),
            resolved_family="revision_marker",
            reason_codes=(
                "deterministic_geometry_complete",
                "local_projection_complete",
            ),
            projection=replace(
                projection,
                disposition="reference_context",
                symbol_kinds=("revision_marker",),
            ),
        ),
    )


@pytest.mark.parametrize("resolution", _invalid_local_resolution_shapes())
def test_invalid_local_resolution_shape_blocks_without_raising(
    resolution: LocalResolution,
) -> None:
    decision = route_visual_observation(resolution)

    assert decision.disposition == "block"
    assert decision.local_resolution_reason_codes == ()
    assert decision.escalation_reason_codes == ()
    assert decision.block_reason_codes == ("routing_contract_invalid",)


def test_empty_hypotheses_are_only_valid_for_unknown_pattern() -> None:
    unknown = LocalResolution(
        visual_observation_id="visual-1",
        family_hypotheses=(),
        resolved_family=None,
        reason_codes=("unknown_symbol_pattern",),
        projection=None,
        confidence=None,
    )
    incompatible = (
        replace(unknown, reason_codes=("local_parse_incomplete",)),
        replace(
            _resolution(
                "native_symbol_explicit",
                "local_projection_complete",
                resolved_family="diameter",
            ),
            family_hypotheses=(),
        ),
    )

    assert route_visual_observation(unknown).disposition == "escalate"
    for resolution in incompatible:
        decision = route_visual_observation(resolution)
        assert decision.disposition == "block"
        assert decision.block_reason_codes == ("routing_contract_invalid",)


def test_non_local_resolution_input_blocks_without_raising() -> None:
    decision = route_visual_observation(object())  # type: ignore[arg-type]

    assert decision.disposition == "block"
    assert decision.visual_observation_id == ""
    assert decision.block_reason_codes == ("routing_contract_invalid",)
    assert validate_routing_decision(decision) == decision


def test_whitespace_observation_id_returns_consumable_block_sentinel() -> None:
    decision = route_visual_observation(
        replace(
            _resolution("local_parse_incomplete"),
            visual_observation_id="   ",
        )
    )

    assert decision.disposition == "block"
    assert decision.visual_observation_id == ""
    assert decision.block_reason_codes == ("routing_contract_invalid",)
    assert validate_routing_decision(decision) == decision


def test_invalid_input_hash_is_distinct_and_replay_stable() -> None:
    first = replace(
        _resolution("local_parse_incomplete"),
        reason_codes=("local_parse_incomplete", 1),  # type: ignore[arg-type]
    )
    second = replace(
        _resolution("local_parse_incomplete"),
        family_hypotheses=("diameter", 1),  # type: ignore[arg-type]
    )

    first_decision = route_visual_observation(first)
    replay = route_visual_observation(first)
    second_decision = route_visual_observation(second)

    assert first_decision == replay
    assert first_decision.input_sha256 != second_decision.input_sha256


def test_cyclic_candidate_envelope_blocks_without_recursion_error() -> None:
    resolution = _resolution(
        "native_symbol_explicit",
        "local_projection_complete",
        resolved_family="diameter",
    )
    assert resolution.projection is not None
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    malformed = replace(
        resolution,
        projection=replace(
            resolution.projection,
            candidate_envelope=cyclic,
        ),
    )

    decision = route_visual_observation(malformed)

    assert decision.disposition == "block"
    assert decision.block_reason_codes == ("routing_contract_invalid",)


def test_raising_mapping_blocks_without_escaping_exception() -> None:
    resolution = _resolution(
        "native_symbol_explicit",
        "local_projection_complete",
        resolved_family="diameter",
    )
    assert resolution.projection is not None
    malformed = replace(
        resolution,
        projection=replace(
            resolution.projection,
            candidate_envelope=_RaisingMapping(),
        ),
    )

    first = route_visual_observation(malformed)
    replay = route_visual_observation(malformed)

    assert first == replay
    assert first.disposition == "block"
    assert first.block_reason_codes == ("routing_contract_invalid",)


def test_malformed_bytes_hash_is_distinct_and_replay_stable() -> None:
    resolution = _resolution(
        "native_symbol_explicit",
        "local_projection_complete",
        resolved_family="diameter",
    )
    assert resolution.projection is not None

    def malformed(content: bytes) -> LocalResolution:
        return replace(
            resolution,
            projection=replace(
                resolution.projection,
                candidate_envelope={"payload": content},
            ),
        )

    first = route_visual_observation(malformed(b"first-private-content"))
    replay = route_visual_observation(malformed(b"first-private-content"))
    second = route_visual_observation(malformed(b"second-private-content"))

    assert first == replay
    assert first.disposition == "block"
    assert first.input_sha256 != second.input_sha256


@pytest.mark.parametrize(
    "resolution",
    (
        _resolution(),
        _resolution(
            "local_projection_complete",
            "local_parse_incomplete",
            resolved_family="diameter",
        ),
        _resolution(
            "local_projection_complete",
            resolved_family=None,
        ),
        _resolution(
            "local_parse_incomplete",
            resolved_family="diameter",
        ),
    ),
)
def test_invalid_reason_or_resolution_shape_fails_closed(
    resolution: LocalResolution,
) -> None:
    decision = route_visual_observation(resolution)

    assert decision.disposition == "block"
    assert decision.block_reason_codes == ("routing_contract_invalid",)


def _escalation_request(
    observation_id: str,
    *,
    page_index: int = 0,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 10.0),
    geometry_sha256: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    family_hypotheses: tuple[str, ...] = ("diameter",),
    reasons: tuple[str, ...] = ("local_parse_incomplete",),
    projected_wall_seconds: float = 1.0,
) -> EscalationRequest:
    resolution = LocalResolution(
        visual_observation_id=observation_id,
        family_hypotheses=family_hypotheses,
        resolved_family=None,
        reason_codes=reasons,
        projection=None,
        confidence=None,
    )
    decision = route_visual_observation(resolution)
    observation = VisualObservation(
        observation_id=observation_id,
        source_type="visual",
        observation_level="annotation_context",
        page_index=page_index,
        bbox_pdf=bbox,
        bbox_normalized=bbox,
        proposal_kind="text_adjacent_vector_context",
        geometry_sha256=geometry_sha256
        or hashlib.sha256(observation_id.encode("utf-8")).hexdigest(),
        associated_text_observation_ids=source_ids or (f"text-{observation_id}",),
    )
    return EscalationRequest(
        decision=decision,
        observation=observation,
        local_resolution=resolution,
        projected_wall_seconds=projected_wall_seconds,
    )


def _budget_state() -> EscalationBudgetState:
    return EscalationBudgetState(
        page_primary_counts=(),
        project_primary_count=0,
        page_actual_call_counts=(),
        page_wall_seconds=(),
        project_wall_seconds=0.0,
        primary_group_identities=(),
        retried_group_identities=(),
    )


def test_planner_enforces_page_project_and_unified_call_budgets() -> None:
    requests = tuple(
        _escalation_request(
            f"visual-{page}-{index}",
            page_index=page,
            bbox=(index * 20.0, 0.0, index * 20.0 + 10.0, 10.0),
        )
        for page in range(3)
        for index in range(5)
    )

    plan = plan_symbol_escalation_batches(
        tuple(reversed(requests)),
        actual_call_capacity_by_page={0: 16, 1: 2, 2: 16},
    )

    assert len(plan.batches) == 8
    assert len([batch for batch in plan.batches if batch.page_index == 0]) == 4
    assert len([batch for batch in plan.batches if batch.page_index == 1]) == 2
    assert len([batch for batch in plan.batches if batch.page_index == 2]) == 2
    assert plan.primary_group_count == 8
    assert {
        reason
        for denial in plan.denied
        for reason in denial.reason_codes
    } == {
        "primary_page_budget_exceeded",
        "primary_project_budget_exceeded",
        "unified_page_actual_call_budget_exceeded",
    }

    project_limited = plan_symbol_escalation_batches(
        requests,
        actual_call_capacity_by_page={0: 16, 1: 16, 2: 16},
    )
    assert len(project_limited.batches) == 8
    assert project_limited.primary_group_count == 8
    assert any(
        "primary_project_budget_exceeded" in denial.reason_codes
        for denial in project_limited.denied
    )


def test_retry_preserves_primary_count_but_consumes_actual_and_wall_budget() -> None:
    request = _escalation_request(
        "visual-retry",
        projected_wall_seconds=12.0,
    )
    batch = plan_symbol_escalation_batches(
        (request,),
        actual_call_capacity_by_page={0: 3},
    ).batches[0]
    initial = _budget_state()
    primary = reserve_escalation_budget_window(
        initial,
        (batch,),
        actual_call_capacity_by_page={0: 3},
    )
    retry = reserve_escalation_budget_window(
        primary.state,
        (batch,),
        actual_call_capacity_by_page={0: 3},
        retry=True,
    )

    assert primary.allowed is True
    assert retry.allowed is True
    assert retry.state.project_primary_count == 1
    assert retry.state.page_primary_counts == ((0, 1),)
    assert retry.state.page_actual_call_counts == ((0, 2),)
    assert retry.state.page_wall_seconds == ((0, 24.0),)
    assert retry.state.project_wall_seconds == 24.0

    denied = reserve_escalation_budget_window(
        retry.state,
        (batch, batch),
        actual_call_capacity_by_page={0: 3},
        retry=True,
    )
    assert denied.allowed is False
    assert denied.reserved_batches == ()
    assert denied.state == retry.state
    assert denied.reason_codes == (
        "unified_page_actual_call_budget_exceeded",
        "page_wall_budget_exceeded",
        "project_retry_budget_exceeded",
    )


def test_planner_fake_clock_enforces_page_and_project_wall_budgets() -> None:
    elapsed = iter((23.0, 23.0, 44.0, 44.0))

    def fake_clock() -> float:
        return next(elapsed)

    requests = (
        _escalation_request(
            "visual-page-0-a",
            page_index=0,
            projected_wall_seconds=fake_clock(),
        ),
        _escalation_request(
            "visual-page-0-b",
            page_index=0,
            bbox=(20.0, 0.0, 30.0, 10.0),
            projected_wall_seconds=fake_clock(),
        ),
        _escalation_request(
            "visual-page-1",
            page_index=1,
            projected_wall_seconds=fake_clock(),
        ),
        _escalation_request(
            "visual-page-2",
            page_index=2,
            projected_wall_seconds=fake_clock(),
        ),
    )

    plan = plan_symbol_escalation_batches(
        requests,
        actual_call_capacity_by_page={0: 16, 1: 16, 2: 16},
    )

    assert tuple(batch.observation_ids for batch in plan.batches) == (
        ("visual-page-0-a",),
        ("visual-page-1",),
    )
    denials = {
        denial.observation_ids: denial.reason_codes for denial in plan.denied
    }
    assert denials[("visual-page-0-b",)] == ("page_wall_budget_exceeded",)
    assert denials[("visual-page-2",)] == ("project_wall_budget_exceeded",)


def test_planner_deduplicates_and_merges_stably_with_exact_once_ids() -> None:
    duplicate_left = _escalation_request(
        "visual-duplicate-left",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )
    duplicate_right = _escalation_request(
        "visual-duplicate-right",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )
    overlapping = _escalation_request(
        "visual-overlap",
        bbox=(8.0, 0.0, 18.0, 10.0),
        geometry_sha256="b" * 64,
        source_ids=("text-shared",),
    )
    separate = _escalation_request(
        "visual-separate",
        bbox=(18.0, 0.0, 28.0, 10.0),
        geometry_sha256="c" * 64,
        source_ids=("text-shared",),
    )
    inputs = (separate, duplicate_right, overlapping, duplicate_left)

    first = plan_symbol_escalation_batches(
        inputs,
        actual_call_capacity_by_page={0: 16},
        window_size=1,
    )
    second = plan_symbol_escalation_batches(
        tuple(reversed(inputs)),
        actual_call_capacity_by_page={0: 16},
        window_size=2,
    )

    assert first == second
    assert len(first.batches) == 2
    assert first.batches[0].observation_ids == (
        "visual-duplicate-left",
        "visual-duplicate-right",
        "visual-overlap",
    )
    assert first.batches[0].bbox_pdf == (0.0, 0.0, 18.0, 10.0)
    assert first.batches[1].observation_ids == ("visual-separate",)
    assert sorted(
        observation_id
        for batch in first.batches
        for observation_id in batch.observation_ids
    ) == sorted(request.decision.visual_observation_id for request in inputs)


def test_planner_content_identity_excludes_only_observation_identity() -> None:
    left = _escalation_request(
        "visual-left",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )
    same_content = _escalation_request(
        "visual-right",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )
    changed_geometry = _escalation_request(
        "visual-geometry",
        geometry_sha256="b" * 64,
        source_ids=("text-shared",),
        bbox=(30.0, 0.0, 40.0, 10.0),
    )

    plan = plan_symbol_escalation_batches(
        (changed_geometry, same_content, left),
        actual_call_capacity_by_page={0: 16},
    )

    assert plan.batches[0].observation_ids == ("visual-left", "visual-right")
    assert plan.batches[1].observation_ids == ("visual-geometry",)
    assert plan.batches[0].content_sha256 != plan.batches[1].content_sha256


def test_planner_rejects_non_escalate_and_non_allowlisted_families() -> None:
    request = _escalation_request("visual-invalid")
    locally_resolved = route_visual_observation(
        _resolution(
            "native_symbol_explicit",
            "local_projection_complete",
            resolved_family="diameter",
        )
    )

    with pytest.raises(ValueError, match="escalate"):
        plan_symbol_escalation_batches(
            (replace(request, decision=locally_resolved),),
            actual_call_capacity_by_page={0: 16},
        )
    with pytest.raises(ValueError, match="local evidence"):
        plan_symbol_escalation_batches(
            (
                replace(
                    request,
                    local_resolution=replace(
                        request.local_resolution,
                        family_hypotheses=("future-family",),
                    ),
                ),
            ),
            actual_call_capacity_by_page={0: 16},
        )


def test_concurrent_budget_window_denial_reserves_zero_members() -> None:
    first = plan_symbol_escalation_batches(
        (_escalation_request("visual-a", projected_wall_seconds=22.0),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    second = plan_symbol_escalation_batches(
        (
            _escalation_request(
                "visual-b",
                bbox=(20.0, 0.0, 30.0, 10.0),
                projected_wall_seconds=24.0,
            ),
        ),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    outcome = reserve_escalation_budget_window(
        _budget_state(),
        (first, second),
        actual_call_capacity_by_page={0: 16},
    )

    assert outcome.allowed is False
    assert outcome.reserved_batches == ()
    assert outcome.state == _budget_state()
    assert outcome.reason_codes == ("page_wall_budget_exceeded",)


@pytest.mark.parametrize(
    ("mode", "expected_version"),
    (
        ("legacy_high_recall", "legacy"),
        ("shadow_uncertainty", "symbol-uncertainty-router/1"),
        ("production_uncertainty", "symbol-uncertainty-router/1"),
    ),
)
def test_symbol_routing_mode_has_one_version_mapping_owner(
    mode: str,
    expected_version: str,
) -> None:
    assert symbol_routing_identity(mode) == (mode, expected_version)
    assert validate_frozen_symbol_routing_identity(
        mode,
        expected_version,
    ) == (mode, expected_version)


def test_symbol_routing_mode_rejects_unknown_or_mismatched_identity() -> None:
    with pytest.raises(ValueError, match="mode"):
        symbol_routing_identity("verification_high_recall")
    with pytest.raises(ValueError, match="router version"):
        validate_frozen_symbol_routing_identity(
            "production_uncertainty",
            "legacy",
        )


def test_symbol_routing_identity_contains_hostile_str() -> None:
    with pytest.raises(ValueError, match="mode"):
        symbol_routing_identity(_HostileStr("production_uncertainty"))


def test_frozen_symbol_routing_identity_contains_hostile_str() -> None:
    with pytest.raises(ValueError, match="router version"):
        validate_frozen_symbol_routing_identity(
            "production_uncertainty",
            _HostileStr("symbol-uncertainty-router/1"),
        )


def test_exact_duplicate_wall_estimate_is_conservative_and_order_stable() -> None:
    fast = _escalation_request(
        "visual-fast",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
        projected_wall_seconds=1.0,
    )
    slow = _escalation_request(
        "visual-slow",
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
        projected_wall_seconds=50.0,
    )

    first = plan_symbol_escalation_batches(
        (fast, slow),
        actual_call_capacity_by_page={0: 16},
    )
    replay = plan_symbol_escalation_batches(
        (slow, fast),
        actual_call_capacity_by_page={0: 16},
    )

    assert first == replay
    assert first.batches == ()
    assert first.denied[0].observation_ids == (
        "visual-fast",
        "visual-slow",
    )
    assert first.denied[0].reason_codes == ("page_wall_budget_exceeded",)


def _valid_escalation_decision():
    return _escalation_request("visual-contract").decision


@pytest.mark.parametrize(
    "decision",
    (
        replace(_valid_escalation_decision(), schema_version="future-schema"),
        replace(_valid_escalation_decision(), router_version="future-router"),
        replace(_valid_escalation_decision(), visual_observation_id=""),
        replace(_valid_escalation_decision(), input_sha256="A" * 64),
        replace(_valid_escalation_decision(), input_sha256="a" * 63),
        replace(
            _valid_escalation_decision(),
            disposition="future",  # type: ignore[arg-type]
        ),
        replace(
            _valid_escalation_decision(),
            escalation_reason_codes=(),
        ),
        replace(
            _valid_escalation_decision(),
            local_resolution_reason_codes=("native_symbol_explicit",),
        ),
        replace(
            _valid_escalation_decision(),
            escalation_reason_codes=(
                "local_parse_incomplete",
                "ambiguous_component_grouping",
            ),
        ),
        replace(
            _valid_escalation_decision(),
            escalation_reason_codes=(
                "local_parse_incomplete",
                "local_parse_incomplete",
            ),
        ),
        replace(
            _valid_escalation_decision(),
            escalation_reason_codes=("future_reason",),
        ),
        replace(
            _valid_escalation_decision(),
            requires_confirmation=False,
        ),
    ),
)
def test_routing_decision_contract_rejects_malformed_escalation(
    decision,
) -> None:
    request = replace(
        _escalation_request("visual-contract"),
        decision=decision,
    )

    with pytest.raises(ValueError, match="routing decision"):
        validate_routing_decision(decision)
    with pytest.raises(ValueError, match="routing decision"):
        plan_symbol_escalation_batches(
            (request,),
            actual_call_capacity_by_page={0: 16},
        )


def test_structural_validator_contains_hostile_reason_tuple() -> None:
    decision = replace(
        _valid_escalation_decision(),
        escalation_reason_codes=_RaisingTuple(
            ("local_parse_incomplete",)
        ),
    )

    with pytest.raises(ValueError, match="routing decision"):
        validate_routing_decision(decision)


def test_escalation_contract_validators_contain_hostile_collections() -> None:
    batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-hostile-contract"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]

    with pytest.raises(ValueError, match="escalation batch"):
        reserve_escalation_budget_window(
            _budget_state(),
            (
                replace(
                    batch,
                    observation_ids=_RaisingTuple(batch.observation_ids),
                ),
            ),
            actual_call_capacity_by_page={0: 16},
        )
    with pytest.raises(ValueError, match="budget state"):
        reserve_escalation_budget_window(
            replace(
                _budget_state(),
                page_actual_call_counts=_RaisingTuple(),
            ),
            (batch,),
            actual_call_capacity_by_page={0: 16},
        )
    with pytest.raises(ValueError, match="actual call capacity"):
        reserve_escalation_budget_window(
            _budget_state(),
            (batch,),
            actual_call_capacity_by_page=_RaisingMapping(),
        )


def test_actual_call_capacity_uses_one_immutable_snapshot() -> None:
    plan = plan_symbol_escalation_batches(
        (_escalation_request("visual-capacity-snapshot"),),
        actual_call_capacity_by_page=_SnapshotThenRaisingMapping(),
    )

    assert len(plan.batches) == 1
    assert plan.denied == ()


def test_reservation_rejects_noncanonical_or_inconsistent_state() -> None:
    batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-state"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    malformed_states = (
        object(),
        replace(_budget_state(), project_primary_count=-1),
        replace(
            _budget_state(),
            page_primary_counts=((0, 1), (0, 1)),
            project_primary_count=2,
        ),
        replace(
            _budget_state(),
            page_primary_counts=((1, 0), (0, 0)),
        ),
        replace(
            _budget_state(),
            page_primary_counts=(("0", 0), (0, 0)),  # type: ignore[arg-type]
        ),
        replace(_budget_state(), project_primary_count=1),
        replace(
            _budget_state(),
            page_actual_call_counts=((0, -1),),
        ),
        replace(
            _budget_state(),
            page_wall_seconds=((0, float("nan")),),
            project_wall_seconds=float("nan"),
        ),
        replace(
            _budget_state(),
            page_wall_seconds=((0, 1.0),),
            project_wall_seconds=0.0,
        ),
        replace(
            _budget_state(),
            page_primary_counts=((0, 5),),
            project_primary_count=5,
        ),
    )

    for state in malformed_states:
        with pytest.raises(ValueError, match="budget state"):
            reserve_escalation_budget_window(
                state,  # type: ignore[arg-type]
                (batch,),
                actual_call_capacity_by_page={0: 16},
            )


@pytest.mark.parametrize(
    "batch_transform",
    (
        lambda batch: replace(batch, page_index=-1),
        lambda batch: replace(batch, bbox_pdf=(0.0, 0.0, 0.0, 1.0)),
        lambda batch: replace(batch, observation_ids=()),
        lambda batch: replace(
            batch,
            observation_ids=("visual-z", "visual-a"),
        ),
        lambda batch: replace(
            batch,
            geometry_sha256s=("A" * 64,),
        ),
        lambda batch: replace(
            batch,
            member_content_sha256s=("a" * 63,),
        ),
        lambda batch: replace(
            batch,
            escalation_reason_codes=(),
        ),
        lambda batch: replace(
            batch,
            escalation_reason_codes=("future_reason",),
        ),
        lambda batch: replace(
            batch,
            family_hypotheses=("future-family",),
        ),
        lambda batch: replace(batch, projected_wall_seconds=-1.0),
        lambda batch: replace(
            batch,
            projected_wall_seconds=float("inf"),
        ),
    ),
)
def test_reservation_rejects_malformed_external_batch(
    batch_transform,
) -> None:
    batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-batch"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]

    with pytest.raises(ValueError, match="escalation batch"):
        reserve_escalation_budget_window(
            _budget_state(),
            (batch_transform(batch),),
            actual_call_capacity_by_page={0: 16},
        )


def test_escalation_reason_priority_precedes_bbox_order() -> None:
    conflict = _escalation_request(
        "visual-conflict",
        bbox=(30.0, 0.0, 40.0, 10.0),
        reasons=("local_evidence_conflict",),
    )
    parse = _escalation_request(
        "visual-parse",
        bbox=(0.0, 0.0, 10.0, 10.0),
        reasons=("local_parse_incomplete",),
    )
    unknown = _escalation_request(
        "visual-unknown",
        bbox=(10.0, 0.0, 20.0, 10.0),
        reasons=("unknown_symbol_pattern",),
    )

    plan = plan_symbol_escalation_batches(
        (unknown, parse, conflict),
        actual_call_capacity_by_page={0: 16},
    )

    assert tuple(batch.observation_ids for batch in plan.batches) == (
        ("visual-conflict",),
        ("visual-parse",),
        ("visual-unknown",),
    )


def test_overlap_merge_uses_original_graph_without_blank_corner_bridge() -> None:
    first = _escalation_request(
        "visual-horizontal",
        bbox=(0.0, 0.0, 10.0, 2.0),
        source_ids=("text-shared",),
    )
    second = _escalation_request(
        "visual-vertical",
        bbox=(8.0, 0.0, 10.0, 10.0),
        source_ids=("text-shared",),
    )
    blank_corner = _escalation_request(
        "visual-blank-corner",
        bbox=(0.0, 8.0, 2.0, 10.0),
        source_ids=("text-shared",),
    )

    plan = plan_symbol_escalation_batches(
        (blank_corner, second, first),
        actual_call_capacity_by_page={0: 16},
    )

    assert len(plan.batches) == 2
    assert {
        batch.observation_ids for batch in plan.batches
    } == {
        ("visual-horizontal", "visual-vertical"),
        ("visual-blank-corner",),
    }


def test_overlap_merge_keeps_true_transitive_component() -> None:
    requests = (
        _escalation_request(
            "visual-a",
            bbox=(0.0, 0.0, 5.0, 5.0),
            source_ids=("text-shared",),
        ),
        _escalation_request(
            "visual-b",
            bbox=(4.0, 0.0, 9.0, 5.0),
            source_ids=("text-shared",),
        ),
        _escalation_request(
            "visual-c",
            bbox=(8.0, 0.0, 13.0, 5.0),
            source_ids=("text-shared",),
        ),
    )

    plan = plan_symbol_escalation_batches(
        requests,
        actual_call_capacity_by_page={0: 16},
    )

    assert len(plan.batches) == 1
    assert plan.batches[0].observation_ids == (
        "visual-a",
        "visual-b",
        "visual-c",
    )


def test_bbox_numeric_normalization_deduplicates_int_and_float() -> None:
    integer_bbox = _escalation_request(
        "visual-int",
        bbox=(0, 0, 10, 10),  # type: ignore[arg-type]
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )
    float_bbox = _escalation_request(
        "visual-float",
        bbox=(0.0, 0.0, 10.0, 10.0),
        geometry_sha256="a" * 64,
        source_ids=("text-shared",),
    )

    plan = plan_symbol_escalation_batches(
        (integer_bbox, float_bbox),
        actual_call_capacity_by_page={0: 16},
    )

    assert len(plan.batches) == 1
    assert plan.batches[0].observation_ids == (
        "visual-float",
        "visual-int",
    )


def test_request_binds_decision_to_canonical_local_resolution() -> None:
    request = _escalation_request("visual-bound")
    swapped_family = replace(
        request,
        local_resolution=replace(
            request.local_resolution,
            family_hypotheses=("depth",),
        ),
    )
    empty_non_unknown = replace(
        request,
        local_resolution=replace(
            request.local_resolution,
            family_hypotheses=(),
        ),
    )

    for malformed in (swapped_family, empty_non_unknown):
        with pytest.raises(ValueError, match="local evidence"):
            plan_symbol_escalation_batches(
                (malformed,),
                actual_call_capacity_by_page={0: 16},
            )

    unknown = _escalation_request(
        "visual-unknown-bound",
        family_hypotheses=(),
        reasons=("unknown_symbol_pattern",),
    )
    plan = plan_symbol_escalation_batches(
        (unknown,),
        actual_call_capacity_by_page={0: 16},
    )
    assert plan.batches[0].family_hypotheses == ()


@pytest.mark.parametrize("capacity", (17, 100))
def test_unified_actual_call_capacity_cannot_exceed_named_ceiling(
    capacity: int,
) -> None:
    with pytest.raises(ValueError, match="actual call capacity"):
        plan_symbol_escalation_batches(
            (_escalation_request("visual-capacity"),),
            actual_call_capacity_by_page={0: capacity},
        )


def test_retry_rejects_primary_state_without_matching_actual_count() -> None:
    batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-retry-state"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    malformed_states = (
        EscalationBudgetState(
            page_primary_counts=((0, 1),),
            project_primary_count=1,
            page_actual_call_counts=(),
            page_wall_seconds=(),
            project_wall_seconds=0.0,
            primary_group_identities=((0, batch.content_sha256),),
            retried_group_identities=(),
        ),
        EscalationBudgetState(
            page_primary_counts=((0, 2),),
            project_primary_count=2,
            page_actual_call_counts=((0, 1),),
            page_wall_seconds=(),
            project_wall_seconds=0.0,
            primary_group_identities=(
                (0, "a" * 64),
                (0, batch.content_sha256),
            ),
            retried_group_identities=(),
        ),
    )

    for state in malformed_states:
        with pytest.raises(ValueError, match="budget state"):
            reserve_escalation_budget_window(
                state,
                (batch,),
                actual_call_capacity_by_page={0: 16},
                retry=True,
            )


def test_external_batch_content_identity_is_self_consistent() -> None:
    single = plan_symbol_escalation_batches(
        (_escalation_request("visual-single-identity"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    merged = plan_symbol_escalation_batches(
        (
            _escalation_request(
                "visual-merged-a",
                geometry_sha256="a" * 64,
                source_ids=("text-shared",),
            ),
            _escalation_request(
                "visual-merged-b",
                bbox=(8.0, 0.0, 18.0, 10.0),
                geometry_sha256="b" * 64,
                source_ids=("text-shared",),
            ),
        ),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    assert len(merged.member_content_sha256s) == 2
    assert len(single.lineage_sha256) == 64
    assert len(single.budget_sha256) == 64

    for corrupted in (
        replace(single, content_sha256="f" * 64),
        replace(single, bbox_pdf=(1.0, 1.0, 11.0, 11.0)),
        replace(single, geometry_sha256s=("c" * 64,)),
        replace(merged, content_sha256="e" * 64),
        replace(merged, page_index=1),
        replace(
            merged,
            escalation_reason_codes=("unknown_symbol_pattern",),
        ),
        replace(merged, family_hypotheses=("depth",)),
        replace(merged, geometry_sha256s=("c" * 64, "d" * 64)),
        replace(
            merged,
            associated_text_observation_ids=("text-other",),
        ),
        replace(single, observation_ids=("visual-tampered",)),
        replace(
            single,
            observation_ids=("visual-tampered",),
            observation_member_bindings=(
                ("visual-tampered", single.content_sha256),
            ),
        ),
        replace(
            merged,
            observation_member_bindings=tuple(
                (observation_id, member_hash)
                for (observation_id, _), (_, member_hash) in zip(
                    merged.observation_member_bindings,
                    reversed(merged.observation_member_bindings),
                    strict=True,
                )
            ),
        ),
        replace(
            single,
            projected_wall_seconds=single.projected_wall_seconds + 1.0,
        ),
        replace(
            single,
            member_content_sha256s=("d" * 64,),
            observation_member_bindings=(
                (single.observation_ids[0], "d" * 64),
            ),
        ),
    ):
        with pytest.raises(ValueError, match="escalation batch"):
            reserve_escalation_budget_window(
                _budget_state(),
                (corrupted,),
                actual_call_capacity_by_page={0: 16},
            )


def test_empty_family_requires_unknown_pattern_only_for_external_batch() -> None:
    unknown = plan_symbol_escalation_batches(
        (
            _escalation_request(
                "visual-empty-family",
                family_hypotheses=(),
                reasons=("unknown_symbol_pattern",),
            ),
        ),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]

    def self_consistent_batch(reason_codes: tuple[str, ...]):
        content_sha256 = semantic_content_sha256(
            page_index=unknown.page_index,
            bbox_pdf=unknown.bbox_pdf,
            geometry_sha256s=unknown.geometry_sha256s,
            associated_text_observation_ids=(
                unknown.associated_text_observation_ids
            ),
            escalation_reason_codes=reason_codes,
            family_hypotheses=(),
        )
        bindings = tuple(
            (observation_id, content_sha256)
            for observation_id in unknown.observation_ids
        )
        return replace(
            unknown,
            content_sha256=content_sha256,
            lineage_sha256=batch_lineage_sha256(
                content_sha256,
                unknown.page_index,
                bindings,
            ),
            budget_sha256=batch_budget_sha256(
                content_sha256,
                unknown.page_index,
                unknown.projected_wall_seconds,
            ),
            member_content_sha256s=(content_sha256,),
            observation_member_bindings=bindings,
            escalation_reason_codes=reason_codes,
        )

    valid = reserve_escalation_budget_window(
        _budget_state(),
        (unknown,),
        actual_call_capacity_by_page={0: 16},
    )
    assert valid.allowed is True

    for invalid_reasons in (
        ("local_parse_incomplete",),
        ("local_parse_incomplete", "unknown_symbol_pattern"),
    ):
        with pytest.raises(ValueError, match="escalation batch"):
            reserve_escalation_budget_window(
                _budget_state(),
                (self_consistent_batch(invalid_reasons),),
                actual_call_capacity_by_page={0: 16},
            )


def test_retry_requires_existing_primary_identity_and_rejects_duplicate() -> None:
    primary_batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-primary"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    foreign_batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-foreign"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    primary = reserve_escalation_budget_window(
        _budget_state(),
        (primary_batch,),
        actual_call_capacity_by_page={0: 16},
    )

    with pytest.raises(ValueError, match="retry identity"):
        reserve_escalation_budget_window(
            primary.state,
            (foreign_batch,),
            actual_call_capacity_by_page={0: 16},
            retry=True,
        )
    with pytest.raises(ValueError, match="duplicate primary"):
        reserve_escalation_budget_window(
            primary.state,
            (primary_batch,),
            actual_call_capacity_by_page={0: 16},
        )


def test_retry_has_one_per_project_all_or_none_budget() -> None:
    first_batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-retry-one"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    second_batch = plan_symbol_escalation_batches(
        (
            _escalation_request(
                "visual-retry-two",
                bbox=(20.0, 0.0, 30.0, 10.0),
            ),
        ),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    primaries = reserve_escalation_budget_window(
        _budget_state(),
        (first_batch, second_batch),
        actual_call_capacity_by_page={0: 16},
    )
    two_member_retry = reserve_escalation_budget_window(
        primaries.state,
        (first_batch, second_batch),
        actual_call_capacity_by_page={0: 16},
        retry=True,
    )

    assert two_member_retry.allowed is False
    assert two_member_retry.reserved_batches == ()
    assert two_member_retry.state == primaries.state
    assert two_member_retry.reason_codes == (
        "project_retry_budget_exceeded",
    )
    duplicate_retry = reserve_escalation_budget_window(
        primaries.state,
        (first_batch, first_batch),
        actual_call_capacity_by_page={0: 16},
        retry=True,
    )
    assert duplicate_retry.allowed is False
    assert duplicate_retry.state == primaries.state
    assert duplicate_retry.reason_codes == (
        "project_retry_budget_exceeded",
    )

    first_retry = reserve_escalation_budget_window(
        primaries.state,
        (first_batch,),
        actual_call_capacity_by_page={0: 16},
        retry=True,
    )
    assert first_retry.allowed is True
    assert first_retry.state.project_retry_count == 1
    second_retry = reserve_escalation_budget_window(
        first_retry.state,
        (first_batch,),
        actual_call_capacity_by_page={0: 16},
        retry=True,
    )
    assert second_retry.allowed is False
    assert second_retry.state == first_retry.state
    assert second_retry.reason_codes == (
        "project_retry_budget_exceeded",
    )


def test_route_hostile_tuple_fails_closed_and_replay_stable() -> None:
    hostile = replace(
        _resolution("local_parse_incomplete"),
        reason_codes=_RaisingTuple(("local_parse_incomplete",)),
    )

    first = route_visual_observation(hostile)
    replay = route_visual_observation(hostile)

    assert first == replay
    assert first.disposition == "block"
    assert first.block_reason_codes == ("routing_contract_invalid",)


def test_structural_validator_rejects_block_without_confirmation() -> None:
    block = route_visual_observation(
        _resolution("coverage_lineage_incomplete")
    )

    with pytest.raises(ValueError, match="routing decision"):
        validate_routing_decision(
            replace(block, requires_confirmation=False)
        )


def test_budget_state_rejects_unaccounted_or_wrong_page_retry_delta() -> None:
    batch = plan_symbol_escalation_batches(
        (_escalation_request("visual-forged-retry"),),
        actual_call_capacity_by_page={0: 16},
    ).batches[0]
    primary = reserve_escalation_budget_window(
        _budget_state(),
        (batch,),
        actual_call_capacity_by_page={0: 16},
    )
    unaccounted = replace(
        primary.state,
        page_actual_call_counts=((0, 2),),
        retried_group_identities=(),
    )
    wrong_page = replace(
        primary.state,
        page_actual_call_counts=((0, 1), (1, 1)),
        retried_group_identities=((0, batch.content_sha256),),
    )

    for forged in (unaccounted, wrong_page):
        with pytest.raises(ValueError, match="budget state"):
            reserve_escalation_budget_window(
                forged,
                (batch,),
                actual_call_capacity_by_page={0: 16, 1: 16},
                retry=True,
            )
