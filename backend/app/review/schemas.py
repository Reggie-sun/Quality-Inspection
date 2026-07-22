from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.candidates.schemas import CandidateType


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class Add(CommandBase):
    type: Literal["add"]
    raw_text: str
    item_type: CandidateType
    coordinates: tuple[float, float, float, float]
    scope: Literal["local_feature", "global_requirement"]
    balloon_required: bool


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


ReviewCommand = Annotated[
    Union[
        Keep,
        Exclude,
        Edit,
        Add,
        Merge,
        Split,
        ResolveConfirmation,
        SetBalloonRequired,
    ],
    Field(discriminator="type"),
]


class LockRequest(CommandBase):
    ttl_seconds: int = Field(default=300, ge=1, le=3600)


class ReviewCommandRequest(CommandBase):
    expected_version: int = Field(ge=1)
    command: ReviewCommand


class FreezeItemsRequest(CommandBase):
    expected_version: int = Field(ge=1)

_REVIEW_COMMAND_ADAPTER = TypeAdapter(ReviewCommand)
COMPLEX_EDITABLE_FIELDS = {
    "raw_text",
    "coordinates",
    "coarse_type",
    "requires_confirmation",
}
PROTECTED_TYPED_EDIT_FIELDS = {"candidate_id", "balloon_required"}


def parse_review_command(command: dict[str, object]) -> ReviewCommand:
    return _REVIEW_COMMAND_ADAPTER.validate_python(command)


def validate_edit_fields(
    item: dict[str, object],
    fields: dict[str, object],
) -> None:
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
