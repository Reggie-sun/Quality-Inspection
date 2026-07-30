from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projects.router import get_project_service
from app.projects.service import ProjectNotFound


REQUIRED_ERROR_FIELDS = {
    "code",
    "message",
    "severity",
    "stage",
    "location_ref",
    "cause_category",
}


def _assert_error_envelope(response, *, status: int, code: str) -> None:
    assert response.status_code == status
    payload = response.json()
    assert set(payload) == {"error"}
    assert REQUIRED_ERROR_FIELDS <= set(payload["error"])
    assert payload["error"]["code"] == code
    assert payload["error"]["severity"] in {
        "fatal",
        "blocking",
        "review_required",
        "warning",
        "informational",
    }


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_framework_validation_error_uses_the_stable_envelope() -> None:
    """Catches FastAPI's default ``detail`` validation response leaking out."""
    app.dependency_overrides[get_project_service] = object
    with TestClient(app) as client:
        response = client.get("/api/v1/projects/not-a-uuid/status")

    _assert_error_envelope(
        response,
        status=422,
        code="request_validation_failed",
    )


def test_framework_not_found_error_uses_the_stable_envelope() -> None:
    """Catches Starlette's default ``detail`` 404 response leaking out."""
    with TestClient(app) as client:
        response = client.get("/api/v1/not-a-formal-endpoint")

    _assert_error_envelope(
        response,
        status=404,
        code="route_not_found",
    )


def test_business_error_uses_the_same_stable_envelope() -> None:
    """Catches per-router error bodies diverging from the global envelope."""

    class MissingProjectService:
        def status(self, project_id: uuid.UUID) -> None:
            raise ProjectNotFound(project_id)

    app.dependency_overrides[get_project_service] = MissingProjectService
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001/status"
        )

    _assert_error_envelope(
        response,
        status=404,
        code="project_not_found",
    )


def test_unhandled_error_is_sanitized_into_the_stable_envelope() -> None:
    """Catches raw exceptions and framework-default 500 bodies."""

    def crash_before_route() -> None:
        raise RuntimeError("sensitive internal detail")

    app.dependency_overrides[get_project_service] = crash_before_route
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001/status"
        )

    _assert_error_envelope(
        response,
        status=500,
        code="internal_server_error",
    )
    assert "sensitive internal detail" not in response.text
