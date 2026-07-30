from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.contracts.openapi import find_breaking_changes


SNAPSHOT = Path(__file__).parent / "snapshots" / "api-v1.openapi.json"


def _baseline() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/widgets/{widget_id}": {
                "get": {
                    "operationId": "QI-API-WID-001",
                    "parameters": [
                        {
                            "name": "widget_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Widget"
                                    }
                                }
                            }
                        },
                        "404": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ErrorEnvelope"
                                    }
                                }
                            }
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Widget": {
                    "type": "object",
                    "required": ["id", "state"],
                    "properties": {
                        "id": {"type": "string"},
                        "state": {
                            "type": "string",
                            "enum": ["queued", "ready", "failed"],
                        },
                    },
                },
                "ErrorEnvelope": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "object"},
                    },
                },
            }
        },
    }


def test_breaking_gate_allows_additive_optional_fields_and_enum_values() -> None:
    """Catches a gate that rejects reader-compatible additive evolution."""
    current = deepcopy(_baseline())
    widget = current["components"]["schemas"]["Widget"]
    widget["properties"]["label"] = {"type": ["string", "null"]}
    widget["properties"]["state"]["enum"].append("archived")

    assert find_breaking_changes(_baseline(), current) == []


def test_breaking_gate_rejects_operation_deletion_or_rename() -> None:
    """Catches removal of a method/path operation from API v1."""
    current = deepcopy(_baseline())
    del current["paths"]["/widgets/{widget_id}"]["get"]

    assert any(
        "operation removed" in change
        for change in find_breaking_changes(_baseline(), current)
    )


def test_breaking_gate_rejects_property_type_change() -> None:
    """Catches request or response field type drift."""
    current = deepcopy(_baseline())
    current["components"]["schemas"]["Widget"]["properties"]["id"] = {
        "type": "integer"
    }

    assert any(
        "type changed" in change
        for change in find_breaking_changes(_baseline(), current)
    )


def test_breaking_gate_rejects_required_set_change() -> None:
    """Catches both newly required and no-longer-required API-v1 fields."""
    current = deepcopy(_baseline())
    current["components"]["schemas"]["Widget"]["required"].remove("state")

    assert any(
        "required changed" in change
        for change in find_breaking_changes(_baseline(), current)
    )


def test_breaking_gate_rejects_enum_shrink() -> None:
    """Catches removal of an accepted or emitted enum value."""
    current = deepcopy(_baseline())
    current["components"]["schemas"]["Widget"]["properties"]["state"][
        "enum"
    ].remove("failed")

    assert any(
        "enum values removed" in change
        for change in find_breaking_changes(_baseline(), current)
    )


def test_breaking_gate_rejects_response_status_change() -> None:
    """Catches success or error response status deletion/change."""
    current = deepcopy(_baseline())
    responses = current["paths"]["/widgets/{widget_id}"]["get"]["responses"]
    responses["201"] = responses.pop("200")

    assert any(
        "response statuses removed" in change
        for change in find_breaking_changes(_baseline(), current)
    )


def _real_snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_real_snapshot_rejects_new_required_parameter() -> None:
    """Catches required request inputs added outside the baseline parameter set."""
    baseline = _real_snapshot()
    current = deepcopy(baseline)
    operation = current["paths"]["/api/v1/health"]["get"]
    operation.setdefault("parameters", []).append(
        {
            "name": "X-QI-Required",
            "in": "header",
            "required": True,
            "schema": {"type": "string"},
        }
    )

    assert any(
        "required parameter added" in change
        for change in find_breaking_changes(baseline, current)
    )


def test_real_snapshot_rejects_request_body_required_change() -> None:
    """Catches an optional request body becoming required."""
    baseline = _real_snapshot()
    current = deepcopy(baseline)
    baseline_operation = baseline["paths"]["/api/v1/projects"]["post"]
    current_operation = current["paths"]["/api/v1/projects"]["post"]
    baseline_operation["requestBody"]["required"] = False
    current_operation["requestBody"]["required"] = True

    assert any(
        "request body: required changed" in change
        for change in find_breaking_changes(baseline, current)
    )


def test_real_snapshot_rejects_stable_error_code_removal() -> None:
    """Catches stable machine code removal even when status/schema stay intact."""
    baseline = _real_snapshot()
    current = deepcopy(baseline)
    response = current["paths"]["/api/v1/projects"]["post"]["responses"]["422"]
    response["x-stable-error-codes"].remove("invalid_pdf")

    assert any(
        "stable error codes removed" in change
        for change in find_breaking_changes(baseline, current)
    )


def test_real_snapshot_rejects_discriminator_const_change() -> None:
    """Catches command rename represented by an OpenAPI 3.1 const change."""
    baseline = _real_snapshot()
    current = deepcopy(baseline)
    current["components"]["schemas"]["MoveBalloon"]["properties"]["type"][
        "const"
    ] = "move_v2"

    assert any(
        "const changed" in change
        for change in find_breaking_changes(baseline, current)
    )
