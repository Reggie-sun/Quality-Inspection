from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[4]
HARNESS = ROOT / ".agent/harness"
SCHEMA_PATH = HARNESS / "schemas/symbol-routing-canary-evidence.schema.json"
COLLECTOR_PATH = HARNESS / "scripts/symbol_canary_evidence.py"
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
TEST_REFS = [
    "backend/tests/unit/candidates/test_symbol_routing.py::"
    "test_concurrent_budget_window_denial_reserves_zero_members",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_concurrent_schema_failures_reserve_exactly_one_project_retry",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_actual_wall_budget_stops_queued_job_with_fake_clock",
    "backend/tests/unit/candidates/test_advisor.py::"
    "test_actual_primary_wall_blocks_retry_before_second_call",
]


def _load_module(name: str, path: Path) -> ModuleType:
    assert path.is_file(), f"missing PRT-8 Step 0 artifact: {path.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _collector() -> ModuleType:
    return _load_module("test_symbol_canary_evidence", COLLECTOR_PATH)


def _schema() -> dict[str, Any]:
    assert SCHEMA_PATH.is_file(), "missing PRT-8 Step 0 evidence schema"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _sha(value: int) -> str:
    return f"{value:064x}"


def _call_record(
    request_id: str,
    duration_ms: int,
    retry_count: int,
) -> dict[str, Any]:
    return {
        "provider": "qwen-vl",
        "request_id": request_id,
        "model": "qwen3-vl-plus-2025-12-19",
        "prompt_version": "visual-symbol-prompt/4",
        "schema_version": "visual-symbol-review/2",
        "duration_ms": duration_ms,
        "retry_count": retry_count,
        "input_image_count": 1,
        "estimated_cost": None,
        "logical_task_reused": False,
        "request_ref": f"asset://safe/requests/{request_id}.json",
        "response_ref": f"asset://safe/responses/{request_id}.json",
    }


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _write_call_record(
    storage_root: Path,
    request_id: str,
    duration_ms: int,
    retry_count: int,
    *,
    retry: bool = False,
) -> Path:
    family = "qwen-symbol-retries" if retry else "qwen-symbol"
    path = (
        storage_root
        / f"projects/{PROJECT_ID}/provider-calls/{family}/{request_id}.json"
    )
    _write_json(path, _call_record(request_id, duration_ms, retry_count))
    return path


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    storage_root = tmp_path / "storage"
    inventory_ref = f"asset://projects/{PROJECT_ID}/inventory/inventory.json"
    visual_ids = (
        "visual-local",
        "visual-main-a",
        "visual-main-b",
        "visual-blocked",
        "visual-cache",
        "visual-retry",
    )
    inventory = {
        "schema_version": "page-inventory/1",
        "pages": [
            {
                "page_index": 0,
                "visual_observations": [
                    {"observation_id": value, "page_index": 0}
                    for value in visual_ids[:4]
                ],
            },
            {
                "page_index": 1,
                "visual_observations": [
                    {"observation_id": value, "page_index": 1}
                    for value in visual_ids[4:]
                ],
            },
        ],
    }
    _write_json(
        storage_root / f"projects/{PROJECT_ID}/inventory/inventory.json",
        inventory,
    )
    _write_call_record(storage_root, "req-primary", 1000, 0)
    _write_call_record(storage_root, "req-retry-primary", 2000, 0)
    _write_call_record(
        storage_root,
        "req-retry-secondary",
        3000,
        1,
        retry=True,
    )
    cache_record = _write_call_record(
        storage_root,
        "req-cache-producer",
        4000,
        0,
    )
    cache_entry_id = "22222222-2222-4222-8222-222222222222"
    decisions = [
        {
            "visual_observation_id": "visual-local",
            "escalation_group_id": None,
            "escalation_group_member_index": None,
            "disposition": "locally_resolved",
            "local_resolution_reason_codes": ["deterministic_geometry_complete"],
            "escalation_reason_codes": [],
            "block_reason_codes": [],
        },
        {
            "visual_observation_id": "visual-main-a",
            "escalation_group_id": "group-main",
            "escalation_group_member_index": 0,
            "disposition": "escalate",
            "local_resolution_reason_codes": [],
            "escalation_reason_codes": ["unknown_symbol_pattern"],
            "block_reason_codes": [],
        },
        {
            "visual_observation_id": "visual-main-b",
            "escalation_group_id": "group-main",
            "escalation_group_member_index": 1,
            "disposition": "escalate",
            "local_resolution_reason_codes": [],
            "escalation_reason_codes": ["unknown_symbol_pattern"],
            "block_reason_codes": [],
        },
        {
            "visual_observation_id": "visual-blocked",
            "escalation_group_id": None,
            "escalation_group_member_index": None,
            "disposition": "block",
            "local_resolution_reason_codes": [],
            "escalation_reason_codes": [],
            "block_reason_codes": ["coverage_lineage_incomplete"],
        },
        {
            "visual_observation_id": "visual-cache",
            "escalation_group_id": "group-cache",
            "escalation_group_member_index": 0,
            "disposition": "escalate",
            "local_resolution_reason_codes": [],
            "escalation_reason_codes": ["unknown_symbol_pattern"],
            "block_reason_codes": [],
        },
        {
            "visual_observation_id": "visual-retry",
            "escalation_group_id": "group-retry",
            "escalation_group_member_index": 0,
            "disposition": "escalate",
            "local_resolution_reason_codes": [],
            "escalation_reason_codes": ["unknown_symbol_pattern"],
            "block_reason_codes": [],
        },
    ]
    attempts = [
        {
            "escalation_group_id": "group-main",
            "routing_decision_sha256": _sha(1),
            "attempt_index": 0,
            "event_code": "provider_response_valid",
            "cache_entry_id": None,
            "provider_request_id": "req-primary",
            "event_sha256": _sha(11),
        },
        {
            "escalation_group_id": "group-cache",
            "routing_decision_sha256": _sha(2),
            "attempt_index": 0,
            "event_code": "cache_hit_valid",
            "cache_entry_id": cache_entry_id,
            "provider_request_id": None,
            "event_sha256": _sha(12),
        },
        {
            "escalation_group_id": "group-retry",
            "routing_decision_sha256": _sha(3),
            "attempt_index": 0,
            "event_code": "provider_schema_invalid",
            "cache_entry_id": None,
            "provider_request_id": "req-retry-primary",
            "event_sha256": _sha(13),
        },
        {
            "escalation_group_id": "group-retry",
            "routing_decision_sha256": _sha(3),
            "attempt_index": 0,
            "event_code": "retry_scheduled",
            "cache_entry_id": None,
            "provider_request_id": "req-retry-primary",
            "event_sha256": _sha(14),
        },
        {
            "escalation_group_id": "group-retry",
            "routing_decision_sha256": _sha(3),
            "attempt_index": 1,
            "event_code": "provider_response_valid",
            "cache_entry_id": None,
            "provider_request_id": "req-retry-secondary",
            "event_sha256": _sha(15),
        },
    ]
    outcomes = [
        {
            "escalation_group_id": "group-main",
            "routing_decision_sha256": _sha(1),
            "outcome_code": "resolved",
            "observation_outcomes": [
                {
                    "visual_observation_id": "visual-main-a",
                    "outcome_code": "provider_resolved",
                },
                {
                    "visual_observation_id": "visual-main-b",
                    "outcome_code": "provider_resolved",
                },
            ],
            "terminal": True,
        },
        {
            "escalation_group_id": "group-cache",
            "routing_decision_sha256": _sha(2),
            "outcome_code": "resolved",
            "observation_outcomes": [
                {
                    "visual_observation_id": "visual-cache",
                    "outcome_code": "cache_resolved",
                },
            ],
            "terminal": True,
        },
        {
            "escalation_group_id": "group-retry",
            "routing_decision_sha256": _sha(3),
            "outcome_code": "resolved",
            "observation_outcomes": [
                {
                    "visual_observation_id": "visual-retry",
                    "outcome_code": "provider_resolved",
                },
            ],
            "terminal": True,
        },
    ]
    bundle = {
        "automatic_result": {
            "project_id": PROJECT_ID,
            "inventory_ref": inventory_ref,
            "coverage": {
                "entries": [
                    *({"observation_id": value} for value in visual_ids),
                    {"observation_id": "text-observation"},
                ],
            },
            "completeness": "partial_review_required",
            "recognition_mode": "production_uncertainty",
            "router_version": "symbol-uncertainty-router/1",
            "recognition_evidence_ref": (
                f"asset://projects/{PROJECT_ID}/routing/evidence.json"
            ),
        },
        "decisions": decisions,
        "attempts": attempts,
        "outcomes": outcomes,
        "cache_entries": [
            {
                "id": cache_entry_id,
                "producer_request_id": "req-cache-producer",
                "producer_call_record_ref": (
                    "asset://" + str(cache_record.relative_to(storage_root))
                ),
            },
        ],
    }
    return bundle, storage_root


