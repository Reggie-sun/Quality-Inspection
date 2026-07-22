from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Balloon(Base):
    __tablename__ = "balloons"
    __table_args__ = (
        Index(
            "uq_balloons_active_item",
            "project_id",
            "inspection_item_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_balloons_active_formal_number",
            "project_id",
            "formal_number",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND formal_number IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    inspection_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_location_id: Mapped[str] = mapped_column(String(256), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_number: Mapped[int] = mapped_column(Integer, nullable=False)
    formal_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_bbox_pdf: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    leader_target_pdf: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    center_pdf: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    placement_status: Mapped[str] = mapped_column(String(32), nullable=False)
    collision_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "project_id": str(self.project_id),
            "inspection_item_id": self.inspection_item_id,
            "source_location_id": self.source_location_id,
            "page_index": self.page_index,
            "suggested_number": self.suggested_number,
            "formal_number": self.formal_number,
            "sort_order": self.sort_order,
            "anchor_bbox_pdf": list(self.anchor_bbox_pdf),
            "leader_target_pdf": list(self.leader_target_pdf),
            "center_pdf": list(self.center_pdf),
            "placement_status": self.placement_status,
            "collision_flags": list(self.collision_flags),
            "status": self.status,
            "version": self.version,
        }
