from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.candidates.geometric_tolerance import (
    GdtFrame,
    GdtModifierKind,
    ToleranceType,
)
from app.candidates.schemas import CandidateType


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
OptionalText = Annotated[
    str,
    StringConstraints(strip_whitespace=True),
]


class Keep(CommandBase):
    type: Literal["keep"]
    item_id: str = Field(min_length=1)


class Exclude(CommandBase):
    type: Literal["exclude"]
    item_id: str = Field(min_length=1)


class Edit(CommandBase):
    type: Literal["edit"]
    item_id: str = Field(min_length=1)
    fields: dict[str, Any] = Field(min_length=1)


class EditGeometricTolerance(CommandBase):
    type: Literal["edit_geometric_tolerance"]
    item_id: str = Field(min_length=1)
    tolerance_type: ToleranceType
    frames: tuple[GdtFrame, ...] = Field(min_length=1)
    standard_context: Literal["unspecified"]


class Add(CommandBase):
    type: Literal["add"]
    raw_text: str
    item_type: CandidateType
    coordinates: tuple[float, float, float, float]
    scope: Literal["local_feature", "global_requirement"]
    balloon_required: bool
    page_index: int | None = Field(default=None, ge=0)


class PromoteSource(CommandBase):
    type: Literal["promote_source"]
    observation_id: str = Field(min_length=1)
    raw_text: NonBlankText
    item_type: CandidateType
    scope: Literal["local_feature", "global_requirement"]
    balloon_required: bool
    page_index: int = Field(ge=0)


class IgnoreSource(CommandBase):
    type: Literal["ignore_source"]
    observation_id: str = Field(min_length=1)


class IgnoreSources(CommandBase):
    type: Literal["ignore_sources"]
    observation_ids: list[NonBlankText] = Field(min_length=1)

    @field_validator("observation_ids")
    @classmethod
    def require_unique_observation_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("observation_ids must be unique")
        return value


class Merge(CommandBase):
    type: Literal["merge"]
    item_ids: list[str] = Field(min_length=2)
    raw_text: str


class SplitPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str


class Split(CommandBase):
    type: Literal["split"]
    item_id: str = Field(min_length=1)
    parts: list[SplitPart] = Field(min_length=2)


class ResolveConfirmation(CommandBase):
    type: Literal["resolve_confirmation"]
    item_id: str = Field(min_length=1)
    accepted: bool


class SetBalloonRequired(CommandBase):
    type: Literal["set_balloon_required"]
    item_id: str = Field(min_length=1)
    balloon_required: bool


SIP_DETAIL_FIELDS = (
    "inspection_item",
    "inspection_standard",
    "inspection_method",
    "key_dimension",
    "inspection_role",
    "source_page",
)
SIP_OPTIONAL_DETAIL_FIELDS = ("remarks",)
SIP_METADATA_FIELDS = (
    "material_code",
    "material_name",
    "drawing_number",
    "material",
    "revision",
)
SIP_REQUIRED_METADATA_FIELDS = (
    "material_code",
    "material_name",
    "drawing_number",
    "revision",
)


def normalize_sip_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    material = normalized.get("material")
    if isinstance(material, str):
        stripped = material.strip()
        normalized["material"] = "" if stripped == "none" else stripped
    return normalized


class SetSipDetailFields(CommandBase):
    type: Literal["set_sip_detail_fields"]
    item_id: str = Field(min_length=1)
    inspection_item: NonBlankText
    inspection_standard: NonBlankText
    inspection_method: NonBlankText
    key_dimension: NonBlankText
    inspection_role: NonBlankText
    source_page: int = Field(ge=1, strict=True)
    remarks: str = Field(default="", max_length=2000)


class GenerateSipTable(CommandBase):
    type: Literal["generate_sip_table"]
    inspection_role: NonBlankText


class SetSipMetadata(CommandBase):
    type: Literal["set_sip_metadata"]
    material_code: NonBlankText
    material_name: NonBlankText
    drawing_number: NonBlankText
    material: OptionalText
    revision: NonBlankText


