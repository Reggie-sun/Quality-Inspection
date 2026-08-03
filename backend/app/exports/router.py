from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.capabilities.service import CapabilityUnavailable
from app.config import get_settings
from app.db import SessionLocal
from app.errors.api import api_error, error_responses
from app.errors.schemas import ErrorSeverity
from app.projects.lifecycle import (
    ProjectAccess,
    ProjectLifecycleNotFound,
    ProjectLifecycleService,
)
from app.exports.models import ExportArtifact, ExportJob
from app.exports.schemas import CreateExportRequest, ExportResponse
from app.exports.service import (
    ExportInProgress,
    ExportInputUnavailable,
    ExportNotFound,
    ExportService,
)
from app.storage.local import LocalFileStorage


router = APIRouter(prefix="/api/v1", tags=["exports"])
_ASCII_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_root)


SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[LocalFileStorage, Depends(get_storage)]


def get_export_service(
    session: SessionDependency,
    storage: StorageDependency,
) -> ExportService:
    return ExportService(session, storage=storage)


ExportServiceDependency = Annotated[ExportService, Depends(get_export_service)]


@router.post(
    "/projects/{project_id}/exports",
    operation_id="QI-API-EXP-001",
    response_model=ExportResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "reviewed_result_not_found"),
            409: (
                "export_in_progress",
                "export_preflight_failed",
                "export_template_unavailable",
                "export_template_mapping_unavailable",
                "export_font_unavailable",
                "export_font_license_unavailable",
                "export_template_mapping_hash_mismatch",
                "export_template_hash_mismatch",
                "export_template_registration_invalid",
                "export_template_invalid",
                "export_template_sheet_missing",
                "export_font_hash_mismatch",
                "export_font_license_hash_mismatch",
            ),
            422: ("request_validation_failed",),
            500: ("internal_server_error",),
        }
    ),
)
def create_export(
    project_id: uuid.UUID,
    body: CreateExportRequest,
    service: ExportServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        export = service.create(body.reviewed_result_id, project_id=project_id)
    except ExportNotFound as error:
        return _error(404, "reviewed_result_not_found", str(error))
    except CapabilityUnavailable as error:
        return _error(409, error.code, error.detail)
    except ExportInProgress as error:
        return _error(409, "export_in_progress", str(error))
    except (ExportInputUnavailable, OSError, ValueError) as error:
        return _error(409, "export_preflight_failed", str(error))
    return _export_payload(service, export)


@router.get(
    "/exports/{export_id}",
    operation_id="QI-API-EXP-002",
    response_model=ExportResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "export_not_found"),
            422: ("request_validation_failed",),
            500: ("internal_server_error",),
        }
    ),
)
def get_export(
    export_id: uuid.UUID,
    service: ExportServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    try:
        export = service.get(export_id)
    except ExportNotFound as error:
        return _error(404, "export_not_found", str(error))
    guard = _active_project_error(session, export.project_id)
    if guard is not None:
        return guard
    return _export_payload(service, export)


@router.get(
    "/exports/{export_id}/downloads/{kind}",
    operation_id="QI-API-EXP-003",
    response_model=None,
    response_class=Response,
    responses={
        200: {
            "description": "Published export artifact.",
            "content": {
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "application/json": {
                    "schema": {"type": "string", "format": "binary"}
                },
            },
        },
        **error_responses(
            {
                404: ("project_not_found", "export_artifact_not_found"),
                409: ("export_artifact_unavailable",),
                422: ("request_validation_failed",),
                500: ("internal_server_error",),
            }
        ),
    },
)
def download_export(
    export_id: uuid.UUID,
    kind: str,
    service: ExportServiceDependency,
    storage: StorageDependency,
    session: SessionDependency,
) -> Response:
    media_types = {
        "ballooned_pdf": "application/pdf",
        "sip_excel": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "manifest": "application/json",
    }
    media_type = media_types.get(kind)
    try:
        export = service.get(export_id)
    except ExportNotFound as error:
        return _error(404, "export_artifact_not_found", str(error))
    guard = _active_project_error(session, export.project_id)
    if guard is not None:
        return guard
    resource_ref = service.download_ref(export_id, kind)
    if media_type is None or resource_ref is None:
        return _error(
            404,
            "export_artifact_not_found",
            "published export artifact was not found",
        )
    try:
        content = storage.read_bytes(resource_ref)
    except (OSError, ValueError):
        return _error(
            409,
            "export_artifact_unavailable",
            "published export artifact is unavailable",
        )
    filename = PurePosixPath(resource_ref.removeprefix("asset://")).name
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def _active_project_error(
    session: Session,
    project_id: uuid.UUID,
) -> JSONResponse | None:
    try:
        ProjectLifecycleService(session).require_access(
            project_id,
            ProjectAccess.ACTIVE,
        )
    except ProjectLifecycleNotFound:
        return _error(404, "project_not_found", "project was not found")
    return None


def _content_disposition(filename: str) -> str:
    fallback = _ASCII_FILENAME.sub("_", filename).strip("._-") or "export"
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _export_payload(
    service: ExportService,
    export: ExportJob,
) -> dict[str, object]:
    artifacts = service.artifacts(export.id)
    return {
        "id": export.id,
        "project_id": export.project_id,
        "reviewed_result_id": export.reviewed_result_id,
        "status": export.status,
        "error_id": export.error_id,
        "template_version": export.template_version,
        "mapping_version": export.mapping_version,
        "renderer_version": export.renderer_version,
        "artifacts": [_artifact_payload(artifact) for artifact in artifacts],
    }


def _artifact_payload(artifact: ExportArtifact) -> dict[str, object]:
    return {
        "kind": artifact.kind,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "reviewed_result_id": artifact.reviewed_result_id,
        "downloadable": artifact.published_ref is not None,
    }


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    severity: ErrorSeverity = "blocking",
) -> JSONResponse:
    return api_error(
        status_code,
        code,
        message,
        severity=severity,
        stage="export_api",
    )
