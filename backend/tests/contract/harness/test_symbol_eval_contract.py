from __future__ import annotations

import copy
import hashlib
import json
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pymupdf
import pytest

from harness_test_support import (
    _load_module,
    _write_json,
    evaluate_receipt,
    make_valid_run_evidence,
)


ROOT = Path(__file__).resolve().parents[4]
HARNESS = ROOT / ".agent/harness"
SOURCE_SHA256 = (
    "58b9cf08ad90ad4ef647661165e989cd45984dbeaa9c0f63042a69eccc017bec"
)
PAGE_BOXES = ((0.0, 0.0, 1190.55, 841.89),) * 2
SYMBOL_KINDS = (
    "diameter",
    "depth",
    "counterbore",
    "surface_roughness",
    "gdt_parallelism",
    "gdt_perpendicularity",
    "gdt_flatness",
    "datum_reference",
    "revision_marker",
)
NEGATIVE_FAMILIES = (
    "part_or_hole_geometry",
    "hatch_center_or_cross",
    "dimension_leader_or_section_line",
    "view_or_section_label",
    "revision_table_or_invalid_marker",
    "datum_like_letter_or_table_cell",
    "watermark_logo_title_or_signoff",
    "isometric_hole_slot_or_edge",
    "ordinary_text_number_material_or_requirement",
)
EVAL_ARTIFACT = "artifacts/visual-symbol-eval.json"
VERDICT_ARTIFACT = "artifacts/visual-symbol-annotation-verdict.json"
ROUTING_COMPARISON_ARTIFACT = "artifacts/symbol-routing-comparison.json"
ROUTING_COMPARISON_FIXTURE = (
    HARNESS / "fixtures/manifests/symbol-routing-comparison-v1.json"
)
FIXTURE_OFFLINE_PROOF = "reports/fixture-offline-proof.json"


def _schema(name: str) -> dict[str, Any]:
    path = HARNESS / "schemas" / name
    assert path.is_file(), f"missing SR-1 schema: {name}"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(document: dict[str, Any], schema_name: str) -> None:
    jsonschema.Draft202012Validator(
        _schema(schema_name),
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)


def _stage_module() -> Any:
    path = HARNESS / "scripts/stage-symbol-eval.py"
    assert path.is_file(), "missing SR-1 staging command"
    return _load_module("test_stage_symbol_eval", path)


def _runner_module() -> Any:
    return _load_module(
        "test_run_p0_symbol_eval",
        HARNESS / "scripts/run-p0.py",
    )


def _receipt_module() -> Any:
    return _load_module(
        "test_generate_receipt_symbol_eval",
        HARNESS / "scripts/generate-receipt.py",
    )


def _evaluator_module() -> Any:
    path = HARNESS / "scripts/symbol_eval.py"
    assert path.is_file(), "missing LIVE-01 post-result evaluator"
    return _load_module("test_sealed_symbol_eval", path)


def _positive(
    label_id: str,
    bbox_pdf: list[float],
    symbol_kinds: list[str],
    expected_disposition: str,
    expected_projection: str | None,
) -> dict[str, Any]:
    return {
        "label_id": label_id,
        "bbox_pdf": bbox_pdf,
        "symbol_kinds": symbol_kinds,
        "expected_disposition": expected_disposition,
        "expected_projection": expected_projection,
    }


def _manifest() -> dict[str, Any]:
    positives = [
        _positive(
            "positive-diameter",
            [10.0, 10.0, 30.0, 30.0],
            ["diameter"],
            "candidate",
            "diameter_dimension",
        ),
        _positive(
            "positive-depth",
            [40.0, 10.0, 70.0, 30.0],
            ["diameter", "depth"],
            "candidate",
            "composite",
        ),
        _positive(
            "positive-counterbore",
            [80.0, 10.0, 120.0, 30.0],
            ["diameter", "depth", "counterbore"],
            "candidate",
            "composite",
        ),
        _positive(
            "positive-roughness",
            [130.0, 10.0, 160.0, 30.0],
            ["surface_roughness"],
            "candidate",
            "roughness",
        ),
        _positive(
            "positive-gdt-parallelism",
            [170.0, 10.0, 210.0, 30.0],
            ["gdt_parallelism"],
            "candidate",
            "geometric_tolerance",
        ),
        _positive(
            "positive-gdt-perpendicularity",
            [220.0, 10.0, 260.0, 30.0],
            ["gdt_perpendicularity"],
            "candidate",
            "geometric_tolerance",
        ),
        _positive(
            "positive-gdt-flatness",
            [270.0, 10.0, 310.0, 30.0],
            ["gdt_flatness"],
            "candidate",
            "geometric_tolerance",
        ),
        _positive(
            "positive-datum",
            [320.0, 10.0, 340.0, 30.0],
            ["datum_reference"],
            "reference_context",
            None,
        ),
        _positive(
            "positive-revision",
            [350.0, 10.0, 370.0, 30.0],
            ["revision_marker"],
            "non_inspection",
            None,
        ),
    ]
    negatives = [
        {
            "label_id": f"negative-{index}",
            "bbox_pdf": [
                10.0 + index * 30.0,
                50.0,
                30.0 + index * 30.0,
                70.0,
            ],
            "symbol_kinds": ["frozen_negative"],
            "negative_family": family,
            "expected_disposition": "ambiguous",
            "expected_projection": None,
        }
        for index, family in enumerate(NEGATIVE_FAMILIES)
    ]
    return {
        "schema_version": "visual-symbol-eval/1",
        "source_sha256": SOURCE_SHA256,
        "annotation_owner_role": "quality_owner",
        "annotation_status": "approved",
        "pages": [
            {"page_index": 0, "labels": positives[:5] + negatives[:4]},
            {"page_index": 1, "labels": positives[5:] + negatives[4:]},
        ],
    }


def _verdict(manifest_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": "visual-symbol-annotation-verdict/1",
        "annotation_owner_role": "quality_owner",
        "overlay_scale_percent": 200,
        "unlabeled_target_count": 0,
        "negative_family_count": 9,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "recorded_at": "2026-07-27T00:00:00Z",
    }


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _artifacts_for_manifest_bytes(manifest_bytes: bytes) -> dict[str, bytes]:
    return {
        EVAL_ARTIFACT: manifest_bytes,
        VERDICT_ARTIFACT: _canonical_bytes(_verdict(manifest_bytes)),
    }


def _synthetic_two_page_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        for _ in range(2):
            document.new_page(width=1190.55, height=841.89)
        document.save(path)


def _manifest_labels(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        label
        for page in document["pages"]
        for label in page["labels"]
    ]


