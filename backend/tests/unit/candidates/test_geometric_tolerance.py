from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.candidates.gdt_evidence import GdtCellEvidence, GdtFrameEvidence
from app.candidates.geometric_tolerance import (
    DatumReference,
    GdtFrame,
    GdtModifier,
    GdtSegment,
    GeometricToleranceNormalizer,
    GeometricToleranceCandidate,
)
from app.pdf.gdt_frames import GdtCellObservation, GdtFrameObservation


def _frame_observation() -> GdtFrameObservation:
    return GdtFrameObservation(
        observation_id="frame-case-a",
        page_index=0,
        bbox_pdf=(10.0, 10.0, 90.0, 30.0),
        bbox_normalized=(0.1, 0.1, 0.9, 0.3),
        cells=(
            GdtCellObservation(0, (10.0, 10.0, 35.0, 30.0), (0.1, 0.1, 0.35, 0.3)),
            GdtCellObservation(1, (35.0, 10.0, 65.0, 30.0), (0.35, 0.1, 0.65, 0.3)),
            GdtCellObservation(2, (65.0, 10.0, 90.0, 30.0), (0.65, 0.1, 0.9, 0.3)),
        ),
        associated_text_observation_ids=("value-a", "datum-a"),
        proposal_source="native_vector",
        proposal_state="complete",
        geometry_sha256="a" * 64,
    )


def _evidence(*, modifier: str | None = None) -> GdtFrameEvidence:
    cells = [
        GdtCellEvidence(
            cell_index=0,
            cell_role="symbol",
            bbox_normalized=(0.1, 0.1, 0.35, 0.3),
            raw_token="⌖" if modifier is not None else "∥",
            confidence_signal=0.97,
        ),
        GdtCellEvidence(
            cell_index=1,
            cell_role="tolerance",
            bbox_normalized=(0.35, 0.1, 0.65, 0.3),
            raw_token="0.1",
            associated_text_observation_ids=("value-a",),
            confidence_signal=0.97,
        ),
    ]
    if modifier is not None:
        cells.append(
            GdtCellEvidence(
                cell_index=len(cells),
                cell_role="modifier",
                bbox_normalized=(0.65, 0.1, 0.78, 0.3),
                raw_token=modifier,
                confidence_signal=0.8,
            )
        )
    else:
        cells.append(
            GdtCellEvidence(
                cell_index=2,
                cell_role="datum",
                bbox_normalized=(0.65, 0.1, 0.9, 0.3),
                raw_token="A",
                associated_text_observation_ids=("datum-a",),
                confidence_signal=0.96,
            )
        )
    return GdtFrameEvidence(
        frame_observation_id="frame-case-a",
        frame_bbox_normalized=(0.1, 0.1, 0.9, 0.3),
        tolerance_type_signal="parallelism" if modifier is None else "position",
        cells=tuple(cells),
        confidence_signal=0.95,
    )


def test_normalizer_builds_parallelism_with_datum_a() -> None:
    result = GeometricToleranceNormalizer().normalize(
        evidence=_evidence(),
        observation=_frame_observation(),
        evidence_ref="asset://fixtures/gdt/case-a-evidence.json",
    )

    assert isinstance(result, GeometricToleranceCandidate)
    assert result.tolerance_type == "parallelism"
    assert result.tolerance_value == Decimal("0.1")
    assert [datum.datum for datum in result.datum_references] == ["A"]


def test_unknown_modifier_fails_closed_without_coarse_candidate() -> None:
    result = GeometricToleranceNormalizer().normalize(
        evidence=_evidence(modifier="P"),
        observation=_frame_observation(),
        evidence_ref="asset://fixtures/gdt/unknown-modifier.json",
    )

    assert result.code == "gdt_modifier_unknown"
    assert result.typed_unknown is not None
    assert result.typed_unknown.item_type == "geometric_tolerance"
    assert result.typed_unknown.tolerance_type == "unknown"


