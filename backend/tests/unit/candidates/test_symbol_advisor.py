from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

import app.candidates.symbol_review as symbol_review
from app.candidates.coverage import CoverageEntry
from app.candidates.local_symbol_resolution import resolve_visual_observation
from app.candidates.symbol_review import (
    ValidatedSymbolDetection,
    VisualReviewDecision,
    VisualSymbolSchemaError,
    build_visual_failure_envelope,
    group_symbol_detections,
    parse_visual_symbol_json,
    plan_visual_batches,
    project_visual_page,
    project_visual_observation,
    validate_symbol_detections,
    visual_cache_identity,
    visual_cache_key,
)
from app.pdf.schemas import PageInventory, TextObservation, VisualObservation
from app.pdf.visual_observations import (
    PROPOSAL_RULE_VERSION,
    VisualGeometryContext,
    VisualObservationBlockingError,
)
from app.processing.automatic_result import CandidateSnapshot


def test_visual_cache_identity_uses_proposal_owner_version() -> None:
    arguments = {
        "source_sha256": "a" * 64,
        "visual_observation_ids": ("visual-001",),
        "crop_bbox_pdf": (1.0, 2.0, 10.0, 20.0),
        "crop_sha256": "b" * 64,
        "model": "qwen-vl-fixture",
    }
    current = visual_cache_identity(**arguments)
    legacy = visual_cache_identity(
        **arguments,
        proposal_version="visual-observation/2",
    )

    assert PROPOSAL_RULE_VERSION == "visual-observation/3"
    assert current["proposal_version"] == PROPOSAL_RULE_VERSION
    assert legacy["proposal_version"] == "visual-observation/2"
    assert visual_cache_key(**arguments) != visual_cache_key(
        **arguments,
        proposal_version="visual-observation/2",
    )
    assert not hasattr(symbol_review, "VISUAL_PROPOSAL_VERSION")


def _payload() -> dict[str, object]:
    return {
        "schema_version": "visual-symbol-review/1",
        "detections": [
            {
                "visual_observation_id": "visual-001",
                "symbol_kind": "diameter",
                "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
                "associated_text_observation_ids": ["text-001"],
                "requires_confirmation": True,
            },
            {
                "visual_observation_id": "visual-002",
                "symbol_kind": "revision_marker",
                "bbox_normalized": [0.6, 0.5, 0.8, 0.9],
                "associated_text_observation_ids": ["text-002"],
                "requires_confirmation": True,
            },
        ],
    }


def test_visual_symbol_response_accepts_only_exact_schema() -> None:
    """ADV-01: only the frozen visual-symbol response shape crosses the port."""
    payload = _payload()
    assert parse_visual_symbol_json(payload) == payload

    invalid_payloads: list[dict[str, object]] = []
    missing = copy.deepcopy(payload)
    del missing["detections"][0]["symbol_kind"]  # type: ignore[index]
    invalid_payloads.append(missing)
    extra_root = copy.deepcopy(payload)
    extra_root["explanation"] = "not allowed"
    invalid_payloads.append(extra_root)
    extra_detection = copy.deepcopy(payload)
    extra_detection["detections"][0]["confidence"] = 0.99  # type: ignore[index]
    invalid_payloads.append(extra_detection)
    unconfirmed = copy.deepcopy(payload)
    unconfirmed["detections"][0]["requires_confirmation"] = False  # type: ignore[index]
    invalid_payloads.append(unconfirmed)

    for invalid in invalid_payloads:
        with pytest.raises(
            VisualSymbolSchemaError,
            match="^visual symbol response violates frozen schema$",
        ):
            parse_visual_symbol_json(invalid)

    private_marker = "private-marker-should-not-cross-schema-boundary"
    with pytest.raises(VisualSymbolSchemaError) as raised:
        parse_visual_symbol_json(private_marker)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert private_marker not in str(raised.value)


def test_visual_symbol_response_reports_only_safe_parser_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_marker = "private-marker-should-not-cross-parser-boundary"
    invalid_schema = _payload()
    del invalid_schema["detections"][0]["symbol_kind"]  # type: ignore[index]
    non_finite = _payload()
    non_finite["detections"][0]["bbox_normalized"][0] = float("nan")  # type: ignore[index]

    for content, expected_stage in (
        (private_marker, "json_invalid"),
        (invalid_schema, "schema_invalid"),
        (non_finite, "schema_invalid"),
    ):
        with pytest.raises(VisualSymbolSchemaError) as raised:
            parse_visual_symbol_json(content)
        assert raised.value.failure_stage == expected_stage
        assert str(raised.value) == (
            "visual symbol response violates frozen schema"
        )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert private_marker not in str(raised.value)

    local_schema_cases = (
        (None, "missing"),
        ("{", "invalid-json"),
        ('{"type": 1}', "invalid-definition"),
    )
    for schema_content, suffix in local_schema_cases:
        schema_path = tmp_path / f"visual-symbol-{suffix}.schema.json"
        if schema_content is not None:
            schema_path.write_text(schema_content, encoding="utf-8")
        monkeypatch.setattr(symbol_review, "SCHEMA_PATH", schema_path)
        with pytest.raises(VisualSymbolSchemaError) as raised:
            parse_visual_symbol_json(_payload())
        assert raised.value.failure_stage == "local_schema_invalid"
        assert str(raised.value) == (
            "visual symbol response violates frozen schema"
        )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda payload: payload["detections"][0].pop("symbol_kind"),
            {
                "schema_version": "visual-symbol-schema-diagnostic/1",
                "validator": "required",
                "instance_path": "/detections/0",
                "schema_path": "/properties/detections/items/required",
                "instance_type": "object",
                "required_member": "symbol_kind",
                "schema_sha256": (
                    "9bce6653860c2302894fa647e1f25e341"
                    "b4318d22f79770004355a353d456b7a"
                ),
            },
        ),
        (
            lambda payload: payload["detections"][0].__setitem__(
                "bbox_normalized",
                "private-bbox-value",
            ),
            {
                "schema_version": "visual-symbol-schema-diagnostic/1",
                "validator": "type",
                "instance_path": "/detections/0/bbox_normalized",
                "schema_path": (
                    "/properties/detections/items/properties/"
                    "bbox_normalized/type"
                ),
                "instance_type": "string",
                "required_member": None,
                "schema_sha256": (
                    "9bce6653860c2302894fa647e1f25e341"
                    "b4318d22f79770004355a353d456b7a"
                ),
            },
        ),
        (
            lambda payload: payload["detections"][0].__setitem__(
                "symbol_kind",
                "private-enum-value",
            ),
            {
                "schema_version": "visual-symbol-schema-diagnostic/1",
                "validator": "enum",
                "instance_path": "/detections/0/symbol_kind",
                "schema_path": (
                    "/properties/detections/items/properties/symbol_kind/enum"
                ),
                "instance_type": "string",
                "required_member": None,
                "schema_sha256": (
                    "9bce6653860c2302894fa647e1f25e341"
                    "b4318d22f79770004355a353d456b7a"
                ),
            },
        ),
        (
            lambda payload: payload["detections"][0].__setitem__(
                "private-property-name",
                "private-property-value",
            ),
            {
                "schema_version": "visual-symbol-schema-diagnostic/1",
                "validator": "additionalProperties",
                "instance_path": "/detections/0",
                "schema_path": (
                    "/properties/detections/items/additionalProperties"
                ),
                "instance_type": "object",
                "required_member": None,
                "schema_sha256": (
                    "9bce6653860c2302894fa647e1f25e341"
                    "b4318d22f79770004355a353d456b7a"
                ),
            },
        ),
    ),
)
def test_visual_symbol_schema_diagnostic_is_exact_and_content_free(
    mutate,
    expected: dict[str, object],
) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(VisualSymbolSchemaError) as raised:
        parse_visual_symbol_json(payload)

    assert raised.value.failure_stage == "schema_invalid"
    assert raised.value.diagnostic == expected
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    serialized = repr(raised.value.diagnostic)
    assert "private-" not in serialized
    assert str(raised.value) == (
        "visual symbol response violates frozen schema"
    )


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("instance_path", "/detections/0/private-marker"),
        ("instance_path", "/detections/١"),
        ("schema_path", "/properties/private-marker"),
        ("required_member", "private-marker"),
        ("schema_sha256", int("1" * 64)),
        ("validator", "type"),
    ),
)
def test_visual_symbol_schema_diagnostic_rejects_untrusted_or_inconsistent_content(
    field: str,
    unsafe_value: object,
) -> None:
    diagnostic = {
        "schema_version": "visual-symbol-schema-diagnostic/1",
        "validator": "required",
        "instance_path": "/detections/0",
        "schema_path": "/properties/detections/items/required",
        "instance_type": "object",
        "required_member": "symbol_kind",
        "schema_sha256": (
            "9bce6653860c2302894fa647e1f25e341"
            "b4318d22f79770004355a353d456b7a"
        ),
    }
    diagnostic[field] = unsafe_value

    with pytest.raises(
        ValueError,
        match="^visual symbol schema diagnostic is invalid$",
    ) as raised:
        VisualSymbolSchemaError(
            failure_stage="schema_invalid",
            diagnostic=diagnostic,
        )

    assert "private-marker" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_visual_symbol_failure_envelope_is_exact_and_allowlisted() -> None:
    assert build_visual_failure_envelope(
        "tool_arguments_schema_invalid"
    ) == {
        "schema_version": "visual-symbol-call-failure/2",
        "error_code": "visual_schema_invalid",
        "failure_stage": "tool_arguments_schema_invalid",
    }

    private_marker = "private-marker-not-an-allowlisted-stage"
    with pytest.raises(ValueError) as raised:
        build_visual_failure_envelope(private_marker)
    assert str(raised.value) == "visual symbol failure stage is invalid"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert private_marker not in str(raised.value)