def _synthetic_actuals(
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    visuals: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for page in manifest["pages"]:
        for label in page["labels"]:
            if label["symbol_kinds"] == ["frozen_negative"]:
                continue
            label_id = label["label_id"]
            visual_id = f"visual-{label_id}"
            candidate_id = (
                f"candidate-{label_id}"
                if label["expected_disposition"] == "candidate"
                else None
            )
            visuals.append(
                {
                    "observation_id": visual_id,
                    "page_index": page["page_index"],
                    "bbox_pdf": label["bbox_pdf"],
                }
            )
            coverage.append(
                {
                    "observation_id": visual_id,
                    "disposition": label["expected_disposition"],
                    "candidate_id": candidate_id,
                    "requires_confirmation": (
                        label["symbol_kinds"] == ["revision_marker"]
                    ),
                    "advisor_review": {
                        "symbol_kinds": label["symbol_kinds"],
                    },
                }
            )
            if candidate_id is None:
                continue
            projection = label["expected_projection"]
            payload = (
                {"coarse_type": projection}
                if projection in {"roughness", "geometric_tolerance"}
                else {"item_type": projection}
            )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "payload": payload,
                    "source_location_ids": [visual_id, f"text-{label_id}"],
                }
            )
    candidates.append(
        {
            "candidate_id": "candidate-text-only",
            "payload": {"item_type": "linear_dimension"},
            "source_location_ids": ["text-only"],
        }
    )
    return visuals, candidates, coverage


def _failure_reasons(report: dict[str, Any]) -> set[str]:
    return {str(item["reason"]) for item in report["failures"]}


def _routing_comparison_evidence() -> dict[str, Any]:
    sealed_digest = "d" * 64
    content_digest = "e" * 64

    def output(
        mode: str,
        cache_state: str,
        *,
        calls: int,
        cache_hits: int,
        completeness: str = "complete",
    ) -> dict[str, Any]:
        completeness_outcomes = {
            "complete": 0,
            "partial_review_required": 0,
            "blocked": 0,
        }
        completeness_outcomes[completeness] = 20
        return {
            "mode": mode,
            "cache_state": cache_state,
            "run_identity": (
                f"offline-{mode}-{cache_state}-20260731"
            ),
            "sealed_input_identity_sha256": sealed_digest,
            "content_identity_sha256": content_digest,
            "counts": {
                "admitted": 205,
                "local": 176 if mode == "production_uncertainty" else 0,
                "escalated": 29 if mode == "production_uncertainty" else 205,
                "deduped": 2 if mode == "production_uncertainty" else 29,
                "cache_hits": cache_hits,
                "calls": calls,
                "unresolved": 0,
            },
            "reason_distribution": {
                (
                    "local_exact_typed_source"
                    if mode == "production_uncertainty"
                    else "legacy_all_admitted"
                ): 176 if mode == "production_uncertainty" else 205,
                "provider_required": 29 if mode == "production_uncertainty" else 0,
            },
            "latency_distribution": {
                "sample_count": 20,
                "durations_ms": [1000 + index * 10 for index in range(20)],
                "p50_ms": 1095,
                "p95_ms": 1181,
            },
            "completeness_outcomes": completeness_outcomes,
        }

    return {
        "schema_version": "symbol-routing-comparison/1",
        "sealed_input_identity": {
            "algorithm": "sha256",
            "digest": sealed_digest,
            "components": [
                f"source_sha256:{SOURCE_SHA256}",
                f"manifest_sha256:{'a' * 64}",
                f"annotation_verdict_sha256:{'b' * 64}",
            ],
        },
        "outputs": [
            output(
                "legacy_high_recall",
                "cold",
                calls=29,
                cache_hits=0,
            ),
            output(
                "legacy_high_recall",
                "warm",
                calls=0,
                cache_hits=29,
            ),
            output(
                "production_uncertainty",
                "cold",
                calls=2,
                cache_hits=0,
            ),
            output(
                "production_uncertainty",
                "warm",
                calls=0,
                cache_hits=2,
                completeness="partial_review_required",
            ),
        ],
        "recall_delta": {
            "legacy_positive_recall": 0.875,
            "uncertainty_positive_recall": 1.0,
            "delta": 0.125,
            "legacy_negative_candidate_count": 0,
            "uncertainty_negative_candidate_count": 0,
        },
        "quality_owner_verdict_refs": {
            "legacy_high_recall": [
                {
                    "ref": "verdicts/legacy-quality-owner.json",
                    "sha256": "f" * 64,
                }
            ],
            "production_uncertainty": [
                {
                    "ref": "verdicts/uncertainty-quality-owner.json",
                    "sha256": "1" * 64,
                }
            ],
        },
    }


def _validate_schema_definition(document: dict[str, Any], name: str) -> None:
    schema = _schema("visual-symbol-eval.schema.json")
    assert name in schema["$defs"], (
        f"missing PRT-7 visual-symbol-eval schema definition: {name}"
    )
    jsonschema.Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{name}",
        },
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)


