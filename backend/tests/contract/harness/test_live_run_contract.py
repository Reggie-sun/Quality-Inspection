from __future__ import annotations

import ast
import base64
import importlib.util
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import jsonschema
import pytest

from app.candidates.symbol_review import (
    build_visual_failure_envelope,
    build_visual_request_evidence,
    parse_visual_request_evidence,
)
from app.providers.call_records import ProviderCallRecord, serialize_call_record
from app.storage.local import LocalFileStorage


ROOT = Path(__file__).resolve().parents[4]
HARNESS = ROOT / ".agent/harness"
RUN_ID = "20260722T000000000000Z-00000000"
PHASES = ["process", "candidates", "review", "balloons", "export", "consistency"]
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606060000000050001a5f645400000000049454e44"
    "ae426082"
)
COMPARISON_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc0f01f00050001ff89993d1d0000000049454e44"
    "ae426082"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _embedded_function(
    program: str,
    name: str,
    namespace: dict[str, object] | None = None,
):
    functions = [
        node
        for node in ast.parse(program).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(functions) == 1, f"missing embedded function: {name}"
    module = ast.fix_missing_locations(
        ast.Module(body=functions, type_ignores=[])
    )
    execution_namespace = {} if namespace is None else dict(namespace)
    exec(
        compile(module, "<embedded-program>", "exec"),
        execution_namespace,
    )
    return execution_namespace[name]


def _schema(name: str) -> dict[str, object]:
    path = HARNESS / "schemas" / name
    assert path.is_file(), f"missing D7-T2 schema: {name}"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(document: dict[str, object], schema_name: str) -> None:
    jsonschema.Draft202012Validator(
        _schema(schema_name),
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)


def _validate_schema_definition(
    document: dict[str, object],
    name: str,
) -> None:
    schema = _schema("visual-symbol-eval.schema.json")
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    assert name in definitions, (
        f"missing PRT-7 visual-symbol-eval schema definition: {name}"
    )
    jsonschema.Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": definitions,
            "$ref": f"#/$defs/{name}",
        },
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)


def _identity(seed: str) -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "digest": seed * 64,
        "components": [f"test:{seed}"],
    }


def _run(execution_state: str = "running") -> dict[str, object]:
    return {
        "schema_version": "run/1",
        "run_id": RUN_ID,
        "mode": "live",
        "scope": "full-p0",
        "task_id": None,
        "code_identity": _identity("1"),
        "git_revision_at_start": "test-revision",
        "config_identity": _identity("2"),
        "input_identity": _identity("3"),
        "contract_definition_hash": "4" * 64,
        "status_projection_hash_at_start": "5" * 64,
        "policy_versions": {
            "harness_policy": "harness-policy/1",
            "p0_acceptance_policy": "p0-acceptance-policy/1",
            "provider_call_policy": "provider-call-policy/1",
            "failure_severity_policy": "failure-severity-policy/1",
        },
        "selected_contract_ids": ["P0-ACC-001"],
        "live_identity": {
            "operator_id": "quality-1",
            "api_base": "http://127.0.0.1:18000",
            "frontend_base": "http://127.0.0.1:14173",
            "browser": {
                "name": "chrome",
                "executable": "google-chrome",
                "version": "Google Chrome 149.0.7827.53",
                "sha256": "a" * 64,
            },
            "viewport": {"width": 1565, "height": 796},
        },
        "execution_state": execution_state,
        "pause_identity": None,
        "failure_reason": None,
        "started_at": "2026-07-22T00:00:00Z",
        "completed_at": None,
    }


def _manifest() -> dict[str, object]:
    schema = json.loads(
        (HARNESS / "schemas/current-four-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    entries = []
    for item in schema["properties"]["entries"]["prefixItems"]:
        properties = item["allOf"][1]["properties"]
        entries.append(
            {
                "order": properties["order"]["const"],
                "basename": properties["basename"]["const"],
                "sha256": properties["sha256"]["const"],
                "opaque_ref": properties["opaque_ref"]["const"],
                "page_metadata": properties["page_metadata"]["const"],
            }
        )
    return {
        "schema_version": "current-four-manifest/1",
        "input_set": "current-four",
        "first_checkpoint": {
            key: entries[0][key]
            for key in ("order", "basename", "sha256", "opaque_ref")
        },
        "entries": entries,
    }


def _item_set_answers() -> dict[str, object]:
    return {
        "automatic_candidates_are_actionable": True,
        "candidates_are_editable": True,
        "operator_confirmed_item_set_is_complete": True,
        "not_false_success": True,
    }


def _balloon_answers() -> dict[str, object]:
    return {
        "all_required_balloons_visible": True,
        "hard_collisions_resolved": True,
    }


def _human_verdict() -> dict[str, object]:
    return {**_item_set_answers(), **_balloon_answers()}


def _verdict_sample(order: int) -> dict[str, object]:
    project_id = f"project-{order}"
    return {
        "order": order,
        "project_id": project_id,
        "item_set": {
            "operator_id": "quality-1",
            "note": "Reviewed every source page and every exclusion.",
            "recorded_at": "2026-07-22T00:01:00Z",
            "merge_split_disposition": "not_applicable",
            "merge_split_note": "No related candidates required merge or split.",
            "answers": _item_set_answers(),
        },
        "balloons": {
            "operator_id": "quality-1",
            "note": "Checked visible balloons before formal publication.",
            "recorded_at": "2026-07-22T00:02:00Z",
            "answers": _balloon_answers(),
        },
        "merged_verdict": _human_verdict(),
    }


def _sample_evidence(order: int) -> dict[str, object]:
    project_id = f"project-{order}"
    item_ids = [f"item-{order}-1", f"item-{order}-2"]
    excluded_item_id = f"excluded-{order}"
    candidate_ids = [*item_ids, excluded_item_id]
    reviewed_result_id = f"reviewed-{order}"
    artifact_kinds = ["ballooned_pdf", "sip_excel", "manifest"]
    return {
        "order": order,
        "opaque_ref": _manifest()["entries"][order - 1]["opaque_ref"],
        "project_id": project_id,
        "project_url": f"/?project_id={project_id}&operator_id=quality-1",
        "process": {
            "source_sha256": _manifest()["entries"][order - 1]["sha256"],
            "expected_page_count": _manifest()["entries"][order - 1][
                "page_metadata"
            ]["page_count"],
            "actual_page_count": _manifest()["entries"][order - 1][
                "page_metadata"
            ]["page_count"],
            "expected_physical_page": _manifest()["entries"][order - 1][
                "page_metadata"
            ]["physical_page"],
            "actual_physical_pages": [
                _manifest()["entries"][order - 1]["page_metadata"][
                    "physical_page"
                ]
            ],
            "automatic_result_id": f"automatic-{order}",
            "prepare_log_ref": f"logs/sample-{order}-prepare.log",
            "prepare_log_sha256": "a" * 64,
        },
        "candidates": {
            "candidate_count": 3,
            "candidate_ids": candidate_ids,
            "source_location_ids": [
                f"source-{order}-1",
                f"source-{order}-2",
                f"source-{order}-3",
            ],
            "coverage_checked": True,
            "coverage_blocking_count": 0,
            "coverage_disposition_count": 3,
            "candidate_records": [
                {
                    "candidate_id": candidate_id,
                    "coordinates": [10 * index, 10, 10 * index + 5, 15],
                    "source_location_ids": [f"source-{order}-{index}"],
                    "source_evidence": [
                        {
                            "source_location_id": f"source-{order}-{index}",
                            "source_type": "native",
                            "observation_level": "line",
                            "coordinates": [10 * index, 10, 10 * index + 5, 15],
                            "coverage": {
                                "disposition": "candidate",
                                "candidate_id": candidate_id,
                            },
                        }
                    ],
                }
                for index, candidate_id in enumerate(candidate_ids, start=1)
            ],
        },
        "review": {
            "working_copy_id": f"working-{order}",
            "frozen_version": 7,
            "frozen_by": "quality-1",
            "items_frozen_at": "2026-07-22T00:01:10Z",
            "active_item_ids": item_ids,
            "balloon_required_item_ids": item_ids,
            "excluded_item_ids": [excluded_item_id],
            "operation_commands": [
                "keep",
                "exclude",
                "edit",
                "add",
                "resolve_confirmation",
            ],
            "operation_operator_ids": ["quality-1"],
            "operation_target_ids": candidate_ids,
            "candidate_decisions": [
                {
                    "candidate_id": candidate_id,
                    "final_state": "excluded" if candidate_id == excluded_item_id else "active",
                    "commands": ["exclude"] if candidate_id == excluded_item_id else ["keep"],
                }
                for candidate_id in candidate_ids
            ],
            "merge_split_disposition": "not_applicable",
            "merge_split_note": "No related candidates required merge or split.",
            "evidence_ref": f"reports/review-{order}.json",
            "evidence_sha256": "b" * 64,
        },
        "human_verdict": _human_verdict(),
        "balloons": {
            "hard_collision_count": 0,
            "unresolved_manual_required_count": 0,
            "active_item_ids": item_ids,
            "formal_numbers": [1, 2],
            "browser": {
                "passed": True,
                "captured_at": "2026-07-22T00:01:30Z",
                "report_ref": f"reports/playwright-{order}-pre-export.json",
                "screenshot_refs": [
                    f"reports/workbench-{order}-pre-export.png"
                ],
                "result_ref": f"reports/e2e-{order}-pre-export.json",
                "report_sha256": "c" * 64,
                "screenshot_sha256": "d" * 64,
                "result_sha256": "e" * 64,
            },
        },
        "export": {
            "reviewed_result_id": reviewed_result_id,
            "export_id": f"export-{order}",
            "status": "success",
            "artifact_kinds": artifact_kinds,
            "artifact_sha256": [str(index) * 64 for index in range(1, 4)],
            "artifact_reviewed_result_ids": [reviewed_result_id] * 3,
            "download_kinds": artifact_kinds,
            "browser": {
                "passed": True,
                "captured_at": "2026-07-22T00:03:00Z",
                "report_ref": f"reports/playwright-{order}-export.json",
                "screenshot_refs": [f"reports/workbench-{order}-export.png"],
                "result_ref": f"reports/e2e-{order}-export.json",
                "report_sha256": "f" * 64,
                "screenshot_sha256": "1" * 64,
                "result_sha256": "2" * 64,
            },
        },
        "consistency": {
            "verified": True,
            "reviewed_result_id": reviewed_result_id,
            "workbench_active_item_ids": item_ids,
            "reviewed_active_item_ids": item_ids,
            "reviewed_item_ids": item_ids,
            "balloon_item_ids": item_ids,
            "workbench_numbers": [1, 2],
            "workbench_item_numbers": [
                {"item_id": item_ids[0], "formal_number": 1},
                {"item_id": item_ids[1], "formal_number": 2},
            ],
            "workbench_overlay_item_numbers": [
                {"item_id": item_ids[0], "formal_number": 1},
                {"item_id": item_ids[1], "formal_number": 2},
            ],
            "reviewed_item_numbers": [
                {"item_id": item_ids[0], "formal_number": 1},
                {"item_id": item_ids[1], "formal_number": 2},
            ],
            "reviewed_numbers": [1, 2],
            "pdf_numbers": [1, 2],
            "excel_numbers": [1, 2],
            "reviewed_item_count": 2,
            "balloon_required_count": 2,
            "balloon_count": 2,
            "source_page_count": _manifest()["entries"][order - 1][
                "page_metadata"
            ]["page_count"],
            "manifest_reviewed_item_count": 2,
            "manifest_balloon_required_count": 2,
            "manifest_balloon_count": 2,
            "manifest_source_page_count": _manifest()["entries"][order - 1][
                "page_metadata"
            ]["page_count"],
            "evidence_ref": f"reports/consistency-{order}.json",
            "evidence_sha256": "3" * 64,
        },
    }


def _visual_text_candidate_evidence() -> dict[str, object]:
    candidate_id = "candidate-visual-text"
    return {
        "candidate_count": 1,
        "candidate_ids": [candidate_id],
        "source_location_ids": ["line-1", "span-1", "visual-1"],
        "coverage_checked": True,
        "coverage_blocking_count": 0,
        "coverage_disposition_count": 2,
        "candidate_records": [
            {
                "candidate_id": candidate_id,
                "coordinates": [10, 10, 40, 40],
                "source_location_ids": ["line-1", "span-1", "visual-1"],
                "source_evidence": [
                    {
                        "source_location_id": "line-1",
                        "source_type": "native",
                        "observation_level": "line",
                        "coordinates": [20, 20, 30, 30],
                        "coverage": {
                            "disposition": "ambiguous",
                            "candidate_id": None,
                        },
                    },
                    {
                        "source_location_id": "span-1",
                        "source_type": "native",
                        "observation_level": "span",
                        "coordinates": [30, 20, 40, 30],
                        "coverage": None,
                    },
                    {
                        "source_location_id": "visual-1",
                        "source_type": "visual",
                        "observation_level": "annotation_context",
                        "coordinates": [10, 10, 20, 20],
                        "coverage": {
                            "disposition": "candidate",
                            "candidate_id": candidate_id,
                        },
                    },
                ],
            }
        ],
    }


def test_live_prepare_projects_candidate_sources_from_inventory() -> None:
    runner = _load_module(
        "qi_run_p0_candidate_source_projection",
        HARNESS / "scripts/run-p0.py",
    )
    project = _embedded_function(
        runner._PREPARE_PROJECT_PROGRAM,
        "project_candidate_evidence",
    )
    candidate_id = "candidate-visual-text"
    projected = project(
        [
            {
                "candidate_id": candidate_id,
                "payload": {"coordinates": [10, 10, 40, 40]},
                "source_location_ids": ["visual-1", "line-1", "span-1"],
            }
        ],
        [
            {
                "observations": [
                    {
                        "observation_id": "line-1",
                        "source_type": "native",
                        "observation_level": "line",
                        "bbox_pdf": [20, 20, 30, 30],
                    },
                    {
                        "observation_id": "span-1",
                        "source_type": "native",
                        "observation_level": "span",
                        "bbox_pdf": [30, 20, 40, 30],
                    },
                ],
                "visual_observations": [
                    {
                        "observation_id": "visual-1",
                        "source_type": "visual",
                        "observation_level": "annotation_context",
                        "bbox_pdf": [10, 10, 20, 20],
                    }
                ],
            }
        ],
        [
            {
                "source_location_id": "visual-1",
                "disposition": "candidate",
                "candidate_id": candidate_id,
            },
            {
                "source_location_id": "line-1",
                "disposition": "ambiguous",
                "candidate_id": None,
            },
        ],
    )

    assert projected == {
        "candidate_ids": [candidate_id],
        "source_location_ids": ["line-1", "span-1", "visual-1"],
        "candidate_records": _visual_text_candidate_evidence()[
            "candidate_records"
        ],
    }


@pytest.mark.parametrize(
    ("configured_mode", "expected_mode", "expected_router"),
    [
        (
            "production_uncertainty",
            "production_uncertainty",
            "symbol-uncertainty-router/1",
        ),
        ("legacy_high_recall", "legacy_high_recall", "legacy"),
    ],
)
def test_live_prepare_freezes_the_configured_project_routing_identity(
    configured_mode: str,
    expected_mode: str,
    expected_router: str,
) -> None:
    runner = _load_module(
        "qi_run_p0_project_routing_" + configured_mode,
        HARNESS / "scripts/run-p0.py",
    )

    class ProjectFactory:
        def __new__(cls, **values: object) -> dict[str, object]:
            return values

    class ProjectStates:
        PROCESSING = "processing"

    class UUIDFactory:
        @staticmethod
        def uuid4() -> str:
            return "project-id"

    class Settings:
        symbol_recognition_mode = configured_mode

    def routing_identity(mode: str) -> tuple[str, str]:
        return {
            "production_uncertainty": (
                "production_uncertainty",
                "symbol-uncertainty-router/1",
            ),
            "legacy_high_recall": ("legacy_high_recall", "legacy"),
        }[mode]

    create_project = _embedded_function(
        runner._PREPARE_PROJECT_PROGRAM,
        "create_live_project",
        {
            "Project": ProjectFactory,
            "ProjectState": ProjectStates,
            "symbol_routing_identity": routing_identity,
            "uuid": UUIDFactory,
        },
    )

    assert create_project(Settings()) == {
        "id": "project-id",
        "state": "processing",
        "recognition_mode": expected_mode,
        "recognition_router_version": expected_router,
    }


def test_live_prepare_rejects_candidate_source_outside_inventory() -> None:
    runner = _load_module(
        "qi_run_p0_candidate_source_rejection",
        HARNESS / "scripts/run-p0.py",
    )
    project = _embedded_function(
        runner._PREPARE_PROJECT_PROGRAM,
        "project_candidate_evidence",
    )

    with pytest.raises(
        RuntimeError,
        match="automatic candidate source relation is incomplete",
    ):
        project(
            [
                {
                    "candidate_id": "candidate-spliced",
                    "payload": {"coordinates": [10, 10, 20, 20]},
                    "source_location_ids": ["source-not-in-inventory"],
                }
            ],
            [{"observations": [], "visual_observations": []}],
            [],
        )

    with pytest.raises(
        RuntimeError,
        match="candidate coverage relation is invalid",
    ):
        project(
            [
                {
                    "candidate_id": "candidate-1",
                    "payload": {"coordinates": [10, 10, 20, 20]},
                    "source_location_ids": ["source-1"],
                }
            ],
            [
                {
                    "observations": [
                        {
                            "observation_id": source_id,
                            "source_type": "native",
                            "observation_level": "line",
                            "bbox_pdf": [10 * index, 10, 10 * index + 5, 15],
                        }
                        for index, source_id in enumerate(
                            ("source-1", "source-extra"),
                            start=1,
                        )
                    ],
                    "visual_observations": [],
                }
            ],
            [
                {
                    "source_location_id": "source-extra",
                    "disposition": "candidate",
                    "candidate_id": "candidate-1",
                }
            ],
        )


def test_candidate_evidence_accepts_inventory_backed_visual_text_union() -> None:
    policy = _load_module(
        "qi_candidate_lineage_policy",
        HARNESS / "scripts/live_evidence_policy.py",
    )

    policy.validate_candidate_evidence(1, _visual_text_candidate_evidence())


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda value: value["candidate_records"][0]["source_evidence"].pop(),
            "candidate source IDs are spliced",
        ),
        (
            lambda value: value["candidate_records"][0][
                "source_evidence"
            ].append(
                value["candidate_records"][0]["source_evidence"][0].copy()
            ),
            "candidate source IDs are spliced",
        ),
        (
            lambda value: value["candidate_records"][0][
                "source_evidence"
            ].append(
                {
                    "source_location_id": "source-extra",
                    "source_type": "native",
                    "observation_level": "span",
                    "coordinates": [40, 20, 50, 30],
                    "coverage": None,
                }
            ),
            "candidate source IDs are spliced",
        ),
        (
            lambda value: value["candidate_records"][0]["source_evidence"][2].__setitem__(
                "coordinates",
                [10, 10, 10, 20],
            ),
            "candidate source coordinates are invalid",
        ),
        (
            lambda value: value["candidate_records"][0]["source_evidence"][2].__setitem__(
                "coverage",
                None,
            ),
            "visual candidate coverage is missing",
        ),
        (
            lambda value: value["candidate_records"][0]["source_evidence"][2][
                "coverage"
            ].__setitem__(
                "candidate_id",
                "candidate-spliced",
            ),
            "visual candidate coverage is missing",
        ),
        (
            lambda value: value["candidate_records"][0]["source_evidence"][0].__setitem__(
                "coverage",
                None,
            ),
            "candidate text coverage is invalid",
        ),
        (
            lambda value: value["candidate_records"][0]["source_evidence"][0][
                "coverage"
            ].update(
                {
                    "disposition": "candidate",
                    "candidate_id": "candidate-spliced",
                }
            ),
            "candidate text coverage is invalid",
        ),
        (
            lambda value: value["source_location_ids"].pop(),
            "candidate inventory is spliced",
        ),
        (
            lambda value: value["source_location_ids"].append("source-extra"),
            "candidate inventory is spliced",
        ),
    ],
)
def test_candidate_evidence_rejects_lineage_splices(
    mutate,
    error: str,
) -> None:
    policy = _load_module(
        "qi_candidate_lineage_rejection_policy",
        HARNESS / "scripts/live_evidence_policy.py",
    )
    candidates = _visual_text_candidate_evidence()
    mutate(candidates)

    with pytest.raises(ValueError, match=error):
        policy.validate_candidate_evidence(1, candidates)


def _symbol_manifest() -> dict[str, object]:
    positive = [
        {
            "label_id": "positive-diameter",
            "bbox_pdf": [10, 10, 30, 30],
            "symbol_kinds": ["diameter"],
            "expected_disposition": "candidate",
            "expected_projection": "diameter_dimension",
        },
        {
            "label_id": "positive-depth",
            "bbox_pdf": [40, 10, 70, 30],
            "symbol_kinds": ["diameter", "depth"],
            "expected_disposition": "candidate",
            "expected_projection": "composite",
        },
        {
            "label_id": "positive-counterbore",
            "bbox_pdf": [80, 10, 120, 30],
            "symbol_kinds": ["diameter", "depth", "counterbore"],
            "expected_disposition": "candidate",
            "expected_projection": "composite",
        },
        {
            "label_id": "positive-roughness",
            "bbox_pdf": [130, 10, 160, 30],
            "symbol_kinds": ["surface_roughness"],
            "expected_disposition": "candidate",
            "expected_projection": "roughness",
        },
        {
            "label_id": "positive-gdt-parallelism",
            "bbox_pdf": [170, 10, 210, 30],
            "symbol_kinds": ["gdt_parallelism"],
            "expected_disposition": "candidate",
            "expected_projection": "geometric_tolerance",
        },
        {
            "label_id": "positive-gdt-perpendicularity",
            "bbox_pdf": [220, 10, 260, 30],
            "symbol_kinds": ["gdt_perpendicularity"],
            "expected_disposition": "candidate",
            "expected_projection": "geometric_tolerance",
        },
        {
            "label_id": "positive-gdt-flatness",
            "bbox_pdf": [270, 10, 310, 30],
            "symbol_kinds": ["gdt_flatness"],
            "expected_disposition": "candidate",
            "expected_projection": "geometric_tolerance",
        },
        {
            "label_id": "positive-datum",
            "bbox_pdf": [320, 10, 340, 30],
            "symbol_kinds": ["datum_reference"],
            "expected_disposition": "reference_context",
            "expected_projection": None,
        },
        {
            "label_id": "positive-revision",
            "bbox_pdf": [350, 10, 370, 30],
            "symbol_kinds": ["revision_marker"],
            "expected_disposition": "non_inspection",
            "expected_projection": None,
        },
    ]
    families = [
        "part_or_hole_geometry",
        "hatch_center_or_cross",
        "dimension_leader_or_section_line",
        "view_or_section_label",
        "revision_table_or_invalid_marker",
        "datum_like_letter_or_table_cell",
        "watermark_logo_title_or_signoff",
        "isometric_hole_slot_or_edge",
        "ordinary_text_number_material_or_requirement",
    ]
    negative = [
        {
            "label_id": f"negative-{index}",
            "bbox_pdf": [10 + index * 30, 50, 30 + index * 30, 70],
            "symbol_kinds": ["frozen_negative"],
            "negative_family": family,
            "expected_disposition": "ambiguous",
            "expected_projection": None,
        }
        for index, family in enumerate(families)
    ]
    return {
        "schema_version": "visual-symbol-eval/1",
        "source_sha256": _manifest()["entries"][0]["sha256"],
        "annotation_owner_role": "quality_owner",
        "annotation_status": "approved",
        "pages": [
            {"page_index": 0, "labels": positive[:5] + negative[:4]},
            {"page_index": 1, "labels": positive[5:] + negative[4:]},
        ],
    }


