from __future__ import annotations

import ast
import importlib.util
import hashlib
import json
import os
import stat
import subprocess
import sys
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
            "api_base": "http://localhost:8000",
            "frontend_base": "http://localhost:3000",
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
    symbol_report = {
        "schema_version": "symbol-recognition-live-report/1",
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
            "label_matches": [],
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
            "--pause-after",
            "first-pdf-balloons",
            "--print-run-id-only",
        ]
    )

    assert result == 2
    assert not runs.exists()


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

    def start(preflight_result: dict[str, dict[str, bytes]]) -> str:
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
    expected = (0, "passed", "controlled failure proof", ["reports/proof.json"])
    monkeypatch.setattr(
        runner,
        "_failure_phase_outcome",
        lambda selector, run_dir: expected,
    )

    assert runner._phase_outcome(
        runner.NO_SILENT_SUCCESS_SELECTOR,
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
        lambda: {"operator_id": "quality-1", "frontend_base": "http://localhost:3000"},
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


def test_live_operator_and_runtime_identity_are_bound_across_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_module("qi_run_p0_live_identity", HARNESS / "scripts/run-p0.py")
    monkeypatch.setenv("QI_P0_OPERATOR_ID", "quality-1")
    monkeypatch.setenv("QI_P0_API_BASE", "http://localhost:8000")
    monkeypatch.setenv("QI_P0_FRONTEND_BASE", "http://localhost:3000")
    monkeypatch.setattr(
        runner,
        "_chrome_identity",
        lambda environment: _run()["live_identity"]["browser"],
    )
    assert runner._current_live_identity() == _run()["live_identity"]

    monkeypatch.setenv("QI_P0_OPERATOR_ID", "quality-2")
    assert runner._current_live_identity() != _run()["live_identity"]


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


def test_all_eleven_harness_schemas_are_checked_and_bound_to_code_identity() -> None:
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
        "max_retries_per_call": 2,
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
        "schema_version": "visual-symbol-review/1",
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
                    schema_version="visual-symbol-review/1",
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
                schema_version="visual-symbol-review/1",
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