def test_sealed_current_pdf_symbol_manifest(tmp_path: Path) -> None:
    """LIVE-01 compares only immutable labels with post-result Owner objects."""
    evaluator = _evaluator_module()
    manifest = _manifest()
    artifact = tmp_path / "visual-symbol-eval.json"
    artifact.write_bytes(_canonical_bytes(manifest))
    artifact.chmod(stat.S_IRUSR)
    parsed_manifest = json.loads(artifact.read_bytes())
    visuals, candidates, coverage = _synthetic_actuals(parsed_manifest)

    def evaluate(
        *,
        current_visuals: list[dict[str, Any]] | None = None,
        current_candidates: list[dict[str, Any]] | None = None,
        current_coverage: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return evaluator.evaluate_symbol_result(
            manifest=parsed_manifest,
            visual_observations=(
                visuals if current_visuals is None else current_visuals
            ),
            raw_candidates=(
                candidates if current_candidates is None else current_candidates
            ),
            raw_coverage=coverage if current_coverage is None else current_coverage,
        )

    passed = evaluate()
    assert passed["passed"] is True
    assert passed["counts"] == {
        "positive_label_count": 9,
        "candidate_label_count": 7,
        "participating_candidate_count": 7,
        "candidate_match_count": 7,
        "reference_match_count": 1,
        "non_inspection_match_count": 1,
        "negative_label_count": 9,
        "negative_false_positive_count": 0,
        "excluded_candidate_count": 1,
    }
    assert passed["excluded_candidate_ids"] == ["candidate-text-only"]
    assert {
        (item["label_id"], item["disposition"])
        for item in passed["label_matches"]
    } == {
        (
            label["label_id"],
            label["expected_disposition"],
        )
        for label in _manifest_labels(parsed_manifest)
        if label["symbol_kinds"] != ["frozen_negative"]
    }
    assert all(item["overlap_ratio"] >= 0.5 for item in passed["label_matches"])
    serialized = json.dumps(passed, sort_keys=True)
    assert "raw_text" not in serialized
    assert "provider" not in serialized.lower()
    assert str(tmp_path) not in serialized

    missing = copy.deepcopy(candidates)
    missing.pop(0)
    degree_zero = evaluate(current_candidates=missing)
    assert degree_zero["passed"] is False
    assert "positive_label_degree_not_one" in _failure_reasons(degree_zero)

    duplicate = copy.deepcopy(candidates)
    duplicate_candidate = copy.deepcopy(duplicate[0])
    duplicate_candidate["candidate_id"] += "-duplicate"
    duplicate.append(duplicate_candidate)
    degree_two = evaluate(current_candidates=duplicate)
    assert degree_two["passed"] is False
    assert "positive_label_degree_not_one" in _failure_reasons(degree_two)

    wrong_kinds = copy.deepcopy(coverage)
    wrong_kinds[0]["advisor_review"]["symbol_kinds"] = ["depth"]
    kinds_report = evaluate(current_coverage=wrong_kinds)
    assert kinds_report["passed"] is False
    assert "positive_label_degree_not_one" in _failure_reasons(kinds_report)

    wrong_projection = copy.deepcopy(candidates)
    wrong_projection[0]["payload"]["item_type"] = "composite"
    projection_report = evaluate(current_candidates=wrong_projection)
    assert projection_report["passed"] is False
    assert "positive_label_degree_not_one" in _failure_reasons(
        projection_report
    )

    min_area_visuals = copy.deepcopy(visuals)
    min_area_visuals[0]["bbox_pdf"] = [10.0, 10.0, 50.0, 30.0]
    min_area_report = evaluate(current_visuals=min_area_visuals)
    assert min_area_report["passed"] is True
    diameter_match = next(
        item
        for item in min_area_report["label_matches"]
        if item["label_id"] == "positive-diameter"
    )
    assert diameter_match["overlap_ratio"] == 1.0

    negative_label = next(
        label
        for label in _manifest_labels(parsed_manifest)
        if label["symbol_kinds"] == ["frozen_negative"]
    )
    negative_visuals = copy.deepcopy(visuals)
    negative_visuals.append(
        {
            "observation_id": "visual-negative-overlap",
            "page_index": 0,
            "bbox_pdf": negative_label["bbox_pdf"],
        }
    )
    negative_candidates = copy.deepcopy(candidates)
    negative_candidates[0]["source_location_ids"].append(
        "visual-negative-overlap"
    )
    negative_report = evaluate(
        current_visuals=negative_visuals,
        current_candidates=negative_candidates,
    )
    assert negative_report["passed"] is False
    assert negative_report["counts"]["negative_false_positive_count"] == 1
    assert "negative_candidate_overlap" in _failure_reasons(negative_report)

    unmatched_visuals = copy.deepcopy(visuals)
    unmatched_visuals.append(
        {
            "observation_id": "visual-unmatched",
            "page_index": 1,
            "bbox_pdf": [900.0, 700.0, 910.0, 710.0],
        }
    )
    unmatched_candidates = copy.deepcopy(candidates)
    unmatched_candidates.append(
        {
            "candidate_id": "candidate-unmatched",
            "payload": {"item_type": "diameter_dimension"},
            "source_location_ids": ["visual-unmatched"],
        }
    )
    unmatched_coverage = copy.deepcopy(coverage)
    unmatched_coverage.append(
        {
            "observation_id": "visual-unmatched",
            "disposition": "candidate",
            "candidate_id": "candidate-unmatched",
            "requires_confirmation": True,
            "advisor_review": {"symbol_kinds": ["diameter"]},
        }
    )
    unmatched_report = evaluate(
        current_visuals=unmatched_visuals,
        current_candidates=unmatched_candidates,
        current_coverage=unmatched_coverage,
    )
    assert unmatched_report["passed"] is False
    assert "visual_candidate_degree_not_one" in _failure_reasons(
        unmatched_report
    )

    revision_index = next(
        index
        for index, item in enumerate(coverage)
        if item["advisor_review"]["symbol_kinds"] == ["revision_marker"]
    )
    for field, value in (
        ("disposition", "candidate"),
        ("candidate_id", "candidate-forbidden"),
        ("requires_confirmation", False),
    ):
        invalid_revision = copy.deepcopy(coverage)
        invalid_revision[revision_index][field] = value
        revision_report = evaluate(current_coverage=invalid_revision)
        assert revision_report["passed"] is False
        assert "semantic_label_match_not_one" in _failure_reasons(
            revision_report
        )


def test_symbol_eval_schema_is_closed_and_current_source_bound() -> None:
    """P0-REC-005: seal a closed manifest for only the current source bytes."""
    manifest = _manifest()
    _validate(manifest, "visual-symbol-eval.schema.json")

    extra = copy.deepcopy(manifest)
    extra["source_path"] = "/private/source.pdf"
    with pytest.raises(jsonschema.ValidationError):
        _validate(extra, "visual-symbol-eval.schema.json")

    wrong_source = copy.deepcopy(manifest)
    wrong_source["source_sha256"] = "0" * 64
    with pytest.raises(jsonschema.ValidationError):
        _validate(wrong_source, "visual-symbol-eval.schema.json")

    oversized_id = copy.deepcopy(manifest)
    oversized_id["pages"][0]["labels"][0]["label_id"] = "a" * 129
    with pytest.raises(jsonschema.ValidationError):
        _validate(oversized_id, "visual-symbol-eval.schema.json")


def test_offline_routing_comparison_schema_is_closed_and_complete() -> None:
    """PRT-7: one sealed identity carries every required offline metric."""
    evidence = _routing_comparison_evidence()
    _validate_schema_definition(evidence, "routingComparisonEvidence")

    for field in (
        "sealed_input_identity",
        "outputs",
        "recall_delta",
        "quality_owner_verdict_refs",
    ):
        missing = copy.deepcopy(evidence)
        missing.pop(field)
        with pytest.raises(jsonschema.ValidationError):
            _validate_schema_definition(missing, "routingComparisonEvidence")

    for output_index in range(4):
        for field in (
            "counts",
            "reason_distribution",
            "latency_distribution",
            "completeness_outcomes",
        ):
            missing_metric = copy.deepcopy(evidence)
            missing_metric["outputs"][output_index].pop(field)
            with pytest.raises(jsonschema.ValidationError):
                _validate_schema_definition(
                    missing_metric,
                    "routingComparisonEvidence",
                )

        for field in (
            "admitted",
            "local",
            "escalated",
            "deduped",
            "cache_hits",
            "calls",
            "unresolved",
        ):
            missing_count = copy.deepcopy(evidence)
            missing_count["outputs"][output_index]["counts"].pop(field)
            with pytest.raises(jsonschema.ValidationError):
                _validate_schema_definition(
                    missing_count,
                    "routingComparisonEvidence",
                )

        for field in (
            "complete",
            "partial_review_required",
            "blocked",
        ):
            missing_outcome = copy.deepcopy(evidence)
            missing_outcome["outputs"][output_index][
                "completeness_outcomes"
            ].pop(field)
            with pytest.raises(jsonschema.ValidationError):
                _validate_schema_definition(
                    missing_outcome,
                    "routingComparisonEvidence",
                )

    output_identity_override = copy.deepcopy(evidence)
    output_identity_override["outputs"][0]["source_sha256"] = "0" * 64
    with pytest.raises(jsonschema.ValidationError):
        _validate_schema_definition(
            output_identity_override,
            "routingComparisonEvidence",
        )

    for mode in ("legacy_high_recall", "production_uncertainty"):
        missing_verdict_ref = copy.deepcopy(evidence)
        missing_verdict_ref["quality_owner_verdict_refs"].pop(mode)
        with pytest.raises(jsonschema.ValidationError):
            _validate_schema_definition(
                missing_verdict_ref,
                "routingComparisonEvidence",
            )


def test_offline_routing_comparison_validator_binds_modes_to_one_identity() -> None:
    """PRT-7: Harness validates Owner evidence without recomputing semantics."""
    evaluator = _evaluator_module()
    evidence = _routing_comparison_evidence()

    evaluator.validate_routing_comparison_evidence(evidence)
    assert "passed" not in evidence

    for output_index in range(4):
        wrong_identity = copy.deepcopy(evidence)
        wrong_identity["outputs"][output_index][
            "sealed_input_identity_sha256"
        ] = "0" * 64
        with pytest.raises(ValueError, match="sealed input identity"):
            evaluator.validate_routing_comparison_evidence(wrong_identity)

    missing_mode_state = copy.deepcopy(evidence)
    missing_mode_state["outputs"].pop()
    with pytest.raises(ValueError, match="legacy.*uncertainty|mode.*cache"):
        evaluator.validate_routing_comparison_evidence(missing_mode_state)

    extra_mode_state = copy.deepcopy(evidence)
    extra_mode_state["outputs"].append(
        copy.deepcopy(extra_mode_state["outputs"][0])
    )
    with pytest.raises(ValueError, match="legacy.*uncertainty|mode.*cache"):
        evaluator.validate_routing_comparison_evidence(extra_mode_state)

    duplicate_mode_state = copy.deepcopy(evidence)
    duplicate_mode_state["outputs"][3] = copy.deepcopy(
        duplicate_mode_state["outputs"][2]
    )
    with pytest.raises(ValueError, match="legacy.*uncertainty|mode.*cache"):
        evaluator.validate_routing_comparison_evidence(duplicate_mode_state)

    for warm_output_index in (1, 3):
        mismatched_warm_content = copy.deepcopy(evidence)
        mismatched_warm_content["outputs"][warm_output_index][
            "content_identity_sha256"
        ] = "0" * 64
        with pytest.raises(ValueError, match="cold.*warm|content identity"):
            evaluator.validate_routing_comparison_evidence(
                mismatched_warm_content
            )

    for output_index in range(4):
        mismatched_latency_samples = copy.deepcopy(evidence)
        mismatched_latency_samples["outputs"][output_index][
            "latency_distribution"
        ]["durations_ms"].pop()
        with pytest.raises(ValueError, match="latency distribution sample count"):
            evaluator.validate_routing_comparison_evidence(mismatched_latency_samples)

    invented_recall_delta = copy.deepcopy(evidence)
    invented_recall_delta["recall_delta"]["delta"] = 0.0
    with pytest.raises(ValueError, match="recall delta"):
        evaluator.validate_routing_comparison_evidence(invented_recall_delta)


def test_offline_routing_comparison_validator_accepts_stable_recall_delta() -> None:
    """PRT-7: binary representation noise does not invalidate Owner arithmetic."""
    evaluator = _evaluator_module()
    evidence = _routing_comparison_evidence()
    evidence["recall_delta"] = {
        **evidence["recall_delta"],
        "legacy_positive_recall": 0.1,
        "uncertainty_positive_recall": 0.3,
        "delta": 0.2,
    }

    evaluator.validate_routing_comparison_evidence(evidence)


def test_d7_t2_fixture_run_seals_sanitized_routing_comparison_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRT-7: fixture-only routing evidence is sealed and never current-four."""
    runner = _runner_module()
    receipt_module = _receipt_module()
    evaluator = _evaluator_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    original_load = runner._load_json
    socket_program = "import socket; socket.create_connection(('127.0.0.1', 1), 0.01)"
    command_selector = f"{sys.executable} -c {json.dumps(socket_program)}"

    def load_with_mixed_fixture_selectors(path: Path) -> dict[str, Any]:
        document = original_load(path)
        if path != runner.MIRROR_PATH:
            return document
        changed = copy.deepcopy(document)
        for row in changed["contracts"]:
            if row["task_id"] == "D7-T2" and not row["verification_selector"].startswith(
                "phase://"
            ):
                row["verification_selector"] = command_selector
        return changed

    monkeypatch.setattr(
        runner,
        "_load_json",
        load_with_mixed_fixture_selectors,
    )

    run_id, _ = runner.run_task("fixture", "task", "D7-T2")
    run_dir = runs / run_id
    artifact = run_dir / ROUTING_COMPARISON_ARTIFACT
    artifact_bytes = ROUTING_COMPARISON_FIXTURE.read_bytes()
    evidence = json.loads(artifact.read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "contract-results.json").read_text(encoding="utf-8"))
    proof = json.loads((run_dir / FIXTURE_OFFLINE_PROOF).read_text(encoding="utf-8"))

    assert artifact.read_bytes() == artifact_bytes
    assert not artifact.stat().st_mode & stat.S_IWUSR
    _validate_schema_definition(evidence, "routingComparisonEvidence")
    evaluator.validate_routing_comparison_evidence(evidence)
    assert receipt["external_calls"] == 0
    assert run["mode"] == "fixture"
    assert not (run_dir / "artifacts/current-four-manifest.json").exists()
    assert proof["external_calls_proven"] is True
    phase_selectors = [
        selector for selector in proof["selectors"] if selector.startswith("phase://")
    ]
    assert proof["attempted_selectors"] == proof["selectors"]
    assert proof["executed_selectors"] == [command_selector]
    assert proof["pre_execution_blocked_selectors"] == phase_selectors
    assert proof["offline_enforced_selectors"] == proof["selectors"]
    assert run["input_identity"] == receipt_module.input_identity(
        "fixture",
        "task",
        "D7-T2",
        {ROUTING_COMPARISON_ARTIFACT: artifact_bytes},
    )
    assert all(
        ROUTING_COMPARISON_ARTIFACT in result["artifact_refs"]
        for result in results["results"]
    )
    assert "fixture network access is blocked" in "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((run_dir / "logs").iterdir())
    )


def test_legacy_receipt_v1_without_external_calls_remains_checkable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRT-7: adding a receipt field must not invalidate sealed v1 evidence."""
    evidence = make_valid_run_evidence(tmp_path)
    receipt = evaluate_receipt(evidence)
    receipt.pop("external_calls", None)
    run_dir = evidence.root / ".agent/harness/runs" / evidence.run["run_id"]
    _write_json(run_dir / "receipt.json", receipt)
    receipt_module = _load_module(
        "qi_generate_receipt_legacy_v1",
        HARNESS / "scripts/generate-receipt.py",
    )

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 7, 22, 0, 4, 1, tzinfo=UTC).astimezone(tz or UTC)

    monkeypatch.setattr(receipt_module, "check_contract_authority", lambda _root: None)
    monkeypatch.setattr(receipt_module, "datetime", FrozenDatetime)

    receipt_module.validate_schema(receipt, "receipt.schema.json", evidence.root)
    assert receipt_module.check_run(evidence.run["run_id"], evidence.root) == receipt


