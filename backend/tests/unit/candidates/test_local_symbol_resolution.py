from __future__ import annotations

import inspect
from collections.abc import Iterator, Mapping
from dataclasses import replace

import pytest

from app.candidates.local_symbol_resolution import (
    prepare_local_family_hypotheses,
    resolve_visual_observation,
)
from app.candidates.symbol_routing import route_visual_observation
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import VisualGeometryContext


class _RaisingMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("hostile candidate access")

    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("hostile candidate iteration")

    def __len__(self) -> int:
        raise RuntimeError("hostile candidate length")


def _text(
    identity: str,
    raw_text: str,
    bbox: tuple[float, float, float, float] = (20, 20, 40, 28),
    *,
    page_index: int = 0,
    confidence: float | None = None,
    source_type: str = "native",
) -> TextObservation:
    return TextObservation(
        identity,
        source_type,
        "line",
        raw_text,
        raw_text,
        page_index,
        bbox,
        tuple(value / 200 for value in bbox),
        (1.0, 0.0),
        0.0,
        confidence,
    )


def _visual(
    associated: tuple[str, ...] = ("text-1",),
    *,
    page_index: int = 0,
    bbox: tuple[float, float, float, float] = (12, 18, 18, 28),
) -> VisualObservation:
    return VisualObservation(
        "visual-1",
        "visual",
        "annotation_context",
        page_index,
        bbox,
        tuple(value / 200 for value in bbox),
        "text_adjacent_vector_context",
        "a" * 64,
        associated,
    )


def _candidate(
    identity: str,
    payload: dict[str, object],
    sources: tuple[str, ...] = ("text-1",),
) -> dict[str, object]:
    return {
        "candidate_id": identity,
        "payload": {
            "candidate_id": identity,
            "raw_text": "",
            "normalized_text": "",
            "coordinates": (20, 20, 40, 28),
            "scope": "local_feature",
            "quantity": None,
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
            **payload,
        },
        "source_location_ids": list(sources),
    }


def _diameter_candidate(
    nominal: str = "10",
    *,
    identity: str = "candidate-diameter",
    sources: tuple[str, ...] = ("text-1",),
) -> dict[str, object]:
    return _candidate(
        identity,
        {
            "item_type": "diameter_dimension",
            "raw_text": f"Φ{nominal}",
            "normalized_text": f"Φ{nominal}",
            "nominal": nominal,
            "feature_kind": "unknown",
        },
        sources,
    )


def _depth_candidate(
    depth: str = "8",
    *,
    identity: str = "candidate-depth",
    sources: tuple[str, ...] = ("text-1",),
) -> dict[str, object]:
    return _candidate(
        identity,
        {
            "item_type": "thread",
            "raw_text": f"M6 深 {depth}",
            "normalized_text": f"M6 深 {depth}",
            "thread_spec": "M6",
            "thread_depth": depth,
        },
        sources,
    )


def _coarse_candidate(
    coarse_type: str,
    *,
    identity: str,
    raw_text: str,
    sources: tuple[str, ...] = ("text-1",),
) -> dict[str, object]:
    return {
        "candidate_id": identity,
        "payload": {
            "raw_text": raw_text,
            "coordinates": (20, 20, 40, 28),
            "coarse_type": coarse_type,
            "requires_confirmation": True,
        },
        "source_location_ids": list(sources),
    }


def _datum_context() -> VisualGeometryContext:
    rectangle = (
        b'{"coordinates":["18","18","28","30"],"opcode":"re",'
        b'"orientation":1,"style":{}}'
    )
    return VisualGeometryContext(
        "visual-1",
        0,
        "a" * 64,
        (20, 20, 26, 28),
        ((18, 18, 28, 30),),
        (rectangle,),
    )


def _revision_context() -> VisualGeometryContext:
    lines = tuple(
        (
            '{"coordinates":[["%s","%s"],["%s","%s"]],'
            '"opcode":"l","style":{}}' % values
        ).encode()
        for values in (
            (12, 28, 20, 12),
            (20, 12, 28, 28),
            (28, 28, 12, 28),
        )
    )
    return VisualGeometryContext(
        "visual-1",
        0,
        "a" * 64,
        (20, 20, 28, 28),
        ((12, 12, 28, 28),),
        lines,
    )