def test_parallelism_candidate_derives_first_segment_fields() -> None:
    frame = GdtFrame(
        segments=(
            GdtSegment(
                tolerance_value=Decimal("0.1"),
                diameter_modifier=False,
                modifiers=(),
                datum_references=(DatumReference(datum="A", modifiers=()),),
            ),
        )
    )
    candidate = GeometricToleranceCandidate.from_frames(
        candidate_id="case-a",
        raw_text="∥ | 0.1 | A",
        tolerance_type="parallelism",
        frames=(frame,),
        coordinates=(659.5, 388.89, 721.3, 428.49),
        source_location_ids=("visual-a", "value-a", "datum-a"),
        evidence_ref="asset://fixtures/gdt/case-a.json",
    )
    assert candidate.tolerance_symbol == "∥"
    assert candidate.tolerance_value == Decimal("0.1")
    assert [item.datum for item in candidate.datum_references] == ["A"]
    assert candidate.normalized_text == "∥ | 0.1 | A"


def test_flatness_alias_serializes_to_canonical_symbol() -> None:
    candidate = GeometricToleranceCandidate.from_frames(
        candidate_id="case-b",
        raw_text="▱ | 0.08",
        tolerance_type="flatness",
        frames=(
            GdtFrame(
                segments=(
                    GdtSegment(
                        tolerance_value=Decimal("0.08"),
                        diameter_modifier=False,
                        modifiers=(),
                        datum_references=(),
                    ),
                )
            ),
        ),
        coordinates=(667.2, 388.89, 726.3, 428.49),
        source_location_ids=("visual-b", "value-b"),
        evidence_ref="asset://fixtures/gdt/case-b.json",
    )
    assert candidate.tolerance_symbol == "⏥"
    assert candidate.normalized_text == "⏥ | 0.08"


def test_modifier_and_datum_order_are_not_set_normalized() -> None:
    segment = GdtSegment(
        tolerance_value=Decimal("0.05"),
        diameter_modifier=True,
        modifiers=(GdtModifier(kind="maximum_material_condition", raw_symbol="M"),),
        datum_references=(
            DatumReference(datum="C", modifiers=()),
            DatumReference(datum="A", modifiers=()),
            DatumReference(datum="B", modifiers=()),
        ),
    )
    assert [item.datum for item in segment.datum_references] == ["C", "A", "B"]


def test_legacy_unknown_preserves_raw_text_without_guessing_frames() -> None:
    candidate = GeometricToleranceCandidate.from_legacy_unknown(
        candidate_id="legacy",
        raw_text="∥ 0.1",
        coordinates=(1.0, 2.0, 3.0, 4.0),
        source_location_ids=("legacy-source",),
    )
    assert candidate.tolerance_type == "unknown"
    assert candidate.frames == ()
    assert candidate.tolerance_value is None
    assert candidate.normalized_text == "∥ 0.1"


def test_direct_construction_rejects_mismatched_derived_fields() -> None:
    frame = GdtFrame(
        segments=(
            GdtSegment(
                tolerance_value=Decimal("0.1"),
                diameter_modifier=False,
            ),
        )
    )
    with pytest.raises(ValidationError):
        GeometricToleranceCandidate(
            candidate_id="mismatch",
            raw_text="∥ | 0.1",
            normalized_text="∥ | 0.2",
            tolerance_type="parallelism",
            tolerance_symbol="∥",
            tolerance_value=Decimal("0.2"),
            diameter_modifier=False,
            modifiers=(),
            datum_references=(),
            frames=(frame,),
            coordinates=(1.0, 2.0, 3.0, 4.0),
            source_location_ids=("source",),
            evidence_ref="asset://fixtures/gdt/mismatch.json",
        )


def test_direct_construction_rejects_empty_frames() -> None:
    with pytest.raises(ValidationError):
        GeometricToleranceCandidate(
            candidate_id="empty",
            raw_text="unknown",
            normalized_text="unknown",
            tolerance_type="unknown",
            tolerance_symbol=None,
            tolerance_value=None,
            diameter_modifier=False,
            modifiers=(),
            datum_references=(),
            frames=(),
            coordinates=(1.0, 2.0, 3.0, 4.0),
            source_location_ids=("source",),
            evidence_ref="asset://fixtures/gdt/empty.json",
        )


def test_negative_tolerance_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GdtSegment(
            tolerance_value=Decimal("-0.1"),
            diameter_modifier=False,
        )


def test_extra_modifier_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GdtModifier(kind="maximum_material_condition", raw_symbol="M", extra="x")
