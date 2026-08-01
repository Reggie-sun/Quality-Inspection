from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.balloons.schemas import BalloonResponse
from app.exports.schemas import ExportResponse
from app.projects.state import ProjectState
from app.review.schemas import ReviewWorkingCopyProjection


class ProjectPhase(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    PARTIAL_REVIEW_REQUIRED = "partial_review_required"
    FAILED = "failed"


class ProcessingStage(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    RECOGNIZING = "recognizing"
    LOCAL_READY = "local_ready"
    VLM_ENRICHING = "vlm_enriching"
    PREPARING_REVIEW = "preparing_review"


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
    stage: ProcessingStage | None = None


class ProjectListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    file_name: str
    created_at: datetime
    last_opened_at: datetime


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProjectListItemResponse]
    count: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    app_name: str


class WorkbenchProjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    state: ProjectState
    version: int


class ProjectWorkbenchPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int
    width: float
    height: float
    pdf_to_render_matrix: tuple[float, float, float, float, float, float]
    render_to_pdf_matrix: tuple[float, float, float, float, float, float]


class ProjectWorkbenchCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    item_id: str
    page_index: int
    bbox_pdf: tuple[float, float, float, float]
    confidence_band: Literal["high", "medium", "low"] | None
    review_disposition: Literal["auto_accepted", "review_required"] | None
    status: str | None


class ProjectWorkbenchSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    item_ids: list[str]
    page_index: int
    bbox_pdf: tuple[float, float, float, float]
    raw_text: str
    source_type: Literal["text", "visual"]


class ProjectWorkbenchSipMetadataSuggestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "material_code",
        "material_name",
        "drawing_number",
        "material",
        "revision",
    ]
    value: str
    observation_id: str
    label_observation_id: str | None
    page_index: int
    bbox_pdf: tuple[float, float, float, float]
    rule_version: Literal["welli-title-metadata/1"]
    evidence_codes: list[str]


class ProjectWorkbenchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: WorkbenchProjectResponse
    working_copy: ReviewWorkingCopyProjection
    pages: list[ProjectWorkbenchPageResponse]
    candidates: list[ProjectWorkbenchCandidateResponse]
    sources: list[ProjectWorkbenchSourceResponse]
    sip_metadata_suggestions: list[
        ProjectWorkbenchSipMetadataSuggestionResponse
    ]
    balloons: list[BalloonResponse]
    balloon_blockers: list[str]
    source_pdf_url: str
    reviewed_result_id: uuid.UUID | None
    latest_export: ExportResponse | None


class RecognitionPreviewCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    kind: str
    label: str


class RecognitionPreviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_location_id: str
    source_type: str
    page_index: int
    raw_text: str


class RecognitionPreviewCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_resolved: int
    cache_resolved: int
    vlm_pending: int
    vlm_resolved: int
    unresolved: int


class RecognitionPreviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["recognition-preview/1"]
    stage: Literal["local_ready", "vlm_enriching"]
    candidates: list[RecognitionPreviewCandidate]
    sources: list[RecognitionPreviewSource]
    counts: RecognitionPreviewCounts


class RecognitionPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    stage: Literal["local_ready", "vlm_enriching"]
    source_pdf_url: str
    semantic_snapshot: RecognitionPreviewSnapshot
    counts: RecognitionPreviewCounts