def _both_reference_hypotheses_context() -> VisualGeometryContext:
    datum = _datum_context()
    revision = _revision_context()
    return replace(
        datum,
        path_bboxes=(*datum.path_bboxes, *revision.path_bboxes),
        canonical_path_items=(
            *datum.canonical_path_items,
            *revision.canonical_path_items,
        ),
    )


def _resolve(
    family: str,
    *,
    text: TextObservation | None = None,
    visual: VisualObservation | None = None,
    candidates: tuple[dict[str, object], ...] = (),
    context: VisualGeometryContext | None = None,
    confidence: float | None = None,
):
    current_text = text or _text("text-1", "10")
    current_visual = visual or _visual()
    return resolve_visual_observation(
        observation=current_visual,
        family_hypotheses=(family,),
        text_observations=(current_text,),
        candidates=candidates,
        geometry_context=context,
        confidence=confidence,
    )


def _prepare(
    *,
    text: TextObservation | None = None,
    visual: VisualObservation | None = None,
    candidates: tuple[Mapping[str, object], ...] = (),
    context: VisualGeometryContext | None = None,
) -> tuple[str, ...]:
    return prepare_local_family_hypotheses(
        observation=visual or _visual(),
        text_observations=(text or _text("text-1", "10"),),
        candidates=candidates,
        geometry_context=context,
    )


@pytest.mark.parametrize(
    ("text", "candidates", "expected"),
    (
        (
            _text("text-1", "Φ10"),
            (_diameter_candidate(),),
            ("diameter",),
        ),
        (
            _text("text-1", "M6 深 8"),
            (_depth_candidate(),),
            ("depth",),
        ),
        (
            _text("text-1", "Ra 3.2"),
            (
                _coarse_candidate(
                    "roughness",
                    identity="candidate-roughness",
                    raw_text="Ra 3.2",
                ),
            ),
            ("surface_roughness",),
        ),
    ),
)
def test_prepares_only_complete_typed_family_positives(
    text: TextObservation,
    candidates: tuple[Mapping[str, object], ...],
    expected: tuple[str, ...],
) -> None:
    assert _prepare(text=text, candidates=candidates) == expected


@pytest.mark.parametrize(
    ("text", "context", "expected"),
    (
        (
            _text("text-1", "A", (20, 20, 26, 28)),
            _datum_context(),
            ("datum_reference",),
        ),
        (
            _text("text-1", "P1", (20, 20, 28, 28)),
            _revision_context(),
            ("revision_marker",),
        ),
    ),
)
def test_prepares_reference_family_through_common_projection(
    text: TextObservation,
    context: VisualGeometryContext,
    expected: tuple[str, ...],
) -> None:
    assert _prepare(text=text, context=context) == expected


@pytest.mark.parametrize(
    ("text", "candidates"),
    (
        (
            _text("text-1", "10 深 8"),
            (_diameter_candidate(), _depth_candidate()),
        ),
        (
            _text("text-1", "0.1 A"),
            (
                _coarse_candidate(
                    "geometric_tolerance",
                    identity="candidate-gdt",
                    raw_text="0.1 A",
                ),
            ),
        ),
        (_text("text-1", "unclassified"), ()),
    ),
)
def test_preparation_keeps_unsupported_or_unknown_evidence_empty(
    text: TextObservation,
    candidates: tuple[Mapping[str, object], ...],
) -> None:
    hypotheses = _prepare(text=text, candidates=candidates)
    resolution = resolve_visual_observation(
        observation=_visual(),
        family_hypotheses=hypotheses,
        text_observations=(text,),
        candidates=candidates,
        geometry_context=None,
    )

    assert hypotheses == ()
    assert resolution.reason_codes == ("unknown_symbol_pattern",)
    assert route_visual_observation(resolution).disposition == "escalate"


def test_preparation_preserves_all_multiple_complete_positives() -> None:
    candidate = _diameter_candidate()
    candidate["payload"]["depth"] = "8"  # type: ignore[index]
    text = _text("text-1", "Φ10 深 8")
    hypotheses = _prepare(text=text, candidates=(candidate,))
    resolution = resolve_visual_observation(
        observation=_visual(),
        family_hypotheses=hypotheses,
        text_observations=(text,),
        candidates=(candidate,),
        geometry_context=None,
    )

    assert hypotheses == ("depth", "diameter")
    assert resolution.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(resolution).disposition == "escalate"


