from __future__ import annotations

import json
from pathlib import Path

from fastapi.routing import APIRoute

from app.main import app


EXPECTED_OPERATIONS = {
    ("GET", "/api/v1/health"): "QI-API-SYS-001",
    ("POST", "/api/v1/projects"): "QI-API-PRJ-001",
    ("GET", "/api/v1/projects/{project_id}/status"): "QI-API-PRJ-002",
    ("GET", "/api/v1/projects/{project_id}/workbench"): "QI-API-PRJ-003",
    ("GET", "/api/v1/projects/{project_id}/source-pdf"): "QI-API-PRJ-004",
    (
        "GET",
        "/api/v1/projects/{project_id}/recognition-preview",
    ): "QI-API-PRJ-005",
    ("POST", "/api/v1/projects/{project_id}/review/lock"): "QI-API-REV-001",
    (
        "GET",
        "/api/v1/projects/{project_id}/review/working-copy",
    ): "QI-API-REV-002",
    (
        "POST",
        "/api/v1/projects/{project_id}/review/commands",
    ): "QI-API-REV-003",
    (
        "POST",
        "/api/v1/projects/{project_id}/review/freeze-items",
    ): "QI-API-REV-004",
    (
        "POST",
        "/api/v1/projects/{project_id}/review/confirm",
    ): "QI-API-REV-005",
    ("GET", "/api/v1/projects/{project_id}/balloons"): "QI-API-BAL-001",
    (
        "POST",
        "/api/v1/projects/{project_id}/balloons/generate",
    ): "QI-API-BAL-002",
    (
        "POST",
        "/api/v1/projects/{project_id}/balloons/commands",
    ): "QI-API-BAL-003",
    ("POST", "/api/v1/projects/{project_id}/exports"): "QI-API-EXP-001",
    ("GET", "/api/v1/exports/{export_id}"): "QI-API-EXP-002",
    (
        "GET",
        "/api/v1/exports/{export_id}/downloads/{kind}",
    ): "QI-API-EXP-003",
}

BINARY_OPERATIONS = {
    ("GET", "/api/v1/projects/{project_id}/source-pdf"): {
        "application/pdf",
    },
    ("GET", "/api/v1/exports/{export_id}/downloads/{kind}"): {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
    },
}

SNAPSHOT = (
    Path(__file__).parent
    / "snapshots"
    / "api-v1.openapi.json"
)
API_INDEX = Path(__file__).parents[3] / "docs" / "contracts" / "API_SURFACE_INDEX.md"


def _formal_routes() -> dict[tuple[str, str], APIRoute]:
    routes: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        candidates = (
            route.original_router.routes
            if type(route).__name__ == "_IncludedRouter"
            else [route]
        )
        for candidate in candidates:
            if (
                not isinstance(candidate, APIRoute)
                or not candidate.path.startswith("/api/v1")
            ):
                continue
            for method in candidate.methods:
                routes[(method, candidate.path)] = candidate
    return routes


def test_formal_routes_have_stable_ids_and_explicit_response_models() -> None:
    """Catches unregistered operations and implicit JSON success schemas."""
    routes = _formal_routes()

    assert set(routes) == set(EXPECTED_OPERATIONS)
    for key, operation_id in EXPECTED_OPERATIONS.items():
        route = routes[key]
        assert route.operation_id == operation_id
        if key in BINARY_OPERATIONS:
            assert route.response_model is None
        else:
            assert route.response_model is not None


def test_openapi_projects_json_and_binary_success_contracts() -> None:
    """Catches empty JSON responses and binary endpoints projected as JSON."""
    document = app.openapi()

    for (method, path), operation_id in EXPECTED_OPERATIONS.items():
        operation = document["paths"][path][method.lower()]
        assert operation["operationId"] == operation_id
        success = operation["responses"][next(
            code for code in operation["responses"] if code.startswith("2")
        )]
        content = success["content"]
        if (method, path) in BINARY_OPERATIONS:
            assert set(content) == BINARY_OPERATIONS[(method, path)]
        else:
            schema = content["application/json"]["schema"]
            assert schema
            assert schema != {}


def test_openapi_documents_the_unified_error_contract() -> None:
    """Catches endpoints that expose framework-default or undocumented errors."""
    document = app.openapi()

    for (method, path) in EXPECTED_OPERATIONS:
        operation = document["paths"][path][method.lower()]
        error_responses = {
            code: response
            for code, response in operation["responses"].items()
            if code.startswith(("4", "5"))
        }
        assert error_responses, f"{method} {path} has no error responses"
        for response in error_responses.values():
            schema = response["content"]["application/json"]["schema"]
            assert schema == {
                "$ref": "#/components/schemas/ErrorEnvelope",
            }


def test_recognition_preview_documents_its_read_only_error_contract() -> None:
    """Catches a preview route that omits its explicit unavailable-state errors."""
    responses = app.openapi()["paths"][
        "/api/v1/projects/{project_id}/recognition-preview"
    ]["get"]["responses"]

    assert {"404", "409", "422", "500"} <= set(responses)
    for status in ("404", "409", "422", "500"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope",
        }


def test_openapi_matches_the_approved_api_v1_snapshot() -> None:
    """Catches any current projection drift from the reviewed API-v1 baseline."""
    assert SNAPSHOT.is_file(), "approved API-v1 OpenAPI snapshot is missing"
    approved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert app.openapi() == approved


def test_human_api_index_projects_every_formal_operation_once() -> None:
    """Catches the derived index omitting or misidentifying a formal operation."""
    indexed: dict[tuple[str, str], str] = {}
    for line in API_INDEX.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `QI-API-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        operation_id = cells[0].strip("`")
        method, path = cells[1].strip("`").split(" ", 1)
        indexed[(method, path)] = operation_id

    assert indexed == EXPECTED_OPERATIONS