@pytest.mark.parametrize("as_symlink", (False, True))
def test_build_receipt_rejects_noncanonical_run_dir_override(
    tmp_path: Path,
    as_symlink: bool,
) -> None:
    """PRT-7: a supplied run directory must retain the sealed run identity."""
    evidence = make_valid_run_evidence(tmp_path)
    receipt_module = _receipt_module()
    expected_run_dir = evidence.root / ".agent/harness/runs" / evidence.run["run_id"]
    override = tmp_path / "wrong-run-directory"
    if as_symlink:
        override.symlink_to(expected_run_dir, target_is_directory=True)
    else:
        override.mkdir()

    with pytest.raises(ValueError, match="run directory is unavailable"):
        receipt_module.build_receipt(
            evidence.root,
            evidence.run,
            evidence.results,
            evidence.mirror,
            evidence.bindings,
            evidence.policies,
            generated_at=evidence.generated_at.isoformat().replace("+00:00", "Z"),
            now=evidence.now,
            run_dir=override,
        )


@pytest.mark.parametrize(
    "input_artifacts",
    (
        {EVAL_ARTIFACT: b"eval", VERDICT_ARTIFACT: b"verdict"},
        {
            "artifacts/current-four-manifest.json": b"current-four",
            EVAL_ARTIFACT: b"eval",
            VERDICT_ARTIFACT: b"verdict",
        },
    ),
)
def test_run_task_rejects_symbol_eval_artifacts_outside_registration_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    input_artifacts: dict[str, bytes],
) -> None:
    """PRT-7: task execution accepts only its two explicitly authorized sets."""
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    monkeypatch.setattr(
        runner,
        "_execute_selector_in_run",
        lambda *_args: pytest.fail("symbol-eval artifacts escaped task admission"),
    )

    with pytest.raises(ValueError, match="symbol-eval artifacts are registration-only"):
        runner.run_task("failure", "task", "D2-T1", input_artifacts=input_artifacts)

    assert list(runs.iterdir()) == []