def test_visual_symbol_response_rejects_invalid_identity_or_shape() -> None:
    """ADV-02: local identity, geometry, cardinality and duplicate rules fail closed."""
    payload = _payload()
    payload["detections"] = [
        payload["detections"][0],  # type: ignore[index]
        copy.deepcopy(payload["detections"][0]),  # type: ignore[index]
        {
            "visual_observation_id": "unknown-visual",
            "symbol_kind": "diameter",
            "bbox_normalized": [0.1, 0.2, 0.3, 0.4],
            "associated_text_observation_ids": ["text-001"],
            "requires_confirmation": True,
        },
        {
            "visual_observation_id": "visual-002",
            "symbol_kind": "depth",
            "bbox_normalized": [0.4, 0.4, 0.4, 0.6],
            "associated_text_observation_ids": ["text-002"],
            "requires_confirmation": True,
        },
        {
            "visual_observation_id": "visual-002",
            "symbol_kind": "counterbore",
            "bbox_normalized": [0.5, 0.5, 0.7, 0.7],
            "associated_text_observation_ids": ["unknown-text"],
            "requires_confirmation": True,
        },
    ]
    unchanged = copy.deepcopy(payload)
    accepted, rejected = validate_symbol_detections(
        parse_visual_symbol_json(payload),
        visual_observation_ids=("visual-001", "visual-002"),
        text_allowlists={
            "visual-001": ("text-001",),
            "visual-002": ("text-002",),
        },
        crop_bbox_pdf=(10.0, 20.0, 110.0, 220.0),
    )

    assert len(accepted) == 1
    assert accepted[0].visual_observation_id == "visual-001"
    assert accepted[0].bbox_pdf == (20.0, 60.0, 40.0, 100.0)
    assert {item.rejection_code for item in rejected} == {
        "visual_bbox_invalid",
        "visual_source_mismatch",
        "visual_duplicate_detection",
    }
    assert payload == unchanged

    overflow = _payload()
    overflow["detections"] = [
        {
            "visual_observation_id": "visual-001",
            "symbol_kind": "diameter",
            "bbox_normalized": [0.1 * index, 0.1, 0.1 * index + 0.05, 0.2],
            "associated_text_observation_ids": ["text-001"],
            "requires_confirmation": True,
        }
        for index in range(5)
    ]
    accepted, rejected = validate_symbol_detections(
        parse_visual_symbol_json(overflow),
        visual_observation_ids=("visual-001",),
        text_allowlists={"visual-001": ("text-001",)},
        crop_bbox_pdf=(0.0, 0.0, 100.0, 100.0),
    )
    assert accepted == ()
    assert len(rejected) == 5
    assert {item.rejection_code for item in rejected} == {
        "visual_source_mismatch"
    }

    for field, value in (
        ("bbox_normalized", [-0.1, 0.1, 0.2, 0.3]),
        ("symbol_kind", "unknown"),
    ):
        invalid = _payload()
        invalid["detections"][0][field] = value  # type: ignore[index]
        with pytest.raises(VisualSymbolSchemaError):
            parse_visual_symbol_json(invalid)


def _text(
    identity: str,
    raw_text: str,
    bbox: tuple[float, float, float, float],
) -> TextObservation:
    return TextObservation(
        identity,
        "native",
        "line",
        raw_text,
        raw_text,
        0,
        bbox,
        tuple(value / 200 for value in bbox),
        (1.0, 0.0),
        0.0,
        None,
    )


def _visual(
    identity: str,
    bbox: tuple[float, float, float, float],
    associated: tuple[str, ...],
) -> VisualObservation:
    return VisualObservation(
        identity,
        "visual",
        "annotation_context",
        0,
        bbox,
        tuple(value / 200 for value in bbox),
        "text_adjacent_vector_context",
        "a" * 64,
        associated,
    )


def _page(
    texts: tuple[TextObservation, ...],
    visuals: tuple[VisualObservation, ...],
) -> PageInventory:
    return PageInventory(
        0,
        200,
        200,
        0,
        "vector",
        "native",
        "supported",
        False,
        None,
        1.0,
        "fixture/1",
        {},
        (1, 0, 0, 1, 0, 0),
        (1, 0, 0, 1, 0, 0),
        texts,
        visuals,
    )


def _snapshot(
    page: PageInventory,
    *,
    candidates: tuple[dict[str, object], ...] = (),
) -> CandidateSnapshot:
    candidate_source_ids = {
        str(source_id)
        for candidate in candidates
        for source_id in candidate.get("source_location_ids", ())  # type: ignore[union-attr]
    }
    text_entries = tuple(
        CoverageEntry(
            item.observation_id,
            (
                "candidate"
                if item.observation_id in candidate_source_ids
                else "ambiguous"
            ),
            item.observation_id,
            item.bbox_pdf,
            candidate_id=(
                str(candidates[0]["candidate_id"])
                if item.observation_id in candidate_source_ids
                else None
            ),
            requires_confirmation=item.observation_id in candidate_source_ids,
        )
        for item in page.observations
    )
    visual_entries = tuple(
        CoverageEntry(
            item.observation_id,
            "ambiguous",
            item.observation_id,
            item.bbox_pdf,
            requires_confirmation=True,
        )
        for item in page.visual_observations
    )
    return CandidateSnapshot(
        candidates,
        (*text_entries, *visual_entries),
        tuple(item.observation_id for item in page.observations)
        + tuple(item.observation_id for item in page.visual_observations),
        (),
        required_visual_observation_ids=tuple(
            item.observation_id for item in page.visual_observations
        ),
    )


def _decision(
    page: PageInventory,
    kinds: tuple[str, ...],
    *,
    context: VisualGeometryContext | None = None,
) -> VisualReviewDecision:
    visual = page.visual_observations[0]
    detections = tuple(
        {
            "visual_observation_id": visual.observation_id,
            "symbol_kind": kind,
            "bbox_pdf": visual.bbox_pdf,
            "associated_text_observation_ids": visual.associated_text_observation_ids,
        }
        for kind in kinds
    )
    return project_visual_observation(
        observation=visual,
        detections=detections,
        text_observations=page.observations,
        candidates=(),
        geometry_context=context,
    )


def test_diameter_enriches_existing_candidate() -> None:
    """ADV-03: diameter preserves source identity while enriching semantics."""
    text = _text("text-1", "10", (20, 20, 32, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("text-1",))
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "10",
            "coordinates": text.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "nominal": "10",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["text-1"],
    }
    detection = {
        "visual_observation_id": "visual-1",
        "symbol_kind": "diameter",
        "bbox_pdf": visual.bbox_pdf,
        "associated_text_observation_ids": ("text-1",),
    }

    decision = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(text,),
        candidates=(existing,),
        geometry_context=None,
    )

    assert decision.candidate_id == "candidate-original"
    assert decision.candidate_envelope is not None
    payload = decision.candidate_envelope["payload"]
    assert payload["raw_text"] == "10"
    assert payload["normalized_text"] == "Φ10"
    assert payload["feature_kind"] == "unknown"
    assert payload["requires_confirmation"] is True
    assert decision.source_location_ids == ("visual-1", "text-1")
    assert decision.coordinates == (12, 18, 32, 28)


