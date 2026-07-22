from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


ArtifactKind = Literal["ballooned_pdf", "sip_excel", "manifest"]


class CreateExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewed_result_id: uuid.UUID


class ExportArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: ArtifactKind
    sha256: str
    size_bytes: int
    reviewed_result_id: uuid.UUID
    downloadable: bool


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    reviewed_result_id: uuid.UUID
    status: Literal["running", "success", "failed"]
    error_id: uuid.UUID | None
    template_version: str
    mapping_version: str
    renderer_version: str
    artifacts: list[ExportArtifactResponse]