def test_fixture_task_records_command_parse_failure_as_pre_execution_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRT-7: a selector rejected before subprocess start is never executed."""
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    original_load = runner._load_json
    selector = '"unterminated-fixture-selector'

    def load_with_socket_selector(path: Path) -> dict[str, Any]:
        document = original_load(path)
        if path != runner.MIRROR_PATH:
            return document
        changed = copy.deepcopy(document)
        for row in changed["contracts"]:
            if row["task_id"] == "D7-T2" and not row["verification_selector"].startswith(
                "phase://"
            ):
                row["verification_selector"] = selector
        return changed

    monkeypatch.setattr(runner, "_load_json", load_with_socket_selector)

    run_id, _ = runner.run_task("fixture", "task", "D7-T2")
    run_dir = runs / run_id
    proof = json.loads((run_dir / FIXTURE_OFFLINE_PROOF).read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))

    assert proof["external_calls_proven"] is True
    assert proof["credential_keys_empty"] == list(runner.LIVE_CREDENTIAL_KEYS)
    assert proof["attempted_selectors"] == proof["selectors"]
    assert proof["executed_selectors"] == []
    assert proof["pre_execution_blocked_selectors"] == proof["selectors"]
    assert proof["offline_enforced_selectors"] == proof["selectors"]
    assert receipt["external_calls"] == 0


def test_fixture_task_without_lifecycle_classification_cannot_claim_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRT-7: a bare `exit_code=None` outcome cannot impersonate a proof."""
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    monkeypatch.setattr(
        runner,
        "_execute_selector_in_run",
        lambda *_args: {
            "exit_code": None,
            "result_state": "blocked",
            "started_at": "2026-07-31T00:00:00Z",
            "completed_at": "2026-07-31T00:00:01Z",
            "output": "unclassified blocked outcome",
            "artifact_refs": [],
        },
    )

    run_id, _ = runner.run_task("fixture", "task", "D7-T2")
    run_dir = runs / run_id
    proof = json.loads((run_dir / FIXTURE_OFFLINE_PROOF).read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))

    assert proof["executed_selectors"] == []
    assert proof["pre_execution_blocked_selectors"] == []
    assert proof["external_calls_proven"] is False
    assert receipt["external_calls"] is None


