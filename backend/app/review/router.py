from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors.api import api_error, error_responses
from app.errors.schemas import ErrorSeverity
from app.projects.lifecycle import (
    ProjectAccess,
    ProjectLifecycleNotFound,
    ProjectLifecycleService,
)
from app.review.locks import LockConflict, LockRequired, acquire_lock, release_lock
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.review.schemas import (
    ConfirmReviewRequest,
    FreezeItemsRequest,
    LockRequest,
    ReleaseLockRequest,
    ReviewedResultResponse,
    ReviewCommandRequest,
    ReviewLockReleaseResponse,
    ReviewLockResponse,
    ReviewWorkingCopyResponse,
    normalize_sip_metadata,
)
from app.review.service import (
    FreezeBlocked,
    ItemsFrozen,
    ReviewConfirmationBlocked,
    ReviewNotFound,
    ReviewService,
    ReviewVersionConflict,
    manual_review_count,
)


router = APIRouter(prefix="/api/v1/projects", tags=["review"])


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


OperatorHeader = Annotated[str, Header(alias="X-QI-Operator")]
SessionDependency = Annotated[Session, Depends(get_session)]


def get_review_service(session: SessionDependency) -> ReviewService:
    return ReviewService(session)


ReviewServiceDependency = Annotated[ReviewService, Depends(get_review_service)]


