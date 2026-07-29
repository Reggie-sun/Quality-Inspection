from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace

import pytest

from app.candidates.local_symbol_resolution import LocalResolution
from app.candidates.symbol_review import VisualReviewDecision
from app.candidates.symbol_routing import route_visual_observation


class _RaisingMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("mapping access failed")

    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("mapping iteration failed")

    def __len__(self) -> int:
        raise RuntimeError("mapping length failed")

    def items(self):
        raise RuntimeError("mapping items failed")


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
