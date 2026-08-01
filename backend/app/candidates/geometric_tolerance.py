from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


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
    "GeometricToleranceCandidate",
    "StandardContext",
    "ToleranceType",
    "serialize_geometric_tolerance",
]
