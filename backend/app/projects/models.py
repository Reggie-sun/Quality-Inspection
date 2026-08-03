import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProjectLifecycleStatus(StrEnum):
    UNLISTED = "unlisted"
    ACTIVE = "active"
    REPROCESSING = "reprocessing"
    REPROCESS_FAILED = "reprocess_failed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('unlisted', 'active', 'reprocessing', "
            "'reprocess_failed', 'superseded', 'deleted')",
            name="ck_projects_lifecycle_status",
        ),
        CheckConstraint(
            "(lifecycle_status = 'deleted' AND deleted_at IS NOT NULL) OR "
            "(lifecycle_status <> 'deleted' AND deleted_at IS NULL)",
            name="ck_projects_deleted_timestamp",
        ),
        CheckConstraint(
            "predecessor_project_id IS NULL OR predecessor_project_id <> id",
            name="ck_projects_predecessor_not_self",
        ),
        Index(
            "uq_projects_reprocessing_predecessor",
            "predecessor_project_id",
            unique=True,
            postgresql_where=text("lifecycle_status = 'reprocessing'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        default="processing",
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recognition_mode: Mapped[str] = mapped_column(
        String(40),
        default="legacy_high_recall",
        server_default="legacy_high_recall",
        nullable=False,
    )
    recognition_router_version: Mapped[str] = mapped_column(
        String(64),
        default="legacy",
        server_default="legacy",
        nullable=False,
    )
    source_filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        default=ProjectLifecycleStatus.ACTIVE,
        server_default=ProjectLifecycleStatus.ACTIVE,
        nullable=False,
    )
    predecessor_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