def test_diameter_existing_nominal_conflict_preserves_candidate() -> None:
    text = _text("text-1", "10", (20, 20, 32, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("text-1",))
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "11",
            "coordinates": text.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "nominal": "11",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["text-1"],
    }
    frozen = copy.deepcopy(existing)

    decision = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "diameter",
                "bbox_pdf": visual.bbox_pdf,
                "associated_text_observation_ids": ("text-1",),
            },
        ),
        text_observations=(text,),
        candidates=(existing,),
        geometry_context=None,
    )

    assert decision.disposition == "ambiguous"
    assert decision.rejection_code == "visual_projection_conflict"
    assert decision.candidate_envelope is None
    assert existing == frozen


def test_candidate_coordinates_exclude_visual_context_bbox() -> None:
    text = _text("text-1", "10", (40, 12, 48, 18))
    visual = _visual("visual-1", (10, 10, 50, 30), ("text-1",))

    decision = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "diameter",
                "bbox_pdf": (12, 12, 16, 18),
                "associated_text_observation_ids": ("text-1",),
            },
        ),
        text_observations=(text,),
        candidates=(),
        geometry_context=None,
    )

    assert decision.disposition == "candidate"
    assert decision.source_location_ids == ("visual-1", "text-1")
    assert decision.coordinates == (12, 12, 48, 18)


def test_depth_uses_same_crop_typed_value_or_stays_ambiguous() -> None:
    """ADV-04: depth uses one typed value and never guesses conflicts."""
    orphan = _text("orphan", "深 8", (20, 20, 36, 28))
    orphan_visual = _visual(
        "visual-orphan",
        (12, 18, 18, 28),
        ("orphan",),
    )
    orphan_decision = _decision(
        _page((orphan,), (orphan_visual,)),
        ("depth",),
    )
    assert orphan_decision.disposition == "ambiguous"
    assert orphan_decision.rejection_code == "visual_local_parse_failed"

    single = _text("single", "M6 深 8", (20, 40, 52, 48))
    single_visual = _visual(
        "visual-single",
        (12, 38, 18, 48),
        ("single",),
    )
    single_decision = _decision(
        _page((single,), (single_visual,)),
        ("depth",),
    )
    assert single_decision.candidate_envelope is not None
    single_payload = single_decision.candidate_envelope["payload"]
    assert single_payload["item_type"] == "thread"
    assert single_payload["thread_depth"] == "8"

    primary = _text("primary", "M6", (20, 60, 36, 68))
    modifier = _text("modifier", "深 8", (20, 70, 36, 78))
    multiline_visual = _visual(
        "visual-multiline",
        (12, 58, 18, 78),
        ("primary", "modifier"),
    )
    multiline_decision = _decision(
        _page((primary, modifier), (multiline_visual,)),
        ("depth",),
    )
    assert multiline_decision.candidate_envelope is not None
    multiline_payload = multiline_decision.candidate_envelope["payload"]
    assert multiline_payload["item_type"] == "composite"
    assert [
        (item["order"], item["kind"])
        for item in multiline_payload["sub_requirements"]
    ] == [(0, "thread"), (1, "depth")]

    second = _text("second", "深 9", (38, 20, 54, 28))
    conflict_visual = _visual(
        "visual-conflict",
        (12, 18, 18, 28),
        ("orphan", "second"),
    )
    conflict_page = _page((orphan, second), (conflict_visual,))
    conflict = _decision(conflict_page, ("depth",))
    assert conflict.disposition == "ambiguous"
    assert conflict.rejection_code == "visual_projection_conflict"

    combined_text = _text("text-3", "10 深 8", (20, 40, 52, 48))
    combined_page = _page(
        (combined_text,),
        (_visual("visual-3", (12, 38, 18, 48), ("text-3",)),),
    )
    combined = _decision(combined_page, ("diameter", "depth"))
    assert combined.candidate_envelope is not None
    assert combined.candidate_envelope["payload"]["depth"] == "8"


def test_exact_duplicate_span_is_canonicalized_to_its_parent_line() -> None:
    line = _text("line", "10", (20, 20, 32, 28))
    span = replace(
        _text("span", "10", (20, 20, 32, 28)),
        observation_level="span",
        parent_region_id="line",
    )
    visual = _visual(
        "visual-1",
        (12, 18, 18, 28),
        ("line", "span"),
    )

    decision = _decision(
        _page((line, span), (visual,)),
        ("diameter",),
    )

    assert decision.disposition == "candidate"
    assert decision.candidate_envelope is not None
    assert decision.source_location_ids == ("visual-1", "line")
    assert decision.candidate_envelope["payload"]["normalized_text"] == "Φ10"

    distinct_span = replace(span, raw_text="11", normalized_text="11")
    conflict = _decision(
        _page((line, distinct_span), (visual,)),
        ("diameter",),
    )
    assert conflict.disposition == "ambiguous"
    assert conflict.rejection_code == "visual_projection_conflict"


def test_visual_depth_enriches_only_one_strong_overlapping_typed_primary() -> None:
    value_line = _text("value-line", "8", (30, 12, 38, 20))
    value_span = replace(
        _text("value-span", "8", (30, 12, 38, 20)),
        observation_level="span",
        parent_region_id="value-line",
    )
    primary = _text("thread-primary", "M6", (12, 12, 28, 20))
    incidental = _text("thread-incidental", "M8", (48, 12, 60, 20))
    foreign = replace(
        _text("thread-foreign", "M10", (14, 12, 26, 20)),
        page_index=1,
    )
    visual = _visual(
        "visual-1",
        (10, 10, 50, 30),
        ("value-line", "value-span"),
    )
    candidates = (
        {
            "candidate_id": "thread-owner",
            "payload": {
                "candidate_id": "thread-owner",
                "item_type": "thread",
                "raw_text": "M6",
                "normalized_text": "M6",
                "coordinates": primary.bbox_pdf,
                "scope": "local_feature",
                "thread_spec": "M6",
                "sub_requirements": [],
                "balloon_required": True,
                "requires_confirmation": False,
            },
            "source_location_ids": ["thread-primary"],
        },
        {
            "candidate_id": "thread-incidental",
            "payload": {
                "candidate_id": "thread-incidental",
                "item_type": "thread",
                "raw_text": "M8",
                "normalized_text": "M8",
                "coordinates": incidental.bbox_pdf,
                "scope": "local_feature",
                "thread_spec": "M8",
                "sub_requirements": [],
                "balloon_required": True,
                "requires_confirmation": False,
            },
            "source_location_ids": ["thread-incidental"],
        },
        {
            "candidate_id": "thread-foreign",
            "payload": {
                "candidate_id": "thread-foreign",
                "item_type": "thread",
                "raw_text": "M10",
                "normalized_text": "M10",
                "coordinates": foreign.bbox_pdf,
                "scope": "local_feature",
                "thread_spec": "M10",
                "sub_requirements": [],
                "balloon_required": True,
                "requires_confirmation": False,
            },
            "source_location_ids": ["thread-foreign"],
        },
    )
    detection = {
        "visual_observation_id": "visual-1",
        "symbol_kind": "depth",
        "bbox_pdf": (28, 12, 30, 20),
        "associated_text_observation_ids": ("value-line", "value-span"),
    }

    decision = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(
            primary,
            value_line,
            value_span,
            incidental,
            foreign,
        ),
        candidates=candidates,
        geometry_context=None,
    )

    assert decision.disposition == "candidate"
    assert decision.candidate_id == "thread-owner"
    assert decision.candidate_envelope is not None
    payload = decision.candidate_envelope["payload"]
    assert payload["raw_text"] == "M6"
    assert payload["normalized_text"] == "M6 深 8"
    assert payload["thread_depth"] == "8"
    assert decision.source_location_ids == (
        "visual-1",
        "thread-primary",
        "value-line",
    )

    second_strong = copy.deepcopy(candidates[1])
    second_strong["payload"]["coordinates"] = (14, 12, 26, 20)
    ambiguous = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(
            primary,
            value_line,
            value_span,
            incidental,
            foreign,
        ),
        candidates=(candidates[0], second_strong),
        geometry_context=None,
    )
    assert ambiguous.disposition == "ambiguous"
    assert ambiguous.rejection_code == "visual_projection_conflict"
    assert ambiguous.candidate_envelope is None

    threshold_primary = _text(
        "threshold-primary",
        "M6",
        (0, 10, 20, 30),
    )
    exact_threshold = copy.deepcopy(candidates[0])
    exact_threshold["payload"]["coordinates"] = threshold_primary.bbox_pdf
    exact_threshold["source_location_ids"] = ["threshold-primary"]
    accepted_at_threshold = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(threshold_primary, value_line, value_span),
        candidates=(exact_threshold,),
        geometry_context=None,
    )
    assert accepted_at_threshold.disposition == "candidate"
    assert accepted_at_threshold.candidate_id == "thread-owner"

    missing_source = copy.deepcopy(candidates[0])
    missing_source["source_location_ids"] = ["missing"]
    rejected_missing_source = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(primary, value_line, value_span),
        candidates=(missing_source,),
        geometry_context=None,
    )
    assert rejected_missing_source.disposition == "ambiguous"
    assert (
        rejected_missing_source.rejection_code
        == "visual_local_parse_failed"
    )