def test_preparation_is_label_free_order_stable_and_replay_stable() -> None:
    signature = inspect.signature(prepare_local_family_hypotheses)
    assert "family_hypotheses" not in signature.parameters
    assert "symbol_kinds" not in signature.parameters
    text = _text("text-1", "Φ10")
    unrelated = _diameter_candidate(sources=("other-text",))
    inputs = {
        "observation": _visual(),
        "text_observations": (text, _text("other-text", "Φ11")),
        "candidates": (_diameter_candidate(), unrelated),
        "geometry_context": None,
    }

    first = prepare_local_family_hypotheses(**inputs)
    replay = prepare_local_family_hypotheses(**inputs)
    reordered = prepare_local_family_hypotheses(
        **{
            **inputs,
            "text_observations": tuple(
                reversed(inputs["text_observations"])
            ),
            "candidates": tuple(reversed(inputs["candidates"])),
        }
    )

    assert first == replay == reordered == ("diameter",)


def test_preparation_propagates_helper_defects() -> None:
    with pytest.raises(RuntimeError, match="hostile candidate"):
        _prepare(candidates=(_RaisingMapping(),))
    with pytest.raises(AttributeError):
        prepare_local_family_hypotheses(
            observation=object(),  # type: ignore[arg-type]
            text_observations=(),
            candidates=(),
            geometry_context=None,
        )


def test_typed_projection_preserves_global_candidate_index() -> None:
    unrelated = _diameter_candidate(
        identity="unrelated",
        sources=("other-text",),
    )
    target = _diameter_candidate(identity="target")

    resolution = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(unrelated, target),
    )

    assert resolution.projection is not None
    assert resolution.projection.candidate_id == "target"
    assert resolution.projection.existing_candidate_index == 1


def test_locally_complete_diameter_skips_escalation() -> None:
    resolution = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(_diameter_candidate(),),
    )

    assert resolution.resolved_family == "diameter"
    assert route_visual_observation(resolution).disposition == "locally_resolved"
    assert resolution.reason_codes == (
        "local_projection_complete",
        "native_symbol_explicit",
    )


def test_diameter_bare_numeric_typed_candidate_does_not_resolve() -> None:
    resolution = _resolve(
        "diameter",
        text=_text("text-1", "10"),
        candidates=(_diameter_candidate(),),
    )

    assert resolution.resolved_family is None
    assert "native_symbol_explicit" not in resolution.reason_codes
    assert route_visual_observation(resolution).disposition == "escalate"


def test_diameter_nominal_mismatch_escalates() -> None:
    resolution = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(_diameter_candidate("11"),),
    )

    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(resolution).disposition == "escalate"


def test_locally_complete_depth_skips_escalation() -> None:
    resolution = _resolve(
        "depth",
        text=_text("text-1", "M6 深 8"),
        candidates=(_depth_candidate(),),
    )

    assert resolution.resolved_family == "depth"
    assert route_visual_observation(resolution).disposition == "locally_resolved"
    assert "local_projection_complete" in resolution.reason_codes


def test_depth_requires_matching_explicit_native_value() -> None:
    mismatch = _resolve(
        "depth",
        text=_text("text-1", "M6 深 8"),
        candidates=(_depth_candidate("9"),),
    )
    ocr = _resolve(
        "depth",
        text=_text("text-1", "M6 深 8", source_type="ocr"),
        candidates=(_depth_candidate(),),
    )

    assert mismatch.resolved_family is None
    assert mismatch.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(mismatch).disposition == "escalate"
    assert ocr.resolved_family is None
    assert "native_symbol_explicit" not in ocr.reason_codes
    assert route_visual_observation(ocr).disposition == "escalate"


