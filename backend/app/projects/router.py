from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.balloons.models import Balloon
from app.balloons.service import BalloonService
from app.candidates.models import AutomaticResult
from app.config import get_settings
from app.db import SessionLocal
from app.exports.router import _export_payload
from app.exports.service import ExportService
from app.processing.tasks import inventory_project
from app.projects.models import Project
from app.projects.service import (
    InvalidPdf,
    ProjectDispatchFailed,
    ProjectDispatcher,
    ProjectIntakeService,
    ProjectNotFound,
)
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.storage.local import LocalFileStorage
from app.storage.models import StoredFile


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectWorkbenchNotFound(LookupError):
    pass


class ProjectWorkbenchUnavailable(RuntimeError):
    pass


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_root)


def get_dispatcher() -> ProjectDispatcher:
    return inventory_project.delay


SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[LocalFileStorage, Depends(get_storage)]
DispatcherDependency = Annotated[ProjectDispatcher, Depends(get_dispatcher)]


def get_project_service(
    session: SessionDependency,
    storage: StorageDependency,
    dispatch: DispatcherDependency,
) -> ProjectIntakeService:
    return ProjectIntakeService(session, storage, dispatch)


ProjectServiceDependency = Annotated[
    ProjectIntakeService,
    Depends(get_project_service),
]


@router.post("", status_code=202)
async def create_project(
    request: Request,
    file: Annotated[UploadFile, File()],
    service: ProjectServiceDependency,
) -> JSONResponse:
    form_parts = list((await request.form()).multi_items())
    if (
        len(form_parts) != 1
        or form_parts[0][0] != "file"
        or not isinstance(form_parts[0][1], StarletteUploadFile)
    ):
        return _error(422, "invalid_pdf", "uploaded file is not a valid PDF")
    try:
        result = service.create_pdf(
            content=await file.read(),
            content_type=file.content_type or "",
        )
    except InvalidPdf:
        return _error(422, "invalid_pdf", "uploaded file is not a valid PDF")
    except ProjectDispatchFailed as error:
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(error.status),
        )
    except Exception:
        return _error(500, "project_intake_failed", "project intake failed")
    return JSONResponse(
        status_code=202,
        content=jsonable_encoder(result),
    )


@router.get("/{project_id}/status")
def get_project_status(
    project_id: uuid.UUID,
    service: ProjectServiceDependency,
) -> JSONResponse:
    try:
        result = service.status(project_id)
    except ProjectNotFound:
        return _error(404, "project_not_found", "project was not found")
    except Exception:
        return _error(500, "project_status_failed", "project status unavailable")
    return JSONResponse(
        content=jsonable_encoder(result, exclude_none=True),
    )


@router.get("/{project_id}/workbench")
def get_workbench(
    project_id: uuid.UUID,
    session: SessionDependency,
    storage: StorageDependency,
) -> JSONResponse:
    try:
        payload = _workbench_payload(session, storage, project_id)
    except ProjectWorkbenchNotFound as error:
        return _error(404, "project_not_found", str(error))
    except ProjectWorkbenchUnavailable as error:
        return _error(409, "project_workbench_unavailable", str(error))
    return JSONResponse(jsonable_encoder(payload))


