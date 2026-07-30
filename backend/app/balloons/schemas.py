from __future__ import annotations

import uuid
from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field


BBox: TypeAlias = tuple[float, float, float, float]
PdfPoint: TypeAlias = tuple[float, float]
PlacementStatus: TypeAlias = Literal["placed", "manual_required"]
HardCollisionFlag: TypeAlias = Literal[
    "circle_overlap",
    "glyph_overlap",
    "glyph_circle_overlap",
    "owner_glyph_outside_circle",
    "outside_cropbox",
    "protected_overlap",
    "source_text_overlap",
    "unreadable_number",
    "invalid_leader",
    "forbidden_overlap",
]


class BalloonCommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateBalloonsRequest(BalloonCommandBase):
    expected_version: int = Field(ge=1)


class MoveBalloon(BalloonCommandBase):
    type: Literal["move"]
    balloon_id: uuid.UUID
    expected_version: int = Field(ge=1)
    center_pdf: PdfPoint


class DeleteBalloon(BalloonCommandBase):
    type: Literal["delete"]
    balloon_id: uuid.UUID
    expected_version: int = Field(ge=1)


class RebuildBalloon(BalloonCommandBase):
    type: Literal["rebuild"]
    balloon_id: uuid.UUID
    expected_version: int = Field(ge=1)


class ReorderBalloon(BalloonCommandBase):
    type: Literal["reorder"]
    balloon_id: uuid.UUID
    expected_version: int = Field(ge=1)
    sort_order: int = Field(ge=0)


class RenumberBalloons(BalloonCommandBase):
    type: Literal["renumber"]
    ordered_balloon_ids: list[uuid.UUID] = Field(min_length=1)
    expected_versions: dict[uuid.UUID, int]


BalloonCommandRequest = Annotated[
    Union[
        MoveBalloon,
        DeleteBalloon,
        RebuildBalloon,
        ReorderBalloon,
        RenumberBalloons,
    ],
    Field(discriminator="type"),
]


class BalloonResponse(BalloonCommandBase):
    id: uuid.UUID
    project_id: uuid.UUID
    inspection_item_id: str
    source_location_id: str
    page_index: int
    suggested_number: int
    formal_number: int | None
    sort_order: int
    anchor_bbox_pdf: BBox
    leader_target_pdf: PdfPoint
    center_pdf: PdfPoint
    placement_status: PlacementStatus
    collision_flags: list[HardCollisionFlag]
    status: Literal["active", "deleted"]
    version: int


class BalloonCollectionResponse(BalloonCommandBase):
    balloons: list[BalloonResponse]


BalloonCommandResponse = Union[BalloonResponse, BalloonCollectionResponse]