def _build(
    module: ModuleType,
    bundle: dict[str, Any],
    storage_root: Path,
) -> dict[str, Any]:
    return module.build_canary_evidence(
        project_id=PROJECT_ID,
        bundle=bundle,
        storage_root=storage_root,
    )


def test_closed_schema_accepts_one_sanitized_ledger(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)

    evidence = _build(module, bundle, storage_root)

    jsonschema.Draft202012Validator(
        _schema(),
        format_checker=jsonschema.FormatChecker(),
    ).validate(evidence)
    assert evidence["counts"] == {
        "admitted": 6,
        "locally_resolved": 1,
        "escalated": 4,
        "blocked": 1,
        "deduped_groups": 3,
        "cache_reuses": 1,
        "primary_calls": 2,
        "retry_calls": 1,
        "external_calls": 3,
        "unresolved": 1,
    }
    assert evidence["recognition_identity"]["completeness"] == (
        "partial_review_required"
    )
    assert evidence["reason_distribution"] == [
        {"code": "coverage_lineage_incomplete", "count": 1},
        {"code": "deterministic_geometry_complete", "count": 1},
        {"code": "unknown_symbol_pattern", "count": 4},
    ]
    assert evidence["group_outcome_distribution"] == [
        {"code": "resolved", "count": 3},
    ]
    assert evidence["observation_outcome_distribution"] == [
        {"code": "cache_resolved", "count": 1},
        {"code": "provider_resolved", "count": 3},
    ]
    assert evidence["page_ledgers"] == [
        {
            "page_index": 0,
            "visual_observations": 4,
            "primary_calls": 1,
            "retry_calls": 0,
            "external_calls": 1,
            "duration_ms": 1000,
        },
        {
            "page_index": 1,
            "visual_observations": 2,
            "primary_calls": 1,
            "retry_calls": 1,
            "external_calls": 2,
            "duration_ms": 5000,
        },
    ]
    assert evidence["project_ledger"] == {
        "primary_calls": 2,
        "retry_calls": 1,
        "external_calls": 3,
        "duration_ms": 6000,
    }
    assert evidence["latency_distribution"] == {
        "sample_count": 1,
        "durations_ms": [6000],
        "p50_eligible": False,
        "p95_eligible": False,
    }
    assert evidence["live_concurrency_observable"] is False
    assert evidence["carried_offline_evidence"] == {
        "in_flight_limit": 2,
        "test_refs": TEST_REFS,
    }
    assert evidence["promotion_eligible"] is False
    assert [
        (item["request_id"], item["page_index"], item["attempt_index"])
        for item in evidence["call_records"]
    ] == [
        ("req-primary", 0, 0),
        ("req-retry-primary", 1, 0),
        ("req-retry-secondary", 1, 1),
    ]
    assert "req-cache-producer" not in {
        item["request_id"] for item in evidence["call_records"]
    }