def _symbol_evidence() -> dict[str, object]:
    return {
        "selector": "phase://live/symbol-recognition?input_set=current-four",
        "passed": True,
        "order": 1,
        "project_id": "project-1",
        "automatic_result_id": "automatic-1",
        "source_sha256": _manifest()["entries"][0]["sha256"],
        "manifest_sha256": "a" * 64,
        "annotation_verdict_sha256": "b" * 64,
        "label_count": 18,
        "positive_label_count": 9,
        "negative_label_count": 9,
        "positive_family_counts": {
            "diameter": 3,
            "depth": 2,
            "counterbore": 1,
            "surface_roughness": 1,
            "gdt_parallelism": 1,
            "gdt_perpendicularity": 1,
            "gdt_flatness": 1,
            "datum_reference": 1,
            "revision_marker": 1,
        },
        "negative_family_counts": {
            "part_or_hole_geometry": 1,
            "hatch_center_or_cross": 1,
            "dimension_leader_or_section_line": 1,
            "view_or_section_label": 1,
            "revision_table_or_invalid_marker": 1,
            "datum_like_letter_or_table_cell": 1,
            "watermark_logo_title_or_signoff": 1,
            "isometric_hole_slot_or_edge": 1,
            "ordinary_text_number_material_or_requirement": 1,
        },
        "visual_calls_by_page": [
            {"page_index": 0, "count": 13},
            {"page_index": 1, "count": 16},
        ],
        "total_vision_calls_by_page": [
            {"page_index": 0, "count": 16},
            {"page_index": 1, "count": 16},
        ],
        "candidate_match_count": 7,
        "reference_match_count": 1,
        "non_inspection_match_count": 1,
        "negative_false_positive_count": 0,
        "source_command_count": 0,
        "report_ref": "reports/symbol-recognition.json",
        "report_sha256": "c" * 64,
    }


def _typed_gdt_cases() -> dict[str, object]:
    return {
        "case_a": {
            "candidate_id": "case-a",
            "annotation_label_id": "positive-gdt-parallelism",
            "schema_version": "geometric-tolerance-candidate/1",
            "item_type": "geometric_tolerance",
            "tolerance_type": "parallelism",
            "tolerance_symbol": "∥",
            "tolerance_value": "0.1",
            "datum_references": [{"datum": "A", "modifiers": []}],
            "frames": [
                {
                    "segments": [
                        {
                            "tolerance_value": "0.1",
                            "diameter_modifier": False,
                            "modifiers": [],
                            "datum_references": [
                                {"datum": "A", "modifiers": []}
                            ],
                        }
                    ]
                }
            ],
            "source_location_ids": ["source-a"],
        },
        "case_b": {
            "candidate_id": "case-b",
            "annotation_label_id": "positive-gdt-flatness",
            "schema_version": "geometric-tolerance-candidate/1",
            "item_type": "geometric_tolerance",
            "tolerance_type": "flatness",
            "tolerance_symbol": "⏥",
            "tolerance_value": "0.08",
            "datum_references": [],
            "frames": [
                {
                    "segments": [
                        {
                            "tolerance_value": "0.08",
                            "diameter_modifier": False,
                            "modifiers": [],
                            "datum_references": [],
                        }
                    ]
                }
            ],
            "source_location_ids": ["source-b"],
        },
    }


def _provider_call_identities(
    *,
    crop_sha256: str,
    crop_ref: str,
) -> list[dict[str, object]]:
    return [
        {
            "source_sha256": _manifest()["entries"][0]["sha256"],
            "visual_observation_ids": ["visual-a"],
            "crop_bbox_pdf": [1.0, 2.0, 3.0, 4.0],
            "crop_sha256": crop_sha256,
            "crop_ref": crop_ref,
            "model": "qwen3-vl-plus",
            "model_identity_sha256": (
                "6918ac1f8497fbd57c88eab5ff17f7e68678c6c5fd1028cb168a8dcf8bc5dae0"
            ),
            "prompt_version": "visual-symbol-prompt/4",
            "prompt_identity_sha256": (
                "5897c04eadbe40c189e500f64ff84738ffc17d59bb607aae665d4d07a41af811"
            ),
            "schema_version": "visual-symbol-review/3",
            "schema_sha256": hashlib.sha256(
                (
                    ROOT
                    / "backend/app/providers/visual_symbol_review.schema.json"
                ).read_bytes()
            ).hexdigest(),
            "request_id_sha256": "2" * 64,
        }
    ]


def _live_evidence() -> dict[str, object]:
    return {
        "schema_version": "live-run-evidence/2",
        "run_id": RUN_ID,
        "input_set": "current-four",
        "phases": PHASES,
        "child_run_ids": [],
        "symbol_recognition": _symbol_evidence(),
        "design_qa": {
            "ref": "design-qa.md",
            "sha256": "6" * 64,
            "final_result": "passed",
            "browser": "chrome",
            "viewport": {"width": 1565, "height": 796},
            "source_sha256": "7" * 64,
            "implementation_route": "/?project_id=project-1&operator_id=quality-1",
            "implementation_state": "visual_qa_pending:first-pdf-balloons",
            "implementation_capture_ref": "reports/design-qa-implementation.png",
            "implementation_capture_sha256": "8" * 64,
            "comparison_capture_ref": "reports/design-qa-comparison.png",
            "comparison_capture_sha256": "9" * 64,
            "console_error_count": 0,
            "network_error_count": 0,
            "issue_counts": {"p0": 0, "p1": 0, "p2": 0},
        },
        "samples": [_sample_evidence(order) for order in range(1, 5)],
    }


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_hashed(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _materialize_bound_live_evidence(
    run_dir: Path,
    design_qa_path: Path,
) -> dict[str, object]:
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    run = _run()
    run["pause_identity"] = {
        "code_identity": run["code_identity"],
        "config_identity": run["config_identity"],
        "contract_definition_hash": run["contract_definition_hash"],
        "input_identity": run["input_identity"],
        "live_identity": run["live_identity"],
    }
    (run_dir / "run.json").write_bytes(_json_bytes(run))
    (run_dir / "artifacts/current-four-manifest.json").write_bytes(
        _json_bytes(_manifest())
    )
    verdict = {
        "schema_version": "human-verdict/1",
        "run_id": RUN_ID,
        "samples": [_verdict_sample(order) for order in range(1, 5)],
    }
    (run_dir / "artifacts/human-verdict.json").write_bytes(_json_bytes(verdict))

    live = _live_evidence()
    symbol_manifest_bytes = _json_bytes(_symbol_manifest())
    symbol_manifest_sha256 = _write_hashed(
        run_dir / "artifacts/visual-symbol-eval.json",
        symbol_manifest_bytes,
    )
    symbol_verdict = {
        "schema_version": "visual-symbol-annotation-verdict/1",
        "annotation_owner_role": "quality_owner",
        "overlay_scale_percent": 200,
        "unlabeled_target_count": 0,
        "negative_family_count": 9,
        "manifest_sha256": symbol_manifest_sha256,
        "recorded_at": "2026-07-27T00:00:00Z",
    }
    symbol_verdict_sha256 = _write_hashed(
        run_dir / "artifacts/visual-symbol-annotation-verdict.json",
        _json_bytes(symbol_verdict),
    )
    symbol_evidence = live["symbol_recognition"]
    assert isinstance(symbol_evidence, dict)
    symbol_evidence["manifest_sha256"] = symbol_manifest_sha256
    symbol_evidence["annotation_verdict_sha256"] = symbol_verdict_sha256
    crop_sha256 = hashlib.sha256(PNG_BYTES).hexdigest()
    crop_ref = f"artifacts/provider-crops/{crop_sha256}.png"
    assert _write_hashed(run_dir / crop_ref, PNG_BYTES) == crop_sha256
    symbol_report = {
        "schema_version": "symbol-recognition-live-report/2",
        "selector": symbol_evidence["selector"],
        "run_id": RUN_ID,
        "order": 1,
        "project_id": symbol_evidence["project_id"],
        "automatic_result_id": symbol_evidence["automatic_result_id"],
        "source_sha256": symbol_evidence["source_sha256"],
        "manifest_sha256": symbol_manifest_sha256,
        "annotation_verdict_sha256": symbol_verdict_sha256,
        "visual_calls_by_page": symbol_evidence["visual_calls_by_page"],
        "total_vision_calls_by_page": symbol_evidence[
            "total_vision_calls_by_page"
        ],
        "source_command_count": 0,
        "typed_gdt_cases": _typed_gdt_cases(),
        "provider_call_identities": _provider_call_identities(
            crop_sha256=crop_sha256,
            crop_ref=crop_ref,
        ),
        "evaluation": {
            "schema_version": "symbol-eval-report/1",
            "passed": True,
            "overlap_threshold": 0.5,
            "counts": {
                "positive_label_count": 9,
                "candidate_label_count": 7,
                "participating_candidate_count": 7,
                "candidate_match_count": 7,
                "reference_match_count": 1,
                "non_inspection_match_count": 1,
                "negative_label_count": 9,
                "negative_false_positive_count": 0,
                "excluded_candidate_count": 0,
            },
            "positive_family_counts": symbol_evidence[
                "positive_family_counts"
            ],
            "negative_family_counts": symbol_evidence[
                "negative_family_counts"
            ],
            "label_matches": [
                {
                    "label_id": "positive-gdt-parallelism",
                    "candidate_id": "case-a",
                    "disposition": "candidate",
                    "overlap_ratio": 1.0,
                },
                {
                    "label_id": "positive-gdt-flatness",
                    "candidate_id": "case-b",
                    "disposition": "candidate",
                    "overlap_ratio": 1.0,
                },
            ],
            "excluded_candidate_ids": [],
            "failures": [],
        },
        "failures": [],
        "passed": True,
    }
    symbol_evidence["report_sha256"] = _write_hashed(
        run_dir / "reports/symbol-recognition.json",
        _json_bytes(symbol_report),
    )
    implementation_digest = _write_hashed(
        run_dir / "reports/design-qa-implementation.png",
        PNG_BYTES,
    )
    comparison_digest = _write_hashed(
        run_dir / "reports/design-qa-comparison.png",
        COMPARISON_PNG_BYTES,
    )
    design_lines = (
        "# Design QA",
        "source sha256: " + "7" * 64,
        "implementation route: /?project_id=project-1&operator_id=quality-1",
        "implementation state: visual_qa_pending:first-pdf-balloons",
        "implementation capture: reports/design-qa-implementation.png",
        "implementation capture sha256: " + implementation_digest,
        "comparison capture: reports/design-qa-comparison.png",
        "comparison capture sha256: " + comparison_digest,
        "browser: chrome",
        "viewport: 1565x796",
        "console errors: 0",
        "network errors: 0",
        "P0 issues: 0",
        "P1 issues: 0",
        "P2 issues: 0",
        "final result: passed",
        "",
    )
    design_content = "\n".join(design_lines).encode("utf-8")
    design_qa_path.write_bytes(design_content)
    design = live["design_qa"]
    assert isinstance(design, dict)
    design["sha256"] = hashlib.sha256(design_content).hexdigest()
    design["implementation_capture_sha256"] = implementation_digest
    design["comparison_capture_sha256"] = comparison_digest

    samples = live["samples"]
    assert isinstance(samples, list)
    for sample in samples:
        assert isinstance(sample, dict)
        order = int(sample["order"])
        project_id = str(sample["project_id"])
        process = sample["process"]
        review = sample["review"]
        balloons = sample["balloons"]
        export = sample["export"]
        consistency = sample["consistency"]
        assert all(
            isinstance(section, dict)
            for section in (process, review, balloons, export, consistency)
        )

        process["prepare_log_sha256"] = _write_hashed(
            run_dir / str(process["prepare_log_ref"]),
            f"run_id={RUN_ID} order={order}\n".encode(),
        )
        review_report = {
            "run_id": RUN_ID,
            "order": order,
            "project_id": project_id,
            "review": {
                key: value
                for key, value in review.items()
                if key
                not in {
                    "merge_split_disposition",
                    "merge_split_note",
                    "evidence_ref",
                    "evidence_sha256",
                }
            },
            "balloons": {
                key: value
                for key, value in balloons.items()
                if key != "browser"
            },
        }
        review["evidence_sha256"] = _write_hashed(
            run_dir / str(review["evidence_ref"]),
            _json_bytes(review_report),
        )

        for phase, section in (("pre-export", balloons), ("export", export)):
            browser = section["browser"]
            assert isinstance(browser, dict)
            browser["captured_at"] = (
                "2026-07-22T00:01:30Z"
                if phase == "pre-export"
                else "2026-07-22T00:03:00Z"
            )
            browser["report_sha256"] = _write_hashed(
                run_dir / str(browser["report_ref"]),
                _json_bytes({"status": "passed", "phase": phase}),
            )
            screenshot_ref = browser["screenshot_refs"][0]
            browser["screenshot_sha256"] = _write_hashed(
                run_dir / str(screenshot_ref),
                PNG_BYTES,
            )
            item_numbers = [
                {"item_id": f"item-{order}-1", "formal_number": 1},
                {"item_id": f"item-{order}-2", "formal_number": 2},
            ]
            if phase == "pre-export":
                result_document = {
                    "schema_version": "p0-browser-pre-export-evidence/1",
                    "run_id": RUN_ID,
                    "order": order,
                    "project_id": project_id,
                    "phase": phase,
                    "captured_at": browser["captured_at"],
                    "formal_publish_attempted": False,
                    "page_count": process["actual_page_count"],
                    "active_item_ids": balloons["active_item_ids"],
                    "active_item_numbers": ["1", "2"],
                    "overlay_numbers": ["1", "2"],
                    "overlay_item_numbers": item_numbers,
                    "backend_item_numbers": item_numbers,
                    "table_item_numbers": item_numbers,
                    "table_active_item_ids": consistency[
                        "workbench_active_item_ids"
                    ],
                    "glyph_metrics_verified": True,
                    "hard_collision_count": 0,
                    "unresolved_manual_required_count": 0,
                    "actions": {
                        "drag": True,
                        "delete": True,
                        "rebuild": True,
                        "renumber": True,
                    },
                }
            else:
                result_document = {
                    "schema_version": "p0-browser-export-evidence/1",
                    "run_id": RUN_ID,
                    "order": order,
                    "project_id": project_id,
                    "phase": phase,
                    "captured_at": browser["captured_at"],
                    "formal_publish_attempted": True,
                    "reviewed_result_id": export["reviewed_result_id"],
                    "export_id": export["export_id"],
                    "status": "success",
                    "reviewed_item_ids": consistency["reviewed_item_ids"],
                    "reviewed_numbers": [1, 2],
                    "workbench_numbers": [1, 2],
                    "overlay_item_numbers": item_numbers,
                    "backend_item_numbers": item_numbers,
                    "table_item_numbers": item_numbers,
                    "table_active_item_ids": consistency[
                        "workbench_active_item_ids"
                    ],
                    "glyph_metrics_verified": True,
                    "artifacts": [
                        {
                            "kind": kind,
                            "sha256": digest,
                            "size_bytes": 10 + index,
                            "reviewed_result_id": export["reviewed_result_id"],
                            "downloadable": True,
                            "download_sha256": digest,
                            "download_size_bytes": 10 + index,
                            "content_type": content_type,
                        }
                        for index, (kind, digest, content_type) in enumerate(
                            zip(
                                export["artifact_kinds"],
                                export["artifact_sha256"],
                                (
                                    "application/pdf",
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    "application/json",
                                ),
                                strict=True,
                            )
                        )
                    ],
                    "download_kinds": export["download_kinds"],
                }
            browser["result_sha256"] = _write_hashed(
                run_dir / str(browser["result_ref"]),
                _json_bytes(result_document),
            )

        consistency["reviewed_item_numbers"] = [
            {"item_id": f"item-{order}-1", "formal_number": 1},
            {"item_id": f"item-{order}-2", "formal_number": 2},
        ]
        consistency_report = {
            "run_id": RUN_ID,
            "order": order,
            "project_id": project_id,
            "export": {
                key: value for key, value in export.items() if key != "browser"
            },
            "consistency": {
                key: value
                for key, value in consistency.items()
                if key not in {"evidence_ref", "evidence_sha256"}
            },
        }
        consistency["evidence_sha256"] = _write_hashed(
            run_dir / str(consistency["evidence_ref"]),
            _json_bytes(consistency_report),
        )

    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(live))
    return live


def test_full_p0_run_schema_adds_lifecycle_without_invalidating_task_runs() -> None:
    _validate(_run(), "run.schema.json")
    paused = _run("visual_qa_pending")
    paused["pause_identity"] = {
        "code_identity": _identity("1"),
        "config_identity": _identity("2"),
        "contract_definition_hash": "4" * 64,
        "input_identity": _identity("3"),
        "live_identity": paused["live_identity"],
    }
    _validate(paused, "run.schema.json")
    pending = _run("terminal_pending")
    _validate(pending, "run.schema.json")

    legacy_task = _run()
    legacy_task.update({"scope": "task", "task_id": "D7-T1"})
    for optional in (
        "execution_state",
        "pause_identity",
        "failure_reason",
        "live_identity",
    ):
        legacy_task.pop(optional)
    _validate(legacy_task, "run.schema.json")


@pytest.mark.parametrize(
    ("api_base", "frontend_base", "valid"),
    [
        ("http://localhost:8000", "http://localhost:3000", True),
        ("http://127.0.0.1:18000", "http://127.0.0.1:14173", True),
        ("http://localhost:8000", "http://127.0.0.1:14173", False),
        ("http://127.0.0.1:18000", "http://localhost:3000", False),
    ],
)
def test_live_run_schema_requires_a_paired_runtime_identity(
    api_base: str,
    frontend_base: str,
    valid: bool,
) -> None:
    run = _run()
    run["live_identity"]["api_base"] = api_base
    run["live_identity"]["frontend_base"] = frontend_base

    if valid:
        _validate(run, "run.schema.json")
    else:
        with pytest.raises(jsonschema.ValidationError):
            _validate(run, "run.schema.json")


