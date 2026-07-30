from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.exc import IntegrityError

from app.db import Base
from app.projects.schemas import RecognitionPreviewSnapshot


class RecognitionPreviewRevision(Base):
    __tablename__ = "recognition_preview_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("recognition_preview_revisions.id"))
    semantic_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    semantic_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)


class RecognitionPreviewHead(Base):
    __tablename__ = "recognition_preview_heads"

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recognition_preview_revisions.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    terminal_result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automatic_results.id"))


class RecognitionPreviewService:
    class CasConflict(RuntimeError):
        pass

    def __init__(self, session: Session, *, project_id: uuid.UUID) -> None:
        self.session = session
        self.project_id = project_id

    @staticmethod
    def _hash(snapshot: Mapping[str, object]) -> str:
        return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _snapshot(snapshot: Mapping[str, object]) -> dict[str, Any]:
        return RecognitionPreviewSnapshot.model_validate(snapshot).model_dump()

    def head(self) -> RecognitionPreviewRevision:
        head = self.session.get(RecognitionPreviewHead, self.project_id, populate_existing=True)
        if head is None:
            raise self.CasConflict("recognition preview is unavailable")
        revision = self.session.get(RecognitionPreviewRevision, head.revision_id)
        if revision is None:
            raise self.CasConflict("recognition preview head is invalid")
        return revision

    def revision_for(self, revision: int) -> RecognitionPreviewRevision:
        result = self.session.scalar(select(RecognitionPreviewRevision).where(
            RecognitionPreviewRevision.project_id == self.project_id,
            RecognitionPreviewRevision.revision == revision,
        ))
        if result is None:
            raise self.CasConflict("recognition preview revision is unavailable")
        return result

    def publish_local(self, *, source_file_id: uuid.UUID, snapshot: Mapping[str, object]) -> RecognitionPreviewRevision:
        existing = self.session.get(RecognitionPreviewHead, self.project_id)
        if existing is not None:
            return self.head()
        normalized_snapshot = self._snapshot(snapshot)
        revision = RecognitionPreviewRevision(
            project_id=self.project_id, source_file_id=source_file_id, revision=1,
            parent_revision_id=None, semantic_snapshot=normalized_snapshot,
            semantic_sha256=self._hash(normalized_snapshot),
            schema_version=normalized_snapshot["schema_version"],
        )
        self.session.add(revision)
        self.session.flush()
        self.session.add(RecognitionPreviewHead(project_id=self.project_id, revision_id=revision.id, version=1))
        self.session.flush()
        return revision

    def append_enrichment(self, *, expected_head_version: int, parent_revision_id: uuid.UUID, snapshot: Mapping[str, object]) -> RecognitionPreviewRevision:
        current = self.session.get(RecognitionPreviewHead, self.project_id)
        if current is None or current.terminal_result_id is not None or current.version != expected_head_version or current.revision_id != parent_revision_id:
            raise self.CasConflict("recognition preview head changed")
        parent = self.session.get(RecognitionPreviewRevision, parent_revision_id)
        if parent is None:
            raise self.CasConflict("recognition preview parent is unavailable")
        normalized_snapshot = self._snapshot(snapshot)
        revision = RecognitionPreviewRevision(
            project_id=self.project_id, source_file_id=parent.source_file_id,
            revision=parent.revision + 1, parent_revision_id=parent.id,
            semantic_snapshot=normalized_snapshot,
            semantic_sha256=self._hash(normalized_snapshot),
            schema_version=normalized_snapshot["schema_version"],
        )
        try:
            with self.session.begin_nested():
                self.session.add(revision)
                self.session.flush()
                outcome = self.session.execute(update(RecognitionPreviewHead).where(
                    RecognitionPreviewHead.project_id == self.project_id,
                    RecognitionPreviewHead.version == expected_head_version,
                    RecognitionPreviewHead.revision_id == parent_revision_id,
                    RecognitionPreviewHead.terminal_result_id.is_(None),
                ).values(revision_id=revision.id, version=expected_head_version + 1))
                if outcome.rowcount != 1:
                    raise self.CasConflict("recognition preview compare-and-swap lost")
        except IntegrityError as error:
            raise self.CasConflict("recognition preview compare-and-swap lost") from error
        return revision

    def supersede_with_terminal(self, *, automatic_result_id: uuid.UUID) -> None:
        outcome = self.session.execute(update(RecognitionPreviewHead).where(
            RecognitionPreviewHead.project_id == self.project_id,
            RecognitionPreviewHead.terminal_result_id.is_(None),
        ).values(terminal_result_id=automatic_result_id))
        if outcome.rowcount != 1:
            raise self.CasConflict("recognition preview is unavailable")