def test_nonfixture_receipt_does_not_invent_zero_external_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRT-7: only fixture mode has a literal zero-call receipt."""
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    monkeypatch.setattr(
        runner,
        "_execute_selector_in_run",
        lambda *_args: {
            "exit_code": None,
            "result_state": "blocked",
            "started_at": "2026-07-31T00:00:00Z",
            "completed_at": "2026-07-31T00:00:01Z",
            "output": "nonfixture selector unavailable",
            "artifact_refs": [],
        },
    )

    run_id, _ = runner.run_task("failure", "task", "D7-T2")
    receipt = json.loads(
        (runs / run_id / "receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["external_calls"] is None


def test_stage_symbol_eval_rejects_wrong_hash_bbox_or_family_set(
    tmp_path: Path,
) -> None:
    """P0-REC-005: staging rejects wrong bytes, bounds, or positive coverage."""
    stage = _stage_module()
    source = tmp_path / "synthetic.pdf"
    _synthetic_two_page_pdf(source)
    with pytest.raises(ValueError, match="SHA-256"):
        stage.verify_source(source)

    invalid_bbox = _manifest()
    invalid_bbox["pages"][0]["labels"][0]["bbox_pdf"] = [
        10.0,
        10.0,
        1191.0,
        30.0,
    ]
    with pytest.raises(ValueError, match="bbox"):
        stage.validate_manifest(invalid_bbox, PAGE_BOXES)

    missing_family = _manifest()
    for page in missing_family["pages"]:
        page["labels"] = [
            label
            for label in page["labels"]
            if label["label_id"] != "positive-revision"
        ]
    with pytest.raises(ValueError, match="positive symbol family"):
        stage.validate_manifest(missing_family, PAGE_BOXES)


def test_symbol_eval_revision_marker_is_positive_noninspection_only() -> None:
    """P0-REC-005: a valid revision marker is not a frozen negative or item."""
    manifest = _manifest()
    revision = next(
        label
        for label in _manifest_labels(manifest)
        if label["label_id"] == "positive-revision"
    )
    assert revision == {
        "label_id": "positive-revision",
        "bbox_pdf": [350.0, 10.0, 370.0, 30.0],
        "symbol_kinds": ["revision_marker"],
        "expected_disposition": "non_inspection",
        "expected_projection": None,
    }
    _validate(manifest, "visual-symbol-eval.schema.json")

    for field, value in (
        ("expected_disposition", "candidate"),
        ("expected_projection", "diameter_dimension"),
        ("negative_family", "revision_table_or_invalid_marker"),
    ):
        invalid = copy.deepcopy(manifest)
        target = next(
            label
            for label in _manifest_labels(invalid)
            if label["label_id"] == "positive-revision"
        )
        target[field] = value
        with pytest.raises(jsonschema.ValidationError):
            _validate(invalid, "visual-symbol-eval.schema.json")


def test_stage_symbol_eval_rejects_missing_or_duplicate_only_negative_family_coverage() -> None:
    """P0-REC-005: all nine distinct negative families are required."""
    stage = _stage_module()
    missing = _manifest()
    for page in missing["pages"]:
        page["labels"] = [
            label
            for label in page["labels"]
            if label.get("negative_family") != NEGATIVE_FAMILIES[-1]
        ]
    with pytest.raises(ValueError, match="negative family"):
        stage.validate_manifest(missing, PAGE_BOXES)

    repeated_only = _manifest()
    for label in _manifest_labels(repeated_only):
        if label["symbol_kinds"] == ["frozen_negative"]:
            label["negative_family"] = NEGATIVE_FAMILIES[0]
    with pytest.raises(ValueError, match="negative family"):
        stage.validate_manifest(repeated_only, PAGE_BOXES)


def test_symbol_eval_rejects_negative_family_on_positive_label() -> None:
    """P0-REC-005: positive labels cannot carry frozen-negative taxonomy."""
    invalid = _manifest()
    invalid["pages"][0]["labels"][0]["negative_family"] = NEGATIVE_FAMILIES[0]
    with pytest.raises(jsonschema.ValidationError):
        _validate(invalid, "visual-symbol-eval.schema.json")


def test_symbol_eval_requires_negative_family_on_frozen_negative_label() -> None:
    """P0-REC-005: frozen negatives keep one family and a non-item state."""
    manifest = _manifest()
    negative = next(
        label
        for label in _manifest_labels(manifest)
        if label["symbol_kinds"] == ["frozen_negative"]
    )
    for disposition in ("ambiguous", "non_inspection"):
        valid = copy.deepcopy(manifest)
        target = next(
            label
            for label in _manifest_labels(valid)
            if label["label_id"] == negative["label_id"]
        )
        target["expected_disposition"] = disposition
        _validate(valid, "visual-symbol-eval.schema.json")

    for disposition in ("candidate", "reference_context"):
        invalid = copy.deepcopy(manifest)
        target = next(
            label
            for label in _manifest_labels(invalid)
            if label["label_id"] == negative["label_id"]
        )
        target["expected_disposition"] = disposition
        with pytest.raises(jsonschema.ValidationError):
            _validate(invalid, "visual-symbol-eval.schema.json")

    missing_family = copy.deepcopy(manifest)
    target = next(
        label
        for label in _manifest_labels(missing_family)
        if label["label_id"] == negative["label_id"]
    )
    target.pop("negative_family")
    with pytest.raises(jsonschema.ValidationError):
        _validate(missing_family, "visual-symbol-eval.schema.json")


def test_symbol_eval_artifacts_exclude_paths_pdf_bytes_and_screenshots() -> None:
    """P0-REC-005: sealed inputs contain only canonical labels and verdict."""
    stage = _stage_module()
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )
    assert set(artifacts) == {EVAL_ARTIFACT, VERDICT_ARTIFACT}
    for name, content in artifacts.items():
        assert isinstance(content, bytes)
        document = json.loads(content)
        serialized = json.dumps(document, ensure_ascii=False).lower()
        assert "source_path" not in serialized
        assert "pdf_bytes" not in serialized
        assert "base64" not in serialized
        assert "screenshot" not in serialized
        assert "credential" not in serialized
        assert "/private/" not in serialized

    runner = _runner_module()
    for invalid in (
        {EVAL_ARTIFACT: artifacts[EVAL_ARTIFACT]},
        {**artifacts, "artifacts/source.pdf": b"%PDF-private"},
        {VERDICT_ARTIFACT: artifacts[VERDICT_ARTIFACT]},
    ):
        with pytest.raises(ValueError, match="exact"):
            runner.register_live_input_artifacts(
                task_id="D7-T2",
                artifacts=invalid,
            )


@pytest.mark.parametrize(
    "private_value",
    (
        "/mnt/secure/current-source.pdf",
        "leak /var/lib/current-source.pdf",
        r"C:\secure\current-source.pdf",
        "file:///var/lib/current-source.pdf",
        "../../etc/passwd",
        r"opaque=C:\secure\source.pdf",
        r"\\server\share\source.pdf",
    ),
)
def test_symbol_eval_rejects_generic_host_paths_before_registration(
    private_value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: any absolute host locator fails before run creation."""
    stage = _stage_module()
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    manifest = _manifest()
    manifest["pages"][0]["labels"][0]["label_id"] = private_value
    manifest_bytes = _canonical_bytes(manifest)
    artifacts = _artifacts_for_manifest_bytes(manifest_bytes)

    with pytest.raises(jsonschema.ValidationError):
        _validate(manifest, "visual-symbol-eval.schema.json")
    with pytest.raises(ValueError, match="forbidden private data"):
        stage.build_artifacts(
            manifest,
            PAGE_BOXES,
            recorded_at="2026-07-27T00:00:00Z",
        )
    with pytest.raises(ValueError, match="forbidden private data"):
        stage.validate_artifacts(artifacts)
    with pytest.raises(ValueError, match="forbidden private data"):
        runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
        )
    assert list(runs.iterdir()) == []
    stage._assert_sanitized(
        {"schema_version": "visual-symbol-eval/1"}
    )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    (
        ("private_path", "forbidden private data"),
        ("duplicate_key", "duplicate JSON key"),
        ("noncanonical", "canonical JSON"),
        ("invalid_utf8", "UTF-8"),
        ("nonfinite", "non-finite JSON number"),
    ),
)
def test_symbol_eval_direct_artifact_validation_is_strict_and_sanitized(
    case: str,
    expected_error: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: direct registration cannot bypass canonical privacy checks."""
    stage = _stage_module()
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)

    manifest = _manifest()
    if case == "private_path":
        manifest["pages"][0]["labels"][0]["label_id"] = (
            "leak /home/private/source.pdf"
        )
        manifest_bytes = _canonical_bytes(manifest)
    elif case == "duplicate_key":
        manifest_bytes = _canonical_bytes(manifest).replace(
            b'{"annotation_owner_role":',
            b'{"annotation_status":"rejected","annotation_owner_role":',
            1,
        )
    elif case == "noncanonical":
        manifest_bytes = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    elif case == "invalid_utf8":
        manifest_bytes = _canonical_bytes(manifest) + b"\xff"
    else:
        manifest_bytes = _canonical_bytes(manifest).replace(
            b"[10.0,10.0,30.0,30.0]",
            b"[NaN,10.0,30.0,30.0]",
            1,
        )
    artifacts = _artifacts_for_manifest_bytes(manifest_bytes)

    with pytest.raises(ValueError, match=expected_error):
        stage.validate_artifacts(artifacts)
    with pytest.raises(ValueError, match=expected_error):
        runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
        )
    assert list(runs.iterdir()) == []
    if case == "noncanonical":
        human_manifest = tmp_path / "human-readable-manifest.json"
        human_manifest.write_bytes(manifest_bytes)
        assert stage._load_manifest(human_manifest) == manifest
        assert stage.build_artifacts(
            manifest,
            PAGE_BOXES,
            recorded_at="2026-07-27T00:00:00Z",
        )[EVAL_ARTIFACT] == _canonical_bytes(manifest)


def test_stage_symbol_eval_cli_rejects_abbreviations_without_path_echo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P0-REC-005: parser rejects unknown flags without echoing host paths."""
    stage = _stage_module()
    private_path = "/home/private/current-source.pdf"

    with pytest.raises(SystemExit) as abbreviated:
        stage.main(
            [
                "--mod",
                "live",
                "--source",
                private_path,
                "--manifest",
                "manifest.json",
            ]
        )
    assert abbreviated.value.code == 2
    assert private_path not in capsys.readouterr().err

    with pytest.raises(SystemExit) as unauthorized:
        stage.main(
            [
                "--mode",
                "live",
                "--source",
                "source.pdf",
                "--manifest",
                "manifest.json",
                "--host-path",
                private_path,
            ]
        )
    assert unauthorized.value.code == 2
    error = capsys.readouterr().err
    assert private_path not in error
    assert "/home/" not in error


def test_symbol_eval_cli_and_schema_errors_never_echo_private_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P0-REC-005: private mapping keys are rejected without value echo."""
    stage = _stage_module()
    injected = "/home/private/current-source.pdf"
    manifest = _manifest()
    manifest[injected] = "private"
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)
    monkeypatch.setattr(stage, "verify_source", lambda _path: PAGE_BOXES)

    def forbidden_load(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("privacy failure must precede registration")

    monkeypatch.setattr(stage, "_load_module", forbidden_load)
    assert stage.main(
        [
            "--mode",
            "live",
            "--source",
            "synthetic-source.pdf",
            "--manifest",
            str(manifest_path),
        ]
    ) == 2
    error = capsys.readouterr().err
    assert injected not in error
    assert "stage-symbol-eval:" in error

    with pytest.raises(ValueError) as schema_error:
        stage._validate_schema(
            manifest,
            "visual-symbol-eval.schema.json",
        )
    assert injected not in str(schema_error.value)


def test_symbol_registration_validates_new_run_before_directory_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: invalid run identity never leaves a registration directory."""
    stage = _stage_module()
    runner = _runner_module()
    receipt = _receipt_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    policies = copy.deepcopy(receipt.load_policies(ROOT))
    policies["provider_call_policy"]["schema_version"] = "invalid-version"
    monkeypatch.setattr(receipt, "load_policies", lambda _root=ROOT: policies)
    monkeypatch.setattr(runner, "_receipt_module", lambda: receipt)
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )

    with pytest.raises(ValueError, match="run.schema.json"):
        runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
        )
    assert list(runs.iterdir()) == []