@router.post(
    "/{project_id}/review/lock",
    operation_id="QI-API-REV-001",
    response_model=ReviewLockResponse,
    responses=error_responses(
        {
            404: ("project_not_found",),
            409: ("review_lock_conflict",),
            422: ("request_validation_failed",),
            500: ("internal_server_error",),
        }
    ),
)
def lock_review(
    project_id: uuid.UUID,
    body: LockRequest,
    operator_id: OperatorHeader,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        lock = acquire_lock(
            session,
            project_id,
            operator_id,
            ttl_seconds=body.ttl_seconds,
        )
    except (LockConflict, ValueError) as error:
        return _error(409, "review_lock_conflict", str(error))
    except LookupError as error:
        return _error(404, "project_not_found", str(error))
    return {
        "project_id": lock.project_id,
        "operator_id": lock.operator_id,
        "expires_at": lock.expires_at,
    }


@router.post(
    "/{project_id}/review/lock/release",
    operation_id="QI-API-REV-006",
    response_model=ReviewLockReleaseResponse,
    responses=error_responses(
        {
            404: ("project_not_found",),
            422: ("review_operator_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def release_review_lock(
    project_id: uuid.UUID,
    body: ReleaseLockRequest,
    operator_id: OperatorHeader,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        released = release_lock(
            session,
            project_id,
            operator_id,
            expires_at=body.expires_at,
        )
    except ValueError as error:
        return _error(422, "review_operator_invalid", str(error))
    except LookupError as error:
        return _error(404, "project_not_found", str(error))
    return {
        "project_id": project_id,
        "released": released,
    }


@router.get(
    "/{project_id}/review/working-copy",
    operation_id="QI-API-REV-002",
    response_model=ReviewWorkingCopyResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "review_working_copy_not_found"),
            422: ("request_validation_failed",),
            500: ("internal_server_error",),
        }
    ),
)
def get_working_copy(
    project_id: uuid.UUID,
    service: ReviewServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        working = service.get_for_project(project_id)
    except ReviewNotFound as error:
        return _error(404, "review_working_copy_not_found", str(error))
    return _working_copy(working)


@router.post(
    "/{project_id}/review/commands",
    operation_id="QI-API-REV-003",
    response_model=ReviewWorkingCopyResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "review_working_copy_not_found"),
            409: (
                "review_version_conflict",
                "review_items_frozen",
                "review_lock_conflict",
            ),
            422: ("review_command_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def apply_command(
    project_id: uuid.UUID,
    body: ReviewCommandRequest,
    operator_id: OperatorHeader,
    service: ReviewServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        working = service.get_for_project(project_id)
        saved = service.apply(
            working.id,
            expected_version=body.expected_version,
            operator_id=operator_id,
            command=body.command.model_dump(mode="json"),
        )
    except ReviewVersionConflict as error:
        return _error(409, "review_version_conflict", str(error))
    except ItemsFrozen as error:
        return _error(409, "review_items_frozen", str(error))
    except (LockConflict, LockRequired) as error:
        return _error(409, "review_lock_conflict", str(error))
    except ReviewNotFound as error:
        return _error(404, "review_working_copy_not_found", str(error))
    except ValueError as error:
        return _error(422, "review_command_invalid", str(error))
    return _working_copy(saved)


@router.post(
    "/{project_id}/review/freeze-items",
    operation_id="QI-API-REV-004",
    response_model=ReviewWorkingCopyResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "review_working_copy_not_found"),
            409: (
                "review_version_conflict",
                "coverage_blocking",
                "unresolved_confirmation",
                "balloon_required_unconfirmed",
                "review_items_frozen",
                "review_lock_conflict",
            ),
            422: ("review_operator_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def freeze_items(
    project_id: uuid.UUID,
    body: FreezeItemsRequest,
    operator_id: OperatorHeader,
    service: ReviewServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        working = service.get_for_project(project_id)
        frozen = service.freeze_items(
            working.id,
            expected_version=body.expected_version,
            operator_id=operator_id,
        )
    except ReviewVersionConflict as error:
        return _error(409, "review_version_conflict", str(error))
    except FreezeBlocked as error:
        return _error(
            409,
            error.code,
            str(error),
            blockers=list(error.blockers),
        )
    except ItemsFrozen as error:
        return _error(409, "review_items_frozen", str(error))
    except (LockConflict, LockRequired) as error:
        return _error(409, "review_lock_conflict", str(error))
    except ReviewNotFound as error:
        return _error(404, "review_working_copy_not_found", str(error))
    except ValueError as error:
        return _error(422, "review_operator_invalid", str(error))
    return _working_copy(frozen)


@router.post(
    "/{project_id}/review/confirm",
    operation_id="QI-API-REV-005",
    response_model=ReviewedResultResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "review_working_copy_not_found"),
            409: (
                "review_version_conflict",
                "item_set_not_frozen",
                "numbering_stale",
                "sip_metadata_unconfirmed",
                "sip_detail_fields_unconfirmed",
                "missing_required_balloon",
                "item_balloon_disconnect",
                "manual_required",
                "unreadable_number",
                "outside_cropbox",
                "owner_glyph_outside_circle",
                "protected_overlap",
                "source_text_overlap",
                "invalid_leader",
                "circle_overlap",
                "glyph_overlap",
                "glyph_circle_overlap",
                "duplicate_or_gapped_number",
                "review_lock_conflict",
            ),
            422: ("review_confirmation_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def confirm_review(
    project_id: uuid.UUID,
    body: ConfirmReviewRequest,
    operator_id: OperatorHeader,
    service: ReviewServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        working = service.get_for_project(project_id)
        reviewed = service.confirm(
            working.id,
            expected_version=body.expected_version,
            operator_id=operator_id,
        )
    except ReviewVersionConflict as error:
        return _error(409, "review_version_conflict", str(error))
    except (FreezeBlocked, ReviewConfirmationBlocked) as error:
        return _error(
            409,
            error.code,
            str(error),
            blockers=list(error.blockers),
        )
    except (LockConflict, LockRequired) as error:
        return _error(409, "review_lock_conflict", str(error))
    except ReviewNotFound as error:
        return _error(404, "review_working_copy_not_found", str(error))
    except ValueError as error:
        return _error(422, "review_confirmation_invalid", str(error))
    return _reviewed_result(reviewed)


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


def _working_copy(working: ReviewWorkingCopy) -> dict[str, object]:
    coverage = ReviewService.normalized_coverage(
        working.coverage,
        working.technical_requirements,
    )
    return {
        "id": working.id,
        "project_id": working.project_id,
        "raw_result_id": working.raw_result_id,
        "version": working.version,
        "items": working.items,
        "coverage": coverage,
        "technical_requirements": working.technical_requirements,
        "sip_metadata": normalize_sip_metadata(working.sip_metadata),
        "numbering_stale": working.numbering_stale,
        "items_frozen_at": working.items_frozen_at,
        "items_frozen_by": working.items_frozen_by,
        "items_frozen_version": working.items_frozen_version,
        "created_at": working.created_at,
        "updated_at": working.updated_at,
        "manual_review_count": manual_review_count(
            working.items,
            coverage,
        ),
    }


def _reviewed_result(reviewed: ReviewedResult) -> dict[str, object]:
    return {
        "id": reviewed.id,
        "project_id": reviewed.project_id,
        "working_copy_id": reviewed.working_copy_id,
        "working_version": reviewed.working_version,
        "items": reviewed.items,
        "balloons": reviewed.balloons,
        "sip_metadata": reviewed.sip_metadata,
        "schema_version": reviewed.schema_version,
        "created_at": reviewed.created_at,
    }


def _error(
    status_code: int,
    code: str,
    message: str,
    severity: ErrorSeverity = "blocking",
    **details: object,
) -> JSONResponse:
    return api_error(
        status_code,
        code,
        message,
        severity=severity,
        stage="review_api",
        blockers=details.get("blockers"),
    )