@pytest.mark.parametrize(
    ("item_type", "owner_text", "expected_field"),
    (
        ("thread", "M6", "thread_depth"),
        ("diameter_dimension", "10", "depth"),
        ("composite", "⌴10", None),
    ),
)
def test_visual_only_depth_value_enriches_direct_unique_typed_primary(
    item_type: str,
    owner_text: str,
    expected_field: str | None,
) -> None:
    owner = _text("owner", owner_text, (12, 12, 28, 20))
    value = _text("value", "8", (30, 12, 38, 20))
    visual = _visual("visual-1", (10, 10, 40, 30), ("owner", "value"))
    payload: dict[str, object] = {
        "candidate_id": "candidate-original",
        "item_type": item_type,
        "raw_text": owner_text,
        "normalized_text": owner_text,
        "coordinates": owner.bbox_pdf,
        "scope": "local_feature",
        "sub_requirements": [],
        "balloon_required": True,
        "requires_confirmation": False,
    }
    if item_type == "thread":
        payload["thread_spec"] = "M6"
    elif item_type == "diameter_dimension":
        payload["nominal"] = "10"
    else:
        payload["sub_requirements"] = [
            {
                "order": 0,
                "kind": "diameter_dimension",
                "raw_text": "10",
                "nominal": "10",
            }
        ]
    existing = {
        "candidate_id": "candidate-original",
        "payload": payload,
        "source_location_ids": ["owner"],
    }
    detection = {
        "visual_observation_id": "visual-1",
        "symbol_kind": "depth",
        "bbox_pdf": visual.bbox_pdf,
        "associated_text_observation_ids": ("owner", "value"),
    }

    decision = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(owner, value),
        candidates=(existing,),
        geometry_context=None,
    )

    assert decision.disposition == "candidate"
    assert decision.candidate_id == "candidate-original"
    assert decision.candidate_envelope is not None
    projected = decision.candidate_envelope["payload"]
    assert projected["raw_text"] == owner_text
    assert projected["normalized_text"] == f"{owner_text} 深 8"
    if expected_field is not None:
        assert projected[expected_field] == "8"
    else:
        assert projected["sub_requirements"][-1] == {
            "order": 1,
            "kind": "depth",
            "raw_text": "深8",
            "value": "8",
        }


def test_equivalent_existing_depth_is_not_duplicated_in_normalized_text() -> None:
    owner = _text("owner", "M6", (12, 12, 28, 20))
    value = _text("value", "8", (30, 12, 38, 20))
    visual = _visual("visual-1", (10, 10, 40, 30), ("owner", "value"))
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "thread",
            "raw_text": "M6",
            "normalized_text": "M6 深 8.0",
            "coordinates": owner.bbox_pdf,
            "scope": "local_feature",
            "thread_spec": "M6",
            "thread_depth": "8.0",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["owner"],
    }

    decision = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "depth",
                "bbox_pdf": visual.bbox_pdf,
                "associated_text_observation_ids": ("owner", "value"),
            },
        ),
        text_observations=(owner, value),
        candidates=(existing,),
        geometry_context=None,
    )

    assert decision.disposition == "candidate"
    assert decision.candidate_envelope is not None
    assert (
        decision.candidate_envelope["payload"]["normalized_text"]
        == "M6 深 8.0"
    )


def test_multiline_diameter_depth_reuses_composite_for_new_and_existing() -> None:
    primary = _text("primary", "10", (20, 20, 36, 28))
    depth = _text("depth", "深 8", (20, 30, 36, 38))
    visual = _visual(
        "visual-1",
        (12, 18, 18, 38),
        ("primary", "depth"),
    )
    page = _page((primary, depth), (visual,))

    projected = _decision(page, ("diameter", "depth"))
    assert projected.candidate_envelope is not None
    projected_payload = projected.candidate_envelope["payload"]
    assert projected_payload["item_type"] == "composite"
    assert projected_payload["raw_text"] == "10\n深 8"
    assert projected_payload["normalized_text"] == "Φ10\n深 8"
    assert [
        (item["order"], item["kind"], item["raw_text"])
        for item in projected_payload["sub_requirements"]
    ] == [
        (0, "diameter_dimension", "10"),
        (1, "depth", "深 8"),
    ]

    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "10",
            "coordinates": primary.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "nominal": "10",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["primary"],
    }
    detection = tuple(
        {
            "visual_observation_id": "visual-1",
            "symbol_kind": kind,
            "bbox_pdf": visual.bbox_pdf,
            "associated_text_observation_ids": ("primary", "depth"),
        }
        for kind in ("diameter", "depth")
    )
    enriched = project_visual_observation(
        observation=visual,
        detections=detection,
        text_observations=(primary, depth),
        candidates=(existing,),
        geometry_context=None,
    )
    assert enriched.candidate_id == "candidate-original"
    assert enriched.candidate_envelope is not None
    assert enriched.candidate_envelope["payload"]["item_type"] == "composite"

    mismatched = copy.deepcopy(existing)
    mismatched["payload"].update(
        item_type="diameter_dimension",
        feature_kind="unknown",
        depth="9",
    )
    frozen = copy.deepcopy(mismatched)
    conflict = project_visual_observation(
        observation=visual,
        detections=detection,
        text_observations=(primary, depth),
        candidates=(mismatched,),
        geometry_context=None,
    )
    assert conflict.disposition == "ambiguous"
    assert conflict.rejection_code == "visual_projection_conflict"
    assert mismatched == frozen


@pytest.mark.parametrize(
    ("item_type", "depth_field"),
    (
        ("diameter_dimension", "depth"),
        ("thread", "thread_depth"),
    ),
)
def test_depth_enriches_the_existing_typed_field_without_shape_drift(
    item_type: str,
    depth_field: str,
) -> None:
    depth = _text("depth", "深 8", (20, 20, 36, 28))
    owner = _text("owner", "M6" if item_type == "thread" else "10", (40, 20, 52, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("depth", "owner"))
    original = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": item_type,
            "raw_text": owner.raw_text,
            "normalized_text": owner.raw_text,
            "coordinates": owner.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["owner"],
    }
    if item_type == "thread":
        original["payload"]["thread_spec"] = "M6"  # type: ignore[index]
    else:
        original["payload"]["nominal"] = "10"  # type: ignore[index]
    frozen = copy.deepcopy(original)
    decision = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "depth",
                "bbox_pdf": visual.bbox_pdf,
                "associated_text_observation_ids": ("depth", "owner"),
            },
        ),
        text_observations=(depth, owner),
        candidates=(original,),
        geometry_context=None,
    )
    assert original == frozen
    assert decision.candidate_envelope is not None
    assert decision.candidate_envelope["payload"][depth_field] == "8"
    other_field = "depth" if depth_field == "thread_depth" else "thread_depth"
    assert other_field not in decision.candidate_envelope["payload"]

    mismatched = copy.deepcopy(original)
    mismatched["payload"][depth_field] = "9"
    mismatch_frozen = copy.deepcopy(mismatched)
    rejected = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "depth",
                "bbox_pdf": visual.bbox_pdf,
                "associated_text_observation_ids": ("depth", "owner"),
            },
        ),
        text_observations=(depth, owner),
        candidates=(mismatched,),
        geometry_context=None,
    )
    assert rejected.disposition == "ambiguous"
    assert rejected.rejection_code == "visual_projection_conflict"
    assert rejected.candidate_envelope is None
    assert mismatched == mismatch_frozen