@router.get("/{project_id}/source-pdf")
def get_source_pdf(
    project_id: uuid.UUID,
    session: SessionDependency,
    storage: StorageDependency,
) -> Response:
    try:
        _, _, raw = _project_review_result(session, project_id)
        source = session.get(StoredFile, raw.source_file_id)
        if source is None or source.mime_type != "application/pdf":
            raise ProjectWorkbenchUnavailable("project source PDF is unavailable")
        content = storage.read_bytes(source.resource_ref)
    except ProjectWorkbenchNotFound as error:
        return _error(404, "project_not_found", str(error))
    except (ProjectWorkbenchUnavailable, ValueError, OSError):
        return _error(
            409,
            "project_source_pdf_unavailable",
            "project source PDF is unavailable",
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _workbench_payload(
    session: Session,
    storage: LocalFileStorage,
    project_id: uuid.UUID,
) -> dict[str, object]:
    project, working, raw = _project_review_result(session, project_id)
    try:
        inventory = json.loads(storage.read_bytes(raw.inventory_ref))
        pages = inventory["pages"]
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        raise ProjectWorkbenchUnavailable("project page inventory is unavailable") from error
    if not isinstance(pages, list):
        raise ProjectWorkbenchUnavailable("project page inventory is unavailable")

    projected_pages, observations = _project_pages(pages)
    candidates, source_items = _project_items(
        working.items,
        working.coverage,
        observations,
    )
    sources = [
        {
            "id": source_id,
            "item_ids": relation["item_ids"],
            "page_index": relation["page_index"],
            "bbox_pdf": relation["bbox_pdf"],
            "raw_text": relation["raw_text"],
        }
        for source_id, relation in sorted(source_items.items())
    ]
    balloons = list(
        session.scalars(
            select(Balloon)
            .where(Balloon.project_id == project_id)
            .order_by(Balloon.sort_order, Balloon.id)
        )
    )
    try:
        blockers = BalloonService(
            session,
            storage=storage,
        ).validation_blockers(project_id)
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
        raise ProjectWorkbenchUnavailable("balloon projection is unavailable") from error
    reviewed = session.scalar(
        select(ReviewedResult)
        .where(ReviewedResult.project_id == project_id)
        .order_by(ReviewedResult.created_at.desc(), ReviewedResult.id.desc())
        .limit(1)
    )
    export_service = ExportService(session, storage=storage)
    latest_export = export_service.latest_for_project(project_id)

    return {
        "project": {
            "id": project.id,
            "state": project.state,
            "version": project.version,
        },
        "working_copy": _working_copy(working),
        "pages": projected_pages,
        "candidates": candidates,
        "sources": sources,
        "balloons": [balloon.snapshot() for balloon in balloons],
        "balloon_blockers": blockers,
        "source_pdf_url": f"/api/v1/projects/{project.id}/source-pdf",
        "reviewed_result_id": reviewed.id if reviewed is not None else None,
        "latest_export": (
            _export_payload(export_service, latest_export)
            if latest_export is not None
            else None
        ),
    }


def _project_review_result(
    session: Session,
    project_id: uuid.UUID,
) -> tuple[Project, ReviewWorkingCopy, AutomaticResult]:
    project = session.get(Project, project_id)
    if project is None:
        raise ProjectWorkbenchNotFound(f"project {project_id} was not found")
    working = session.scalar(
        select(ReviewWorkingCopy).where(ReviewWorkingCopy.project_id == project_id)
    )
    if working is None:
        raise ProjectWorkbenchUnavailable("project has no review working copy")
    raw = session.get(AutomaticResult, working.raw_result_id)
    if raw is None or raw.project_id != project_id:
        raise ProjectWorkbenchUnavailable("project automatic result is unavailable")
    return project, working, raw


def _project_pages(
    pages: list[object],
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    projected: list[dict[str, object]] = []
    observations: dict[str, dict[str, object]] = {}
    try:
        for raw_page in pages:
            if not isinstance(raw_page, dict):
                raise TypeError
            page: dict[str, Any] = raw_page
            page_index = int(page["page_index"])
            projected.append(
                {
                    "page_index": page_index,
                    "width": float(page["width"]),
                    "height": float(page["height"]),
                    "pdf_to_render_matrix": list(page["pdf_to_render_matrix"]),
                    "render_to_pdf_matrix": list(page["render_to_pdf_matrix"]),
                }
            )
            for raw_observation in page.get("observations", []):
                if not isinstance(raw_observation, dict):
                    raise TypeError
                source_id = str(raw_observation["observation_id"])
                raw_text = raw_observation.get("raw_text")
                observations[source_id] = {
                    "page_index": page_index,
                    "bbox_pdf": list(raw_observation["bbox_pdf"]),
                    "raw_text": raw_text if isinstance(raw_text, str) else "",
                }
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectWorkbenchUnavailable("project page inventory is invalid") from error
    return sorted(projected, key=lambda page: int(page["page_index"])), observations


def _project_items(
    items: list[dict[str, Any]],
    coverage: dict[str, Any],
    observations: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    sources: dict[str, dict[str, object]] = {}
    for item in items:
        if not item.get("active", True):
            continue
        item_id = str(item["item_id"])
        source_ids = [str(value) for value in item.get("source_location_ids", [])]
        source = next(
            (observations[source_id] for source_id in source_ids if source_id in observations),
            None,
        )
        page_index = item.get("page_index")
        if not isinstance(page_index, int) and source is not None:
            page_index = source["page_index"]
        coordinates = item.get("coordinates")
        if isinstance(page_index, int) and _is_bbox(coordinates):
            candidates.append(
                {
                    "id": f"candidate-{item_id}",
                    "item_id": item_id,
                    "page_index": page_index,
                    "bbox_pdf": list(coordinates),
                }
            )
        for source_id in source_ids:
            geometry = observations.get(source_id)
            if geometry is None and source_id.startswith("manual:") and _is_bbox(coordinates):
                if not isinstance(page_index, int):
                    continue
                geometry = {"page_index": page_index, "bbox_pdf": list(coordinates)}
            if geometry is None:
                continue
            relation = sources.setdefault(
                source_id,
                {
                    "item_ids": [],
                    "page_index": geometry["page_index"],
                    "bbox_pdf": geometry["bbox_pdf"],
                    "raw_text": geometry.get("raw_text", ""),
                },
            )
            relation["item_ids"].append(item_id)  # type: ignore[union-attr]
    for raw_entry in coverage.get("entries", []):
        if not isinstance(raw_entry, dict):
            continue
        if raw_entry.get("requires_confirmation") is not True:
            continue
        source_id = raw_entry.get("source_location_id")
        if not isinstance(source_id, str):
            continue
        geometry = observations.get(source_id)
        if geometry is None:
            continue
        sources.setdefault(
            source_id,
            {
                "item_ids": [],
                "page_index": geometry["page_index"],
                "bbox_pdf": geometry["bbox_pdf"],
                "raw_text": geometry.get("raw_text", ""),
            },
        )
    return sorted(candidates, key=lambda value: str(value["id"])), sources


def _is_bbox(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(coordinate, (int, float)) for coordinate in value)
    )


def _working_copy(working: ReviewWorkingCopy) -> dict[str, object]:
    return {
        "id": working.id,
        "project_id": working.project_id,
        "raw_result_id": working.raw_result_id,
        "version": working.version,
        "items": working.items,
        "coverage": working.coverage,
        "sip_metadata": working.sip_metadata,
        "numbering_stale": working.numbering_stale,
        "items_frozen_at": working.items_frozen_at,
        "items_frozen_by": working.items_frozen_by,
        "items_frozen_version": working.items_frozen_version,
    }


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
