from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.processing.recognition_preview import (
    RecognitionPreviewHead,
    RecognitionPreviewRevision,
)
from app.projects.models import Project
from app.storage.models import StoredFile


class ProjectSourceNotFound(LookupError):
    pass


class ProjectSourceUnavailable(RuntimeError):
    pass


def project_source_file(session: Session, project_id: uuid.UUID) -> StoredFile:
    if session.get(Project, project_id) is None:
        raise ProjectSourceNotFound("project was not found")

    head = session.get(RecognitionPreviewHead, project_id)
    if head is not None:
        revision = session.get(RecognitionPreviewRevision, head.revision_id)
        if revision is not None:
            source = session.get(StoredFile, revision.source_file_id)
            if source is not None:
                return source

    raw = session.scalar(
        select(AutomaticResult)
        .where(AutomaticResult.project_id == project_id)
        .order_by(AutomaticResult.created_at.desc(), AutomaticResult.id.desc())
        .limit(1)
    )
    if raw is not None:
        source = session.get(StoredFile, raw.source_file_id)
        if source is not None:
            return source

    source = session.scalar(
        select(StoredFile).where(
            StoredFile.resource_ref
            == f"asset://projects/{project_id}/source.pdf"
        )
    )
    if source is not None:
        return source
    raise ProjectSourceUnavailable("project source PDF is unavailable")