def test_multiline_native_composite_depth_resolves() -> None:
    primary = _text("text-1", "M6", (20, 20, 40, 28))
    modifier = _text("text-2", "深 8", (20, 30, 40, 38))
    candidate = _candidate(
        "candidate-composite",
        {
            "item_type": "composite",
            "raw_text": "M6\n深 8",
            "normalized_text": "M6\n深 8",
            "coordinates": (20, 20, 40, 38),
            "sub_requirements": [
                {
                    "order": 0,
                    "kind": "thread",
                    "raw_text": "M6",
                    "thread_spec": "M6",
                },
                {
                    "order": 1,
                    "kind": "depth",
                    "raw_text": "深 8",
                    "value": "8",
                },
            ],
        },
        ("text-1", "text-2"),
    )
    resolution = resolve_visual_observation(
        observation=_visual(("text-1", "text-2")),
        family_hypotheses=("depth",),
        text_observations=(primary, modifier),
        candidates=(candidate,),
        geometry_context=None,
    )

    assert resolution.resolved_family == "depth"
    assert route_visual_observation(resolution).disposition == "locally_resolved"


def test_counterbore_without_typed_evidence_escalates() -> None:
    resolution = _resolve(
        "counterbore",
        text=_text("text-1", "10 深 8"),
        candidates=(_diameter_candidate(), _depth_candidate()),
    )

    decision = route_visual_observation(resolution)
    assert resolution.resolved_family is None
    assert decision.disposition == "escalate"
    assert decision.escalation_reason_codes == (
        "missing_local_discriminator",
    )


def test_roughness_requires_exact_typed_source() -> None:
    text = _text("text-1", "Ra 3.2")
    exact = _resolve(
        "surface_roughness",
        text=text,
        candidates=(
            _coarse_candidate(
                "roughness",
                identity="candidate-roughness",
                raw_text="Ra 3.2",
            ),
        ),
    )
    wrong_source = _resolve(
        "surface_roughness",
        text=text,
        candidates=(
            _coarse_candidate(
                "roughness",
                identity="candidate-roughness",
                raw_text="Ra 3.2",
                sources=("other-text",),
            ),
        ),
    )

    assert route_visual_observation(exact).disposition == "locally_resolved"
    assert route_visual_observation(wrong_source).disposition == "escalate"
    assert wrong_source.reason_codes == ("local_parse_incomplete",)


def test_roughness_source_and_typed_candidate_values_must_match() -> None:
    resolution = _resolve(
        "surface_roughness",
        text=_text("text-1", "Ra 6.3"),
        candidates=(
            _coarse_candidate(
                "roughness",
                identity="candidate-roughness",
                raw_text="Ra 3.2",
            ),
        ),
    )

    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(resolution).disposition == "escalate"


@pytest.mark.parametrize(
    "family",
    (
        "gdt_parallelism",
        "gdt_perpendicularity",
        "gdt_flatness",
    ),
)
def test_each_gdt_family_always_escalates_without_exact_local_kind(
    family: str,
) -> None:
    resolution = _resolve(
        family,
        text=_text("text-1", "0.1 A"),
        candidates=(
            _coarse_candidate(
                "geometric_tolerance",
                identity=f"candidate-{family}",
                raw_text="0.1 A",
            ),
        ),
    )

    assert resolution.family_hypotheses == (family,)
    assert resolution.resolved_family is None
    assert route_visual_observation(resolution).disposition == "escalate"
    assert resolution.reason_codes == ("missing_local_discriminator",)


def test_datum_requires_exact_one_projection() -> None:
    valid = _resolve(
        "datum_reference",
        text=_text("text-1", "A", (20, 20, 26, 28)),
        context=_datum_context(),
    )
    invalid = _resolve(
        "datum_reference",
        text=_text("text-1", "A", (20, 20, 26, 28)),
        context=replace(_datum_context(), canonical_path_items=()),
    )
    both = _resolve(
        "datum_reference",
        text=_text("text-1", "A", (20, 20, 26, 28)),
        context=_both_reference_hypotheses_context(),
    )

    assert route_visual_observation(valid).disposition == "locally_resolved"
    assert valid.resolved_family == "datum_reference"
    assert valid.reason_codes == (
        "deterministic_geometry_complete",
        "local_projection_complete",
    )
    assert route_visual_observation(invalid).disposition == "escalate"
    assert invalid.reason_codes == ("local_parse_incomplete",)
    assert route_visual_observation(both).disposition == "escalate"
    assert both.reason_codes == ("local_evidence_conflict",)