def test_depth_preserves_existing_composite_subrequirements() -> None:
    depth = _text("depth", "深 8", (20, 20, 36, 28))
    owner = _text("owner", "⌴10", (40, 20, 52, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("depth", "owner"))
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "composite",
            "raw_text": "⌴10",
            "normalized_text": "⌴10",
            "coordinates": owner.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "sub_requirements": [
                {
                    "order": 0,
                    "kind": "diameter_dimension",
                    "raw_text": "10",
                    "nominal": "10",
                }
            ],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["owner"],
    }
    decision = project_visual_observation(
        observation=visual,
        detections=(
            {
                "visual_observation_id": "visual-1",
                "symbol_kind": "depth",
                "bbox_pdf": visual.bbox_pdf,
                "associated_text_observation_ids": ("depth", "owner"),
            },
        ),
        text_observations=(depth, owner),
        candidates=(existing,),
        geometry_context=None,
    )
    payload = decision.candidate_envelope["payload"]  # type: ignore[index]
    assert [item["kind"] for item in payload["sub_requirements"]] == [
        "diameter_dimension",
        "depth",
    ]
    assert payload["sub_requirements"][0] == existing["payload"]["sub_requirements"][0]  # type: ignore[index]


def test_existing_sources_use_local_allowlist_not_provider_subset() -> None:
    owner = _text("owner", "10", (20, 20, 32, 28))
    depth = _text("depth", "深 8", (20, 30, 36, 38))
    visual = _visual(
        "visual-1",
        (12, 18, 18, 38),
        ("owner", "depth"),
    )
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "composite",
            "raw_text": "10\n深 8",
            "normalized_text": "Φ10\n深 8",
            "coordinates": (20, 20, 36, 38),
            "scope": "local_feature",
            "quantity": None,
            "sub_requirements": [
                {
                    "order": 0,
                    "kind": "diameter_dimension",
                    "raw_text": "10",
                    "nominal": "10",
                },
                {
                    "order": 1,
                    "kind": "depth",
                    "raw_text": "深 8",
                    "value": "8",
                },
            ],
            "balloon_required": True,
            "requires_confirmation": True,
        },
        "source_location_ids": ["owner", "depth"],
    }
    detection = {
        "visual_observation_id": "visual-1",
        "symbol_kind": "depth",
        "bbox_pdf": (12, 24, 18, 34),
        "associated_text_observation_ids": ("depth",),
    }

    projected = project_visual_observation(
        observation=visual,
        detections=(detection,),
        text_observations=(owner, depth),
        candidates=(existing,),
        geometry_context=None,
    )

    assert projected.disposition == "candidate"
    assert projected.candidate_id == "candidate-original"
    assert projected.source_location_ids == (
        "visual-1",
        "owner",
        "depth",
    )
    assert projected.coordinates == (12, 20, 36, 38)

    outside_context = replace(
        visual,
        associated_text_observation_ids=("depth",),
    )
    rejected = project_visual_observation(
        observation=outside_context,
        detections=(detection,),
        text_observations=(owner, depth),
        candidates=(existing,),
        geometry_context=None,
    )

    assert rejected.disposition == "ambiguous"
    assert rejected.rejection_code == "visual_projection_conflict"
    assert rejected.candidate_envelope is None


def test_counterbore_maps_to_stable_composite() -> None:
    """ADV-05: counterbore is the existing ordered composite shape."""
    diameter = _text("text-1", "10", (20, 20, 32, 28))
    depth = _text("text-2", "深 8", (20, 30, 36, 38))
    page = _page(
        (diameter, depth),
        (_visual("visual-1", (12, 18, 18, 38), ("text-1", "text-2")),),
    )
    decision = _decision(page, ("counterbore", "diameter", "depth"))
    payload = decision.candidate_envelope["payload"]  # type: ignore[index]
    assert payload["item_type"] == "composite"
    assert payload["normalized_text"].startswith("⌴")
    assert [item["order"] for item in payload["sub_requirements"]] == [0, 1]
    assert [item["kind"] for item in payload["sub_requirements"]] == [
        "diameter_dimension",
        "depth",
    ]

    compact = _text("text-compact", "22 6", (20, 50, 44, 58))
    compact_page = _page(
        (compact,),
        (_visual("visual-compact", (12, 48, 18, 58), ("text-compact",)),),
    )
    compact_decision = _decision(
        compact_page,
        ("counterbore", "diameter", "depth"),
    )
    compact_payload = compact_decision.candidate_envelope["payload"]  # type: ignore[index]
    assert compact_payload["item_type"] == "composite"
    assert compact_payload["normalized_text"] == "⌴22 6"
    assert [
        item.get("nominal", item.get("value"))
        for item in compact_payload["sub_requirements"]
    ] == ["22", "6"]

    full_width = _text("text-full-width", "２２　   ６", (20, 60, 44, 68))
    full_width_page = _page(
        (full_width,),
        (
            _visual(
                "visual-full-width",
                (12, 58, 18, 68),
                ("text-full-width",),
            ),
        ),
    )
    full_width_decision = _decision(
        full_width_page,
        ("counterbore", "diameter", "depth"),
    )
    full_width_payload = full_width_decision.candidate_envelope["payload"]  # type: ignore[index]
    assert full_width_payload["normalized_text"] == "⌴22 6"


def test_counterbore_existing_conflict_preserves_candidate() -> None:
    diameter = _text("primary", "10", (20, 20, 32, 28))
    old_depth = _text("old-depth", "深 9", (20, 30, 36, 38))
    new_depth = _text("new-depth", "深 8", (20, 40, 36, 48))
    visual = _visual(
        "visual-1",
        (12, 18, 18, 48),
        ("primary", "new-depth"),
    )
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "composite",
            "raw_text": "10\n深 9",
            "normalized_text": "⌴10\n深 9",
            "coordinates": (20, 20, 36, 38),
            "scope": "local_feature",
            "quantity": None,
            "sub_requirements": [
                {
                    "order": 0,
                    "kind": "diameter_dimension",
                    "raw_text": "10",
                    "nominal": "10",
                    "feature_kind": "unknown",
                },
                {
                    "order": 1,
                    "kind": "depth",
                    "raw_text": "深 9",
                    "value": "9",
                },
            ],
            "balloon_required": True,
            "requires_confirmation": True,
        },
        "source_location_ids": ["primary", "old-depth"],
    }
    detections = tuple(
        {
            "visual_observation_id": "visual-1",
            "symbol_kind": kind,
            "bbox_pdf": visual.bbox_pdf,
            "associated_text_observation_ids": (
                "primary",
                "new-depth",
            ),
        }
        for kind in ("counterbore", "diameter", "depth")
    )
    frozen = copy.deepcopy(existing)

    conflict = project_visual_observation(
        observation=visual,
        detections=detections,
        text_observations=(diameter, old_depth, new_depth),
        candidates=(existing,),
        geometry_context=None,
    )

    assert conflict.disposition == "ambiguous"
    assert conflict.rejection_code == "visual_projection_conflict"
    assert conflict.candidate_envelope is None
    assert existing == frozen

    same_source_mismatch = copy.deepcopy(existing)
    same_source_mismatch["source_location_ids"] = [
        "primary",
        "new-depth",
    ]
    same_source_frozen = copy.deepcopy(same_source_mismatch)
    mismatched = project_visual_observation(
        observation=visual,
        detections=detections,
        text_observations=(diameter, new_depth),
        candidates=(same_source_mismatch,),
        geometry_context=None,
    )

    assert mismatched.disposition == "ambiguous"
    assert mismatched.rejection_code == "visual_projection_conflict"
    assert mismatched.candidate_envelope is None
    assert same_source_mismatch == same_source_frozen

    compatible = copy.deepcopy(existing)
    compatible["payload"]["raw_text"] = "10\n深 8"
    compatible["payload"]["normalized_text"] = "⌴10\n深 8"
    compatible["payload"]["sub_requirements"][1].update(
        raw_text="深 8",
        value="8",
    )
    compatible["source_location_ids"] = ["primary", "new-depth"]
    projected = project_visual_observation(
        observation=visual,
        detections=detections,
        text_observations=(diameter, new_depth),
        candidates=(compatible,),
        geometry_context=None,
    )

    assert projected.disposition == "candidate"
    assert projected.candidate_id == "candidate-original"
    assert projected.candidate_envelope is not None