def test_live_and_human_verdict_schemas_are_closed() -> None:
    runner = _load_module(
        "qi_run_p0_live_evidence_version",
        HARNESS / "scripts/run-p0.py",
    )
    live = _live_evidence()
    assert runner.LIVE_EVIDENCE_SCHEMA_VERSION == live["schema_version"]
    _validate(live, "live-run-evidence.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        _validate({**live, "unexpected": True}, "live-run-evidence.schema.json")

    verdict = {
        "schema_version": "human-verdict/1",
        "run_id": RUN_ID,
        "samples": [_verdict_sample(order) for order in range(1, 5)],
    }
    _validate(verdict, "human-verdict.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        _validate({**verdict, "prefilled": True}, "human-verdict.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        _validate(
            {
                **verdict,
                "samples": [
                    {
                        **_verdict_sample(1),
                        "item_set": None,
                        "merged_verdict": _human_verdict(),
                    }
                ],
            },
            "human-verdict.schema.json",
        )


@pytest.mark.parametrize(
    "committed_total_cny",
    (
        "0.000000",
        "3.526656",
        "9.999999",
        "10.000000",
        "49.999999",
        "50.000000",
    ),
)
def test_paid_ledger_schema_accepts_full_approved_ceiling_domain(
    committed_total_cny: str,
) -> None:
    live = _live_evidence()
    live["paid_cycle"] = {
        "cycle_id": "gdt10d-contract-cycle",
        "pricing_sha256": "a" * 64,
        "issuance_sha256": "b" * 64,
        "consumption_sha256": "c" * 64,
        "run_authorization_sha256": "d" * 64,
        "journal_ref": (
            "asset://provider-usage-cycles/gdt10d-contract-cycle/"
        ),
        "projects": [],
        "resume_consumed_sha256": None,
        "ledger": {
            "committed_total_cny": committed_total_cny,
            "reservation_count": 0,
            "reserved_only_count": 0,
            "submission_started_count": 0,
            "settled_count": 0,
            "evidence_sha256": "e" * 64,
        },
        "terminal": None,
    }

    _validate(live, "live-run-evidence.schema.json")


def test_single_live_canary_cannot_masquerade_as_latency_percentiles() -> None:
    """PRT-7: 513.44s is one raw sample, never a fabricated P50/P95."""
    single_sample = {
        "sample_count": 1,
        "durations_ms": [513440.2794169728],
    }
    _validate_schema_definition(single_sample, "latencyDistribution")

    fabricated_percentiles = {
        **single_sample,
        "p50_ms": 513440.2794169728,
        "p95_ms": 513440.2794169728,
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate_schema_definition(
            fabricated_percentiles,
            "latencyDistribution",
        )

    measured_distribution = {
        "sample_count": 20,
        "durations_ms": [
            42000.0 + index * 1000.0 for index in range(20)
        ],
        "p50_ms": 51500.0,
        "p95_ms": 60050.0,
    }
    _validate_schema_definition(
        measured_distribution,
        "latencyDistribution",
    )


def test_staged_human_verdict_is_explicit_and_immutable(tmp_path: Path) -> None:
    script = HARNESS / "scripts/record-human-verdict.py"
    assert script.is_file(), "missing D7-T2 staged verdict writer"
    verdict_module = _load_module("qi_record_human_verdict", script)
    run_dir = tmp_path / RUN_ID
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps(_run()), encoding="utf-8")
    (run_dir / "artifacts/current-four-manifest.json").write_text(
        json.dumps(_manifest()),
        encoding="utf-8",
    )

    item_answers = {
        key: value
        for key, value in _human_verdict().items()
        if key in {
            "automatic_candidates_are_actionable",
            "candidates_are_editable",
            "operator_confirmed_item_set_is_complete",
            "not_false_success",
        }
    }
    item_document = verdict_module.record_stage(
        run_dir,
        order=1,
        project_id="project-1",
        stage="item-set",
        operator_id="quality-1",
        note="Reviewed every page and every exclusion.",
        merge_split_disposition="not_applicable",
        merge_split_note="No candidates required merge or split.",
        answers=item_answers,
    )
    first = item_document["samples"][0]
    assert first["item_set"]["answers"] == item_answers
    assert first["balloons"] is None
    assert first["merged_verdict"] is None

    with pytest.raises(ValueError, match="already recorded"):
        verdict_module.record_stage(
            run_dir,
            order=1,
            project_id="project-1",
            stage="item-set",
            operator_id="quality-1",
            note="attempted overwrite",
            merge_split_disposition="not_applicable",
            merge_split_note="No candidates required merge or split.",
            answers=item_answers,
        )

    balloon_answers = {
        key: value
        for key, value in _human_verdict().items()
        if key in {"all_required_balloons_visible", "hard_collisions_resolved"}
    }
    completed = verdict_module.record_stage(
        run_dir,
        order=1,
        project_id="project-1",
        stage="balloons",
        operator_id="quality-1",
        note="All hard collisions resolved.",
        merge_split_disposition=None,
        merge_split_note=None,
        answers=balloon_answers,
    )
    assert completed["samples"][0]["merged_verdict"] == _human_verdict()
    assert completed["samples"][0]["item_set"] == first["item_set"]

    second = verdict_module.record_stage(
        run_dir,
        order=2,
        project_id="project-2",
        stage="item-set",
        operator_id="quality-1",
        note="Reviewed every page and every exclusion.",
        merge_split_disposition="merge",
        merge_split_note="Merged the duplicated diameter callout.",
        answers=item_answers,
    )
    assert [sample["order"] for sample in second["samples"]] == [1, 2]
    assert second["samples"][1]["project_id"] == "project-2"
    assert second["samples"][1]["balloons"] is None

    with pytest.raises(ValueError, match="same operator"):
        verdict_module.record_stage(
            run_dir,
            order=2,
            project_id="project-2",
            stage="balloons",
            operator_id="quality-2",
            note="Different operator must not splice evidence.",
            merge_split_disposition=None,
            merge_split_note=None,
            answers=balloon_answers,
        )


def test_human_verdict_cannot_cross_run_identity(tmp_path: Path) -> None:
    verdict_module = _load_module(
        "qi_record_human_verdict_identity",
        HARNESS / "scripts/record-human-verdict.py",
    )
    run_dir = tmp_path / RUN_ID
    artifact = run_dir / "artifacts/human-verdict.json"
    artifact.parent.mkdir(parents=True)
    document = {
        "schema_version": "human-verdict/1",
        "run_id": "20260722T000000000001Z-00000001",
        "samples": [],
    }
    artifact.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="run identity"):
        verdict_module.record_stage(
            run_dir,
            order=1,
            project_id="project-1",
            stage="item-set",
            operator_id="quality-1",
            note="real operator note",
            merge_split_disposition="not_applicable",
            merge_split_note="No candidates required merge or split.",
            answers={
                "automatic_candidates_are_actionable": True,
                "candidates_are_editable": True,
                "operator_confirmed_item_set_is_complete": True,
                "not_false_success": True,
            },
        )


def test_current_four_manifest_attaches_to_the_same_open_run(tmp_path: Path) -> None:
    stage = _load_module(
        "qi_stage_current_four_live",
        HARNESS / "scripts/stage-current-four.py",
    )
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(_run()), encoding="utf-8")
    manifest_bytes = json.dumps(_manifest(), sort_keys=True).encode()

    attached = stage.attach_manifest(run_dir, manifest_bytes)

    assert attached == run_dir / "artifacts/current-four-manifest.json"
    assert attached.read_bytes() == manifest_bytes
    assert list(tmp_path.iterdir()) == [run_dir]


def test_live_run_contains_exact_current_four_and_no_missing_phase(tmp_path: Path) -> None:
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    run = _run("completed")
    run["completed_at"] = "2026-07-22T00:10:00Z"
    manifest = _manifest()
    live = _live_evidence()
    results = {
        "schema_version": "contract-results/1",
        "run_id": RUN_ID,
        "results": [
            {"p0_contract_id": f"P0-TEST-{index:03d}"}
            for index in range(1, 112)
        ],
    }

    _validate(run, "run.schema.json")
    _validate(live, "live-run-evidence.schema.json")
    assert run["mode"] == "live" and run["scope"] == "full-p0"
    assert len(manifest["entries"]) == 4
    assert live["phases"] == PHASES
    assert len(results["results"]) == 111
    assert live["child_run_ids"] == []
    assert live["design_qa"]["final_result"] == "passed"
    assert all(
        sample["human_verdict"]["operator_confirmed_item_set_is_complete"]
        for sample in live["samples"]
    )
    assert all(
        sample["balloons"]["hard_collision_count"] == 0
        and sample["balloons"]["browser"]["passed"]
        and sample["export"]["browser"]["passed"]
        and sample["export"]["download_kinds"]
        == ["ballooned_pdf", "sip_excel", "manifest"]
        and sample["consistency"]["verified"] is True
        for sample in live["samples"]
    )