def test_datum_cross_page_geometry_context_blocks() -> None:
    resolution = _resolve(
        "datum_reference",
        text=_text("text-1", "A", (20, 20, 26, 28)),
        context=replace(_datum_context(), page_index=1),
    )

    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("source_reconstruction_mismatch",)
    assert route_visual_observation(resolution).disposition == "block"


def test_revision_requires_exact_one_projection() -> None:
    valid = _resolve(
        "revision_marker",
        text=_text("text-1", "P1", (20, 20, 28, 28)),
        context=_revision_context(),
    )
    invalid = _resolve(
        "revision_marker",
        text=_text("text-1", "P1", (20, 20, 28, 28)),
        context=replace(
            _revision_context(),
            canonical_path_items=_revision_context().canonical_path_items[:2],
        ),
    )
    both = _resolve(
        "revision_marker",
        text=_text("text-1", "A", (20, 20, 26, 28)),
        context=_both_reference_hypotheses_context(),
    )

    assert route_visual_observation(valid).disposition == "locally_resolved"
    assert valid.resolved_family == "revision_marker"
    assert route_visual_observation(invalid).disposition == "escalate"
    assert invalid.reason_codes == ("local_parse_incomplete",)
    assert route_visual_observation(both).disposition == "escalate"
    assert both.reason_codes == ("local_evidence_conflict",)


def test_conflicting_family_evidence_escalates() -> None:
    resolution = resolve_visual_observation(
        observation=_visual(),
        family_hypotheses=("depth", "diameter"),
        text_observations=(_text("text-1", "Φ10 深 8"),),
        candidates=(_diameter_candidate(), _depth_candidate()),
        geometry_context=None,
    )

    decision = route_visual_observation(resolution)
    assert resolution.resolved_family is None
    assert decision.disposition == "escalate"
    assert decision.escalation_reason_codes == ("local_evidence_conflict",)


def test_empty_family_hypotheses_route_unknown_pattern_to_escalation() -> None:
    resolution = resolve_visual_observation(
        observation=_visual(),
        family_hypotheses=(),
        text_observations=(_text("text-1", "A"),),
        candidates=(),
        geometry_context=None,
    )

    assert resolution.family_hypotheses == ()
    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("unknown_symbol_pattern",)
    assert route_visual_observation(resolution).disposition == "escalate"


def test_candidate_coordinates_must_agree_with_associated_source() -> None:
    candidate = _diameter_candidate()
    candidate["payload"]["coordinates"] = (100, 100, 120, 108)  # type: ignore[index]
    resolution = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(candidate,),
    )

    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(resolution).disposition == "escalate"


def test_overlapping_candidate_source_superset_is_not_prefiltered_away() -> None:
    text_1 = _text("text-1", "Φ10")
    text_2 = _text("text-2", "Φ10", (22, 20, 42, 28))
    resolution = resolve_visual_observation(
        observation=_visual(),
        family_hypotheses=("diameter",),
        text_observations=(text_1, text_2),
        candidates=(
            _diameter_candidate(identity="exact"),
            _diameter_candidate(
                identity="superset",
                sources=("text-1", "text-2"),
            ),
        ),
        geometry_context=None,
    )

    assert resolution.resolved_family is None
    assert resolution.reason_codes == ("local_evidence_conflict",)
    assert route_visual_observation(resolution).disposition == "escalate"


