from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.balloons.models import Balloon
from app.balloons.schemas import (
    BalloonCommandRequest,
    BalloonCommandResponse,
    BalloonCollectionResponse,
    DeleteBalloon,
    GenerateBalloonsRequest,
    MoveBalloon,
    RebuildBalloon,
    RenumberBalloons,
    ReorderBalloon,
)
from app.balloons.service import (
    BalloonNotFound,
    BalloonOrderConflict,
    BalloonReviewFinalized,
    BalloonService,
    BalloonSourceUnavailable,
    BalloonVersionConflict,
    ItemSetNotFrozen,
)
from app.db import SessionLocal
from app.errors.api import api_error, error_responses
from app.errors.schemas import ErrorSeverity
from app.review.locks import LockConflict, LockRequired
from app.projects.lifecycle import (
    ProjectAccess,
    ProjectLifecycleNotFound,
    ProjectLifecycleService,
)


router = APIRouter(prefix="/api/v1/projects", tags=["balloons"])


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


SessionDependency = Annotated[Session, Depends(get_session)]
OperatorHeader = Annotated[str, Header(alias="X-QI-Operator")]


def get_balloon_service(session: SessionDependency) -> BalloonService:
    return BalloonService(session)


BalloonServiceDependency = Annotated[BalloonService, Depends(get_balloon_service)]


@router.get(
    "/{project_id}/balloons",
    operation_id="QI-API-BAL-001",
    response_model=BalloonCollectionResponse,
    responses=error_responses(
        {
            404: ("project_not_found",),
            422: ("request_validation_failed",),
            500: ("internal_server_error",),
        }
    ),
)
def list_balloons(
    project_id: uuid.UUID,
    service: BalloonServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    return {
        "balloons": [
            _balloon(balloon)
            for balloon in service.list_for_project(project_id)
        ]
    }


@router.post(
    "/{project_id}/balloons/generate",
    operation_id="QI-API-BAL-002",
    response_model=BalloonCollectionResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "review_working_copy_not_found"),
            409: (
                "review_item_set_not_frozen",
                "balloon_version_conflict",
                "review_lock_conflict",
                "balloon_source_unavailable",
                "balloon_order_conflict",
                "review_already_confirmed",
            ),
            422: ("balloon_command_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def generate_balloons(
    project_id: uuid.UUID,
    body: GenerateBalloonsRequest,
    operator_id: OperatorHeader,
    service: BalloonServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        balloons = service.generate_formal(
            project_id,
            expected_version=body.expected_version,
            operator_id=operator_id,
        )
    except ItemSetNotFrozen as error:
        return _error(409, "review_item_set_not_frozen", str(error))
    except BalloonVersionConflict as error:
        return _error(409, "balloon_version_conflict", str(error))
    except (LockConflict, LockRequired) as error:
        return _error(409, "review_lock_conflict", str(error))
    except BalloonSourceUnavailable as error:
        return _error(409, "balloon_source_unavailable", str(error))
    except BalloonOrderConflict as error:
        return _error(409, "balloon_order_conflict", str(error))
    except BalloonReviewFinalized as error:
        return _error(409, "review_already_confirmed", str(error))
    except BalloonNotFound as error:
        return _error(404, "review_working_copy_not_found", str(error))
    except ValueError as error:
        return _error(422, "balloon_command_invalid", str(error))
    return {"balloons": [_balloon(balloon) for balloon in balloons]}


@router.post(
    "/{project_id}/balloons/commands",
    operation_id="QI-API-BAL-003",
    response_model=BalloonCommandResponse,
    responses=error_responses(
        {
            404: ("project_not_found", "balloon_not_found"),
            409: (
                "balloon_version_conflict",
                "review_lock_conflict",
                "balloon_source_unavailable",
                "balloon_order_conflict",
                "review_already_confirmed",
            ),
            422: ("balloon_command_invalid", "request_validation_failed"),
            500: ("internal_server_error",),
        }
    ),
)
def apply_balloon_command(
    project_id: uuid.UUID,
    body: BalloonCommandRequest,
    operator_id: OperatorHeader,
    service: BalloonServiceDependency,
    session: SessionDependency,
) -> JSONResponse:
    guard = _active_project_error(session, project_id)
    if guard is not None:
        return guard
    try:
        if isinstance(body, RenumberBalloons):
            balloons = service.renumber(
                project_id,
                ordered_balloon_ids=body.ordered_balloon_ids,
                expected_versions=body.expected_versions,
                operator_id=operator_id,
            )
            return {"balloons": [_balloon(balloon) for balloon in balloons]}

        balloon = service.get(body.balloon_id)
        if balloon.project_id != project_id:
            raise BalloonNotFound(f"balloon {body.balloon_id} was not found")
        if isinstance(body, MoveBalloon):
            saved = service.move(
                body.balloon_id,
                center_pdf=body.center_pdf,
                expected_version=body.expected_version,
                operator_id=operator_id,
            )
        elif isinstance(body, DeleteBalloon):
            saved = service.delete(
                body.balloon_id,
                expected_version=body.expected_version,
                operator_id=operator_id,
            )
        elif isinstance(body, RebuildBalloon):
            saved = service.rebuild(
                body.balloon_id,
                expected_version=body.expected_version,
                operator_id=operator_id,
            )
        elif isinstance(body, ReorderBalloon):
            saved = service.reorder(
                body.balloon_id,
                sort_order=body.sort_order,
                expected_version=body.expected_version,
                operator_id=operator_id,
            )
        else:
            raise AssertionError(f"unsupported balloon command: {body.type}")
    except BalloonVersionConflict as error:
        return _error(409, "balloon_version_conflict", str(error))
    except (LockConflict, LockRequired) as error:
        return _error(409, "review_lock_conflict", str(error))
    except BalloonSourceUnavailable as error:
        return _error(409, "balloon_source_unavailable", str(error))
    except BalloonOrderConflict as error:
        return _error(409, "balloon_order_conflict", str(error))
    except BalloonReviewFinalized as error:
        return _error(409, "review_already_confirmed", str(error))
    except BalloonNotFound as error:
        return _error(404, "balloon_not_found", str(error))
    except ValueError as error:
        return _error(422, "balloon_command_invalid", str(error))
    return _balloon(saved)


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


def _balloon(balloon: Balloon) -> dict[str, object]:
    return balloon.snapshot()


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
        stage="balloon_api",
    )
