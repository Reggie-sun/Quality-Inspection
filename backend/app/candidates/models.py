from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AutomaticResult(Base):
    __tablename__ = "automatic_results"
    __table_args__ = (
        UniqueConstraint(
            "logical_job_id",
            name="uq_automatic_results_logical_job_id",
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
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stored_files.id"),
        nullable=False,
    )
    logical_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("logical_jobs.id"),
        nullable=False,
    )
    inventory_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    technical_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    provider_call_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