@pytest.mark.parametrize(
    ("target_name", "schema_name"),
    (
        ("MIRROR_PATH", "p0-contracts.schema.json"),
        ("BINDINGS_PATH", "global-contract-bindings.schema.json"),
    ),
)
def test_symbol_registration_preflight_validates_contract_documents(
    target_name: str,
    schema_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: canonical contract schemas veto registration before writes."""
    stage = _stage_module()
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    target_path = getattr(runner, target_name)
    original_load = runner._load_json

    def load_with_invalid_target(path: Path) -> dict[str, Any]:
        document = original_load(path)
        if path == target_path:
            document["unexpected_registration_field"] = True
        return document

    monkeypatch.setattr(runner, "_load_json", load_with_invalid_target)
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )

    with pytest.raises(ValueError, match=schema_name):
        runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
        )
    assert list(runs.iterdir()) == []


def test_symbol_eval_loader_requires_literal_sealed_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: registration is input-only and literal sealed reuse only."""
    stage = _stage_module()
    runner = _runner_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)

    def forbidden_selector(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("input registration must not execute a selector")

    for name in (
        "_command_outcome",
        "_execute_selector",
        "_execute_selector_in_run",
        "_http_json",
        "_phase_outcome",
        "urlopen",
    ):
        monkeypatch.setattr(runner, name, forbidden_selector)
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )
    run_id = runner.register_live_input_artifacts(
        task_id="D7-T2",
        artifacts=artifacts,
    )
    run_dir = runs / run_id
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    phase = json.loads(
        (run_dir / "reports/symbol-eval-registration.json").read_text(
            encoding="utf-8"
        )
    )

    assert run["mode"] == "live"
    assert run["scope"] == "task"
    assert run["task_id"] == "D7-T2"
    assert run["selected_contract_ids"] == []
    assert run["completed_at"] is not None
    assert phase["selector"] == "phase://live/symbol-eval-registration"
    assert not (run_dir / "receipt.json").exists()
    assert not (run_dir / "contract-results.json").exists()
    assert not bool(run_dir.stat().st_mode & stat.S_IWUSR)
    assert runner.load_symbol_eval_artifacts(run_id) == artifacts

    for alias in ("latest", "latest-successful", "../" + run_id):
        with pytest.raises(ValueError, match="literal"):
            runner.load_symbol_eval_artifacts(alias)

    eval_path = run_dir / EVAL_ARTIFACT
    eval_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(ValueError, match="sealed"):
        runner.load_symbol_eval_artifacts(run_id)


