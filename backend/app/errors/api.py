from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from fastapi.responses import JSONResponse

from app.errors.schemas import ErrorDetail, ErrorEnvelope, ErrorSeverity


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    severity: ErrorSeverity,
    stage: str,
    location_ref: str | None = None,
    cause_category: str | None = None,
    blockers: list[str] | None = None,
    project_id: uuid.UUID | None = None,
    retryable: bool | None = None,
    phase: str | None = None,
    workbench_ready: bool | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            severity=severity,
            stage=stage,
            location_ref=location_ref,
            cause_category=cause_category or _cause_category(status_code),
            blockers=blockers,
            project_id=project_id,
            retryable=retryable,
            phase=phase,
            workbench_ready=workbench_ready,
        )
    )
    payload = envelope.model_dump(mode="json", exclude_none=True)
    payload["error"]["location_ref"] = location_ref
    return JSONResponse(
        status_code=status_code,
        content=payload,
    )


def error_responses(
    codes_by_status: Mapping[int, Sequence[str]],
) -> dict[int, dict[str, object]]:
    return {
        status: {
            "model": ErrorEnvelope,
            "description": _status_description(status),
            "x-stable-error-codes": list(codes),
        }
        for status, codes in codes_by_status.items()
    }


def _cause_category(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "validation"
    if status_code >= 500:
        return "internal"
    return "request"


def _status_description(status_code: int) -> str:
    return {
        404: "Requested resource was not found.",
        409: "Request conflicts with current aggregate or capability state.",
        422: "Request failed transport or business validation.",
        500: "Unexpected internal failure.",
        503: "Required dispatch or service is unavailable.",
    }.get(status_code, "Request failed.")
