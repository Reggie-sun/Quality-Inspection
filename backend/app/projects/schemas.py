from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ProjectPhase(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"


class ProjectError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    stage: str


class ProjectStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID | None = None
    phase: ProjectPhase
    workbench_ready: bool
    retryable: bool
    error: ProjectError | None