def test_visual_qa_code_change_seals_paused_attempt_failed(tmp_path: Path) -> None:
    runner = _load_module("qi_run_p0_live", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    paused = _run("visual_qa_pending")
    paused["pause_identity"] = {
        "code_identity": _identity("1"),
        "config_identity": _identity("2"),
        "contract_definition_hash": "4" * 64,
        "input_identity": _identity("3"),
        "live_identity": paused["live_identity"],
    }
    (run_dir / "run.json").write_text(json.dumps(paused), encoding="utf-8")

    runner.abort_live_run(run_dir, reason="visual_qa_code_changed", seal=False)
    failed = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert failed["execution_state"] == "failed"
    assert failed["failure_reason"] == "visual_qa_code_changed"
    assert failed["completed_at"] is not None
    assert runner.can_resume_live_run(run_dir) is False


def test_live_cli_rejects_missing_server_credentials_before_run_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_module("qi_run_p0_live_preflight", HARNESS / "scripts/run-p0.py")
    runs = tmp_path / "runs"
    monkeypatch.setattr(runner, "RUNS", runs)
    for key in (
        "QI_TENCENT_SECRET_ID",
        "QI_TENCENT_SECRET_KEY",
        "QI_QWEN_API_KEY",
        "QI_QWEN_WORKSPACE_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    result = runner.main(
        [
            "live",
            "--scope",
            "full-p0",
            "--input-set",
            "current-four",
            "--activate-current-inputs",
            "--pause-after",
            "first-pdf-balloons",
            "--print-run-id-only",
            "--authorized-run-id",
            RUN_ID,
        ]
    )

    assert result == 2
    assert not runs.exists()
    assert "server-only Provider configuration is incomplete" in capsys.readouterr().err


def test_repository_live_target_requests_fresh_activation_and_pause() -> None:
    result = subprocess.run(
        ["make", "--no-print-directory", "-n", "verify-p0-live"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    command = next(
        line
        for line in result.stdout.splitlines()
        if "live_cycle_authorization.py execute-start" in line
    )
    assert "QI_LIVE_CYCLE_AUTHORIZATION_REF" in result.stdout
    assert "QI_LIVE_CYCLE_OVERRIDE_REF" in result.stdout
    assert "check-contracts" not in command
    assert "run-p0.py live" not in result.stdout


def test_full_live_activation_passes_generated_literal_runs_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_live_activation",
        HARNESS / "scripts/run-p0.py",
    )
    current_four_run = "20260801T010101000000Z-11111111"
    symbol_eval_run = "20260801T020202000000Z-22222222"
    observed: list[tuple[str, str]] = []

    monkeypatch.setattr(
        runner,
        "activate_full_live_inputs",
        lambda **_kwargs: (current_four_run, symbol_eval_run),
        raising=False,
    )

    def preflight(**kwargs: object) -> dict[str, object]:
        observed.append(
            (
                str(kwargs["current_four_run"]),
                str(kwargs["symbol_eval_run"]),
            )
        )
        return {"ready": True}

    monkeypatch.setattr(runner, "preflight_full_p0_live", preflight)
    monkeypatch.setattr(
        runner,
        "start_live_run",
        lambda _preflight, *, authorized_run_id: (
            RUN_ID
            if authorized_run_id == RUN_ID
            else pytest.fail("wrong authorized run identity")
        ),
    )

    result = runner.main(
        [
            "live",
            "--scope",
            "full-p0",
            "--input-set",
            "current-four",
            "--activate-current-inputs",
            "--pause-after",
            "first-pdf-balloons",
            "--print-run-id-only",
            "--authorized-run-id",
            RUN_ID,
        ]
    )

    assert result == 0
    assert observed == [(current_four_run, symbol_eval_run)]


@pytest.mark.parametrize(
    "argv",
    (
        [
            "live",
            "--scope",
            "full-p0",
            "--resume-run",
            RUN_ID,
            "--design-qa",
            "design-qa.md",
        ],
        [
            "live",
            "--scope",
            "full-p0",
            "--abort-run",
            RUN_ID,
            "--reason",
            "blocked",
        ],
        [
            "live",
            "--scope",
            "full-p0",
            "--finalize-run",
            RUN_ID,
            "--terminal-status",
            "failed",
        ],
        ["fixture", "--scope", "task", "--task", "D1-T1"],
    ),
)
def test_authorized_run_id_is_rejected_outside_live_start(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _load_module(
        f"qi_run_p0_authorized_start_only_{argv[0]}_{len(argv)}",
        HARNESS / "scripts/run-p0.py",
    )

    result = runner.main([*argv, "--authorized-run-id", RUN_ID])

    assert result == 2
    assert "--authorized-run-id is limited" in capsys.readouterr().err


def test_full_live_activation_preflights_bytes_before_fresh_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_live_input_registration",
        HARNESS / "scripts/run-p0.py",
    )
    current_four_run = "20260801T030303000000Z-33333333"
    symbol_eval_run = "20260801T040404000000Z-44444444"
    artifacts = {
        runner.CURRENT_FOUR_ARTIFACT: b"current-four",
        runner.SYMBOL_EVAL_ARTIFACT: b"symbol-eval",
        runner.SYMBOL_VERDICT_ARTIFACT: b"symbol-verdict",
    }
    events: list[str] = []
    monkeypatch.setattr(
        runner,
        "_current_live_input_artifacts",
        lambda _source_root: artifacts,
        raising=False,
    )
    monkeypatch.setattr(runner, "_require_live_environment", lambda _env: None)
    monkeypatch.setattr(runner, "_current_live_identity", lambda _env: {})

    def preflight(**kwargs: object) -> object:
        events.append("preflight")
        assert kwargs["input_artifacts"] == artifacts
        assert kwargs["current_four_run"] is None
        assert kwargs["symbol_eval_run"] is None
        return object()

    def run_task(*_args: object, **kwargs: object) -> tuple[str, str]:
        events.append("current-four-registration")
        assert kwargs["input_artifacts"] == {
            runner.CURRENT_FOUR_ARTIFACT: b"current-four"
        }
        return current_four_run, "passed"

    def register(**kwargs: object) -> str:
        events.append("symbol-registration")
        assert kwargs["artifacts"] == {
            runner.SYMBOL_EVAL_ARTIFACT: b"symbol-eval",
            runner.SYMBOL_VERDICT_ARTIFACT: b"symbol-verdict",
        }
        return symbol_eval_run

    monkeypatch.setattr(runner, "preflight_full_p0_live", preflight)
    monkeypatch.setattr(runner, "run_task", run_task)
    monkeypatch.setattr(runner, "register_live_input_artifacts", register)

    assert runner.activate_full_live_inputs(
        source_root="/current-four",
        environment={"ignored": "by mocked preflight"},
    ) == (current_four_run, symbol_eval_run)
    assert events == [
        "preflight",
        "current-four-registration",
        "symbol-registration",
    ]


def _expected_gdt_runtime_payload(runner: ModuleType) -> dict[str, object]:
    return {
        **runner.EXPECTED_RECOGNITION_IDENTITY,
        "hashes": {
            relative: hashlib.sha256(
                (runner.ROOT / "backend" / relative).read_bytes()
            ).hexdigest()
            for relative in runner.LIVE_API_GDT_RUNTIME_PATHS
        },
    }


def _runtime_identity_run(
    runner: ModuleType,
    *,
    payloads: dict[str, object],
    returncodes: dict[str, int] | None = None,
    ports: dict[str, str] | None = None,
):
    calls: list[str] = []

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        assert argv[:2] == ["docker", "compose"]
        if argv[2:4] == ["port", "api"]:
            service = "api-port"
            payload = (ports or {}).get(service, "127.0.0.1:18000\n")
        elif argv[2:4] == ["port", "frontend"]:
            service = "frontend-port"
            payload = (ports or {}).get(service, "127.0.0.1:14173\n")
        else:
            assert argv[2:4] == ["exec", "-T"]
            service = argv[4]
            payload = payloads[service]
        calls.append(service)
        stdout = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(
            argv,
            (returncodes or {}).get(service, 0),
            stdout,
            "",
        )

    return calls, fake_run


@pytest.mark.parametrize(
    ("port", "observed"),
    [
        ("api-port", "0.0.0.0:8000\n"),
        ("frontend-port", "127.0.0.1:3000\n"),
    ],
)
def test_live_runtime_identity_rejects_unbound_published_port(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
    observed: str,
) -> None:
    runner = _load_module(
        f"qi_run_p0_unbound_{port}",
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    payloads = {"api": valid, "worker": valid, "postgres": "0014\n"}
    _calls, fake_run = _runtime_identity_run(
        runner,
        payloads=payloads,
        ports={port: observed},
    )
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize("field", ["mode", "router", "model"])
def test_live_preflight_rejects_recognition_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    field: str,
) -> None:
    runner = _load_module(
        f"qi_run_p0_runtime_identity_{service}_{field}",
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    mismatched = {**valid, field: "mismatch"}
    payloads = {
        "api": mismatched if service == "api" else valid,
        "worker": mismatched if service == "worker" else valid,
        "postgres": "0014\n",
    }
    _calls, fake_run = _runtime_identity_run(runner, payloads=payloads)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize(
    "relative",
    [
        "app/providers/visual_symbol_review.schema.json",
        "app/providers/qwen_vl.py",
        "app/candidates/advisor.py",
        "app/candidates/gdt_evidence.py",
        "app/candidates/geometric_tolerance.py",
        "app/candidates/symbol_review.py",
        "app/candidates/complex_fallback.py",
        "app/processing/automatic_result.py",
        "app/processing/runtime_recognition.py",
        "app/pdf/inventory.py",
        "app/pdf/gdt_frames.py",
        "app/pdf/gdt_raster_frames.py",
    ],
)
def test_live_runtime_identity_rejects_each_stale_hash(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    relative: str,
) -> None:
    runner = _load_module(
        "qi_run_p0_runtime_hash_" + service + "_" + relative.replace("/", "_"),
        HARNESS / "scripts/run-p0.py",
    )
    expected_paths = {
        str(path.relative_to(ROOT / "backend"))
        for path in (ROOT / "backend/app").rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json"}
    }
    assert set(runner.LIVE_API_GDT_RUNTIME_PATHS) == expected_paths
    valid = _expected_gdt_runtime_payload(runner)
    stale = json.loads(json.dumps(valid))
    stale["hashes"][relative] = "0" * 64
    payloads = {
        "api": stale if service == "api" else valid,
        "worker": stale if service == "worker" else valid,
        "postgres": "0014\n",
    }
    _calls, fake_run = _runtime_identity_run(runner, payloads=payloads)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


@pytest.mark.parametrize("service", ["api", "worker", "postgres"])
def test_live_runtime_identity_rejects_missing_compose_service(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
) -> None:
    runner = _load_module(
        f"qi_run_p0_missing_runtime_{service}",
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    payloads = {"api": valid, "worker": valid, "postgres": "0014\n"}
    _calls, fake_run = _runtime_identity_run(
        runner,
        payloads=payloads,
        returncodes={service: 1},
    )
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize("payload", ["not-json", {}, {"unexpected": True}])
def test_live_runtime_identity_rejects_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    payload: object,
) -> None:
    runner = _load_module(
        f"qi_run_p0_malformed_runtime_{service}_{type(payload).__name__}",
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    payloads = {
        "api": payload if service == "api" else valid,
        "worker": payload if service == "worker" else valid,
        "postgres": "0014\n",
    }
    _calls, fake_run = _runtime_identity_run(runner, payloads=payloads)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


@pytest.mark.parametrize(
    "revision",
    ["0013\n", "0014\n0013\n", "not-a-revision\n"],
)
def test_live_runtime_identity_rejects_database_revision_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
) -> None:
    runner = _load_module(
        "qi_run_p0_database_revision_" + hashlib.sha256(
            revision.encode()
        ).hexdigest()[:8],
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    payloads = {"api": valid, "worker": valid, "postgres": revision}
    _calls, fake_run = _runtime_identity_run(runner, payloads=payloads)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner._require_compose_runtime_identity()


def test_live_preflight_accepts_exact_api_worker_and_database_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_exact_runtime_identity",
        HARNESS / "scripts/run-p0.py",
    )
    valid = _expected_gdt_runtime_payload(runner)
    payloads = {"api": valid, "worker": valid, "postgres": "0014\n"}
    calls, fake_run = _runtime_identity_run(runner, payloads=payloads)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner._require_compose_runtime_identity()

    assert calls == ["api", "worker", "api-port", "frontend-port", "postgres"]


def test_live_runtime_identity_fails_before_registration_or_run_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _load_module(
        "qi_run_p0_runtime_identity_order",
        HARNESS / "scripts/run-p0.py",
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    artifacts = {
        runner.CURRENT_FOUR_ARTIFACT: b"current-four",
        runner.SYMBOL_EVAL_ARTIFACT: b"symbol-eval",
        runner.SYMBOL_VERDICT_ARTIFACT: b"symbol-verdict",
    }
    events: list[str] = []
    monkeypatch.setattr(runner, "RUNS", runs)
    monkeypatch.setattr(
        runner,
        "_current_live_input_artifacts",
        lambda _source_root: artifacts,
    )
    monkeypatch.setattr(runner, "_require_live_environment", lambda _env: None)
    monkeypatch.setattr(runner, "_current_live_identity", lambda _env: {})

    def reject_runtime() -> None:
        events.append("runtime-identity")
        raise ValueError(
            "Compose runtime identity does not match GDT-10 live contract"
        )

    monkeypatch.setattr(runner, "_require_compose_runtime_identity", reject_runtime)
    monkeypatch.setattr(
        runner,
        "run_task",
        lambda *_args, **_kwargs: events.append("registration"),
    )
    monkeypatch.setattr(
        runner,
        "register_live_input_artifacts",
        lambda **_kwargs: events.append("symbol-registration"),
    )

    with pytest.raises(
        ValueError,
        match="Compose runtime identity does not match GDT-10 live contract",
    ):
        runner.activate_full_live_inputs(
            source_root="/current-four",
            environment={},
        )

    assert events == ["runtime-identity"]
    assert list(runs.iterdir()) == []


def test_typed_gdt_case_evidence_requires_exact_case_a_and_b() -> None:
    runner = _load_module(
        "qi_run_p0_typed_gdt_evidence",
        HARNESS / "scripts/run-p0.py",
    )
    cases = _typed_gdt_cases()
    raw_candidates = [
        {
            "candidate_id": case["candidate_id"],
            "payload": case,
            "source_location_ids": case["source_location_ids"],
        }
        for case in cases.values()
    ]

    evaluation = {
        "label_matches": [
            {
                "label_id": case["annotation_label_id"],
                "candidate_id": case["candidate_id"],
                "disposition": "candidate",
                "overlap_ratio": 1.0,
            }
            for case in cases.values()
        ]
    }

    assert runner._typed_gdt_case_evidence(
        raw_candidates,
        evaluation=evaluation,
        manifest=_symbol_manifest(),
    ) == cases

    raw_candidates[1]["payload"] = {
        **raw_candidates[1]["payload"],
        "tolerance_value": "0.05",
    }
    with pytest.raises(RuntimeError, match="typed GDT Case A/B"):
        runner._typed_gdt_case_evidence(
            raw_candidates,
            evaluation=evaluation,
            manifest=_symbol_manifest(),
        )


def test_embedded_provider_call_identity_seals_source_crop_model_prompt_schema() -> None:
    runner = _load_module(
        "qi_run_p0_provider_call_identity",
        HARNESS / "scripts/run-p0.py",
    )
    identity_builder = _embedded_function(
        runner._SYMBOL_RESULT_PROGRAM,
        "provider_call_identity",
        {"hashlib": hashlib, "json": json},
    )
    identity = {
        "source_sha256": "a" * 64,
        "visual_observation_ids": ["visual-a"],
        "crop_bbox_pdf": [1.0, 2.0, 3.0, 4.0],
        "crop_sha256": "b" * 64,
        "model": "qwen3-vl-plus",
        "prompt_version": "visual-symbol-prompt/4",
        "schema_version": "visual-symbol-review/3",
    }

    assert identity_builder(
        identity,
        request_id="request-a",
        schema_sha256="c" * 64,
    ) == {
        **identity,
        "model_identity_sha256": (
            "6918ac1f8497fbd57c88eab5ff17f7e68678c6c5fd1028cb168a8dcf8bc5dae0"
        ),
        "prompt_identity_sha256": (
            "5897c04eadbe40c189e500f64ff84738ffc17d59bb607aae665d4d07a41af811"
        ),
        "schema_sha256": "c" * 64,
        "request_id_sha256": (
            "80d51bb829a6e379a6f43309aa6b28d206ff39953816b748267b16bed58be497"
        ),
    }


def test_provider_crop_evidence_is_run_bound_and_content_addressed(
    tmp_path: Path,
) -> None:
    runner = _load_module(
        "qi_run_p0_provider_crop_evidence",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    (run_dir / "artifacts").mkdir(parents=True)
    crop_sha256 = hashlib.sha256(PNG_BYTES).hexdigest()
    identity = {"crop_sha256": crop_sha256, "request_id_sha256": "a" * 64}
    artifacts = [
        {
            "crop_sha256": crop_sha256,
            "content_base64": base64.b64encode(PNG_BYTES).decode("ascii"),
        }
    ]

    assert runner._seal_provider_crop_evidence(
        run_dir,
        [identity, {**identity, "request_id_sha256": "b" * 64}],
        artifacts,
    ) == [
        {
            **identity,
            "crop_ref": f"artifacts/provider-crops/{crop_sha256}.png",
        },
        {
            **identity,
            "request_id_sha256": "b" * 64,
            "crop_ref": f"artifacts/provider-crops/{crop_sha256}.png",
        },
    ]
    assert (
        run_dir / f"artifacts/provider-crops/{crop_sha256}.png"
    ).read_bytes() == PNG_BYTES

    second_run_dir = tmp_path / f"{RUN_ID}-tamper"
    (second_run_dir / "artifacts").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="crop artifact is invalid"):
        runner._seal_provider_crop_evidence(
            second_run_dir,
            [identity],
            [{**artifacts[0], "content_base64": base64.b64encode(
                COMPARISON_PNG_BYTES
            ).decode("ascii")}],
        )


def test_full_live_symbol_eval_run_is_literal_and_binds_sealed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LIVE-01 binds both sealed Quality Owner artifacts before live work."""
    runner = _load_module(
        "qi_run_p0_live_symbol_binding",
        HARNESS / "scripts/run-p0.py",
    )
    current_four_run = "20260727T010101000000Z-11111111"
    symbol_eval_run = "20260727T020202000000Z-22222222"
    full_run_id = "20260727T030303000000Z-33333333"
    current_four_bytes = json.dumps(_manifest(), sort_keys=True).encode()
    manifest_bytes = b'{"schema_version":"visual-symbol-eval/1"}'
    verdict_bytes = (
        b'{"schema_version":"visual-symbol-annotation-verdict/1"}'
    )
    expected_artifacts = {
        "artifacts/current-four-manifest.json": current_four_bytes,
        "artifacts/visual-symbol-eval.json": manifest_bytes,
        "artifacts/visual-symbol-annotation-verdict.json": verdict_bytes,
    }
    starts: list[dict[str, bytes]] = []

    def load_current(run_id: str) -> dict[str, bytes]:
        if run_id != current_four_run:
            raise ValueError("--current-four-run requires one literal registration run ID")
        return {"artifacts/current-four-manifest.json": current_four_bytes}

    def load_symbol(run_id: str) -> dict[str, bytes]:
        if run_id != symbol_eval_run:
            raise ValueError("--symbol-eval-run requires one literal sealed staging run ID")
        return {
            "artifacts/visual-symbol-eval.json": manifest_bytes,
            "artifacts/visual-symbol-annotation-verdict.json": verdict_bytes,
        }

    monkeypatch.setattr(runner, "_load_current_four_artifact", load_current)
    monkeypatch.setattr(runner, "load_symbol_eval_artifacts", load_symbol)

    def preflight(
        *,
        input_set: str,
        source_root: str | None,
        current_four_run: str,
        symbol_eval_run: str,
    ) -> dict[str, dict[str, bytes]]:
        assert input_set == "current-four"
        assert source_root is None
        return {
            "input_artifacts": runner._load_full_live_input_artifacts(
                current_four_run=current_four_run,
                symbol_eval_run=symbol_eval_run,
            )
        }

    def start(
        preflight_result: dict[str, dict[str, bytes]],
        *,
        authorized_run_id: str,
    ) -> str:
        assert authorized_run_id == full_run_id
        artifacts = preflight_result["input_artifacts"]
        starts.append(artifacts)
        run_dir = tmp_path / full_run_id
        (run_dir / "artifacts").mkdir(parents=True)
        runner._attach_full_live_input_artifacts(run_dir, artifacts)
        for name, expected in expected_artifacts.items():
            assert (run_dir / name).read_bytes() == expected
        return full_run_id

    monkeypatch.setattr(runner, "preflight_full_p0_live", preflight)
    monkeypatch.setattr(runner, "start_live_run", start)

    for alias in ("latest", "../" + symbol_eval_run):
        result = runner.main(
            [
                "live",
                "--scope",
                "full-p0",
                "--input-set",
                "current-four",
                "--current-four-run",
                current_four_run,
                "--symbol-eval-run",
                alias,
                "--pause-after",
                "first-pdf-balloons",
                "--print-run-id-only",
                "--authorized-run-id",
                full_run_id,
            ]
        )
        assert result == 2
    assert starts == []

    assert (
        runner.main(
            [
                "live",
                "--scope",
                "full-p0",
                "--input-set",
                "current-four",
                "--current-four-run",
                current_four_run,
                "--symbol-eval-run",
                symbol_eval_run,
                "--pause-after",
                "first-pdf-balloons",
                "--print-run-id-only",
                "--authorized-run-id",
                full_run_id,
            ]
        )
        == 0
    )
    assert starts == [expected_artifacts]


def test_full_p0_live_reuses_failure_proof_inside_the_same_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_live_failure", HARNESS / "scripts/run-p0.py")
    mirror = json.loads(
        (HARNESS / "contracts/p0-contracts.json").read_text(encoding="utf-8")
    )
    registered_selector = next(
        row["verification_selector"]
        for row in mirror["contracts"]
        if row["p0_contract_id"] == "P0-ACC-007"
    )
    expected = (0, "passed", "controlled failure proof", ["reports/proof.json"])
    monkeypatch.setattr(
        runner,
        "_failure_phase_outcome",
        lambda selector, run_dir: expected,
    )

    assert runner._phase_outcome(
        registered_selector,
        "live",
        tmp_path,
    ) == expected


def test_run_seal_removes_every_write_bit(tmp_path: Path) -> None:
    runner = _load_module("qi_run_p0_live_seal", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    nested = run_dir / "artifacts"
    nested.mkdir(parents=True)
    evidence = nested / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")

    runner._seal_run(run_dir)

    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    assert not run_dir.stat().st_mode & write_bits
    assert not nested.stat().st_mode & write_bits
    assert not evidence.stat().st_mode & write_bits


def test_pause_binds_identity_without_receipt_or_child_run(tmp_path: Path) -> None:
    runner = _load_module("qi_run_p0_live_pause", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(_run()), encoding="utf-8")
    live = _live_evidence()
    sample = live["samples"][0]
    sample["human_verdict"] = None
    sample["balloons"] = None
    sample["export"] = None
    sample["consistency"] = None
    live["design_qa"] = None
    live["samples"] = [sample]
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(live),
        encoding="utf-8",
    )

    runner.pause_live_run(run_dir)

    paused = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    live = json.loads(
        (run_dir / "live-run-evidence.json").read_text(encoding="utf-8")
    )
    _validate(paused, "run.schema.json")
    _validate(live, "live-run-evidence.schema.json")
    assert paused["execution_state"] == "visual_qa_pending"
    assert paused["pause_identity"] == {
        "code_identity": paused["code_identity"],
        "config_identity": paused["config_identity"],
        "contract_definition_hash": paused["contract_definition_hash"],
        "input_identity": paused["input_identity"],
        "live_identity": paused["live_identity"],
    }
    assert live["child_run_ids"] == []
    assert live["design_qa"] is None
    assert not (run_dir / "receipt.json").exists()
    assert runner.can_resume_live_run(run_dir) is True


def test_resume_loads_the_paused_live_evidence_before_continuing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_resume_load",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    live = _live_evidence()
    live["samples"] = [live["samples"][0]]
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(live))
    preflight = runner.LivePreflight(
        source_root=tmp_path,
        source_paths=tuple(tmp_path / f"source-{order}.pdf" for order in range(1, 5)),
        manifest_bytes=_json_bytes(_manifest()),
        input_artifacts={
            "artifacts/current-four-manifest.json": _json_bytes(_manifest()),
            "artifacts/visual-symbol-eval.json": _json_bytes(
                _symbol_manifest()
            ),
            "artifacts/visual-symbol-annotation-verdict.json": b"{}",
        },
        mirror={},
        bindings={},
        policies={},
        code_identity={},
        config_identity={},
        input_identity={},
    )

    class ResumeReached(RuntimeError):
        pass

    class ReceiptStub:
        @staticmethod
        def validate_schema(*args) -> None:
            del args

    monkeypatch.setattr(
        runner,
        "_current_live_identity",
        lambda: {
            "operator_id": "quality-1",
            "frontend_base": "http://127.0.0.1:14173",
        },
    )
    monkeypatch.setattr(runner, "_wait_seconds", lambda: 1)
    monkeypatch.setattr(runner, "_resume_identity_preflight", lambda _run_dir: preflight)
    monkeypatch.setattr(runner, "_design_qa_evidence", lambda *args: {})
    monkeypatch.setattr(runner, "_bind_design_qa_and_resume", lambda *args: _run("running"))
    monkeypatch.setattr(runner, "_receipt_module", ReceiptStub)
    monkeypatch.setattr(runner, "abort_live_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner,
        "_complete_sample_after_balloons",
        lambda *args, **kwargs: (_ for _ in ()).throw(ResumeReached("continued")),
    )

    with pytest.raises(ResumeReached, match="continued"):
        runner.resume_live_run(run_dir, design_qa=tmp_path / "design-qa.md")


def test_design_qa_resume_gate_requires_bound_zero_issue_comparison_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_design_qa", HARNESS / "scripts/run-p0.py")
    design_qa = tmp_path / "design-qa.md"
    monkeypatch.setattr(runner, "_design_qa_document_path", lambda: design_qa)
    run_dir = tmp_path / RUN_ID
    reports = run_dir / "reports"
    reports.mkdir(parents=True)
    implementation = reports / "design-qa-implementation.png"
    comparison = reports / "design-qa-comparison.png"
    implementation.write_bytes(PNG_BYTES)
    comparison.write_bytes(COMPARISON_PNG_BYTES)
    live = _live_evidence()
    live["design_qa"] = None
    live["samples"] = [live["samples"][0]]
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(live),
        encoding="utf-8",
    )
    valid_text = "\n".join(
        (
            "# Design QA",
            "source sha256: " + "7" * 64,
            "implementation route: /?project_id=project-1&operator_id=quality-1",
            "implementation state: visual_qa_pending:first-pdf-balloons",
            "implementation capture: reports/design-qa-implementation.png",
            "implementation capture sha256: "
            + hashlib.sha256(PNG_BYTES).hexdigest(),
            "comparison capture: reports/design-qa-comparison.png",
            "comparison capture sha256: "
            + hashlib.sha256(COMPARISON_PNG_BYTES).hexdigest(),
            "browser: chrome",
            "viewport: 1565x796",
            "console errors: 0",
            "network errors: 0",
            "P0 issues: 0",
            "P1 issues: 0",
            "P2 issues: 0",
            "final result: passed",
            "",
        )
    )
    design_qa.write_text(
        valid_text,
        encoding="utf-8",
    )

    evidence = runner._design_qa_evidence(design_qa, run_dir)

    assert evidence["final_result"] == "passed"
    assert evidence["browser"] == "chrome"
    assert evidence["viewport"] == {"width": 1565, "height": 796}
    assert evidence["issue_counts"] == {"p0": 0, "p1": 0, "p2": 0}

    same_capture_text = valid_text.replace(
        "reports/design-qa-comparison.png",
        "reports/design-qa-implementation.png",
    ).replace(
        hashlib.sha256(COMPARISON_PNG_BYTES).hexdigest(),
        hashlib.sha256(PNG_BYTES).hexdigest(),
    )
    design_qa.write_text(same_capture_text, encoding="utf-8")
    with pytest.raises(ValueError, match="must be distinct"):
        runner._design_qa_evidence(design_qa, run_dir)

    escaped = run_dir / "escaped.png"
    escaped.write_bytes(PNG_BYTES)
    design_qa.write_text(
        valid_text.replace(
            "reports/design-qa-implementation.png",
            "reports/../escaped.png",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="capture ref is invalid"):
        runner._design_qa_evidence(design_qa, run_dir)

    implementation.write_bytes(b"not-a-png")
    design_qa.write_text(
        valid_text.replace(
            hashlib.sha256(PNG_BYTES).hexdigest(),
            hashlib.sha256(b"not-a-png").hexdigest(),
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be a PNG"):
        runner._design_qa_evidence(design_qa, run_dir)

    minimal = "# Design QA\n\nfinal result: passed\n"
    design_qa.write_text(minimal, encoding="utf-8")
    with pytest.raises(ValueError, match="required structured field"):
        runner._design_qa_evidence(design_qa, run_dir)


def test_resume_reopens_the_same_bound_run_before_continuation(tmp_path: Path) -> None:
    runner = _load_module("qi_run_p0_resume_state", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    paused = _run("visual_qa_pending")
    paused["pause_identity"] = {
        "code_identity": paused["code_identity"],
        "config_identity": paused["config_identity"],
        "contract_definition_hash": paused["contract_definition_hash"],
        "input_identity": paused["input_identity"],
        "live_identity": paused["live_identity"],
    }
    (run_dir / "run.json").write_bytes(_json_bytes(paused))

    resumed = runner._mark_live_run_resumed(run_dir)

    assert resumed["execution_state"] == "running"
    assert resumed["pause_identity"] == paused["pause_identity"]
    assert resumed["run_id"] == RUN_ID
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8")) == resumed


def test_invalid_live_evidence_seals_a_failed_resume_transition(tmp_path: Path) -> None:
    runner = _load_module("qi_run_p0_resume_failure", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    paused = _run("visual_qa_pending")
    paused["pause_identity"] = {
        "code_identity": paused["code_identity"],
        "config_identity": paused["config_identity"],
        "contract_definition_hash": paused["contract_definition_hash"],
        "input_identity": paused["input_identity"],
        "live_identity": paused["live_identity"],
    }
    (run_dir / "run.json").write_bytes(_json_bytes(paused))
    invalid_live = _live_evidence()
    design_evidence = invalid_live["design_qa"]
    invalid_live["design_qa"] = None
    invalid_live["samples"] = [invalid_live["samples"][0]]
    invalid_live["child_run_ids"] = ["forbidden-child"]
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(invalid_live))

    with pytest.raises(ValueError, match="live-run-evidence.schema.json"):
        runner._bind_design_qa_and_resume(run_dir, design_evidence)

    failed = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert failed["execution_state"] == "failed"
    assert failed["completed_at"] is not None
    assert runner.can_resume_live_run(run_dir) is False
    assert stat.S_IMODE((run_dir / "run.json").stat().st_mode) & stat.S_IWUSR == 0


def test_browser_export_cannot_run_before_bound_balloon_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_export_gate", HARNESS / "scripts/run-p0.py")
    sample = _sample_evidence(1)
    sample["human_verdict"] = None
    sample["balloons"]["browser"] = None
    sample["export"] = None
    sample["consistency"] = None
    events: list[str] = []

    def browser(_run_dir, _sample, *, operator_id, phase):
        del operator_id
        events.append(f"browser:{phase}")
        result = (
            {
                "phase": phase,
                "hard_collision_count": 0,
                "unresolved_manual_required_count": 0,
                "active_item_ids": ["item-1-1", "item-1-2"],
                "active_item_numbers": ["1", "2"],
            }
            if phase == "pre-export"
            else {"phase": phase}
        )
        return {"passed": True}, result

    def verdict(_run_dir, *, order, project_id, stage, timeout):
        del order, project_id, timeout
        events.append(f"verdict:{stage}")
        return _human_verdict()

    def collect(_run_dir, _sample, _browser_result):
        events.append("collect:post-export")
        return _sample_evidence(1)

    monkeypatch.setattr(runner, "_run_browser_e2e", browser)
    monkeypatch.setattr(runner, "_wait_for_sample_verdict", verdict)
    monkeypatch.setattr(runner, "_collect_post_export_evidence", collect)
    monkeypatch.setattr(runner, "_write_live_sample", lambda *args: None)

    runner._complete_sample_after_balloons(
        tmp_path,
        sample,
        operator_id="quality-1",
        timeout=1,
    )

    assert events == [
        "browser:pre-export",
        "verdict:balloons",
        "browser:export",
        "collect:post-export",
    ]

    events.clear()

    def rejected(*args, **kwargs):
        del args, kwargs
        events.append("verdict:balloons")
        raise RuntimeError("negative balloons verdict blocks formal publication")

    monkeypatch.setattr(runner, "_wait_for_sample_verdict", rejected)
    with pytest.raises(RuntimeError, match="blocks formal publication"):
        runner._complete_sample_after_balloons(
            tmp_path,
            sample,
            operator_id="quality-1",
            timeout=1,
        )
    assert events == ["browser:pre-export", "verdict:balloons"]


def test_missing_review_command_proof_blocks_before_item_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_review_readiness", HARNESS / "scripts/run-p0.py")
    sample = _sample_evidence(1)
    weak_review = dict(sample["review"])
    weak_review["frozen_version"] = None
    weak_review["frozen_by"] = None
    weak_review["items_frozen_at"] = None
    weak_review["operation_commands"] = [
        command
        for command in weak_review["operation_commands"]
        if command != "edit"
    ]
    freezes: list[str] = []
    monkeypatch.setattr(runner, "_wait_for_sample_verdict", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        runner,
        "_load_human_verdict",
        lambda _run_dir: {
            "schema_version": "human-verdict/1",
            "run_id": RUN_ID,
            "samples": [_verdict_sample(1)],
        },
    )
    monkeypatch.setattr(
        runner,
        "_collect_item_set_readiness",
        lambda *args, **kwargs: weak_review,
    )
    monkeypatch.setattr(
        runner,
        "_freeze_and_generate_when_ready",
        lambda *args, **kwargs: freezes.append("freeze"),
    )

    with pytest.raises(RuntimeError, match="review command/disposition proof"):
        runner._freeze_sample_after_item_verdict(
            tmp_path / RUN_ID,
            sample,
            operator_id="quality-1",
            timeout=1,
        )

    assert freezes == []


def test_item_set_verdict_cannot_be_recorded_after_item_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_pre_frozen_review",
        HARNESS / "scripts/run-p0.py",
    )
    sample = _sample_evidence(1)
    pre_frozen = dict(sample["review"])
    pre_frozen["items_frozen_at"] = "2026-07-22T00:00:30Z"
    freezes: list[str] = []
    monkeypatch.setattr(runner, "_wait_for_sample_verdict", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        runner,
        "_load_human_verdict",
        lambda _run_dir: {
            "schema_version": "human-verdict/1",
            "run_id": RUN_ID,
            "samples": [_verdict_sample(1)],
        },
    )
    monkeypatch.setattr(
        runner,
        "_collect_item_set_readiness",
        lambda *args, **kwargs: pre_frozen,
    )
    monkeypatch.setattr(
        runner,
        "_freeze_and_generate_when_ready",
        lambda *args, **kwargs: freezes.append("freeze"),
    )
    monkeypatch.setattr(
        runner,
        "_collect_review_balloon_evidence",
        lambda *args, **kwargs: {
            "review": sample["review"],
            "balloons": sample["balloons"],
        },
    )
    monkeypatch.setattr(runner, "_write_live_sample", lambda *args: None)

    with pytest.raises(RuntimeError, match="must precede item freeze"):
        runner._freeze_sample_after_item_verdict(
            tmp_path / RUN_ID,
            sample,
            operator_id="quality-1",
            timeout=1,
        )

    assert freezes == []


def test_balloon_verdict_target_requires_post_action_browser_evidence(
    tmp_path: Path,
) -> None:
    verdict_module = _load_module(
        "qi_record_human_verdict_browser_gate",
        HARNESS / "scripts/record-human-verdict.py",
    )
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "run.json").write_bytes(_json_bytes(_run()))
    live = _live_evidence()
    live["samples"] = [live["samples"][0]]
    live["samples"][0]["balloons"]["browser"] = None
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(live))

    with pytest.raises(ValueError, match="post-action pre-export browser evidence"):
        verdict_module._validate_target(
            run_dir,
            order=1,
            project_id="project-1",
            operator_id="quality-1",
            stage="balloons",
        )


def test_browser_e2e_environment_does_not_forward_server_credentials(
    tmp_path: Path,
) -> None:
    runner = _load_module("qi_run_p0_browser_env", HARNESS / "scripts/run-p0.py")
    base = {
        "PATH": "/usr/bin",
        "HOME": "/tmp/browser-home",
        "LANG": "C.UTF-8",
        "QI_TENCENT_SECRET_ID": "server-secret",
        "QI_TENCENT_SECRET_KEY": "server-secret",
        "QI_QWEN_API_KEY": "server-secret",
        "QI_QWEN_WORKSPACE_ID": "server-secret",
        "QI_PROVIDER_MODE": "live",
        "QI_PROVIDER_NETWORK_ENABLED": "enabled",
        "QI_DATABASE_URL": "postgresql://server-only",
        "QI_REDIS_URL": "redis://server-only",
        "QI_P0_FRONTEND_BASE": "http://127.0.0.1:14173",
    }
    browser = runner._browser_environment(
        tmp_path / RUN_ID,
        _sample_evidence(1),
        operator_id="quality-1",
        phase="pre-export",
        base_environment=base,
    )

    assert browser["PATH"] == "/usr/bin"
    assert browser["QI_P0_RUN_ID"] == RUN_ID
    assert browser["QI_P0_SAMPLE_ORDER"] == "1"
    assert browser["QI_P0_PROJECT_URL"].startswith("http://127.0.0.1:14173/")
    assert all(key not in browser for key in runner.LIVE_CREDENTIAL_KEYS)
    assert "QI_PROVIDER_MODE" not in browser
    assert "QI_PROVIDER_NETWORK_ENABLED" not in browser
    assert "QI_DATABASE_URL" not in browser
    assert "QI_REDIS_URL" not in browser


def test_selector_environment_uses_host_reachable_current_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_selector_env", HARNESS / "scripts/run-p0.py")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv == ["docker", "compose", "ps", "-q", "postgres"]:
            return subprocess.CompletedProcess(argv, 0, "postgres-container\n", "")
        if argv == ["docker", "inspect", "postgres-container"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    [
                        {
                            "NetworkSettings": {
                                "Networks": {
                                    "quality-inspection_default": {
                                        "IPAddress": "172.23.0.4"
                                    }
                                }
                            }
                        }
                    ]
                ),
                "",
            )
        raise AssertionError(f"unexpected subprocess: {argv}")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    environment = runner._selector_environment(
        {
            "PATH": "/usr/bin",
            "PYTHONPATH": "/existing/pythonpath",
            "QI_QWEN_API_KEY": "server-secret",
            "QI_QWEN_WORKSPACE_ID": "server-secret",
            "QI_TENCENT_SECRET_ID": "server-secret",
            "QI_TENCENT_SECRET_KEY": "server-secret",
            "QI_PROVIDER_MODE": "live",
            "QI_PROVIDER_NETWORK_ENABLED": "enabled",
            "QI_DATABASE_URL": (
                "postgresql+psycopg://qi:qi@postgres:5432/qi?sslmode=disable"
            ),
        }
    )

    database_url = urlsplit(environment["QI_DATABASE_URL"])
    assert database_url.hostname == "172.23.0.4"
    assert database_url.path == "/qi"
    assert database_url.query == "sslmode=disable"
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(ROOT / "backend"),
        "/existing/pythonpath",
    ]
    assert all(key not in environment for key in runner.LIVE_CREDENTIAL_KEYS)
    assert runner.LIVE_PROVIDER_MODE not in environment
    assert runner.LIVE_PROVIDER_NETWORK not in environment

    default_environment = runner._selector_environment({"PATH": "/usr/bin"})
    assert urlsplit(default_environment["QI_DATABASE_URL"]).hostname == "172.23.0.4"


def test_live_phase_outcomes_require_strong_per_sample_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_phase_evidence", HARNESS / "scripts/run-p0.py")
    run_dir = tmp_path / RUN_ID
    design_qa = tmp_path / "design-qa.md"
    monkeypatch.setattr(runner, "_design_qa_document_path", lambda: design_qa)
    _materialize_bound_live_evidence(run_dir, design_qa)
    for phase in PHASES:
        exit_code, state, _, refs = runner._live_phase_outcome(
            f"phase://live/{phase}?input_set=current-four",
            run_dir,
        )
        assert exit_code == 0
        assert state == "passed"
        assert refs

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["candidates"]["coverage_checked"] = False
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(weak),
        encoding="utf-8",
    )
    assert runner._live_phase_outcome(
        "phase://live/candidates?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["consistency"]["excel_numbers"] = [1, 3]
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(weak),
        encoding="utf-8",
    )
    assert runner._live_phase_outcome(
        "phase://live/consistency?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["review"]["operation_target_ids"] = [
        "item-1-1",
        "item-1-2",
    ]
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(weak),
        encoding="utf-8",
    )
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["review"]["operation_commands"].remove("edit")
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(weak))
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["candidates"]["candidate_records"][0][
        "source_evidence"
    ][0]["coordinates"] = [10, 10, 10, 15]
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(weak))
    assert runner._live_phase_outcome(
        "phase://live/candidates?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    _materialize_bound_live_evidence(run_dir, design_qa)
    verdict = json.loads(
        (run_dir / "artifacts/human-verdict.json").read_text(encoding="utf-8")
    )
    verdict["samples"][0]["project_id"] = "spliced-project"
    (run_dir / "artifacts/human-verdict.json").write_bytes(_json_bytes(verdict))
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    _materialize_bound_live_evidence(run_dir, design_qa)
    verdict = json.loads(
        (run_dir / "artifacts/human-verdict.json").read_text(encoding="utf-8")
    )
    verdict["samples"][0]["item_set"]["recorded_at"] = (
        "2026-07-22T00:01:20Z"
    )
    (run_dir / "artifacts/human-verdict.json").write_bytes(
        _json_bytes(verdict)
    )
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    _materialize_bound_live_evidence(run_dir, design_qa)
    verdict = json.loads(
        (run_dir / "artifacts/human-verdict.json").read_text(encoding="utf-8")
    )
    verdict["samples"][0]["item_set"]["answers"][
        "automatic_candidates_are_actionable"
    ] = False
    (run_dir / "artifacts/human-verdict.json").write_bytes(
        _json_bytes(verdict)
    )
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    browser = weak["samples"][0]["balloons"]["browser"]
    browser_result_path = run_dir / str(browser["result_ref"])
    browser_result = json.loads(browser_result_path.read_text(encoding="utf-8"))
    browser_result["backend_item_numbers"] = [
        {"item_id": "item-1-1", "formal_number": 1},
        {"item_id": "item-1-2", "formal_number": 2},
    ]
    browser_result["overlay_item_numbers"] = [
        {"item_id": "item-1-1", "formal_number": 2},
        {"item_id": "item-1-2", "formal_number": 1},
    ]
    browser["result_sha256"] = _write_hashed(
        browser_result_path,
        _json_bytes(browser_result),
    )
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(weak))
    assert runner._live_phase_outcome(
        "phase://live/balloons?input_set=current-four",
        run_dir,
    )[1] == "blocked"
    live = _materialize_bound_live_evidence(run_dir, design_qa)
    review_ref = live["samples"][0]["review"]["evidence_ref"]
    (run_dir / review_ref).write_text("tampered\n", encoding="utf-8")
    assert runner._live_phase_outcome(
        "phase://live/review?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["consistency"]["workbench_item_numbers"][0][
        "formal_number"
    ] = 2
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(weak))
    assert runner._live_phase_outcome(
        "phase://live/consistency?input_set=current-four",
        run_dir,
    )[1] == "blocked"

    weak = _materialize_bound_live_evidence(run_dir, design_qa)
    weak["samples"][0]["balloons"]["browser"]["captured_at"] = (
        "2026-07-22T00:02:30Z"
    )
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(weak))
    assert runner._live_phase_outcome(
        "phase://live/balloons?input_set=current-four",
        run_dir,
    )[1] == "blocked"


@pytest.mark.parametrize(
    "tamper",
    ("case_frame", "prompt_identity", "crop_identity", "malformed_counts"),
)
def test_symbol_report_rejects_typed_frame_or_provider_identity_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    runner = _load_module(
        f"qi_run_p0_symbol_report_tamper_{tamper}",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    design_qa = tmp_path / "design-qa.md"
    monkeypatch.setattr(runner, "_design_qa_document_path", lambda: design_qa)
    live = _materialize_bound_live_evidence(run_dir, design_qa)
    report_path = run_dir / "reports/symbol-recognition.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if tamper == "case_frame":
        report["typed_gdt_cases"]["case_b"]["frames"][0]["segments"][0][
            "tolerance_value"
        ] = "9.9"
    elif tamper == "prompt_identity":
        report["provider_call_identities"][0]["prompt_identity_sha256"] = "0" * 64
    elif tamper == "crop_identity":
        report["provider_call_identities"][0]["crop_sha256"] = "0" * 64
    else:
        report["evaluation"]["counts"] = []
    live["symbol_recognition"]["report_sha256"] = _write_hashed(
        report_path,
        _json_bytes(report),
    )
    (run_dir / "live-run-evidence.json").write_bytes(_json_bytes(live))

    assert runner._live_phase_outcome(
        "phase://live/candidates?input_set=current-four",
        run_dir,
    )[1] == "blocked"


def test_live_operator_and_runtime_identity_are_bound_across_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_live_identity", HARNESS / "scripts/run-p0.py")
    monkeypatch.setenv("QI_P0_OPERATOR_ID", "quality-1")
    monkeypatch.setenv("QI_P0_API_BASE", "http://127.0.0.1:18000")
    monkeypatch.setenv("QI_P0_FRONTEND_BASE", "http://127.0.0.1:14173")
    monkeypatch.setenv(
        "COMPOSE_PROJECT_NAME",
        "structured-geometric-tolerance-recognition-qa",
    )
    monkeypatch.setattr(
        runner,
        "_chrome_identity",
        lambda environment: _run()["live_identity"]["browser"],
    )
    assert runner._current_live_identity() == _run()["live_identity"]

    monkeypatch.setenv("QI_P0_OPERATOR_ID", "quality-2")
    assert runner._current_live_identity() != _run()["live_identity"]


def test_live_identity_accepts_exact_isolated_compose_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_run_p0_isolated_live_target",
        HARNESS / "scripts/run-p0.py",
    )
    monkeypatch.setattr(
        runner,
        "_chrome_identity",
        lambda environment: _run()["live_identity"]["browser"],
    )

    identity = runner._current_live_identity(
        {
            "QI_P0_OPERATOR_ID": "quality-1",
            "QI_P0_API_BASE": "http://127.0.0.1:18000",
            "QI_P0_FRONTEND_BASE": "http://127.0.0.1:14173",
            "COMPOSE_PROJECT_NAME": "structured-geometric-tolerance-recognition-qa",
        }
    )

    assert identity["api_base"] == "http://127.0.0.1:18000"
    assert identity["frontend_base"] == "http://127.0.0.1:14173"


@pytest.mark.parametrize(
    ("api_base", "frontend_base", "compose_project"),
    [
        (
            "http://localhost:8000",
            "http://localhost:3000",
            "structured-geometric-tolerance-recognition-qa",
        ),
        (
            "http://127.0.0.1:18000",
            "http://127.0.0.1:14173",
            "quality_inspection",
        ),
        (
            "http://127.0.0.1:18000",
            "http://127.0.0.1:14173",
            "",
        ),
    ],
)
def test_live_identity_rejects_main_or_unbound_compose_target(
    monkeypatch: pytest.MonkeyPatch,
    api_base: str,
    frontend_base: str,
    compose_project: str,
) -> None:
    runner = _load_module(
        "qi_run_p0_reject_unbound_live_target_"
        + hashlib.sha256(
            f"{api_base}|{frontend_base}|{compose_project}".encode()
        ).hexdigest()[:8],
        HARNESS / "scripts/run-p0.py",
    )
    monkeypatch.setattr(
        runner,
        "_chrome_identity",
        lambda environment: _run()["live_identity"]["browser"],
    )

    with pytest.raises(ValueError, match="verified isolated Compose"):
        runner._current_live_identity(
            {
                "QI_P0_OPERATOR_ID": "quality-1",
                "QI_P0_API_BASE": api_base,
                "QI_P0_FRONTEND_BASE": frontend_base,
                "COMPOSE_PROJECT_NAME": compose_project,
            }
        )


def test_chrome_identity_uses_the_resolved_binary_version_and_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_chrome_identity", HARNESS / "scripts/run-p0.py")
    chrome = tmp_path / "google-chrome"
    chrome.write_bytes(b"verified chrome launcher")
    monkeypatch.setattr(
        runner.shutil,
        "which",
        lambda name, path: str(chrome) if name == "google-chrome" else None,
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="Google Chrome 149.0.7827.53\n",
            stderr="",
        ),
    )

    identity = runner._chrome_identity({"PATH": str(tmp_path), "LANG": "C"})

    assert identity == {
        "name": "chrome",
        "executable": "google-chrome",
        "version": "Google Chrome 149.0.7827.53",
        "sha256": hashlib.sha256(b"verified chrome launcher").hexdigest(),
    }


def test_all_twelve_harness_schemas_are_checked_and_bound_to_code_identity() -> None:
    checker = _load_module(
        "qi_contract_checker_schema_inventory",
        HARNESS / "scripts/check-contracts.py",
    )
    receipt = _load_module(
        "qi_receipt_schema_inventory",
        HARNESS / "scripts/generate-receipt.py",
    )
    expected = {
        "contract-result.schema.json",
        "current-four-manifest.schema.json",
        "global-contract-bindings.schema.json",
        "human-verdict.schema.json",
        "live-run-evidence.schema.json",
        "p0-contracts.schema.json",
        "provider-fixture.schema.json",
        "receipt.schema.json",
        "run.schema.json",
        "symbol-routing-canary-evidence.schema.json",
        "visual-symbol-annotation-verdict.schema.json",
        "visual-symbol-eval.schema.json",
    }
    assert set(checker.EXPECTED_SCHEMA_FILES) == expected
    assert set(receipt.SCHEMA_FILES) == expected


def test_live_policy_requires_visual_symbol_page_budget() -> None:
    """P0-REC-005: live visual review stays within sixteen calls per page."""
    runner = _load_module(
        "qi_runner_visual_page_budget",
        HARNESS / "scripts/run-p0.py",
    )
    provider_policy = {
        "explicit_flag_required": True,
        "max_coordinator_retries_per_logical_call": 1,
        "max_submissions_per_logical_call": 2,
        "max_crop_expansions": 1,
        "max_ocr_calls_per_page": 16,
        "max_vision_calls_per_candidate": 2,
        "max_total_estimated_cost_cny": 50,
        "budget_exceeded_result": "blocked",
    }
    with pytest.raises(ValueError, match="budget/retry"):
        runner._validate_live_policy(
            {"provider_call_policy": {"live": provider_policy}}
        )

    plan = (
        ROOT
        / "docs/superpowers/plans/2026-07-21-pdf-auto-balloon-and-excel.md"
    ).read_text(encoding="utf-8")
    provider_example = plan.split(
        "# .agent/harness/policy/provider-call-policy.yaml",
        1,
    )[1].split("```", 1)[0]
    assert "max_vision_calls_per_page: 16" in provider_example

    provider_policy["max_vision_calls_per_page"] = 16
    runner._validate_live_policy(
        {"provider_call_policy": {"live": provider_policy}}
    )

    provider_policy["max_vision_calls_per_page"] = 17
    with pytest.raises(ValueError, match="budget/retry"):
        runner._validate_live_policy(
            {"provider_call_policy": {"live": provider_policy}}
        )


def _issue_cycle_authorization(module: ModuleType, root: Path) -> dict[str, str]:
    identity = {
        "cycle_id": "gdt10d-contract-cycle",
        "expires_at": "2099-08-02T23:59:59+00:00",
        "head_revision": "a" * 40,
        "plan_sha256": "b" * 64,
        "pricing_sha256": "c" * 64,
        "runtime_closure_sha256": "d" * 64,
        "current_four_sha256": "e" * 64,
        "backend_image_id": "sha256:" + "9" * 64,
        "compose_project": "quality_inspection-qa",
        "expected_db_revision": "0014",
        "max_total_cny": "50.000000",
    }
    module.issue_authorization(root, **identity)
    return identity


def test_cycle_authorization_consume_run_project_and_terminal_are_exclusive(
    tmp_path: Path,
) -> None:
    authorization_path = HARNESS / "scripts/live_cycle_authorization.py"
    authorization = _load_module(
        "qi_live_cycle_authorization_exclusive",
        authorization_path,
    )
    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)

    commands = [
        subprocess.Popen(
            [
                sys.executable,
                str(authorization_path),
                "consume",
                "--authorization",
                str(root),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [command.communicate(timeout=10) for command in commands]
    assert sorted(command.returncode for command in commands) == [0, 2]
    assert all(identity["cycle_id"] not in output for pair in results for output in pair)

    authorization.bind_run(root, run_id=RUN_ID)
    with pytest.raises(ValueError, match="already bound"):
        authorization.bind_run(root, run_id=RUN_ID)
    authorization.admit_project(
        root,
        run_id=RUN_ID,
        project_id="project-1",
        project_order=1,
        source_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="already admitted"):
        authorization.admit_project(
            root,
            run_id=RUN_ID,
            project_id="project-1",
            project_order=1,
            source_sha256="f" * 64,
        )
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="9" * 64,
    )
    resume_commands = [
        subprocess.Popen(
            [
                sys.executable,
                str(authorization_path),
                "resume-consume",
                "--authorization",
                str(root),
                "--run-id",
                RUN_ID,
                "--pause-evidence-sha256",
                "9" * 64,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    resume_results = [
        command.communicate(timeout=10) for command in resume_commands
    ]
    assert sorted(command.returncode for command in resume_commands) == [0, 2]
    assert all(
        identity["cycle_id"] not in output
        for pair in resume_results
        for output in pair
    )
    from app.providers.cycle_authorization import (
        write_terminal_from_close_bridge,
    )

    terminal = write_terminal_from_close_bridge(
        authorization_root=root,
        cycle_id=identity["cycle_id"],
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="1" * 64,
    )
    assert terminal["status"] == "failed"
    assert write_terminal_from_close_bridge(
        authorization_root=root,
        cycle_id=identity["cycle_id"],
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="1" * 64,
    ) == terminal
    with pytest.raises(ValueError, match="terminal"):
        authorization.admit_project(
            root,
            run_id=RUN_ID,
            project_id="project-2",
            project_order=2,
            source_sha256="2" * 64,
        )

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for path in (root / "issuance.json", root / "consumption.json", root / "run.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_cycle_authorization_protocol_matches_runtime_read_only_validator(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_runtime_contract",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    from app.providers.cycle_authorization import (
        validate_active_cycle_authorization,
        write_terminal_from_close_bridge,
    )

    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.admit_project(
        root,
        run_id=RUN_ID,
        project_id="project-1",
        project_order=1,
        source_sha256="f" * 64,
    )

    active = validate_active_cycle_authorization(
        authorization_root=root,
        cycle_id=identity["cycle_id"],
        project_id="project-1",
        pricing_sha256=identity["pricing_sha256"],
    )
    assert active.run_id == RUN_ID
    assert active.project_order == 1

    write_terminal_from_close_bridge(
        authorization_root=root,
        cycle_id=identity["cycle_id"],
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="1" * 64,
    )
    with pytest.raises(ValueError, match="terminal"):
        validate_active_cycle_authorization(
            authorization_root=root,
            cycle_id=identity["cycle_id"],
            project_id="project-1",
            pricing_sha256=identity["pricing_sha256"],
        )


def test_current_api_image_id_normalizes_compose_v5_bare_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_compose_image",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    digest = "8" * 64
    monkeypatch.setattr(
        authorization.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv,
            0,
            digest + "\n",
            "",
        ),
    )

    assert authorization._current_api_image_id() == f"sha256:{digest}"


def test_provider_policy_v2_has_unambiguous_retry_and_submission_limits() -> None:
    import yaml

    policy = yaml.safe_load(
        (HARNESS / "policy/provider-call-policy.yaml").read_text(encoding="utf-8")
    )
    assert policy["schema_version"] == "provider-call-policy/2"
    assert "max_retries_per_call" not in policy["live"]
    assert policy["live"]["max_coordinator_retries_per_logical_call"] == 1
    assert policy["live"]["max_submissions_per_logical_call"] == 2


def test_live_override_binds_exact_private_authorization_source(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_override_authorization_binding",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)
    environment = {
        "QI_TENCENT_SECRET_ID": "present-one",
        "QI_TENCENT_SECRET_KEY": "present-two",
        "QI_QWEN_API_KEY": "present-three",
        "QI_QWEN_WORKSPACE_ID": "present-four",
        "QI_SYMBOL_RECOGNITION_MODE": "production_uncertainty",
        "QI_QWEN_MODEL": "qwen3-vl-plus-2025-12-19",
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID": identity["cycle_id"],
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT": (
            "/run/qi-live-authorization"
        ),
    }
    override = tmp_path / "live.override.yaml"

    def write_override(source: str) -> None:
        override.write_text(
            json.dumps(
                {
                    "services": {
                        service: {
                            "environment": environment,
                            "volumes": [
                                {
                                    "type": "bind",
                                    "source": source,
                                    "target": "/run/qi-live-authorization",
                                    "read_only": True,
                                }
                            ],
                        }
                        for service in ("api", "worker")
                    }
                }
            ),
            encoding="utf-8",
        )
        override.chmod(0o600)

    write_override(str(root.resolve()))
    authorization.validate_live_override(override, root)

    write_override(str((tmp_path / "other-authorization").resolve()))
    with pytest.raises(ValueError, match="mount"):
        authorization.validate_live_override(override, root)


def test_safe_override_allows_only_mode_and_model_identity(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_safe_override_contract",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    safe_override = tmp_path / "safe.override.yaml"

    def write_override(service_extra: str = "") -> None:
        safe_override.write_text(
            "services:\n"
            "  api:\n"
            "    environment:\n"
            "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
            "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n"
            f"{service_extra}"
            "  worker:\n"
            "    environment:\n"
            "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
            "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n",
            encoding="utf-8",
        )
        safe_override.chmod(0o600)

    write_override()
    authorization.validate_safe_override(safe_override)

    write_override("      QI_QWEN_API_KEY: forbidden\n")
    with pytest.raises(ValueError, match="safe override"):
        authorization.validate_safe_override(safe_override)

    write_override("    volumes: [/run/qi-live-authorization]\n")
    with pytest.raises(ValueError, match="safe override"):
        authorization.validate_safe_override(safe_override)


def test_deactivate_runtime_proves_paid_controls_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_safe_runtime_proof",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    safe_override = tmp_path / "safe.override.yaml"
    safe_override.write_text(
        "services:\n"
        "  api:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n"
        "  worker:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n",
        encoding="utf-8",
    )
    safe_override.chmod(0o600)
    monkeypatch.setenv(
        "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
        str(safe_override),
    )
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "exec" not in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "credential_keys_present": [],
                    "cycle_keys_present": [],
                    "authorization_mount_present": False,
                    "mode": "production_uncertainty",
                    "model": "qwen3-vl-plus-2025-12-19",
                }
            ),
            "",
        )

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    authorization.deactivate_runtime()

    assert len(calls) == 3
    assert calls[0][-2:] == ["api", "worker"]
    assert [call[call.index("exec") + 2] for call in calls[1:]] == [
        "api",
        "worker",
    ]


def test_deactivate_runtime_rejects_residual_paid_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_safe_runtime_residual",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    safe_override = tmp_path / "safe.override.yaml"
    safe_override.write_text(
        "services:\n"
        "  api:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n"
        "  worker:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n",
        encoding="utf-8",
    )
    safe_override.chmod(0o600)
    monkeypatch.setenv(
        "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
        str(safe_override),
    )

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if "exec" not in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "credential_keys_present": ["QI_QWEN_API_KEY"],
                    "cycle_keys_present": [],
                    "authorization_mount_present": False,
                    "mode": "production_uncertainty",
                    "model": "qwen3-vl-plus-2025-12-19",
                }
            ),
            "",
        )

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="safe runtime identity"):
        authorization.deactivate_runtime()


def test_activate_runtime_validates_and_proves_live_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_activation_identity",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)
    safe_override = tmp_path / "safe.override.yaml"
    safe_override.write_text(
        "services:\n"
        "  api:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n"
        "  worker:\n"
        "    environment:\n"
        "      QI_SYMBOL_RECOGNITION_MODE: production_uncertainty\n"
        "      QI_QWEN_MODEL: qwen3-vl-plus-2025-12-19\n",
        encoding="utf-8",
    )
    safe_override.chmod(0o600)
    live_override = tmp_path / "live.override.yaml"
    live_environment = {
        "QI_TENCENT_SECRET_ID": "present-one",
        "QI_TENCENT_SECRET_KEY": "present-two",
        "QI_QWEN_API_KEY": "present-three",
        "QI_QWEN_WORKSPACE_ID": "present-four",
        "QI_SYMBOL_RECOGNITION_MODE": "production_uncertainty",
        "QI_QWEN_MODEL": "qwen3-vl-plus-2025-12-19",
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID": identity["cycle_id"],
        "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT": (
            "/run/qi-live-authorization"
        ),
    }
    live_override.write_text(
        json.dumps(
            {
                "services": {
                    service: {
                        "environment": live_environment,
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str(root.resolve()),
                                "target": "/run/qi-live-authorization",
                                "read_only": True,
                            }
                        ],
                    }
                    for service in ("api", "worker")
                }
            }
        ),
        encoding="utf-8",
    )
    live_override.chmod(0o600)
    monkeypatch.setenv(
        "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
        str(safe_override),
    )
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "exec" not in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "credential_keys_present": sorted(
                        key
                        for key in live_environment
                        if key
                        in {
                            "QI_TENCENT_SECRET_ID",
                            "QI_TENCENT_SECRET_KEY",
                            "QI_QWEN_API_KEY",
                            "QI_QWEN_WORKSPACE_ID",
                        }
                    ),
                    "cycle_keys_present": [
                        "QI_PROVIDER_CYCLE_AUTHORIZATION_ID",
                        "QI_PROVIDER_CYCLE_AUTHORIZATION_ROOT",
                    ],
                    "authorization_mount_present": True,
                    "authorization_mount_read_only": True,
                    "cycle_id_matches": True,
                    "authorization_root_matches": True,
                    "mode": "production_uncertainty",
                    "model": "qwen3-vl-plus-2025-12-19",
                }
            ),
            "",
        )

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    authorization.activate_runtime(live_override)

    assert len(calls) == 3
    assert calls[0][-2:] == ["api", "worker"]


def test_atomic_live_evidence_write_fsyncs_file_and_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_paid_project_durable_evidence",
        HARNESS / "scripts/run-p0.py",
    )
    syncs: list[int] = []
    monkeypatch.setattr(runner.os, "fsync", lambda fd: syncs.append(fd))

    target = tmp_path / "live-run-evidence.json"
    runner._atomic_write_json(target, {"state": "pending"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "state": "pending"
    }
    assert len(syncs) == 2


def test_cycle_authorization_current_four_hash_matches_canonical_staging() -> None:
    authorization = _load_module(
        "qi_live_authorization_current_four_identity",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    staging = _load_module(
        "qi_live_authorization_current_four_staging",
        HARNESS / "scripts/stage-current-four.py",
    )

    assert authorization._current_four_manifest_sha256() == hashlib.sha256(
        staging._manifest_bytes(staging.FROZEN_DOCUMENTS)
    ).hexdigest()


def test_runtime_closure_checker_requires_an_explicit_supported_source() -> None:
    checker_path = HARNESS / "scripts/check-contracts.py"

    working = subprocess.run(
        [
            sys.executable,
            str(checker_path),
            "--runtime-closure-source",
            "working",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    invalid = subprocess.run(
        [
            sys.executable,
            str(checker_path),
            "--runtime-closure-source",
            "unknown",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert working.returncode == 0
    assert "runtime_closure_files=" in working.stdout
    assert invalid.returncode != 0
    assert (
        HARNESS / "policy/gdt10d-runtime-closure.txt"
    ).is_file()


def test_paid_ledger_summary_recovers_from_durable_report(
    tmp_path: Path,
) -> None:
    runner = _load_module(
        "qi_paid_ledger_durable_report_recovery",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    (run_dir / "reports").mkdir(parents=True)
    paid_cycle = {
        "cycle_id": "gdt10d-contract-cycle",
        "pricing_sha256": "a" * 64,
        "journal_ref": (
            "asset://provider-usage-cycles/gdt10d-contract-cycle/"
        ),
    }
    report = {
        "schema_version": "provider-usage-evidence/1",
        "run_id": RUN_ID,
        "pricing_sha256": paid_cycle["pricing_sha256"],
        "cycle_id": paid_cycle["cycle_id"],
        "journal_ref": paid_cycle["journal_ref"],
        "committed_total_cny": "3.526656",
        "reservation_count": 2,
        "reserved_only_count": 0,
        "submission_started_count": 2,
        "unsettled_started_count": 0,
        "settled_count": 2,
        "entries": [{"attempt_index": 1}, {"attempt_index": 2}],
    }
    report["content_sha256"] = hashlib.sha256(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    (run_dir / "reports/provider-usage-ledger.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    assert runner._paid_cycle_ledger_summary_from_report(
        run_dir,
        paid_cycle,
    ) == {
        "committed_total_cny": "3.526656",
        "reservation_count": 2,
        "reserved_only_count": 0,
        "submission_started_count": 2,
        "settled_count": 2,
        "evidence_sha256": report["content_sha256"],
    }

    for field, value in (
        ("content_sha256", "f" * 64),
        ("run_id", "20260722T000000000000Z-11111111"),
        ("cycle_id", "foreign-cycle"),
        ("pricing_sha256", "f" * 64),
        ("journal_ref", "asset://provider-usage-cycles/foreign-cycle/"),
        ("reservation_count", 3),
    ):
        tampered = {**report, field: value}
        if field != "content_sha256":
            tampered.pop("content_sha256")
            tampered["content_sha256"] = hashlib.sha256(
                json.dumps(
                    tampered,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        (run_dir / "reports/provider-usage-ledger.json").write_text(
            json.dumps(tampered),
            encoding="utf-8",
        )
        with pytest.raises(
            RuntimeError,
            match="paid cycle ledger evidence is invalid",
        ):
            runner._paid_cycle_ledger_summary_from_report(
                run_dir,
                paid_cycle,
            )


def test_paid_routing_aggregate_separates_plan_denied_from_admitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_paid_routing_aggregate_contract",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    (run_dir / "reports").mkdir(parents=True)
    escalated = [f"group-{index:03d}" for index in range(198)]
    denied = escalated[:190]
    admitted = escalated[190:]
    started = admitted[:2]
    cancelled = admitted[2:]
    (run_dir / "reports/provider-usage-ledger.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "project_id": "project-1",
                        "subject_kind": "escalation_group",
                        "subject_id": group_id,
                        "state": "reserved_unknown",
                    }
                    for group_id in started
                ]
                + [
                    {
                        "project_id": "project-2",
                        "subject_kind": "escalation_group",
                        "subject_id": "foreign-project-group",
                        "state": "reserved_unknown",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "reports/provider-storage-1.json").write_text(
        json.dumps(
            {
                "project_id": "project-1",
                "artifacts": [
                    {
                        "ref": (
                            "asset://projects/project-1/provider-inputs/"
                            f"qwen-symbol/crop-{index}.png"
                        )
                    }
                    for index in range(2)
                ],
            }
        ),
        encoding="utf-8",
    )
    routing = {
        "project_id": "project-1",
        "total_decisions": 199,
        "escalated_group_ids": escalated,
        "budget_terminal_facts": [
            {
                "escalation_group_id": group_id,
                "diagnostic": {
                    "schema_version": "visual-symbol-budget-control/1",
                    "budget_origin": "routing_plan",
                },
            }
            for group_id in denied
        ],
        "cancelled_group_ids": cancelled,
        "terminal_group_ids": escalated,
        "paid_artifact_group_ids": started,
        "attempt_event_codes": [
            *(["not_started_budget_exhausted"] * 190),
            *(["provider_rate_limited"] * 2),
            *(["not_started_after_project_failure"] * 6),
        ],
    }
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(routing),
            stderr="",
        ),
    )

    aggregate = runner._capture_paid_routing_aggregate(
        run_dir,
        project_id="project-1",
        order=1,
    )

    assert aggregate["admitted_group_ids"] == admitted
    assert aggregate["submission_started_group_ids"] == started
    assert aggregate["never_submission_started_group_ids"] == cancelled
    assert aggregate["cancelled_group_ids"] == cancelled

    routing["budget_terminal_facts"][0]["diagnostic"][
        "budget_origin"
    ] = "provider_cycle_reservation"
    with pytest.raises(RuntimeError, match="terminal reconciliation"):
        runner._capture_paid_routing_aggregate(
            run_dir,
            project_id="project-1",
            order=1,
        )


def test_paid_routing_budget_origin_keeps_provider_reservation_admitted() -> None:
    runner = _load_module(
        "qi_paid_routing_budget_origin_contract",
        HARNESS / "scripts/run-p0.py",
    )
    escalated = ["routing-denied", "provider-reservation-denied"]
    facts = [
        {
            "escalation_group_id": "routing-denied",
            "diagnostic": {
                "schema_version": "visual-symbol-budget-control/1",
                "budget_origin": "routing_plan",
            },
        },
        {
            "escalation_group_id": "provider-reservation-denied",
            "diagnostic": {
                "schema_version": "visual-symbol-budget-control/1",
                "budget_origin": "provider_cycle_reservation",
            },
        },
    ]

    denied, admitted, provider_reservation_denied = (
        runner._partition_paid_budget_terminals(
        escalated,
        facts,
        )
    )

    assert denied == ["routing-denied"]
    assert admitted == ["provider-reservation-denied"]
    assert provider_reservation_denied == [
        "provider-reservation-denied"
    ]

    for invalid in (
        [{"escalation_group_id": "routing-denied", "diagnostic": None}],
        [
            {
                "escalation_group_id": "routing-denied",
                "diagnostic": {
                    "schema_version": "visual-symbol-budget-control/1",
                    "budget_origin": "unknown",
                },
            }
        ],
    ):
        with pytest.raises(RuntimeError, match="budget origin"):
            runner._partition_paid_budget_terminals(escalated, invalid)


def test_paid_project_identity_is_persisted_before_admission_and_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module(
        "qi_paid_project_admission_contract",
        HARNESS / "scripts/run-p0.py",
    )
    run_dir = tmp_path / RUN_ID
    (run_dir / "logs").mkdir(parents=True)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"sealed-source")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(
            {
                "paid_cycle": {
                    "projects": [],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        runner.LIVE_CYCLE_AUTHORIZATION_ENV,
        str(tmp_path / "authorization"),
    )
    events: list[str] = []

    class Authorization:
        @staticmethod
        def admit_project(*_args: object, **_kwargs: object) -> dict[str, str]:
            persisted = json.loads(
                (run_dir / "live-run-evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            assert persisted["paid_cycle"]["projects"] == [
                {
                    "project_order": 1,
                    "project_id": "project-1",
                    "source_sha256": source_sha256,
                    "admission_sha256": None,
                }
            ]
            events.append("admit")
            return {"content_sha256": "a" * 64}

    class Receipt:
        @staticmethod
        def validate_schema(*_args: object, **_kwargs: object) -> None:
            return None

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        phase = next(
            value.split("=", 1)[1]
            for value in argv
            if isinstance(value, str)
            and value.startswith("QI_P0_PREPARE_PHASE=")
        )
        events.append(phase)
        if phase == "create":
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    {
                        "project_id": "project-1",
                        "source_ref": "asset://source.pdf",
                        "source_sha256": source_sha256,
                    }
                ).encode(),
                b"",
            )
        persisted = json.loads(
            (run_dir / "live-run-evidence.json").read_text(encoding="utf-8")
        )
        assert persisted["paid_cycle"]["projects"] == [
            {
                "project_order": 1,
                "project_id": "project-1",
                "source_sha256": source_sha256,
                "admission_sha256": "a" * 64,
            }
        ]
        assert events == ["create", "admit", "process"]
        return subprocess.CompletedProcess(argv, 1, b"", b"blocked")

    monkeypatch.setattr(runner, "_cycle_authorization_module", lambda: Authorization)
    monkeypatch.setattr(runner, "_receipt_module", lambda: Receipt)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner,
        "_refresh_paid_cycle_ledger",
        lambda _run_dir: events.append("ledger") or {},
    )
    monkeypatch.setattr(
        runner,
        "_capture_paid_routing_aggregate",
        lambda _run_dir, **_kwargs: events.append("routing") or {},
    )
    monkeypatch.setattr(
        runner,
        "_capture_paid_storage_inventory",
        lambda _run_dir, **_kwargs: events.append("storage") or {},
    )

    with pytest.raises(RuntimeError, match="application process failed"):
        runner._prepare_live_project(
            run_dir,
            source_path=source,
            order=1,
            expected_sha256=source_sha256,
        )

    assert events == [
        "create",
        "admit",
        "process",
        "ledger",
        "storage",
        "routing",
    ]
    assert not (run_dir / "receipt.json").exists()
    assert not (run_dir / "reports/symbol-recognition.json").exists()


def test_failed_paid_cycle_allows_evidenced_unadmitted_project_without_ledger(
    tmp_path: Path,
) -> None:
    policy, run, live, run_dir = _paid_policy_evidence(tmp_path)
    run["execution_state"] = "failed"
    live["paid_cycle"]["terminal"]["status"] = "failed"
    live["paid_cycle"]["projects"] = [
        {
            "project_order": 1,
            "project_id": "created-before-admission-failure",
            "source_sha256": "1" * 64,
            "admission_sha256": None,
        }
    ]
    live["paid_cycle"]["ledger"] = None

    policy.validate_paid_cycle_evidence(
        run,
        live,
        require_success=False,
        evidence_dir=run_dir,
        root=ROOT,
    )


def _write_content_hashed(path: Path, document: dict[str, object]) -> str:
    payload = dict(document)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["content_sha256"] = digest
    path.write_text(json.dumps(payload), encoding="utf-8")
    return digest


def _paid_policy_evidence(
    tmp_path: Path,
) -> tuple[ModuleType, dict[str, object], dict[str, object], Path]:
    policy = _load_module(
        f"qi_paid_policy_{tmp_path.name}",
        HARNESS / "scripts/live_evidence_policy.py",
    )
    run_dir = tmp_path / RUN_ID
    (run_dir / "reports").mkdir(parents=True)
    pricing = json.loads(
        (
            ROOT
            / "backend/app/providers/provider_pricing_gdt10d_v1.json"
        ).read_text(encoding="utf-8")
    )
    pricing_sha256 = pricing["content_sha256"]
    projects = [
        {
            "project_order": order,
            "project_id": f"project-{order}",
            "source_sha256": str(order) * 64,
            "admission_sha256": str(order + 4) * 64,
        }
        for order in range(1, 5)
    ]
    run = _run("completed")
    run.update(
        {
            "schema_version": "run/2",
            "completed_at": "2026-08-02T00:10:00Z",
            "cycle_authorization": {
                "cycle_id": "gdt10d-contract-cycle",
                "pricing_sha256": pricing_sha256,
                "issuance_sha256": "a" * 64,
                "consumption_sha256": "b" * 64,
                "backend_image_id": "sha256:" + "9" * 64,
                "run_id": RUN_ID,
                "run_authorization_sha256": "c" * 64,
            },
        }
    )
    entries = [
        {
            "attempt_index": index,
            "provider": "qwen-vl",
            "operation": "review_symbols",
            "project_id": "project-1",
            "page_index": 0,
            "subject_kind": "escalation_group",
            "subject_id": f"group-{190 + index - 1:03d}",
            "retry_index": 0,
            "crop_expansion_count": 0,
            "state": "reserved_unknown",
            "reservation_cny": "0.983040",
            "charged_cny": "0.983040",
        }
        for index in (1, 2)
    ]
    ledger_report: dict[str, object] = {
        "schema_version": "provider-usage-evidence/1",
        "run_id": RUN_ID,
        "pricing_sha256": pricing_sha256,
        "cycle_id": "gdt10d-contract-cycle",
        "journal_ref": (
            "asset://provider-usage-cycles/gdt10d-contract-cycle/"
        ),
        "committed_total_cny": "1.966080",
        "reservation_count": 2,
        "reserved_only_count": 0,
        "submission_started_count": 2,
        "unsettled_started_count": 0,
        "settled_count": 2,
        "entries": entries,
    }
    ledger_sha256 = _write_content_hashed(
        run_dir / "reports/provider-usage-ledger.json",
        ledger_report,
    )
    escalated = [f"group-{index:03d}" for index in range(198)]
    for order in range(1, 5):
        denied = escalated[:190] if order == 1 else []
        admitted = escalated[190:] if order == 1 else []
        started = admitted[:2] if order == 1 else []
        cancelled = admitted[2:] if order == 1 else []
        routing: dict[str, object] = {
            "schema_version": "provider-routing-aggregate/1",
            "run_id": RUN_ID,
            "order": order,
            "project_id": f"project-{order}",
            "total_decisions": 199 if order == 1 else 0,
            "escalated_group_ids": escalated if order == 1 else [],
            "denied_group_ids": denied,
            "admitted_group_ids": admitted,
            "cancelled_group_ids": cancelled,
            "terminal_group_ids": escalated if order == 1 else [],
            "paid_artifact_group_ids": started,
            "attempt_event_codes": [],
            "submission_started_group_ids": started,
            "never_submission_started_group_ids": cancelled,
            "reserved_only_group_ids": [],
            "provider_cycle_reservation_denied_group_ids": [],
        }
        _write_content_hashed(
            run_dir / f"reports/provider-routing-{order}.json",
            routing,
        )
        _write_content_hashed(
            run_dir / f"reports/provider-storage-{order}.json",
            {
                "schema_version": "provider-storage-inventory/1",
                "run_id": RUN_ID,
                "order": order,
                "project_id": f"project-{order}",
                "artifacts": (
                    [
                        {
                            "ref": (
                                "asset://projects/project-1/"
                                "provider-inputs/qwen-symbol/"
                                f"crop-{index}.png"
                            ),
                            "sha256": str(index + 1) * 64,
                            "size": 100 + index,
                        }
                        for index in range(2)
                    ]
                    if order == 1
                    else []
                ),
            },
        )
    bridge_sha256 = _write_content_hashed(
        run_dir / "reports/provider-cycle-close-bridge.json",
        {
            "schema_version": "provider-cycle-close-bridge/1",
            "run_id": RUN_ID,
            "image_id": "sha256:" + "9" * 64,
            "storage_volume": "quality_inspection-qa_storage_qa_dev",
            "network": "none",
            "container_user": "0:0",
            "authorization_owner_uid": os.getuid(),
            "authorization_owner_gid": os.getgid(),
            "mounts": [
                {"type": "volume", "target": "/data", "mode": "rw"},
                {"type": "bind", "target": "/auth", "mode": "rw"},
            ],
            "terminal_sha256": "f" * 64,
        },
    )
    live = {
        "paid_cycle": {
            "cycle_id": "gdt10d-contract-cycle",
            "pricing_sha256": pricing_sha256,
            "issuance_sha256": "a" * 64,
            "consumption_sha256": "b" * 64,
            "run_authorization_sha256": "c" * 64,
            "journal_ref": (
                "asset://provider-usage-cycles/gdt10d-contract-cycle/"
            ),
            "projects": projects,
            "resume_consumed_sha256": "d" * 64,
            "ledger": {
                "committed_total_cny": "1.966080",
                "reservation_count": 2,
                "reserved_only_count": 0,
                "submission_started_count": 2,
                "settled_count": 2,
                "evidence_sha256": ledger_sha256,
            },
            "terminal": {
                "status": "completed",
                "quiescence_sha256": "e" * 64,
                "terminal_sha256": "f" * 64,
                "bridge_evidence_sha256": bridge_sha256,
            },
        }
    }
    return policy, run, live, run_dir


def test_paid_cycle_policy_revalidates_ledger_routing_and_pricing(
    tmp_path: Path,
) -> None:
    policy, run, live, run_dir = _paid_policy_evidence(tmp_path)
    policy.validate_paid_cycle_evidence(
        run,
        live,
        evidence_dir=run_dir,
        root=ROOT,
    )

    live["paid_cycle"]["pricing_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pricing snapshot"):
        policy.validate_paid_cycle_evidence(
            run,
            live,
            evidence_dir=run_dir,
            root=ROOT,
        )


def test_paid_cycle_policy_rejects_provider_cycle_reservation_denial(
    tmp_path: Path,
) -> None:
    policy, run, live, run_dir = _paid_policy_evidence(tmp_path)
    routing_path = run_dir / "reports/provider-routing-1.json"
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    routing.pop("content_sha256")
    routing["provider_cycle_reservation_denied_group_ids"] = [
        "group-192"
    ]
    _write_content_hashed(routing_path, routing)

    with pytest.raises(ValueError, match="reservation rejection"):
        policy.validate_paid_cycle_evidence(
            run,
            live,
            evidence_dir=run_dir,
            root=ROOT,
        )

    run["execution_state"] = "failed"
    live["paid_cycle"]["terminal"]["status"] = "failed"
    policy.validate_paid_cycle_evidence(
        run,
        live,
        require_success=False,
        evidence_dir=run_dir,
        root=ROOT,
    )


def test_paid_cycle_policy_rejects_duplicate_attempt_and_cancelled_ledger(
    tmp_path: Path,
) -> None:
    policy, run, live, run_dir = _paid_policy_evidence(tmp_path)
    ledger_path = run_dir / "reports/provider-usage-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger.pop("content_sha256")
    ledger["entries"][1]["attempt_index"] = 1
    live["paid_cycle"]["ledger"]["evidence_sha256"] = _write_content_hashed(
        ledger_path,
        ledger,
    )
    with pytest.raises(ValueError, match="attempt sequence"):
        policy.validate_paid_cycle_evidence(
            run,
            live,
            evidence_dir=run_dir,
            root=ROOT,
        )

    policy, run, live, run_dir = _paid_policy_evidence(tmp_path / "cancelled")
    ledger_path = run_dir / "reports/provider-usage-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger.pop("content_sha256")
    ledger["entries"][0]["subject_id"] = "group-192"
    live["paid_cycle"]["ledger"]["evidence_sha256"] = _write_content_hashed(
        ledger_path,
        ledger,
    )
    with pytest.raises(ValueError, match="terminal reconciliation"):
        policy.validate_paid_cycle_evidence(
            run,
            live,
            evidence_dir=run_dir,
            root=ROOT,
        )


def test_failed_paid_cycle_with_admitted_projects_requires_durable_ledger(
    tmp_path: Path,
) -> None:
    policy, run, live, run_dir = _paid_policy_evidence(tmp_path)
    run["execution_state"] = "failed"
    live["paid_cycle"]["terminal"]["status"] = "failed"
    live["paid_cycle"]["ledger"] = None

    with pytest.raises(ValueError, match="ledger"):
        policy.validate_paid_cycle_evidence(
            run,
            live,
            require_success=False,
            evidence_dir=run_dir,
            root=ROOT,
        )


def test_paid_cycle_start_consumes_before_activation_and_deactivates_pause(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_start_lifecycle",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    def activate(_override: Path) -> None:
        assert (root / "consumption.json").is_file()
        events.append("activate")

    def run_harness(run_id: str) -> dict[str, object]:
        events.append("run")
        assert run_id == RUN_ID
        assert json.loads((root / "run.json").read_text(encoding="utf-8"))[
            "run_id"
        ] == RUN_ID
        return {
            "returncode": 0,
            "run_id": RUN_ID,
            "execution_state": "visual_qa_pending",
        }

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: events.append("validate"),
        validate_issuance=lambda _path: events.append("validate-issuance"),
        new_run_id=lambda: RUN_ID,
        activate_runtime=activate,
        check_contracts=lambda: events.append("contracts"),
        run_harness=run_harness,
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: None,
        validate_pause=lambda _run_id: "2" * 64,
        close_cycle=lambda *_args, **_kwargs: events.append("close"),
    )

    assert result == 0
    assert events == [
        "validate",
        "validate-issuance",
        "activate",
        "contracts",
        "run",
        "deactivate",
    ]
    assert not (root / "terminal.json").exists()


def test_paid_cycle_start_failure_closes_and_deactivates(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_failed_lifecycle",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    def run_harness(run_id: str) -> dict[str, object]:
        assert run_id == RUN_ID
        return {
            "returncode": 1,
            "run_id": RUN_ID,
            "execution_state": "failed",
        }

    def close_cycle(path: Path, **kwargs: object) -> None:
        events.append("close")
        from app.providers.cycle_authorization import (
            write_terminal_from_close_bridge,
        )

        write_terminal_from_close_bridge(
            authorization_root=path,
            cycle_id="gdt10d-contract-cycle",
            **kwargs,
        )

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=lambda _path: events.append("activate"),
        check_contracts=lambda: events.append("contracts"),
        run_harness=run_harness,
        prove_quiescence=lambda _run_id, _status: events.append("quiesce")
        or "1" * 64,
        finalize_harness=lambda _run_id, _status: pytest.fail(
            "a missing durable Harness run must not be finalized"
        ),
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: None,
        close_cycle=close_cycle,
    )

    assert result == 1
    assert events == [
        "activate",
        "contracts",
        "quiesce",
        "close",
        "deactivate",
    ]
    assert json.loads((root / "terminal.json").read_text(encoding="utf-8"))[
        "status"
    ] == "failed"


def test_paid_cycle_start_binds_run_before_activation_failure_close(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_pre_activation_failure",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    close_calls: list[dict[str, object]] = []
    harness_called = False

    def activate(_override: Path) -> None:
        raise RuntimeError("activation failed")

    def run_harness(_run_id: str) -> dict[str, object]:
        nonlocal harness_called
        harness_called = True
        return {}

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=activate,
        check_contracts=lambda: None,
        run_harness=run_harness,
        prove_quiescence=lambda _run_id, _status: "1" * 64,
        finalize_harness=lambda _run_id, _status: {},
        deactivate_runtime=lambda: None,
        cleanup_controls=lambda _path: None,
        close_cycle=lambda _path, **kwargs: close_calls.append(kwargs),
    )

    assert result == 1
    assert not harness_called
    assert json.loads((root / "run.json").read_text(encoding="utf-8"))["run_id"] == RUN_ID
    assert close_calls == [
        {
            "run_id": RUN_ID,
            "status": "failed",
            "quiescence_sha256": "1" * 64,
        }
    ]


def test_paid_cycle_start_bind_failure_still_closes_consumed_cycle(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_bind_failure",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        bind_run_state=lambda _path, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("bind failed")
        ),
        activate_runtime=lambda _path: events.append("activate"),
        check_contracts=lambda: events.append("contracts"),
        run_harness=lambda _run_id: {},
        prove_quiescence=lambda _run_id, _status: "1" * 64,
        finalize_harness=lambda _run_id, _status: {},
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: None,
        close_cycle=lambda _path, **kwargs: events.append(
            f"close:{kwargs['run_id']}"
        ),
    )

    assert result == 1
    assert (root / "consumption.json").is_file()
    assert not (root / "run.json").exists()
    assert events == [f"close:{RUN_ID}", "deactivate"]


def test_repeat_start_does_not_close_or_deactivate_foreign_consumption(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_repeat_start_owner",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    with pytest.raises(ValueError, match="already bound"):
        authorization.execute_start(
            root,
            override=override,
            validate_override=lambda _path, _root: None,
            validate_issuance=lambda _path: None,
            new_run_id=lambda: "20260722T000000000000Z-11111111",
            activate_runtime=lambda _path: events.append("activate"),
            check_contracts=lambda: events.append("contracts"),
            run_harness=lambda _run_id: {},
            prove_quiescence=lambda _run_id, _status: events.append(
                "quiesce"
            )
            or "1" * 64,
            finalize_harness=lambda _run_id, _status: {},
            deactivate_runtime=lambda: events.append("deactivate"),
            cleanup_controls=lambda _path: events.append("cleanup"),
            close_cycle=lambda *_args, **_kwargs: events.append("close"),
        )

    assert events == ["cleanup"]
    assert not (root / "terminal.json").exists()


def test_start_owns_fact_when_interrupted_after_durable_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_start_consumption_boundary",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []
    real_consume = authorization.consume_authorization

    def consume_then_interrupt(*args: object, **kwargs: object) -> None:
        real_consume(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        authorization,
        "consume_authorization",
        consume_then_interrupt,
    )

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=lambda _path: events.append("activate"),
        check_contracts=lambda: events.append("contracts"),
        run_harness=lambda _run_id: {},
        prove_quiescence=lambda _run_id, _status: events.append("quiesce")
        or "1" * 64,
        finalize_harness=lambda _run_id, _status: {},
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: events.append("cleanup"),
        close_cycle=lambda *_args, **_kwargs: events.append("close"),
    )

    assert result == 1
    assert events == ["quiesce", "close", "deactivate", "cleanup"]


def test_paid_cycle_cleanup_failure_writes_durable_sanitized_blocker(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_cleanup_blocker",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=lambda _path: (_ for _ in ()).throw(
            RuntimeError("private activation detail")
        ),
        check_contracts=lambda: None,
        run_harness=lambda _run_id: {},
        prove_quiescence=lambda _run_id, _status: (_ for _ in ()).throw(
            RuntimeError("private quiescence detail")
        ),
        deactivate_runtime=lambda: (_ for _ in ()).throw(
            RuntimeError("private deactivation detail")
        ),
        cleanup_controls=lambda _path: None,
        close_cycle=lambda *_args, **_kwargs: None,
    )

    blocker = json.loads(
        (root / "cleanup-blocker.json").read_text(encoding="utf-8")
    )
    assert result == 2
    assert blocker["schema_version"] == "provider-cycle-cleanup-blocker/1"
    assert blocker["run_id"] == RUN_ID
    assert blocker["status"] == "failed"
    assert blocker["failure_codes"] == [
        "quiescence_close_or_finalize_failed",
        "safe_deactivation_failed",
    ]
    assert "private" not in json.dumps(blocker)


def test_paid_cycle_unclean_pause_cannot_consume_resume(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_unclean_pause",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)

    result = authorization.execute_start(
        root,
        override=override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=lambda _path: None,
        check_contracts=lambda: None,
        run_harness=lambda _run_id: {
            "returncode": 0,
            "run_id": RUN_ID,
            "execution_state": "visual_qa_pending",
        },
        deactivate_runtime=lambda: (_ for _ in ()).throw(
            RuntimeError("private deactivation detail")
        ),
        cleanup_controls=lambda _path: None,
        validate_pause=lambda _run_id: "2" * 64,
        close_cycle=lambda *_args, **_kwargs: None,
    )

    assert result == 2
    assert (root / "cleanup-blocker.json").is_file()
    with pytest.raises(ValueError, match="cleanup|handoff"):
        authorization.consume_resume(
            root,
            run_id=RUN_ID,
            pause_evidence_sha256="2" * 64,
        )
    assert not (root / "resume-consumed.json").exists()


def test_runtime_control_cleanup_deletes_overrides_and_unsets_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_private_cleanup",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    live_override = tmp_path / "live.override.yaml"
    safe_override = tmp_path / "safe.override.yaml"
    for path in (live_override, safe_override):
        path.write_text("services: {}\n", encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setenv(
        "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
        str(safe_override),
    )
    for key in (
        *authorization._LIVE_CREDENTIAL_KEYS,
        *authorization._CYCLE_RUNTIME_KEYS,
        "QI_LIVE_CYCLE_AUTHORIZATION_REF",
        "QI_LIVE_CYCLE_OVERRIDE_REF",
        "GDT10D_RUN_ID",
    ):
        monkeypatch.setenv(key, "present")

    authorization.cleanup_runtime_controls(live_override)

    assert not live_override.exists()
    assert not safe_override.exists()
    assert all(
        key not in authorization.os.environ
        for key in (
            *authorization._LIVE_CREDENTIAL_KEYS,
            *authorization._CYCLE_RUNTIME_KEYS,
            "QI_LIVE_CYCLE_AUTHORIZATION_REF",
            "QI_LIVE_CYCLE_OVERRIDE_REF",
            "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
            "GDT10D_RUN_ID",
        )
    )


def test_paid_cycle_clean_pause_deletes_controls_and_writes_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_clean_pause_handoff",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    live_override = tmp_path / "live.override.yaml"
    safe_override = tmp_path / "safe.override.yaml"
    for path in (live_override, safe_override):
        path.write_text("services: {}\n", encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setenv(
        "QI_LIVE_CYCLE_SAFE_OVERRIDE_REF",
        str(safe_override),
    )

    result = authorization.execute_start(
        root,
        override=live_override,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        new_run_id=lambda: RUN_ID,
        activate_runtime=lambda _path: None,
        check_contracts=lambda: None,
        run_harness=lambda _run_id: {
            "returncode": 0,
            "run_id": RUN_ID,
            "execution_state": "visual_qa_pending",
        },
        deactivate_runtime=lambda: None,
        validate_pause=lambda _run_id: "2" * 64,
        close_cycle=lambda *_args, **_kwargs: None,
    )

    assert result == 0
    assert not live_override.exists()
    assert not safe_override.exists()
    assert (root / "pause-handoff.json").is_file()
    assert not (root / "cleanup-blocker.json").exists()


def test_cleanup_blocker_write_failure_never_creates_resumable_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_blocker_write_failure",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    monkeypatch.setattr(
        authorization,
        "_record_cleanup_blocker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("private persistence detail")
        ),
    )

    with pytest.raises(RuntimeError, match="blocker persistence"):
        authorization.execute_start(
            root,
            override=override,
            validate_override=lambda _path, _root: None,
            validate_issuance=lambda _path: None,
            new_run_id=lambda: RUN_ID,
            activate_runtime=lambda _path: None,
            check_contracts=lambda: None,
            run_harness=lambda _run_id: {
                "returncode": 0,
                "run_id": RUN_ID,
                "execution_state": "visual_qa_pending",
            },
            deactivate_runtime=lambda: (_ for _ in ()).throw(
                RuntimeError("private deactivation detail")
            ),
            cleanup_controls=lambda _path: None,
            validate_pause=lambda _run_id: "2" * 64,
            close_cycle=lambda *_args, **_kwargs: None,
        )

    assert not (root / "pause-handoff.json").exists()
    with pytest.raises(ValueError, match="handoff"):
        authorization.consume_resume(
            root,
            run_id=RUN_ID,
            pause_evidence_sha256="2" * 64,
        )


@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
@pytest.mark.parametrize("stage", ["activation", "run", "quiescence"])
def test_paid_cycle_start_real_signals_close_and_clean(
    tmp_path: Path,
    signal_name: str,
    stage: str,
) -> None:
    authorization = _load_module(
        f"qi_live_cycle_signal_setup_{signal_name}_{stage}",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events = tmp_path / "events.log"
    child_program = r'''
import importlib.util
import os
import signal
import sys
from pathlib import Path

module_path, root_arg, override_arg, events_arg, stage = sys.argv[1:]
spec = importlib.util.spec_from_file_location("qi_signal_child", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
events = Path(events_arg)

def record(value):
    with events.open("a", encoding="utf-8") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def wait_at(name):
    record("ready:" + name)
    while True:
        signal.pause()

def activate(_override):
    record("activate")
    if stage == "activation":
        wait_at(stage)

def run(_run_id):
    record("run")
    if stage == "run":
        wait_at(stage)
    return {"returncode": 1, "run_id": "20260722T000000000000Z-00000000", "execution_state": "failed"}

def quiesce(_run_id, _status):
    record("quiesce")
    if stage == "quiescence":
        wait_at(stage)
    return "1" * 64

module.install_lifecycle_signal_handlers()
result = module.execute_start(
    Path(root_arg),
    override=Path(override_arg),
    validate_override=lambda _path, _root: None,
    validate_issuance=lambda _path: None,
    new_run_id=lambda: "20260722T000000000000Z-00000000",
    activate_runtime=activate,
    check_contracts=lambda: record("contracts"),
    run_harness=run,
    prove_quiescence=quiesce,
    finalize_harness=lambda _run_id, _status: {"execution_state": "failed"},
    deactivate_runtime=lambda: record("deactivate"),
    cleanup_controls=lambda _path: record("cleanup"),
    close_cycle=lambda *_args, **_kwargs: record("close"),
)
record("result:" + str(result))
raise SystemExit(result)
'''
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_program,
            str(HARNESS / "scripts/live_cycle_authorization.py"),
            str(root),
            str(override),
            str(events),
            stage,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if events.is_file() and f"ready:{stage}" in events.read_text(
            encoding="utf-8"
        ):
            break
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert process.poll() is None
    process.send_signal(getattr(signal, signal_name))
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode in {1, 2}, (stdout, stderr)
    recorded = events.read_text(encoding="utf-8").splitlines()
    assert "deactivate" in recorded
    assert "cleanup" in recorded
    if stage == "quiescence":
        blocker = json.loads(
            (root / "cleanup-blocker.json").read_text(encoding="utf-8")
        )
        assert blocker["failure_codes"] == [
            "quiescence_close_or_finalize_failed"
        ]
    else:
        assert "close" in recorded


def test_paid_cycle_resume_real_signal_closes_and_cleans(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_resume_signal_setup",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events = tmp_path / "resume-events.log"
    child_program = r'''
import importlib.util
import os
import signal
import sys
from pathlib import Path

module_path, root_arg, override_arg, events_arg = sys.argv[1:]
spec = importlib.util.spec_from_file_location("qi_resume_signal_child", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
events = Path(events_arg)

def record(value):
    with events.open("a", encoding="utf-8") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def run(_run_id):
    record("ready:run")
    while True:
        signal.pause()

module.install_lifecycle_signal_handlers()
result = module.execute_resume(
    Path(root_arg),
    override=Path(override_arg),
    run_id="20260722T000000000000Z-00000000",
    validate_override=lambda _path, _root: None,
    validate_issuance=lambda _path: None,
    validate_pause=lambda _run_id: "2" * 64,
    activate_runtime=lambda _path: record("activate"),
    check_contracts=lambda: record("contracts"),
    run_harness=run,
    prove_quiescence=lambda _run_id, _status: "1" * 64,
    finalize_harness=lambda _run_id, _status: {"execution_state": "failed"},
    deactivate_runtime=lambda: record("deactivate"),
    cleanup_controls=lambda _path: record("cleanup"),
    close_cycle=lambda *_args, **_kwargs: record("close"),
)
record("result:" + str(result))
raise SystemExit(result)
'''
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_program,
            str(HARNESS / "scripts/live_cycle_authorization.py"),
            str(root),
            str(override),
            str(events),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if events.is_file() and "ready:run" in events.read_text(encoding="utf-8"):
            break
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert process.poll() is None
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 1, (stdout, stderr)
    recorded = events.read_text(encoding="utf-8").splitlines()
    assert "close" in recorded
    assert "deactivate" in recorded
    assert "cleanup" in recorded
    assert (root / "resume-consumed.json").is_file()


def test_paid_cycle_close_has_no_host_terminal_fallback(tmp_path: Path) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_no_host_terminal",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)

    with pytest.raises(ValueError, match="run identity"):
        authorization.close_paid_cycle(
            root,
            run_id=None,
            status="failed",
            quiescence_sha256="1" * 64,
        )

    assert not (root / "terminal.json").exists()


def test_paid_cycle_resume_consumes_pause_before_activation_and_closes(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_resume_lifecycle",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    def activate(_override: Path) -> None:
        assert (root / "resume-consumed.json").is_file()
        events.append("activate")

    def close_cycle(path: Path, **kwargs: object) -> None:
        events.append("close")
        from app.providers.cycle_authorization import (
            write_terminal_from_close_bridge,
        )

        write_terminal_from_close_bridge(
            authorization_root=path,
            cycle_id="gdt10d-contract-cycle",
            **kwargs,
        )

    result = authorization.execute_resume(
        root,
        override=override,
        run_id=RUN_ID,
        validate_override=lambda _path, _root: events.append(
            "validate-override"
        ),
        validate_issuance=lambda _path: events.append("validate-issuance"),
        validate_pause=lambda _run_id: "2" * 64,
        activate_runtime=activate,
        check_contracts=lambda: events.append("contracts"),
        run_harness=lambda _run_id: {
            "returncode": 0,
            "run_id": RUN_ID,
            "execution_state": "terminal_pending",
        },
        prove_quiescence=lambda _run_id, _status: events.append("quiesce")
        or "1" * 64,
        finalize_harness=lambda _run_id, _status: events.append("finalize")
        or {"execution_state": "completed"},
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: None,
        close_cycle=close_cycle,
    )

    assert result == 0
    assert events == [
        "validate-override",
        "validate-issuance",
        "activate",
        "contracts",
        "quiesce",
        "close",
        "finalize",
        "deactivate",
    ]
    assert json.loads((root / "terminal.json").read_text(encoding="utf-8"))[
        "status"
    ] == "completed"


def test_repeat_resume_does_not_close_or_deactivate_foreign_invocation(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_repeat_resume_owner",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    authorization.consume_resume(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []

    result = authorization.execute_resume(
        root,
        override=override,
        run_id=RUN_ID,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        validate_pause=lambda _run_id: "2" * 64,
        activate_runtime=lambda _path: events.append("activate"),
        check_contracts=lambda: events.append("contracts"),
        run_harness=lambda _run_id: {},
        prove_quiescence=lambda _run_id, _status: events.append("quiesce")
        or "1" * 64,
        finalize_harness=lambda _run_id, _status: {},
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: events.append("cleanup"),
        close_cycle=lambda *_args, **_kwargs: events.append("close"),
    )

    assert result == 1
    assert events == ["cleanup"]
    assert not (root / "terminal.json").exists()


def test_execute_resume_real_process_contenders_have_one_lifecycle_owner(
    tmp_path: Path,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_resume_process_contenders_setup",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    authorization_path = HARNESS / "scripts/live_cycle_authorization.py"
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    release = tmp_path / "release-winner"
    event_paths = [tmp_path / f"resume-contender-{index}.log" for index in range(2)]
    overrides = [tmp_path / f"resume-contender-{index}.yaml" for index in range(2)]
    for override in overrides:
        override.write_text("services: {}\n", encoding="utf-8")
        override.chmod(0o600)
    child_program = r'''
import importlib.util
import os
import sys
import time
from pathlib import Path

module_path, root_arg, override_arg, events_arg, release_arg = sys.argv[1:]
spec = importlib.util.spec_from_file_location("qi_resume_contender", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
events = Path(events_arg)
release = Path(release_arg)

def record(value):
    with events.open("a", encoding="utf-8") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())

def run(_run_id):
    record("run")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not release.is_file():
        time.sleep(0.01)
    if not release.is_file():
        raise RuntimeError("winner release timed out")
    return {
        "returncode": 1,
        "run_id": "20260722T000000000000Z-00000000",
        "execution_state": "failed",
    }

result = module.execute_resume(
    Path(root_arg),
    override=Path(override_arg),
    run_id="20260722T000000000000Z-00000000",
    validate_override=lambda _path, _root: None,
    validate_issuance=lambda _path: None,
    validate_pause=lambda _run_id: "2" * 64,
    activate_runtime=lambda _path: record("activate"),
    check_contracts=lambda: record("contracts"),
    run_harness=run,
    prove_quiescence=lambda _run_id, _status: record("quiesce") or "1" * 64,
    finalize_harness=lambda _run_id, _status: record("finalize") or {
        "execution_state": "failed"
    },
    deactivate_runtime=lambda: record("deactivate"),
    cleanup_controls=lambda _path: record("cleanup"),
    close_cycle=lambda *_args, **_kwargs: record("close"),
)
record("result:" + str(result))
raise SystemExit(result)
'''
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                child_program,
                str(authorization_path),
                str(root),
                str(override),
                str(events),
                str(release),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for override, events in zip(overrides, event_paths, strict=True)
    ]
    outputs: list[tuple[str, str]] = []
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            event_lines = [
                path.read_text(encoding="utf-8").splitlines()
                if path.is_file()
                else []
                for path in event_paths
            ]
            if sum("run" in lines for lines in event_lines) == 1 and any(
                process.poll() is not None for process in processes
            ):
                break
            time.sleep(0.02)
        else:
            pytest.fail("resume contenders did not elect one lifecycle owner")
        release.touch()
        outputs = [process.communicate(timeout=10) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    assert [process.returncode for process in processes] == [1, 1], outputs
    recorded = [path.read_text(encoding="utf-8").splitlines() for path in event_paths]
    owner = next(lines for lines in recorded if "run" in lines)
    loser = next(lines for lines in recorded if "run" not in lines)
    assert owner == [
        "activate",
        "contracts",
        "run",
        "quiesce",
        "close",
        "finalize",
        "deactivate",
        "cleanup",
        "result:1",
    ]
    assert loser == ["cleanup", "result:1"]
    assert not (root / "terminal.json").exists()


def test_resume_owns_fact_when_interrupted_after_durable_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_resume_consumption_boundary",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.record_pause_handoff(
        root,
        run_id=RUN_ID,
        pause_evidence_sha256="2" * 64,
    )
    override = tmp_path / "live.override.yaml"
    override.write_text("services: {}\n", encoding="utf-8")
    override.chmod(0o600)
    events: list[str] = []
    issuance_checks: list[bool] = []
    real_issuance = authorization._issuance
    real_consume = authorization.consume_resume

    def track_issuance(
        path: Path,
        *,
        require_active: bool = True,
    ) -> dict[str, object]:
        issuance_checks.append(require_active)
        return real_issuance(path, require_active=require_active)

    def consume_then_interrupt(*args: object, **kwargs: object) -> None:
        real_consume(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        authorization,
        "consume_resume",
        consume_then_interrupt,
    )
    monkeypatch.setattr(authorization, "_issuance", track_issuance)

    result = authorization.execute_resume(
        root,
        override=override,
        run_id=RUN_ID,
        validate_override=lambda _path, _root: None,
        validate_issuance=lambda _path: None,
        validate_pause=lambda _run_id: "2" * 64,
        activate_runtime=lambda _path: events.append("activate"),
        check_contracts=lambda: events.append("contracts"),
        run_harness=lambda _run_id: {},
        prove_quiescence=lambda _run_id, _status: events.append("quiesce")
        or "1" * 64,
        finalize_harness=lambda _run_id, _status: {
            "execution_state": "failed"
        },
        deactivate_runtime=lambda: events.append("deactivate"),
        cleanup_controls=lambda _path: events.append("cleanup"),
        close_cycle=lambda *_args, **_kwargs: events.append("close"),
    )

    assert result == 1
    assert events == ["quiesce", "close", "deactivate", "cleanup"]
    assert issuance_checks[-1] is False


def test_cycle_close_bridge_is_network_none_credential_free_and_exactly_mounted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_close_bridge",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    authorization.admit_project(
        root,
        run_id=RUN_ID,
        project_id="project-1",
        project_order=1,
        source_sha256="f" * 64,
    )
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    terminal = {
        "schema_version": "provider-cycle-terminal/1",
        "cycle_id": identity["cycle_id"],
        "run_id": RUN_ID,
        "status": "failed",
        "quiescence_sha256": "1" * 64,
        "run_sha256": run["content_sha256"],
    }
    terminal["content_sha256"] = authorization._canonical_hash(terminal)
    calls: list[list[str]] = []
    bridge_evidence: list[dict[str, object]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "images" in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                identity["backend_image_id"].removeprefix("sha256:") + "\n",
                "",
            )
        return subprocess.CompletedProcess(argv, 0, json.dumps(terminal), "")

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)
    monkeypatch.setattr(
        authorization,
        "_write_close_bridge_evidence",
        lambda **kwargs: bridge_evidence.append(kwargs) or {},
    )

    assert authorization.close_via_bridge(
        root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="1" * 64,
    ) == terminal
    command = calls[-1]
    assert command[:4] == ["docker", "run", "--rm", "--network"]
    assert command[4] == "none"
    assert command.count("--mount") == 2
    assert any("type=volume" in value and "dst=/data" in value for value in command)
    assert any("type=bind" in value and "dst=/auth" in value for value in command)
    assert not any("KEY=" in value or "SECRET=" in value for value in command)
    assert bridge_evidence[0]["image_id"] == identity["backend_image_id"]
    assert bridge_evidence[0]["storage_volume"].endswith("_storage_qa_dev")
    assert bridge_evidence[0]["terminal"] == terminal


def test_cycle_close_bridge_recovers_consumed_pre_harness_run_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_recover_run_bridge",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    identity = _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    (tmp_path / ".agent/harness/runs" / RUN_ID / "reports").mkdir(
        parents=True
    )
    monkeypatch.setattr(authorization, "ROOT", tmp_path)

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if "images" in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                identity["backend_image_id"] + "\n",
                "",
            )
        from app.providers.cycle_authorization import (
            write_empty_cycle_terminal_from_close_bridge,
        )

        terminal = write_empty_cycle_terminal_from_close_bridge(
            authorization_root=root,
            cycle_id=identity["cycle_id"],
            run_id=RUN_ID,
            status="failed",
            quiescence_sha256="1" * 64,
        )
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(terminal),
            "",
        )

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    terminal = authorization.close_via_bridge(
        root,
        run_id=RUN_ID,
        status="failed",
        quiescence_sha256="1" * 64,
    )

    assert terminal["status"] == "failed"
    assert json.loads((root / "run.json").read_text(encoding="utf-8"))[
        "run_id"
    ] == RUN_ID
    assert (
        tmp_path
        / ".agent/harness/runs"
        / RUN_ID
        / "reports/provider-cycle-close-bridge.json"
    ).is_file()


def test_cycle_close_bridge_rejects_image_not_bound_by_issuance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_close_image_binding",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    root = tmp_path / "authorization"
    _issue_cycle_authorization(authorization, root)
    authorization.consume_authorization(root)
    authorization.bind_run(root, run_id=RUN_ID)
    monkeypatch.setattr(
        authorization.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv,
            0,
            "sha256:" + "8" * 64 + "\n",
            "",
        ),
    )

    with pytest.raises(RuntimeError, match="image identity"):
        authorization.close_via_bridge(
            root,
            run_id=RUN_ID,
            status="failed",
            quiescence_sha256="1" * 64,
        )


def test_quiescence_evidence_is_written_only_after_harness_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_quiescence",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    run_dir = tmp_path / ".agent/harness/runs" / RUN_ID
    (run_dir / "reports").mkdir(parents=True)
    monkeypatch.setattr(authorization, "ROOT", tmp_path)

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        stdout = (
            "0\n"
            if "redis-cli" in argv
            else json.dumps(
                {
                    "active": {"worker@fixture": []},
                    "reserved": {"worker@fixture": []},
                    "scheduled": {"worker@fixture": []},
                }
            )
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    digest = authorization.prove_run_quiescence(RUN_ID, "completed")
    report = json.loads(
        (run_dir / "reports/provider-cycle-quiescence.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["harness_returned"] is True
    assert report["status"] == "completed"
    assert report["queue_depth"] == 0
    assert report["content_sha256"] == digest


def test_quiescence_creates_bounded_evidence_shell_before_harness_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _load_module(
        "qi_live_cycle_authorization_pre_harness_quiescence",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    (tmp_path / ".agent/harness/runs").mkdir(parents=True)
    monkeypatch.setattr(authorization, "ROOT", tmp_path)

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        stdout = (
            "0\n"
            if "redis-cli" in argv
            else json.dumps(
                {
                    "active": {"worker@fixture": []},
                    "reserved": {"worker@fixture": []},
                    "scheduled": {"worker@fixture": []},
                }
            )
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    digest = authorization.prove_run_quiescence(RUN_ID, "failed")

    report_path = (
        tmp_path
        / ".agent/harness/runs"
        / RUN_ID
        / "reports/provider-cycle-quiescence.json"
    )
    assert report_path.is_file()
    assert json.loads(report_path.read_text(encoding="utf-8"))[
        "content_sha256"
    ] == digest


@pytest.mark.parametrize("inspection_mode", ("active", "api-unavailable"))
def test_quiescence_stops_feature_worker_before_close_when_needed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    inspection_mode: str,
) -> None:
    authorization = _load_module(
        f"qi_live_cycle_authorization_stop_worker_{inspection_mode}",
        HARNESS / "scripts/live_cycle_authorization.py",
    )
    run_dir = tmp_path / ".agent/harness/runs" / RUN_ID
    (run_dir / "reports").mkdir(parents=True)
    monkeypatch.setattr(authorization, "ROOT", tmp_path)
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "redis-cli" in argv:
            return subprocess.CompletedProcess(argv, 0, "0\n", "")
        if "stop" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "ps" in argv:
            return subprocess.CompletedProcess(argv, 0, "api\nredis\n", "")
        if inspection_mode == "api-unavailable":
            return subprocess.CompletedProcess(argv, 1, "", "unavailable")
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                {
                    "active": {"worker@fixture": [{"id": "task-1"}]},
                    "reserved": {"worker@fixture": []},
                    "scheduled": {"worker@fixture": []},
                }
            ),
            "",
        )

    monkeypatch.setattr(authorization.subprocess, "run", fake_run)

    digest = authorization.prove_run_quiescence(RUN_ID, "failed")

    report = json.loads(
        (run_dir / "reports/provider-cycle-quiescence.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["content_sha256"] == digest
    assert report["worker_stopped"] is True
    assert report["queue_depth"] == 0
    assert any("stop" in call and call[-1] == "worker" for call in calls)
    assert any("ps" in call for call in calls)


def test_make_routes_start_and_resume_only_through_cycle_orchestrator() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    start_recipe = makefile.split("verify-p0-live:", 1)[1].split("\n\n", 1)[0]
    assert not start_recipe.startswith(" check-contracts")
    assert "live_cycle_authorization.py execute-start" in start_recipe
    resume_recipe = makefile.split("resume-gdt10d-live:", 1)[1].split(
        "\n\n", 1
    )[0]
    assert "live_cycle_authorization.py execute-resume" in resume_recipe

def _materialize_visual_retry_chain(
    tmp_path: Path,
) -> tuple[
    object,
    Path,
    LocalFileStorage,
    str,
    dict[str, Path],
    dict[str, object],
]:
    runner = _load_module(
        f"qi_runner_retry_chain_{tmp_path.name}",
        HARNESS / "scripts/run-p0.py",
    )
    attempt_count = _embedded_function(
        runner._SYMBOL_RESULT_PROGRAM,
        "visual_attempt_count",
    )
    paired_cache = _embedded_function(
        runner._SYMBOL_RESULT_PROGRAM,
        "paired_cache",
        {
            "build_visual_failure_envelope": build_visual_failure_envelope,
            "hashlib": hashlib,
            "json": json,
            "parse_visual_request_evidence": parse_visual_request_evidence,
            "serialize_call_record": serialize_call_record,
            "visual_attempt_count": attempt_count,
        },
    )
    storage = LocalFileStorage(tmp_path / "storage")
    project_id = "project-retry"
    project_root = storage.root / "projects" / project_id
    cache_key = hashlib.sha256(b"retry-cache").hexdigest()
    crop_content = b"canonical-visual-crop"
    crop_sha256 = hashlib.sha256(crop_content).hexdigest()
    filename = f"{cache_key}.attempt-1.json"
    identity = {
        "crop_sha256": crop_sha256,
        "model": "qwen3-vl-plus",
        "prompt_version": "visual-symbol-prompt/4",
        "schema_version": "visual-symbol-review/2",
        "visual_observation_ids": ["visual-1"],
    }
    cache = {
        "request_id": "fixture-final-request",
        "identity": identity,
    }
    relatives = {
        "cache": (
            f"projects/{project_id}/provider-cache/qwen-symbol/"
            f"{cache_key}.json"
        ),
        "final_audit": (
            f"projects/{project_id}/provider-calls/qwen-symbol/"
            f"{cache_key}.json"
        ),
        "retry_audit": (
            f"projects/{project_id}/provider-calls/"
            f"qwen-symbol-retries/{filename}"
        ),
        "retry_request": (
            f"projects/{project_id}/provider-requests/"
            f"qwen-symbol-retries/{filename}"
        ),
        "retry_response": (
            f"projects/{project_id}/provider-responses/"
            f"qwen-symbol-retries/{filename}"
        ),
        "crop": (
            f"projects/{project_id}/provider-inputs/qwen-symbol/"
            f"{crop_sha256}.png"
        ),
    }

    def compact(document: object) -> bytes:
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def write(relative: str, content: bytes) -> Path:
        return storage.write_verified(
            relative,
            content,
            hashlib.sha256(content).hexdigest(),
        ).path

    paths = {
        "cache": write(relatives["cache"], compact(cache)),
        "final_audit": write(
            relatives["final_audit"],
            serialize_call_record(
                ProviderCallRecord(
                    provider="qwen-vl",
                    request_id="fixture-final-request",
                    model="qwen3-vl-plus",
                    prompt_version="visual-symbol-prompt/4",
                    schema_version="visual-symbol-review/2",
                    duration_ms=2,
                    retry_count=1,
                    input_image_count=1,
                    estimated_cost=None,
                    logical_task_reused=False,
                    request_ref=(
                        f"asset://projects/{project_id}/provider-requests/"
                        f"qwen-symbol/{cache_key}.json"
                    ),
                    response_ref=(
                        f"asset://projects/{project_id}/provider-responses/"
                        f"qwen-symbol/final.json"
                    ),
                )
            ),
        ),
        "crop": write(relatives["crop"], crop_content),
    }
    retry_request = build_visual_request_evidence(
        crop_ref=f"asset://{relatives['crop']}",
        crop_sha256=crop_sha256,
        usage={"total_tokens": 11},
    )
    retry_response = build_visual_failure_envelope(
        "tool_arguments_schema_invalid"
    )
    paths["retry_request"] = write(
        relatives["retry_request"],
        compact(retry_request),
    )
    paths["retry_response"] = write(
        relatives["retry_response"],
        compact(retry_response),
    )
    paths["retry_audit"] = write(
        relatives["retry_audit"],
        serialize_call_record(
            ProviderCallRecord(
                provider="qwen-vl",
                request_id="fixture-first-request",
                model="qwen3-vl-plus",
                prompt_version="visual-symbol-prompt/4",
                schema_version="visual-symbol-review/2",
                duration_ms=1,
                retry_count=0,
                input_image_count=1,
                estimated_cost=None,
                logical_task_reused=False,
                request_ref=f"asset://{relatives['retry_request']}",
                response_ref=f"asset://{relatives['retry_response']}",
            )
        ),
    )
    return paired_cache, project_root, storage, project_id, paths, cache


def test_live_symbol_retry_chain_is_canonical_and_identity_bound(
    tmp_path: Path,
) -> None:
    """P0-REC-005: Harness counts only one exact, canonical retry chain."""
    (
        paired_cache,
        project_root,
        storage,
        project_id,
        _paths,
        cache,
    ) = _materialize_visual_retry_chain(tmp_path)

    assert paired_cache(
        project_root,
        storage,
        project_id,
        "qwen-symbol",
    ) == [(cache, 2)]


def test_live_symbol_retry_chain_rejects_second_document_retry(
    tmp_path: Path,
) -> None:
    """P0-REC-005: Harness rejects two valid retry chains in one document."""
    (
        paired_cache,
        project_root,
        storage,
        project_id,
        paths,
        cache,
    ) = _materialize_visual_retry_chain(tmp_path)
    second_key = hashlib.sha256(b"second-retry-cache").hexdigest()
    second_filename = f"{second_key}.attempt-1.json"

    def write(relative: str, content: bytes) -> None:
        storage.write_verified(
            relative,
            content,
            hashlib.sha256(content).hexdigest(),
        )

    second_cache = {
        **cache,
        "request_id": "fixture-second-final-request",
    }
    write(
        f"projects/{project_id}/provider-cache/qwen-symbol/"
        f"{second_key}.json",
        json.dumps(
            second_cache,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    final_audit = json.loads(
        paths["final_audit"].read_text(encoding="utf-8")
    )
    final_audit.update(
        {
            "request_id": "fixture-second-final-request",
            "request_ref": (
                f"asset://projects/{project_id}/provider-requests/"
                f"qwen-symbol/{second_key}.json"
            ),
            "response_ref": (
                f"asset://projects/{project_id}/provider-responses/"
                "qwen-symbol/second-final.json"
            ),
        }
    )
    write(
        f"projects/{project_id}/provider-calls/qwen-symbol/"
        f"{second_key}.json",
        serialize_call_record(final_audit),
    )
    write(
        f"projects/{project_id}/provider-requests/qwen-symbol-retries/"
        f"{second_filename}",
        paths["retry_request"].read_bytes(),
    )
    write(
        f"projects/{project_id}/provider-responses/qwen-symbol-retries/"
        f"{second_filename}",
        paths["retry_response"].read_bytes(),
    )
    retry_audit = json.loads(
        paths["retry_audit"].read_text(encoding="utf-8")
    )
    retry_audit.update(
        {
            "request_id": "fixture-second-first-request",
            "request_ref": (
                f"asset://projects/{project_id}/provider-requests/"
                f"qwen-symbol-retries/{second_filename}"
            ),
            "response_ref": (
                f"asset://projects/{project_id}/provider-responses/"
                f"qwen-symbol-retries/{second_filename}"
            ),
        }
    )
    write(
        f"projects/{project_id}/provider-calls/qwen-symbol-retries/"
        f"{second_filename}",
        serialize_call_record(retry_audit),
    )

    with pytest.raises(RuntimeError, match="retry evidence"):
        paired_cache(
            project_root,
            storage,
            project_id,
            "qwen-symbol",
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "orphan_request",
        "missing_response",
        "unrelated_request_ref",
        "noncanonical_request",
        "crop_mismatch",
        "response_stage_tampered",
    ),
)
def test_live_symbol_retry_chain_rejects_orphan_or_tampered_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    """P0-REC-005: retry evidence cannot be orphaned or rebound."""
    (
        paired_cache,
        project_root,
        storage,
        project_id,
        paths,
        _cache,
    ) = _materialize_visual_retry_chain(tmp_path)

    if mutation == "orphan_request":
        orphan_name = f"{'c' * 64}.attempt-1.json"
        orphan = (
            project_root
            / "provider-requests/qwen-symbol-retries"
            / orphan_name
        )
        orphan.write_bytes(paths["retry_request"].read_bytes())
    elif mutation == "missing_response":
        paths["retry_response"].unlink()
    elif mutation == "unrelated_request_ref":
        unrelated = (
            project_root
            / "provider-requests/qwen-symbol/unrelated.json"
        )
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_bytes(paths["retry_request"].read_bytes())
        audit = json.loads(paths["retry_audit"].read_text(encoding="utf-8"))
        audit["request_ref"] = (
            f"asset://projects/{project_id}/provider-requests/"
            "qwen-symbol/unrelated.json"
        )
        paths["retry_audit"].write_bytes(serialize_call_record(audit))
    elif mutation == "noncanonical_request":
        paths["retry_request"].write_bytes(
            paths["retry_request"].read_bytes() + b"\n"
        )
    elif mutation == "crop_mismatch":
        request = json.loads(
            paths["retry_request"].read_text(encoding="utf-8")
        )
        request["crop_sha256"] = "d" * 64
        paths["retry_request"].write_text(
            json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    else:
        response = build_visual_failure_envelope(
            "tool_arguments_json_invalid"
        )
        paths["retry_response"].write_text(
            json.dumps(
                response,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    with pytest.raises(RuntimeError, match="retry evidence"):
        paired_cache(
            project_root,
            storage,
            project_id,
            "qwen-symbol",
        )


def test_live_symbol_retry_attempt_counts_are_bounded_and_audited() -> None:
    """P0-REC-005: one explicit schema retry counts as one actual Vision call."""
    runner = _load_module(
        "qi_runner_visual_retry_budget",
        HARNESS / "scripts/run-p0.py",
    )
    attempt_count = _embedded_function(
        runner._SYMBOL_RESULT_PROGRAM,
        "visual_attempt_count",
    )
    canonical = {
        "request_id": "fixture-final-request",
        "retry_count": 1,
    }
    retry = {
        "request_id": "fixture-first-request",
        "retry_count": 0,
        "failure_stage": "tool_arguments_schema_invalid",
    }

    assert attempt_count(canonical, [retry]) == 2
    assert attempt_count(
        {"request_id": "fixture-no-retry", "retry_count": 0},
        [],
    ) == 1

    invalid_cases = (
        (canonical, []),
        ({**canonical, "retry_count": 2}, [retry, retry]),
        (canonical, [{**retry, "retry_count": 1}]),
        (
            canonical,
            [{**retry, "failure_stage": "tool_arguments_json_invalid"}],
        ),
        (canonical, [{**retry, "request_id": "fixture-final-request"}]),
    )
    for audit, retries in invalid_cases:
        with pytest.raises(RuntimeError, match="retry evidence"):
            attempt_count(audit, retries)


def test_live_symbol_retry_derived_seventeenth_call_is_blocked() -> None:
    """P0-REC-005: a retry-derived seventeenth Vision call blocks the gate."""
    runner = _load_module(
        "qi_runner_visual_retry_budget_exceeded",
        HARNESS / "scripts/run-p0.py",
    )

    assert runner._vision_call_budget_failures(
        [
            {"page_index": 0, "count": 17},
            {"page_index": 1, "count": 16},
        ],
        [
            {"page_index": 0, "count": 17},
            {"page_index": 1, "count": 16},
        ],
    ) == [
        {"reason": "visual_call_budget_exceeded"},
        {"reason": "total_vision_call_budget_exceeded"},
    ]
