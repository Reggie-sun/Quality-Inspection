import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

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