def test_surface_roughness_maps_to_four_field_coarse_candidate() -> None:
    """ADV-06: roughness projection stays inside the coarse public shape."""
    text = _text("text-1", "Ra 3.2", (20, 20, 48, 28))
    page = _page((text,), (_visual("visual-1", (12, 18, 18, 28), ("text-1",)),))
    decision = _decision(page, ("surface_roughness",))
    payload = decision.candidate_envelope["payload"]  # type: ignore[index]
    assert set(payload) == {
        "raw_text",
        "coordinates",
        "coarse_type",
        "requires_confirmation",
    }
    assert payload["raw_text"] == "Ra 3.2"
    assert payload["coarse_type"] == "roughness"


def test_roughness_decimal_distinctness_and_duplicate_sources() -> None:
    line = _text("line", "Ra 3.2", (20, 20, 48, 28))
    span = _text("span", "Ra 3.2", (20, 20, 48, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("line", "span"))
    duplicate = _decision(
        _page((span, line), (visual,)),
        ("surface_roughness",),
    )
    assert duplicate.candidate_envelope is not None
    assert duplicate.candidate_envelope["payload"]["raw_text"] == (
        "Ra 3.2\nRa 3.2"
    )

    for raw_text in ("Ra", "Ra 3.2 6.3"):
        text = _text("text", raw_text, (20, 20, 64, 28))
        rejected = _decision(
            _page(
                (text,),
                (_visual("visual", (12, 18, 18, 28), ("text",)),),
            ),
            ("surface_roughness",),
        )
        assert rejected.disposition == "ambiguous"
        assert rejected.rejection_code == "visual_local_parse_failed"


@pytest.mark.parametrize(
    ("kind", "symbol"),
    (
        ("gdt_parallelism", "∥"),
        ("gdt_perpendicularity", "⊥"),
        ("gdt_flatness", "⏥"),
    ),
)
def test_gdt_kinds_map_to_four_field_coarse_candidate(
    kind: str,
    symbol: str,
) -> None:
    """ADV-07: each GD&T kind maps to one frozen coarse candidate."""
    tolerance = _text("text-1", "0.1", (20, 20, 32, 28))
    datum = _text("text-2", "A", (34, 20, 40, 28))
    page = _page(
        (tolerance, datum),
        (_visual("visual-1", (12, 18, 18, 28), ("text-1", "text-2")),),
    )
    decision = _decision(page, (kind,))
    payload = decision.candidate_envelope["payload"]  # type: ignore[index]
    assert set(payload) == {
        "raw_text",
        "coordinates",
        "coarse_type",
        "requires_confirmation",
    }
    assert payload["raw_text"] == f"{symbol} 0.1\nA"


def test_gdt_combined_line_and_duplicate_sources_extract_ascii_tokens() -> None:
    combined = _text("combined", "0.1 A", (20, 20, 52, 28))
    visual = _visual("visual-1", (12, 18, 18, 28), ("combined",))
    projected = _decision(
        _page((combined,), (visual,)),
        ("gdt_parallelism",),
    )
    assert projected.candidate_envelope is not None
    assert projected.candidate_envelope["payload"]["raw_text"] == "∥ 0.1 A"

    duplicate = _text("duplicate", "0.1 A", (20, 20, 52, 28))
    duplicate_visual = replace(
        visual,
        associated_text_observation_ids=("combined", "duplicate"),
    )
    deduplicated = _decision(
        _page((duplicate, combined), (duplicate_visual,)),
        ("gdt_parallelism",),
    )
    assert deduplicated.candidate_envelope is not None
    assert deduplicated.candidate_envelope["payload"]["raw_text"] == (
        "∥ 0.1 A\n0.1 A"
    )

    conflicting = _text(
        "conflicting",
        "0.1 0.2 A",
        (20, 20, 72, 28),
    )
    conflict = _decision(
        _page(
            (conflicting,),
            (_visual("visual-2", (12, 18, 18, 28), ("conflicting",)),),
        ),
        ("gdt_parallelism",),
    )
    assert conflict.disposition == "ambiguous"
    assert conflict.rejection_code == "visual_projection_conflict"

    invalid_datum = _text(
        "invalid-datum",
        "0.1 AB",
        (20, 20, 72, 28),
    )
    invalid = _decision(
        _page(
            (invalid_datum,),
            (_visual("visual-3", (12, 18, 18, 28), ("invalid-datum",)),),
        ),
        ("gdt_parallelism",),
    )
    assert invalid.disposition == "ambiguous"
    assert invalid.rejection_code == "visual_local_parse_failed"


@pytest.mark.parametrize(
    ("kinds", "raw_text"),
    (
        (("diameter",), "not-a-number"),
        (("counterbore", "diameter", "depth"), "10"),
        (("gdt_parallelism",), "A"),
    ),
)
def test_valid_kind_set_with_missing_local_value_is_local_parse_failed(
    kinds: tuple[str, ...],
    raw_text: str,
) -> None:
    text = _text("text", raw_text, (20, 20, 72, 28))
    decision = _decision(
        _page(
            (text,),
            (_visual("visual", (12, 18, 18, 28), ("text",)),),
        ),
        kinds,
    )

    assert decision.disposition == "ambiguous"
    assert decision.rejection_code == "visual_local_parse_failed"


def test_gdt_accepts_duplicate_source_with_one_distinct_tolerance() -> None:
    texts = (
        _text("text-1", "0.1", (20, 20, 32, 28)),
        _text("text-2", "0.1", (34, 20, 46, 28)),
        _text("text-3", "A", (48, 20, 54, 28)),
    )
    page = _page(
        texts,
        (_visual("visual-1", (12, 18, 18, 28), tuple(item.observation_id for item in texts)),),
    )
    decision = _decision(page, ("gdt_parallelism",))
    assert decision.candidate_envelope is not None
    assert decision.candidate_envelope["payload"]["raw_text"] == (
        "∥ 0.1\n0.1\nA"
    )


def test_reference_revision_and_no_detection_dispositions() -> None:
    """ADV-08: local geometry separates reference, revision and ambiguity."""
    datum_text = _text("text-1", "A", (20, 20, 26, 28))
    datum_visual = _visual("visual-1", (18, 18, 28, 30), ("text-1",))
    datum_page = _page((datum_text,), (datum_visual,))
    rect = b'{"coordinates":["18","18","28","30"],"opcode":"re","orientation":1,"style":{}}'
    datum_context = VisualGeometryContext(
        "visual-1", 0, "a" * 64, datum_text.bbox_pdf, ((18, 18, 28, 30),), (rect,)
    )
    datum = _decision(datum_page, ("datum_reference",), context=datum_context)
    assert datum.disposition == "reference_context"
    assert datum.requires_confirmation is False
    assert datum.candidate_id is None

    revision_text = _text("text-2", "P1", (20, 20, 28, 28))
    revision_visual = _visual("visual-2", (12, 12, 28, 28), ("text-2",))
    revision_page = _page((revision_text,), (revision_visual,))
    lines = tuple(
        (
            '{"coordinates":[["%s","%s"],["%s","%s"]],"opcode":"l","style":{}}'
            % values
        ).encode()
        for values in (
            (12, 28, 20, 12),
            (20, 12, 28, 28),
            (28, 28, 12, 28),
        )
    )
    revision_context = VisualGeometryContext(
        "visual-2", 0, "a" * 64, revision_text.bbox_pdf, ((12, 12, 28, 28),), lines
    )
    revision = _decision(
        revision_page,
        ("revision_marker",),
        context=revision_context,
    )
    assert revision.disposition == "non_inspection"
    assert revision.requires_confirmation is True

    invalid_revision = _decision(
        revision_page,
        ("revision_marker",),
        context=replace(revision_context, canonical_path_items=lines[:2]),
    )
    assert invalid_revision.disposition == "ambiguous"
    assert invalid_revision.rejection_code == "visual_local_parse_failed"

    invalid_lines = (
        (
            (12, 28, 20, 12),
            (20, 12, 28, 28),
            (40, 40, 48, 48),
        ),
        (
            (12, 12, 20, 12),
            (20, 12, 28, 12),
            (28, 12, 12, 12),
        ),
        (
            (12, 28, 12, 28),
            (20, 12, 28, 28),
            (28, 28, 12, 28),
        ),
    )
    for segments in invalid_lines:
        malformed = tuple(
            (
                '{"coordinates":[["%s","%s"],["%s","%s"]],'
                '"opcode":"l","style":{}}' % values
            ).encode()
            for values in segments
        )
        rejected = _decision(
            revision_page,
            ("revision_marker",),
            context=replace(
                revision_context,
                canonical_path_items=malformed,
            ),
        )
        assert rejected.disposition == "ambiguous"
        assert rejected.rejection_code == "visual_local_parse_failed"

    no_detection = _decision(revision_page, ())
    assert no_detection.disposition == "ambiguous"
    assert no_detection.rejection_code == "visual_no_detection"


def test_datum_accepts_one_line_built_box_among_unrelated_lines() -> None:
    token = _text("datum", "A", (20, 20, 26, 28))
    visual = _visual("visual-1", (18, 18, 28, 30), ("datum",))
    page = _page((token,), (visual,))
    line_box = tuple(
        (
            '{"coordinates":[["%s","%s"],["%s","%s"]],'
            '"opcode":"l","style":{}}' % values
        ).encode()
        for values in (
            (18, 18, 28, 18),
            (28, 18, 28, 30),
            (28, 30, 18, 30),
            (18, 30, 18, 18),
            (30, 30, 36, 36),
        )
    )
    context = VisualGeometryContext(
        "visual-1",
        0,
        "a" * 64,
        token.bbox_pdf,
        ((18, 18, 28, 30),),
        line_box,
    )

    decision = _decision(page, ("datum_reference",), context=context)

    assert decision.disposition == "reference_context"
    assert decision.requires_confirmation is False

    second_box = tuple(
        (
            '{"coordinates":[["%s","%s"],["%s","%s"]],'
            '"opcode":"l","style":{}}' % values
        ).encode()
        for values in (
            (16, 16, 30, 16),
            (30, 16, 30, 32),
            (30, 32, 16, 32),
            (16, 32, 16, 16),
        )
    )
    ambiguous = _decision(
        page,
        ("datum_reference",),
        context=replace(
            context,
            canonical_path_items=(*line_box, *second_box),
        ),
    )
    assert ambiguous.disposition == "ambiguous"
    assert ambiguous.rejection_code == "visual_local_parse_failed"

    for invalid_box in (
        line_box[:3],
        tuple(
            (
                '{"coordinates":[["%s","%s"],["%s","%s"]],'
                '"opcode":"l","style":{}}' % values
            ).encode()
            for values in (
                (18, 24, 23, 18),
                (23, 18, 28, 24),
                (28, 24, 23, 30),
                (23, 30, 18, 24),
            )
        ),
    ):
        rejected = _decision(
            page,
            ("datum_reference",),
            context=replace(
                context,
                canonical_path_items=invalid_box,
            ),
        )
        assert rejected.disposition == "ambiguous"
        assert rejected.rejection_code == "visual_local_parse_failed"

    duplicate = _text("datum-duplicate", "A", (21, 20, 27, 28))
    duplicate_visual = replace(
        visual,
        associated_text_observation_ids=("datum", "datum-duplicate"),
    )
    duplicate_token = _decision(
        _page((token, duplicate), (duplicate_visual,)),
        ("datum_reference",),
        context=context,
    )
    assert duplicate_token.disposition == "ambiguous"
    assert duplicate_token.rejection_code == "visual_local_parse_failed"


def test_revision_selects_one_triangle_among_unrelated_lines() -> None:
    token = _text("token", "P1", (20, 20, 28, 28))
    visual = _visual("visual-1", (12, 12, 28, 28), ("token",))
    page = _page((token,), (visual,))
    triangle = tuple(
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
    unrelated = (
        b'{"coordinates":[["40","40"],["48","48"]],"opcode":"l","style":{}}',
    )
    context = VisualGeometryContext(
        "visual-1",
        0,
        "a" * 64,
        token.bbox_pdf,
        ((12, 12, 28, 28),),
        (*triangle, *unrelated),
    )

    decision = _decision(page, ("revision_marker",), context=context)

    assert decision.disposition == "non_inspection"
    assert decision.requires_confirmation is True

    second_triangle = tuple(
        (
            '{"coordinates":[["%s","%s"],["%s","%s"]],'
            '"opcode":"l","style":{}}' % values
        ).encode()
        for values in (
            (10, 30, 20, 10),
            (20, 10, 30, 30),
            (30, 30, 10, 30),
        )
    )
    ambiguous = _decision(
        page,
        ("revision_marker",),
        context=replace(
            context,
            canonical_path_items=(*triangle, *second_triangle),
        ),
    )
    assert ambiguous.disposition == "ambiguous"
    assert ambiguous.rejection_code == "visual_local_parse_failed"

    n5 = _text("n5", "N5", (40, 40, 48, 48))
    n5_visual = replace(
        visual,
        associated_text_observation_ids=("n5",),
    )
    n5_without_inner_token = _decision(
        _page((n5,), (n5_visual,)),
        ("revision_marker",),
        context=context,
    )
    assert n5_without_inner_token.disposition == "ambiguous"
    assert (
        n5_without_inner_token.rejection_code
        == "visual_local_parse_failed"
    )


def test_revision_uses_token_bbox_center_for_triangle_margin() -> None:
    token = _text("token", "P1", (18, 14, 32, 22))
    visual = _visual("visual-1", (12, 12, 32, 28), ("token",))
    page = _page((token,), (visual,))
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
    context = VisualGeometryContext(
        "visual-1",
        0,
        "a" * 64,
        token.bbox_pdf,
        ((12, 12, 28, 28),),
        lines,
    )

    decision = _decision(
        page,
        ("revision_marker",),
        context=context,
    )

    assert decision.disposition == "non_inspection"
    assert decision.rejection_code is None


def test_nonoverlap_same_kind_is_conflict_in_both_input_orders() -> None:
    text = _text("text-1", "10", (40, 10, 52, 20))
    visual = _visual("visual-1", (10, 10, 30, 20), ("text-1",))
    detections = (
        ValidatedSymbolDetection(
            "visual-1",
            "diameter",
            (10, 10, 18, 20),
            ("text-1",),
        ),
        ValidatedSymbolDetection(
            "visual-1",
            "diameter",
            (22, 10, 30, 20),
            ("text-1",),
        ),
    )

    decisions = tuple(
        project_visual_observation(
            observation=visual,
            detections=ordered,
            text_observations=(text,),
            candidates=(),
            geometry_context=None,
        )
        for ordered in (detections, tuple(reversed(detections)))
    )

    assert decisions[0] == decisions[1]
    assert decisions[0].disposition == "ambiguous"
    assert decisions[0].symbol_kinds == ("diameter",)
    assert decisions[0].rejection_code == "visual_projection_conflict"


def test_multiple_existing_candidate_projections_merge_or_conflict_stably() -> None:
    owner = _text("owner", "10", (40, 10, 52, 20))
    existing = {
        "candidate_id": "candidate-original",
        "payload": {
            "candidate_id": "candidate-original",
            "item_type": "linear_dimension",
            "raw_text": "10",
            "normalized_text": "10",
            "coordinates": owner.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "nominal": "10",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["owner"],
    }
    compatible_visuals = (
        _visual("visual-1", (10, 10, 18, 20), ("owner",)),
        _visual("visual-2", (22, 10, 30, 20), ("owner",)),
    )
    compatible_detections = tuple(
        ValidatedSymbolDetection(
            visual.observation_id,
            "diameter",
            visual.bbox_pdf,
            ("owner",),
        )
        for visual in compatible_visuals
    )

    compatible = project_visual_page(
        visual_observations=compatible_visuals,
        detections=compatible_detections,
        rejection_codes={},
        text_observations=(owner,),
        candidates=(existing,),
        geometry_contexts={},
    )
    compatible_reversed = project_visual_page(
        visual_observations=tuple(reversed(compatible_visuals)),
        detections=tuple(reversed(compatible_detections)),
        rejection_codes={},
        text_observations=(owner,),
        candidates=(existing,),
        geometry_contexts={},
    )
    assert compatible == compatible_reversed
    assert sum(
        decision.candidate_envelope is not None
        for decision in compatible
    ) == 1
    assert all(
        decision.source_location_ids == ("visual-1", "visual-2", "owner")
        and decision.coordinates == (10, 10, 52, 20)
        for decision in compatible
    )

    depth_eight = _text("depth-8", "深 8", (40, 24, 52, 32))
    depth_nine = _text("depth-9", "深 9", (40, 36, 52, 44))
    diameter_existing = copy.deepcopy(existing)
    diameter_existing["payload"]["item_type"] = "diameter_dimension"
    diameter_existing["payload"]["feature_kind"] = "unknown"
    conflict_visuals = (
        _visual("visual-3", (10, 24, 18, 32), ("owner", "depth-8")),
        _visual("visual-4", (22, 36, 30, 44), ("owner", "depth-9")),
    )
    conflict_detections = tuple(
        ValidatedSymbolDetection(
            visual.observation_id,
            "depth",
            visual.bbox_pdf,
            tuple(visual.associated_text_observation_ids),
        )
        for visual in conflict_visuals
    )

    conflict = project_visual_page(
        visual_observations=conflict_visuals,
        detections=conflict_detections,
        rejection_codes={},
        text_observations=(owner, depth_eight, depth_nine),
        candidates=(diameter_existing,),
        geometry_contexts={},
    )
    conflict_reversed = project_visual_page(
        visual_observations=tuple(reversed(conflict_visuals)),
        detections=tuple(reversed(conflict_detections)),
        rejection_codes={},
        text_observations=(owner, depth_eight, depth_nine),
        candidates=(diameter_existing,),
        geometry_contexts={},
    )
    assert conflict == conflict_reversed
    assert all(
        decision.disposition == "ambiguous"
        and decision.candidate_envelope is None
        and decision.rejection_code == "visual_projection_conflict"
        for decision in conflict
    )


def test_nonfirst_local_projection_merges_with_same_page_vlm_decision() -> None:
    owner = _text("owner", "Φ10", (40, 10, 52, 20))
    unrelated = {
        "candidate_id": "candidate-unrelated",
        "payload": {
            "candidate_id": "candidate-unrelated",
            "item_type": "linear_dimension",
            "raw_text": "5",
            "normalized_text": "5",
            "coordinates": owner.bbox_pdf,
            "scope": "local_feature",
            "quantity": None,
            "nominal": "5",
            "sub_requirements": [],
            "balloon_required": True,
            "requires_confirmation": False,
        },
        "source_location_ids": ["other"],
    }
    target = copy.deepcopy(unrelated)
    target["candidate_id"] = "candidate-target"
    target["payload"].update(
        {
            "candidate_id": "candidate-target",
            "item_type": "diameter_dimension",
            "raw_text": "Φ10",
            "normalized_text": "Φ10",
            "nominal": "10",
            "feature_kind": "unknown",
        }
    )
    target["source_location_ids"] = ["owner"]
    local_visual = _visual("visual-local", (10, 10, 18, 20), ("owner",))
    vlm_visual = _visual("visual-vlm", (22, 10, 30, 20), ("owner",))
    local = resolve_visual_observation(
        observation=local_visual,
        family_hypotheses=("diameter",),
        text_observations=(owner,),
        candidates=(unrelated, target),
        geometry_context=None,
    )
    assert local.projection is not None
    assert local.projection.existing_candidate_index == 1

    decisions = project_visual_page(
        visual_observations=(local_visual, vlm_visual),
        detections=(
            ValidatedSymbolDetection(
                vlm_visual.observation_id,
                "diameter",
                vlm_visual.bbox_pdf,
                ("owner",),
            ),
        ),
        rejection_codes={},
        text_observations=(owner,),
        candidates=(unrelated, target),
        geometry_contexts={},
        local_decisions=(local.projection,),
    )

    assert all(
        decision.existing_candidate_index == 1
        and decision.candidate_id == "candidate-target"
        and decision.source_location_ids
        == ("visual-local", "visual-vlm", "owner")
        for decision in decisions
    )
    assert sum(
        decision.candidate_envelope is not None for decision in decisions
    ) == 1


def test_rejected_detection_preserves_accepted_symbol_kinds() -> None:
    text = _text("text-1", "10", (24, 10, 36, 20))
    visual = _visual("visual-1", (10, 10, 20, 20), ("text-1",))
    detection = ValidatedSymbolDetection(
        "visual-1",
        "diameter",
        visual.bbox_pdf,
        ("text-1",),
    )

    decisions = project_visual_page(
        visual_observations=(visual,),
        detections=(detection,),
        rejection_codes={"visual-1": "visual_duplicate_detection"},
        text_observations=(text,),
        candidates=(),
        geometry_contexts={},
    )

    assert len(decisions) == 1
    assert decisions[0].disposition == "ambiguous"
    assert decisions[0].symbol_kinds == ("diameter",)
    assert decisions[0].rejection_code == "visual_duplicate_detection"


def test_cross_batch_overlap_grouping_is_order_independent() -> None:
    detections = (
        ValidatedSymbolDetection(
            "visual-2",
            "diameter",
            (11.0, 10.0, 21.0, 20.0),
            ("text-2",),
        ),
        ValidatedSymbolDetection(
            "visual-1",
            "diameter",
            (10.0, 10.0, 20.0, 20.0),
            ("text-1",),
        ),
        ValidatedSymbolDetection(
            "visual-3",
            "diameter",
            (12.1, 10.0, 22.1, 20.0),
            ("text-3",),
        ),
    )
    forward = group_symbol_detections(detections)
    reverse = group_symbol_detections(tuple(reversed(detections)))
    assert forward == reverse
    assert len(forward) == 1
    assert forward[0].visual_observation_ids == (
        "visual-1",
        "visual-2",
        "visual-3",
    )
    assert forward[0].detection.associated_text_observation_ids == (
        "text-1",
        "text-2",
        "text-3",
    )


def test_page_projection_unions_cross_batch_visual_sources() -> None:
    text = _text("text-1", "10", (24, 10, 36, 20))
    visuals = (
        _visual("visual-1", (10, 10, 20, 20), ("text-1",)),
        _visual("visual-2", (11, 10, 21, 20), ("text-1",)),
    )
    detections = (
        ValidatedSymbolDetection(
            "visual-2",
            "diameter",
            (11, 10, 21, 20),
            ("text-1",),
        ),
        ValidatedSymbolDetection(
            "visual-1",
            "diameter",
            (10, 10, 20, 20),
            ("text-1",),
        ),
    )
    decisions = project_visual_page(
        visual_observations=visuals,
        detections=detections,
        rejection_codes={},
        text_observations=(text,),
        candidates=(),
        geometry_contexts={},
    )
    reversed_decisions = project_visual_page(
        visual_observations=tuple(reversed(visuals)),
        detections=tuple(reversed(detections)),
        rejection_codes={},
        text_observations=(text,),
        candidates=(),
        geometry_contexts={},
    )
    assert decisions == reversed_decisions
    assert len(decisions) == 2
    assert decisions[0].candidate_envelope is not None
    assert decisions[1].candidate_envelope is None
    assert decisions[0].source_location_ids == (
        "visual-1",
        "visual-2",
        "text-1",
    )
    assert decisions[0].candidate_id == decisions[1].candidate_id


def test_unified_scheduler_is_deterministic_and_blocks_visual_overflow() -> None:
    """ADV-09: visual priority is deterministic and the hard budget fails closed."""
    texts = (
        _text("parser-failed", "10??", (10, 10, 20, 18)),
        _text("confirmed", "10", (10, 40, 20, 48)),
        _text("other", "note", (10, 70, 20, 78)),
    )
    visuals = tuple(
        _visual(
            f"visual-{index}",
            (30 + index * 30, 10, 40 + index * 30, 20),
            (text.observation_id,),
        )
        for index, text in enumerate(texts)
    ) + (
        replace(
            _visual("visual-kind-z", (120, 10, 130, 20), ("other",)),
            proposal_kind="z-kind",
        ),
        replace(
            _visual("visual-tie-b", (120, 10, 130, 20), ("other",)),
            proposal_kind="a-kind",
        ),
        replace(
            _visual("visual-tie-a", (120, 10, 130, 20), ("other",)),
            proposal_kind="a-kind",
        ),
    )
    page = _page(texts, visuals)
    candidate = {
        "candidate_id": "candidate-confirmed",
        "payload": {"requires_confirmation": True},
        "source_location_ids": ["confirmed"],
    }
    snapshot = _snapshot(page, candidates=(candidate,))

    first = plan_visual_batches((page,), snapshot)
    second = plan_visual_batches((page,), snapshot)
    assert first == second
    assert tuple(
        observation_id
        for batch in first[0]
        for observation_id in batch.observation_ids
    ) == (
        "visual-0",
        "visual-1",
        "visual-2",
        "visual-tie-a",
        "visual-tie-b",
        "visual-kind-z",
    )

    overflow = tuple(
        _visual(
            f"v-{index}",
            (index * 1000.0, 10, index * 1000.0 + 3, 13),
            (),
        )
        for index in range(17)
    )
    wide_page = replace(page, width=17000, visual_observations=overflow)
    with pytest.raises(
        VisualObservationBlockingError,
        match="symbol_route_budget_exhausted",
    ):
        plan_visual_batches((wide_page,), _snapshot(wide_page))
