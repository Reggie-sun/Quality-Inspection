from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from app.candidates.gdt_evidence import GdtFrameEvidence
    from app.pdf.gdt_frames import GdtFrameObservation


ToleranceType = Literal[
    "straightness",
    "flatness",
    "circularity",
    "cylindricity",
    "profile_of_line",
    "profile_of_surface",
    "angularity",
    "perpendicularity",
    "parallelism",
    "position",
    "concentricity_or_coaxiality",
    "symmetry",
    "circular_runout",
    "total_runout",
    "unknown",
]

GdtModifierKind = Literal[
    "maximum_material_condition",
    "least_material_condition",
    "regardless_of_feature_size",
    "unknown",
]

StandardContext = Literal["unspecified"]

_SYMBOL_BY_TOLERANCE_TYPE: dict[str, str] = {
    "straightness": "⏤",
    "flatness": "⏥",
    "circularity": "○",
    "cylindricity": "⌭",
    "profile_of_line": "⌒",
    "profile_of_surface": "⌓",
    "angularity": "∠",
    "perpendicularity": "⊥",
    "parallelism": "∥",
    "position": "⌖",
    "concentricity_or_coaxiality": "◎",
    "symmetry": "⌯",
    "circular_runout": "↗",
    "total_runout": "⌰",
}
_LEGACY_UNKNOWN_CONTEXT = "allow_legacy_unknown"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GdtModifier(_FrozenModel):
    kind: GdtModifierKind
    raw_symbol: str = Field(min_length=1)


class DatumReference(_FrozenModel):
    datum: str = Field(pattern=r"^[A-Z]$")
    modifiers: tuple[GdtModifier, ...] = ()


class GdtSegment(_FrozenModel):
    tolerance_value: Decimal = Field(gt=0)
    diameter_modifier: bool
    modifiers: tuple[GdtModifier, ...] = ()
    datum_references: tuple[DatumReference, ...] = ()

    @field_validator("tolerance_value", mode="before")
    @classmethod
    def reject_binary_float(cls, value: object) -> object:
        if isinstance(value, (bool, float)):
            raise ValueError("tolerance_value must be an exact decimal")
        return value


class GdtFrame(_FrozenModel):
    segments: tuple[GdtSegment, ...] = Field(min_length=1)


@dataclass(frozen=True)
class GdtNormalizationFailure:
    code: str
    typed_unknown: GeometricToleranceCandidate


def _dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _evidence_raw_text(evidence: Any) -> str:
    tokens = tuple(
        cell.raw_token.strip()
        for cell in evidence.cells
        if cell.cell_role != "separator" and cell.raw_token.strip()
    )
    return " | ".join(tokens) or "unknown geometric tolerance"


def _tolerance_symbol(raw_token: str) -> tuple[ToleranceType, str] | None:
    token = raw_token.strip()
    if token in {"▱", "⏥"}:
        return "flatness", "⏥"
    for tolerance_type, symbol in _SYMBOL_BY_TOLERANCE_TYPE.items():
        if token == symbol:
            return tolerance_type, symbol
    return None


def _modifier(raw_symbol: str) -> GdtModifier | None:
    kinds = {
        "M": "maximum_material_condition",
        "L": "least_material_condition",
        "S": "regardless_of_feature_size",
    }
    kind = kinds.get(raw_symbol.strip())
    return (
        None
        if kind is None
        else GdtModifier(kind=kind, raw_symbol=raw_symbol.strip())
    )


def _exact_decimal(raw_value: str) -> tuple[Decimal, bool] | None:
    token = raw_value.strip().replace("∅", "⌀").replace("Ø", "⌀")
    diameter_modifier = token.startswith("⌀")
    if diameter_modifier:
        token = token[1:].strip()
    if not token:
        return None
    try:
        value = Decimal(token)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value, diameter_modifier


