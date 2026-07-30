from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


ErrorSeverity = Literal[
    "fatal",
    "blocking",
    "review_required",
    "warning",
    "informational",
]


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    severity: ErrorSeverity
    stage: str
    location_ref: str | None
    cause_category: str
    blockers: list[str] | None = None
    project_id: uuid.UUID | None = None
    retryable: bool | None = None
    phase: str | None = None
    workbench_ready: bool | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