def test_symbol_annotation_verdict_requires_exact_overlay_review() -> None:
    """P0-REC-005: only the approved 200 percent complete overlay can seal."""
    manifest_bytes = _canonical_bytes(_manifest())
    verdict = _verdict(manifest_bytes)
    _validate(verdict, "visual-symbol-annotation-verdict.schema.json")

    for field, value in (
        ("overlay_scale_percent", 100),
        ("unlabeled_target_count", 1),
        ("negative_family_count", 8),
        ("annotation_owner_role", "model"),
    ):
        invalid = {**verdict, field: value}
        with pytest.raises(jsonschema.ValidationError):
            _validate(invalid, "visual-symbol-annotation-verdict.schema.json")


@pytest.mark.parametrize(
    "changed_artifact",
    (EVAL_ARTIFACT, VERDICT_ARTIFACT),
)
def test_symbol_eval_byte_change_stales_input_identity(
    changed_artifact: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: each exact artifact independently binds sealed identity."""
    stage = _stage_module()
    runner = _runner_module()
    receipt = _receipt_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )
    run_id = runner.register_live_input_artifacts(
        task_id="D7-T2",
        artifacts=artifacts,
    )
    run_dir = runs / run_id
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    changed_artifacts = dict(artifacts)
    if changed_artifact == EVAL_ARTIFACT:
        changed_document = json.loads(artifacts[EVAL_ARTIFACT])
        changed_document["pages"][0]["labels"][0]["label_id"] += "-changed"
    else:
        changed_document = json.loads(artifacts[VERDICT_ARTIFACT])
        changed_document["recorded_at"] = "2026-07-27T00:00:01Z"
    changed_artifacts[changed_artifact] = _canonical_bytes(changed_document)
    assert run["input_identity"] != receipt.input_identity(
        "live",
        "task",
        "D7-T2",
        changed_artifacts,
    )

    path = run_dir / changed_artifact
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    path.write_bytes(changed_artifacts[changed_artifact])
    runner._seal_run(run_dir)
    with pytest.raises(ValueError, match="manifest_sha256|input identity"):
        runner.load_symbol_eval_artifacts(run_id)


def test_symbol_registration_only_run_cannot_masquerade_as_task_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: ordinary task receipts still require all task mirror rows."""
    stage = _stage_module()
    runner = _runner_module()
    receipt = _receipt_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )
    run_id = runner.register_live_input_artifacts(
        task_id="D7-T2",
        artifacts=artifacts,
    )
    run = json.loads((runs / run_id / "run.json").read_text(encoding="utf-8"))
    mirror = json.loads(
        (HARNESS / "contracts/p0-contracts.json").read_text(encoding="utf-8")
    )
    bindings = json.loads(
        (HARNESS / "contracts/global-contract-bindings.json").read_text(
            encoding="utf-8"
        )
    )
    policies = receipt.load_policies(ROOT)
    with pytest.raises(ValueError, match="task scope selected_contract_ids"):
        receipt.build_receipt(
            ROOT,
            run,
            [],
            mirror,
            bindings,
            policies,
        )


def test_symbol_eval_registration_attaches_only_to_open_d7_t2_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-005: optional run attachment preserves one canonical run."""
    stage = _stage_module()
    runner = _runner_module()
    receipt = _receipt_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(runner, "RUNS", runs)
    run_id = "20260727T000000000000Z-00000000"
    run_dir = runs / run_id
    run_dir.mkdir()
    for name in ("logs", "reports", "artifacts"):
        (run_dir / name).mkdir()
    mirror = json.loads(
        (HARNESS / "contracts/p0-contracts.json").read_text(encoding="utf-8")
    )
    policies = receipt.load_policies(ROOT)
    _write_json(
        run_dir / "run.json",
        {
            "schema_version": "run/1",
            "run_id": run_id,
            "mode": "live",
            "scope": "task",
            "task_id": "D7-T2",
            "code_identity": receipt.code_identity(ROOT),
            "git_revision_at_start": "test-revision",
            "config_identity": receipt.config_identity(
                "live",
                "task",
                "D7-T2",
                ROOT,
            ),
            "input_identity": receipt.input_identity(
                "live",
                "task",
                "D7-T2",
                root=ROOT,
            ),
            "contract_definition_hash": mirror["contract_definition_hash"],
            "status_projection_hash_at_start": mirror[
                "status_projection_hash"
            ],
            "policy_versions": receipt.policy_versions(policies),
            "selected_contract_ids": [],
            "started_at": "2026-07-27T00:00:00Z",
            "completed_at": None,
        },
    )
    artifacts = stage.build_artifacts(
        _manifest(),
        PAGE_BOXES,
        recorded_at="2026-07-27T00:00:00Z",
    )
    assert runner.register_live_input_artifacts(
        task_id="D7-T2",
        artifacts=artifacts,
        run_id=run_id,
    ) == run_id
    assert runner.load_symbol_eval_artifacts(run_id) == artifacts

    with pytest.raises(ValueError, match="members|open and writable"):
        runner.register_live_input_artifacts(
            task_id="D7-T2",
            artifacts=artifacts,
            run_id=run_id,
        )
