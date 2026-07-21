import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OperationRecord(Base):
    __tablename__ = "operation_records"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(operator_id)) > 0",
            name="ck_operation_records_operator_id_nonblank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    command: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    before_version: Mapped[int] = mapped_column(Integer, nullable=False)
    after_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