class GeometricToleranceNormalizer:
    """Own the only business-semantic projection from validated GDT evidence."""

    def normalize(
        self,
        *,
        evidence: GdtFrameEvidence | tuple[GdtFrameEvidence, ...],
        observation: GdtFrameObservation | tuple[GdtFrameObservation, ...],
        evidence_ref: str,
    ) -> GeometricToleranceCandidate | GdtNormalizationFailure:
        evidence_frames = (
            evidence if isinstance(evidence, tuple) else (evidence,)
        )
        observations = (
            observation if isinstance(observation, tuple) else (observation,)
        )
        if not evidence_frames or len(evidence_frames) != len(observations):
            return self._failure(
                code="gdt_composite_truncated",
                evidence_frames=evidence_frames,
                observations=observations,
                evidence_ref=evidence_ref,
            )

        segments: list[GdtSegment] = []
        raw_parts: list[str] = []
        tolerance_type: ToleranceType | None = None
        for frame_evidence in evidence_frames:
            raw_parts.append(_evidence_raw_text(frame_evidence))
            parsed = self._segment(frame_evidence)
            if isinstance(parsed, str):
                return self._failure(
                    code=parsed,
                    evidence_frames=evidence_frames,
                    observations=observations,
                    evidence_ref=evidence_ref,
                )
            segment, frame_type = parsed
            if tolerance_type is None:
                tolerance_type = frame_type
            elif frame_type != tolerance_type:
                return self._failure(
                    code="gdt_projection_conflict",
                    evidence_frames=evidence_frames,
                    observations=observations,
                    evidence_ref=evidence_ref,
                )
            segments.append(segment)

        assert tolerance_type is not None
        frames = tuple(GdtFrame(segments=(segment,)) for segment in segments)
        source_ids = self._source_ids(evidence_frames, observations)
        from app.candidates.schemas import stable_candidate_id

        return GeometricToleranceCandidate.from_frames(
            candidate_id=stable_candidate_id(
                "geometric-tolerance",
                *(
                    frame.frame_observation_id
                    for frame in evidence_frames
                ),
                evidence_ref,
            ),
            raw_text=" / ".join(raw_parts),
            tolerance_type=tolerance_type,
            frames=frames,
            coordinates=observations[0].bbox_pdf,
            source_location_ids=source_ids,
            evidence_ref=evidence_ref,
        )

    def _segment(
        self,
        evidence: GdtFrameEvidence,
    ) -> tuple[GdtSegment, ToleranceType] | str:
        cells = tuple(
            cell for cell in evidence.cells if cell.cell_role != "separator"
        )
        if len(cells) < 2 or cells[0].cell_role != "symbol":
            return "gdt_symbol_unknown"
        symbol_cells = tuple(cell for cell in cells if cell.cell_role == "symbol")
        if len(symbol_cells) != 1:
            return "gdt_projection_conflict"
        symbol = _tolerance_symbol(symbol_cells[0].raw_token)
        if symbol is None or evidence.tolerance_type_signal == "unknown":
            return "gdt_symbol_unknown"
        tolerance_type, _ = symbol
        if tolerance_type != evidence.tolerance_type_signal:
            return "gdt_projection_conflict"
        if cells[1].cell_role != "tolerance":
            return "gdt_value_missing"
        parsed_value = _exact_decimal(cells[1].raw_token)
        if parsed_value is None:
            return "gdt_value_missing"
        tolerance_value, diameter_modifier = parsed_value
        modifiers: list[GdtModifier] = []
        datum_references: list[DatumReference] = []
        seen_datum = False
        for cell in cells[2:]:
            if cell.cell_role == "modifier":
                if seen_datum:
                    return "gdt_projection_conflict"
                if cell.raw_token.strip() in {"⌀", "∅", "Ø"}:
                    diameter_modifier = True
                    continue
                modifier = _modifier(cell.raw_token)
                if modifier is None:
                    return "gdt_modifier_unknown"
                modifiers.append(modifier)
                continue
            if cell.cell_role != "datum":
                return "gdt_projection_conflict"
            seen_datum = True
            datum = cell.raw_token.strip()
            if re.fullmatch(r"[A-Z]", datum) is None:
                return "gdt_datum_association_ambiguous"
            datum_references.append(DatumReference(datum=datum))
        return (
            GdtSegment(
                tolerance_value=tolerance_value,
                diameter_modifier=diameter_modifier,
                modifiers=tuple(modifiers),
                datum_references=tuple(datum_references),
            ),
            tolerance_type,
        )

    @staticmethod
    def _source_ids(
        evidence_frames: tuple[GdtFrameEvidence, ...],
        observations: tuple[GdtFrameObservation, ...],
    ) -> tuple[str, ...]:
        values: list[str] = []
        for frame_evidence, observation in zip(
            evidence_frames,
            observations,
            strict=True,
        ):
            values.extend(
                (
                    frame_evidence.frame_observation_id,
                    *observation.associated_text_observation_ids,
                    *(
                        source_id
                        for cell in frame_evidence.cells
                        for source_id in cell.associated_text_observation_ids
                    ),
                )
            )
        return _dedupe_preserving_order(tuple(values))

    def _failure(
        self,
        *,
        code: str,
        evidence_frames: tuple[GdtFrameEvidence, ...],
        observations: tuple[GdtFrameObservation, ...],
        evidence_ref: str,
    ) -> GdtNormalizationFailure:
        raw_text = (
            " / ".join(_evidence_raw_text(item) for item in evidence_frames)
            or "unknown geometric tolerance"
        )
        coordinates = (
            observations[0].bbox_pdf
            if observations
            else (0.0, 0.0, 1.0, 1.0)
        )
        return GdtNormalizationFailure(
            code=code,
            typed_unknown=GeometricToleranceCandidate.from_legacy_unknown(
                candidate_id="gdt-unknown-"
                + hashlib.sha256(
                    f"{raw_text}:{evidence_ref}".encode("utf-8")
                ).hexdigest()[:24],
                raw_text=raw_text,
                coordinates=coordinates,
                source_location_ids=self._source_ids(
                    evidence_frames,
                    observations,
                ),
                evidence_ref=evidence_ref,
            ),
        )