@pytest.mark.parametrize(
    ("family", "text", "candidates", "expected_reason"),
    (
        (
            "diameter",
            "10",
            (),
            "local_parse_incomplete",
        ),
        (
            "depth",
            "8",
            (),
            "local_parse_incomplete",
        ),
        (
            "counterbore",
            "10 8",
            (),
            "missing_local_discriminator",
        ),
        (
            "surface_roughness",
            "3.2",
            (),
            "local_parse_incomplete",
        ),
        (
            "gdt_parallelism",
            "0.1 A",
            (),
            "missing_local_discriminator",
        ),
        (
            "gdt_perpendicularity",
            "0.1 A",
            (),
            "missing_local_discriminator",
        ),
        (
            "gdt_flatness",
            "0.1",
            (),
            "missing_local_discriminator",
        ),
        (
            "datum_reference",
            "A B",
            (),
            "local_parse_incomplete",
        ),
        (
            "revision_marker",
            "P1 P2",
            (),
            "local_parse_incomplete",
        ),
    ),
)
def test_nine_family_near_miss_matrix_escalates(
    family: str,
    text: str,
    candidates: tuple[dict[str, object], ...],
    expected_reason: str,
) -> None:
    resolution = _resolve(family, text=_text("text-1", text), candidates=candidates)

    assert resolution.family_hypotheses == (family,)
    assert resolution.resolved_family is None
    assert route_visual_observation(resolution).disposition == "escalate"
    assert resolution.reason_codes == (expected_reason,)


@pytest.mark.parametrize(
    "family",
    (
        "diameter",
        "depth",
        "counterbore",
        "surface_roughness",
        "gdt_parallelism",
        "gdt_perpendicularity",
        "gdt_flatness",
        "datum_reference",
        "revision_marker",
    ),
)
def test_nine_family_conflict_matrix_escalates(family: str) -> None:
    candidates: tuple[dict[str, object], ...]
    text = _text("text-1", "10")
    context = None
    if family == "diameter":
        candidates = (
            _diameter_candidate(identity="diameter-1"),
            _diameter_candidate(identity="diameter-2"),
        )
    elif family == "depth":
        text = _text("text-1", "M6 深 8")
        candidates = (
            _depth_candidate(identity="depth-1"),
            _depth_candidate(identity="depth-2"),
        )
    elif family == "surface_roughness":
        text = _text("text-1", "Ra 3.2")
        candidates = (
            _coarse_candidate(
                "roughness",
                identity="roughness",
                raw_text="Ra 3.2",
            ),
            _coarse_candidate("weld", identity="weld", raw_text="Ra 3.2"),
        )
    elif family in {"datum_reference", "revision_marker"}:
        text = _text("text-1", "A", (20, 20, 26, 28))
        candidates = ()
        context = _both_reference_hypotheses_context()
    else:
        candidates = (
            _coarse_candidate(
                "geometric_tolerance",
                identity=f"{family}-1",
                raw_text="0.1 A",
            ),
            _coarse_candidate(
                "geometric_tolerance",
                identity=f"{family}-2",
                raw_text="0.2 B",
            ),
        )

    resolution = _resolve(
        family,
        text=text,
        candidates=candidates,
        context=context,
    )

    assert resolution.family_hypotheses == (family,)
    assert resolution.resolved_family is None
    assert route_visual_observation(resolution).disposition == "escalate"
    assert "local_evidence_conflict" in resolution.reason_codes


def test_missing_and_cross_page_source_never_resolve_locally() -> None:
    missing = _resolve(
        "diameter",
        candidates=(_diameter_candidate(),),
        visual=_visual(("missing-text",)),
    )
    cross_page = _resolve(
        "diameter",
        text=_text("text-1", "10", page_index=1),
        candidates=(_diameter_candidate(),),
    )

    assert route_visual_observation(missing).disposition == "block"
    assert missing.reason_codes == ("coverage_lineage_incomplete",)
    assert route_visual_observation(cross_page).disposition == "escalate"
    assert cross_page.reason_codes == ("local_evidence_conflict",)


def test_confidence_only_cannot_resolve_or_escalate() -> None:
    low = _resolve("diameter", confidence=0.0)
    high = _resolve("diameter", confidence=1.0)
    low_resolved = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(_diameter_candidate(),),
        confidence=0.0,
    )
    high_resolved = _resolve(
        "diameter",
        text=_text("text-1", "Φ10"),
        candidates=(_diameter_candidate(),),
        confidence=1.0,
    )

    assert route_visual_observation(low).disposition == "escalate"
    assert route_visual_observation(high).disposition == "escalate"
    assert low.reason_codes == high.reason_codes
    assert route_visual_observation(low_resolved).disposition == "locally_resolved"
    assert route_visual_observation(high_resolved).disposition == "locally_resolved"
    assert low_resolved.reason_codes == high_resolved.reason_codes