def test_schema_rejects_unowned_fields(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    evidence = _build(module, bundle, storage_root)
    evidence["candidate_semantics"] = {"owner": "harness"}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema()).validate(evidence)


def test_collector_rejects_coverage_gap(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    bundle["automatic_result"]["coverage"]["entries"] = [
        item
        for item in bundle["automatic_result"]["coverage"]["entries"]
        if item["observation_id"] != "visual-retry"
    ]

    with pytest.raises(ValueError, match="coverage"):
        _build(module, bundle, storage_root)


def test_collector_rejects_cross_page_group(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    decision = next(
        item
        for item in bundle["decisions"]
        if item["visual_observation_id"] == "visual-cache"
    )
    decision["escalation_group_id"] = "group-main"
    decision["escalation_group_member_index"] = 2

    with pytest.raises(ValueError, match="cross-page"):
        _build(module, bundle, storage_root)


def test_cache_producer_is_never_a_current_call(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    cache_event = next(
        item for item in bundle["attempts"] if item["event_code"] == "cache_hit_valid"
    )
    cache_event["provider_request_id"] = "req-cache-producer"

    with pytest.raises(ValueError, match="cache"):
        _build(module, bundle, storage_root)


@pytest.mark.parametrize("defect", ["missing", "duplicate"])
def test_current_call_requires_exactly_one_redacted_record(
    tmp_path: Path,
    defect: str,
) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    primary = (
        storage_root / f"projects/{PROJECT_ID}/provider-calls/qwen-symbol/"
        "req-primary.json"
    )
    if defect == "missing":
        primary.unlink()
    else:
        duplicate = (
            storage_root / f"projects/{PROJECT_ID}/provider-calls/"
            "qwen-symbol-retries/duplicate.json"
        )
        _write_json(duplicate, _call_record("req-primary", 1000, 0))

    with pytest.raises(ValueError, match="call record"):
        _build(module, bundle, storage_root)


def test_collector_rejects_private_call_record_fields(
    tmp_path: Path,
) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    primary = (
        storage_root / f"projects/{PROJECT_ID}/provider-calls/qwen-symbol/"
        "req-primary.json"
    )
    document = json.loads(primary.read_text(encoding="utf-8"))
    document["api_key"] = "must-not-enter-evidence"
    _write_json(primary, document)

    with pytest.raises(ValueError, match="call record"):
        _build(module, bundle, storage_root)


def test_collector_rejects_observed_budget_excess(tmp_path: Path) -> None:
    module = _collector()
    bundle, storage_root = _fixture(tmp_path)
    primary = (
        storage_root / f"projects/{PROJECT_ID}/provider-calls/qwen-symbol/"
        "req-primary.json"
    )
    _write_json(primary, _call_record("req-primary", 45001, 0))

    with pytest.raises(ValueError, match="page duration budget"):
        _build(module, bundle, storage_root)


def test_cli_accepts_only_isolated_database_and_four_required_flags() -> None:
    module = _collector()
    args = module.parse_args(
        [
            "--database-url",
            "postgresql+psycopg://qi:qi@qi-prt8-canary-postgres:5432/qi",
            "--storage-root",
            "/data",
            "--project-id",
            PROJECT_ID,
            "--schema",
            "/collector/symbol-routing-canary-evidence.schema.json",
        ]
    )
    assert args.project_id == PROJECT_ID
    module.validate_database_url(args.database_url)

    with pytest.raises(ValueError, match="isolated"):
        module.validate_database_url(
            "postgresql+psycopg://qi:qi@shared-postgres:5432/qi"
        )
    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--database-url",
                "postgresql+psycopg://qi:qi@qi-prt8-canary-postgres:5432/qi",
                "--storage-root",
                "/data",
                "--project-id",
                str(uuid.UUID(PROJECT_ID)),
                "--schema",
                "/collector/symbol-routing-canary-evidence.schema.json",
                "--extra",
                "forbidden",
            ]
        )