def _serialize_segment(segment: GdtSegment) -> str:
    value = str(segment.tolerance_value)
    if segment.diameter_modifier:
        value = f"⌀{value}"
    if segment.modifiers:
        value = f"{value} {' '.join(item.raw_symbol for item in segment.modifiers)}"
    tokens = [value]
    tokens.extend(
        datum.datum
        + (" " + " ".join(modifier.raw_symbol for modifier in datum.modifiers)
           if datum.modifiers
           else "")
        for datum in segment.datum_references
    )
    return " | ".join(tokens)


def _serialize_frames(
    tolerance_type: ToleranceType,
    frames: tuple[GdtFrame, ...],
    standard_context: StandardContext,
) -> str:
    symbol = _SYMBOL_BY_TOLERANCE_TYPE.get(tolerance_type)
    rendered_segments: list[str] = []
    for frame in frames:
        for segment in frame.segments:
            rendered_segments.append(_serialize_segment(segment))
    if not rendered_segments:
        return ""
    if symbol is not None:
        rendered_segments[0] = f"{symbol} | {rendered_segments[0]}"
    return " / ".join(rendered_segments)


class GeometricToleranceCandidate(_FrozenModel):
    candidate_id: str = Field(min_length=1)
    item_type: Literal["geometric_tolerance"] = "geometric_tolerance"
    schema_version: Literal["geometric-tolerance-candidate/1"] = (
        "geometric-tolerance-candidate/1"
    )
    raw_text: str
    normalized_text: str
    tolerance_type: ToleranceType
    tolerance_symbol: str | None
    tolerance_value: Decimal | None
    diameter_modifier: bool
    modifiers: tuple[GdtModifier, ...] = ()
    datum_references: tuple[DatumReference, ...] = ()
    frames: tuple[GdtFrame, ...] = ()
    standard_context: StandardContext = "unspecified"
    coordinates: tuple[float, float, float, float]
    source_location_ids: tuple[str, ...] = ()
    evidence_ref: str = Field(min_length=1)
    requires_confirmation: bool = True

    @model_validator(mode="after")
    def validate_derived_fields(self, info: ValidationInfo) -> Self:
        allow_legacy_unknown = bool(
            info.context and info.context.get(_LEGACY_UNKNOWN_CONTEXT)
        )
        if not self.frames:
            if (
                not allow_legacy_unknown
                or self.tolerance_type != "unknown"
                or self.tolerance_symbol is not None
                or self.tolerance_value is not None
                or self.modifiers
                or self.datum_references
                or self.normalized_text != self.raw_text
            ):
                raise ValueError(
                    "empty frames are reserved for from_legacy_unknown()"
                )
            return self

        first_segment = self.frames[0].segments[0]
        expected_symbol = _SYMBOL_BY_TOLERANCE_TYPE.get(self.tolerance_type)
        expected_text = _serialize_frames(
            self.tolerance_type,
            self.frames,
            self.standard_context,
        )
        if self.tolerance_symbol != expected_symbol:
            raise ValueError("tolerance_symbol must derive from tolerance_type")
        if self.tolerance_value != first_segment.tolerance_value:
            raise ValueError("tolerance_value must derive from the first segment")
        if self.diameter_modifier != first_segment.diameter_modifier:
            raise ValueError(
                "diameter_modifier must derive from the first segment"
            )
        if self.modifiers != first_segment.modifiers:
            raise ValueError("modifiers must derive from the first segment")
        if self.datum_references != first_segment.datum_references:
            raise ValueError(
                "datum_references must derive from the first segment"
            )
        if self.normalized_text != expected_text:
            raise ValueError("normalized_text must derive from frames")
        return self

    @classmethod
    def from_frames(
        cls,
        *,
        candidate_id: str,
        raw_text: str,
        tolerance_type: ToleranceType,
        frames: tuple[GdtFrame, ...],
        coordinates: tuple[float, float, float, float],
        source_location_ids: tuple[str, ...],
        evidence_ref: str,
        standard_context: StandardContext = "unspecified",
        requires_confirmation: bool = True,
    ) -> Self:
        first_segment = frames[0].segments[0] if frames else None
        if first_segment is None:
            raise ValueError("from_frames() requires at least one frame")
        return cls.model_validate(
            {
                "candidate_id": candidate_id,
                "raw_text": raw_text,
                "normalized_text": _serialize_frames(
                    tolerance_type,
                    frames,
                    standard_context,
                ),
                "tolerance_type": tolerance_type,
                "tolerance_symbol": _SYMBOL_BY_TOLERANCE_TYPE.get(
                    tolerance_type
                ),
                "tolerance_value": first_segment.tolerance_value,
                "diameter_modifier": first_segment.diameter_modifier,
                "modifiers": first_segment.modifiers,
                "datum_references": first_segment.datum_references,
                "frames": frames,
                "standard_context": standard_context,
                "coordinates": coordinates,
                "source_location_ids": source_location_ids,
                "evidence_ref": evidence_ref,
                "requires_confirmation": requires_confirmation,
            }
        )

    @classmethod
    def from_legacy_unknown(
        cls,
        *,
        candidate_id: str,
        raw_text: str,
        coordinates: tuple[float, float, float, float],
        source_location_ids: tuple[str, ...],
        evidence_ref: str = "legacy://geometric-tolerance",
    ) -> Self:
        return cls.model_validate(
            {
                "candidate_id": candidate_id,
                "raw_text": raw_text,
                "normalized_text": raw_text,
                "tolerance_type": "unknown",
                "tolerance_symbol": None,
                "tolerance_value": None,
                "diameter_modifier": False,
                "modifiers": (),
                "datum_references": (),
                "frames": (),
                "standard_context": "unspecified",
                "coordinates": coordinates,
                "source_location_ids": source_location_ids,
                "evidence_ref": evidence_ref,
                "requires_confirmation": True,
            },
            context={_LEGACY_UNKNOWN_CONTEXT: True},
        )


def serialize_geometric_tolerance(
    candidate: GeometricToleranceCandidate,
) -> str:
    if not candidate.frames:
        return candidate.raw_text
    return _serialize_frames(
        candidate.tolerance_type,
        candidate.frames,
        candidate.standard_context,
    )


__all__ = [
    "DatumReference",
    "GdtFrame",
    "GdtModifier",
    "GdtModifierKind",
    "GdtSegment",
    "GdtNormalizationFailure",
    "GeometricToleranceNormalizer",
    "GeometricToleranceCandidate",
    "StandardContext",
    "ToleranceType",
    "serialize_geometric_tolerance",
]