class SetTechnicalRequirementMatch(CommandBase):
    type: Literal["set_technical_requirement_match"]
    requirement_id: NonBlankText
    outcome: Literal["matched_items", "global_scope", "excluded"]
    matched_item_ids: list[NonBlankText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relation(self) -> SetTechnicalRequirementMatch:
        if self.outcome == "matched_items" and not self.matched_item_ids:
            raise ValueError("matched_items requires at least one item")
        if self.outcome != "matched_items" and self.matched_item_ids:
            raise ValueError("only matched_items accepts item targets")
        if len(set(self.matched_item_ids)) != len(self.matched_item_ids):
            raise ValueError("matched_item_ids must be unique")
        return self


ReviewCommand = Annotated[
    Union[
        Keep,
        Exclude,
        Edit,
        EditGeometricTolerance,
        Add,
        PromoteSource,
        IgnoreSource,
        IgnoreSources,
        Merge,
        Split,
        ResolveConfirmation,
        SetBalloonRequired,
        SetSipDetailFields,
        GenerateSipTable,
        SetSipMetadata,
        SetTechnicalRequirementMatch,
    ],
    Field(discriminator="type"),
]


class LockRequest(CommandBase):
    ttl_seconds: int = Field(default=300, ge=1, le=3600)


class ReleaseLockRequest(CommandBase):
    expires_at: datetime


class ReviewCommandRequest(CommandBase):
    expected_version: int = Field(ge=1)
    command: ReviewCommand


class FreezeItemsRequest(CommandBase):
    expected_version: int = Field(ge=1)


class ConfirmReviewRequest(CommandBase):
    expected_version: int = Field(ge=1)


class ReviewLockResponse(CommandBase):
    project_id: uuid.UUID
    operator_id: str
    expires_at: datetime


class ReviewLockReleaseResponse(CommandBase):
    project_id: uuid.UUID
    released: bool


class ReviewItemBase(CommandBase):
    item_id: NonBlankText
    raw_text: str
    normalized_text: str | None = None
    coordinates: tuple[float, float, float, float] | None = None
    source_location_ids: list[NonBlankText]
    source_type: Literal["automatic", "manual"]
    status: str
    requires_confirmation: bool
    acceptance_source: str | None = None
    active: bool = True
    confirmation_accepted: bool | None = None
    scope: Literal["local_feature", "global_requirement"] | None = None
    balloon_required: bool | None = None
    page_index: int | None = Field(default=None, ge=0)
    technical_requirement_refs: list[NonBlankText] | None = None
    confidence_decision: dict[str, Any] | None = None
    inspection_item: str | None = None
    inspection_standard: str | None = None
    inspection_method: str | None = None
    key_dimension: str | None = None
    inspection_role: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    remarks: str | None = None
    sip_detail_fields_confirmed: bool | None = None
    sip_suggestion_provenance: dict[str, str] | None = None
    sip_mapping_exceptions: list[str] | None = None
    merged_from_item_ids: list[NonBlankText] | None = None
    split_from_item_id: NonBlankText | None = None


class TypedReviewItem(ReviewItemBase):
    item_type: CandidateType
    quantity: int | None = Field(default=None, ge=1)
    nominal: Decimal | None = None
    upper_tolerance: Decimal | None = None
    lower_tolerance: Decimal | None = None
    feature_kind: Literal[
        "hole", "shaft", "cylindrical_feature", "unknown"
    ] | None = None
    depth: Decimal | None = None
    through: bool | None = None
    thread_spec: str | None = None
    thread_depth: Decimal | None = None
    radius_value: Decimal | None = None
    angle_value: Decimal | None = None
    sub_requirements: list[dict[str, Any]] = Field(default_factory=list)


class CoarseReviewItem(ReviewItemBase):
    coarse_type: Literal["roughness", "weld", "cross_view_duplicate"]


class GeometricToleranceReviewModifier(CommandBase):
    kind: GdtModifierKind
    raw_symbol: NonBlankText


class GeometricToleranceReviewDatumReference(CommandBase):
    datum: Annotated[str, StringConstraints(pattern=r"^[A-Z]$")]
    modifiers: list[GeometricToleranceReviewModifier] = Field(
        default_factory=list
    )


class GeometricToleranceReviewSegment(CommandBase):
    tolerance_value: Decimal = Field(gt=0)
    diameter_modifier: bool
    modifiers: list[GeometricToleranceReviewModifier]
    datum_references: list[GeometricToleranceReviewDatumReference]


class GeometricToleranceReviewFrame(CommandBase):
    segments: list[GeometricToleranceReviewSegment] = Field(min_length=1)


class GeometricToleranceReviewItem(ReviewItemBase):
    item_type: Literal["geometric_tolerance"]
    schema_version: Literal["geometric-tolerance-candidate/1"]
    normalized_text: NonBlankText
    coordinates: tuple[float, float, float, float]
    tolerance_type: ToleranceType
    tolerance_symbol: str | None
    tolerance_value: Decimal | None
    diameter_modifier: bool
    modifiers: list[GeometricToleranceReviewModifier]
    datum_references: list[GeometricToleranceReviewDatumReference]
    frames: list[GeometricToleranceReviewFrame] = Field(min_length=0)
    standard_context: Literal["unspecified"]
    evidence_ref: NonBlankText


ReviewItemProjection = Annotated[
    Union[
        GeometricToleranceReviewItem,
        TypedReviewItem,
        CoarseReviewItem,
    ],
    Field(json_schema_extra={"type": "object"}),
]


class ReviewWorkingCopyProjection(CommandBase):
    id: uuid.UUID
    project_id: uuid.UUID
    raw_result_id: uuid.UUID
    version: int
    items: list[ReviewItemProjection]
    coverage: dict[str, Any]
    technical_requirements: list[dict[str, Any]]
    sip_metadata: dict[str, Any]
    numbering_stale: bool
    items_frozen_at: datetime | None
    items_frozen_by: str | None
    items_frozen_version: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    manual_review_count: int


class ReviewWorkingCopyResponse(ReviewWorkingCopyProjection):
    created_at: datetime
    updated_at: datetime


class ReviewedResultResponse(CommandBase):
    id: uuid.UUID
    project_id: uuid.UUID
    working_copy_id: uuid.UUID
    working_version: int
    items: list[ReviewItemProjection]
    balloons: list[dict[str, Any]]
    sip_metadata: dict[str, Any]
    schema_version: str
    created_at: datetime

_REVIEW_COMMAND_ADAPTER = TypeAdapter(ReviewCommand)
COMPLEX_EDITABLE_FIELDS = {
    "raw_text",
    "coordinates",
    "coarse_type",
    "requires_confirmation",
}
PROTECTED_TYPED_EDIT_FIELDS = {"candidate_id", "balloon_required"}
PROTECTED_GDT_EDIT_FIELDS = {
    "item_type",
    "schema_version",
    "normalized_text",
    "tolerance_type",
    "tolerance_symbol",
    "tolerance_value",
    "diameter_modifier",
    "modifiers",
    "datum_references",
    "frames",
    "standard_context",
    "evidence_ref",
}


def parse_review_command(command: dict[str, object]) -> ReviewCommand:
    return _REVIEW_COMMAND_ADAPTER.validate_python(command)


def validate_edit_fields(
    item: dict[str, object],
    fields: dict[str, object],
) -> None:
    if item.get("item_type") == "geometric_tolerance":
        protected = set(fields) & PROTECTED_GDT_EDIT_FIELDS
        if protected:
            raise ValueError(
                "derived geometric tolerance fields are editable only with "
                f"edit_geometric_tolerance: {sorted(protected)}"
            )
    if "coarse_type" not in item:
        protected = set(fields) & PROTECTED_TYPED_EDIT_FIELDS
        if protected:
            raise ValueError(f"typed item fields are not editable: {sorted(protected)}")
        return
    extra = set(fields) - COMPLEX_EDITABLE_FIELDS
    if extra:
        raise ValueError(
            f"complex item fields are not editable in P0: {sorted(extra)}"
        )
