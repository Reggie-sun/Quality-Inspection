from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from test_live_run_contract import (
    RUN_ID,
    _materialize_bound_live_evidence,
)


ROOT = Path(__file__).resolve().parents[4]
HARNESS = ROOT / ".agent/harness"
GENERATED_AT = datetime(2026, 7, 22, 0, 4, 1, tzinfo=UTC)


class ReceiptRejected(RuntimeError):
    """Raised when evidence cannot produce a fresh passed formal receipt."""


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class RunEvidence:
    root: Path
    run: dict[str, Any]
    results: list[dict[str, Any]]
    mirror: dict[str, Any]
    bindings: dict[str, Any]
    policies: dict[str, dict[str, Any]]
    generated_at: datetime
    now: datetime

    def with_defect(self, defect: str) -> RunEvidence:
        run = copy.deepcopy(self.run)
        results = copy.deepcopy(self.results)
        now = self.now
        run_dir = self.root / ".agent/harness/runs" / RUN_ID
        if defect == "stale":
            now = self.generated_at + timedelta(hours=25)
        elif defect == "not_run":
            results[0]["result_state"] = "not_run"
            results[0]["exit_code"] = None
        elif defect == "code_mismatch":
            run["code_identity"]["digest"] = "0" * 64
        elif defect == "missing_current_four":
            (
                self.root
                / ".agent/harness/runs"
                / RUN_ID
                / "artifacts/current-four-manifest.json"
            ).unlink()
        elif defect == "required_artifact_symlink":
            live_path = run_dir / "live-run-evidence.json"
            outside = run_dir.parent / "spliced-live-run-evidence.json"
            outside.write_bytes(live_path.read_bytes())
            live_path.unlink()
            live_path.symlink_to(outside)
        elif defect == "blocking_failed":
            blocking_id = next(
                row["p0_contract_id"]
                for row in self.mirror["contracts"]
                if row["blocking_level"] in {"fatal", "blocking"}
            )
            result = next(
                item for item in results if item["p0_contract_id"] == blocking_id
            )
            result["result_state"] = "failed"
            result["exit_code"] = 1
        elif defect == "corrupt_failure_proof":
            (run_dir / "reports/no-silent-success.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            (run_dir / "reports/no-silent-success.junit.xml").write_text(
                "<broken/>\n",
                encoding="utf-8",
            )
        elif defect == "invalid_candidate_box":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            live["samples"][0]["candidates"]["candidate_records"][0][
                "coordinates"
            ] = [20, 20, 10, 10]
            _write_json(live_path, live)
        elif defect == "browser_mapping_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            browser = live["samples"][0]["export"]["browser"]
            result_path = run_dir / browser["result_ref"]
            result_document = json.loads(result_path.read_text(encoding="utf-8"))
            result_document["glyph_metrics_verified"] = False
            result_document["table_item_numbers"][0]["formal_number"] = 1001
            _write_json(result_path, result_document)
            browser["result_sha256"] = hashlib.sha256(
                result_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "review_owner_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            sample = live["samples"][0]
            review = sample["review"]
            review["frozen_by"] = "unrelated-operator"
            review["active_item_ids"] = ["spliced-active"]
            review["balloon_required_item_ids"] = ["spliced-balloon"]
            report_path = run_dir / review["evidence_ref"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["review"] = {
                key: value
                for key, value in review.items()
                if key
                not in {
                    "merge_split_disposition",
                    "merge_split_note",
                    "evidence_ref",
                    "evidence_sha256",
                }
            }
            _write_json(report_path, report)
            review["evidence_sha256"] = hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "review_operation_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            sample = live["samples"][0]
            review = sample["review"]
            review["operation_commands"] = []
            review["operation_target_ids"] = []
            for decision in review["candidate_decisions"]:
                decision["commands"] = (
                    ["exclude"]
                    if decision["final_state"] == "active"
                    else ["keep"]
                )
            report_path = run_dir / review["evidence_ref"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["review"] = {
                key: value
                for key, value in review.items()
                if key
                not in {
                    "merge_split_disposition",
                    "merge_split_note",
                    "evidence_ref",
                    "evidence_sha256",
                }
            }
            _write_json(report_path, report)
            review["evidence_sha256"] = hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "design_route_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            live["samples"][0]["project_url"] = (
                "/?project_id=unrelated-project&operator_id=quality-1"
            )
            design_path = self.root / "design-qa.md"
            design_text = design_path.read_text(encoding="utf-8").replace(
                "/?project_id=project-1&operator_id=quality-1",
                "/?project_id=unrelated-project&operator_id=quality-1",
            )
            design_path.write_text(design_text, encoding="utf-8")
            live["design_qa"]["implementation_route"] = (
                "/?project_id=unrelated-project&operator_id=quality-1"
            )
            live["design_qa"]["sha256"] = hashlib.sha256(
                design_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "design_document_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            design_path = self.root / "design-qa.md"
            design_path.write_text(
                design_path.read_text(encoding="utf-8").replace(
                    "final result: passed",
                    "final result: blocked",
                ),
                encoding="utf-8",
            )
            live["design_qa"]["sha256"] = hashlib.sha256(
                design_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "browser_content_type_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            browser = live["samples"][0]["export"]["browser"]
            result_path = run_dir / browser["result_ref"]
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["artifacts"][0]["content_type"] = "text/plain"
            _write_json(result_path, result)
            browser["result_sha256"] = hashlib.sha256(
                result_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "final_item_id_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            sample = live["samples"][0]
            replacement_ids = ["unrelated-item-1", "unrelated-item-2"]
            consistency = sample["consistency"]
            for name in (
                "workbench_item_numbers",
                "workbench_overlay_item_numbers",
                "reviewed_item_numbers",
            ):
                for item, replacement in zip(
                    consistency[name], replacement_ids, strict=True
                ):
                    item["item_id"] = replacement
            consistency_path = run_dir / consistency["evidence_ref"]
            consistency_report = json.loads(
                consistency_path.read_text(encoding="utf-8")
            )
            consistency_report["consistency"] = {
                key: value
                for key, value in consistency.items()
                if key not in {"evidence_ref", "evidence_sha256"}
            }
            _write_json(consistency_path, consistency_report)
            consistency["evidence_sha256"] = hashlib.sha256(
                consistency_path.read_bytes()
            ).hexdigest()

            browser = sample["export"]["browser"]
            result_path = run_dir / browser["result_ref"]
            result = json.loads(result_path.read_text(encoding="utf-8"))
            for name in (
                "table_item_numbers",
                "backend_item_numbers",
                "overlay_item_numbers",
            ):
                for item, replacement in zip(
                    result[name], replacement_ids, strict=True
                ):
                    item["item_id"] = replacement
            _write_json(result_path, result)
            browser["result_sha256"] = hashlib.sha256(
                result_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "manifest_page_count_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            consistency = live["samples"][0]["consistency"]
            consistency["manifest_source_page_count"] += 1
            report_path = run_dir / consistency["evidence_ref"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["consistency"] = {
                key: value
                for key, value in consistency.items()
                if key not in {"evidence_ref", "evidence_sha256"}
            }
            _write_json(report_path, report)
            consistency["evidence_sha256"] = hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        elif defect == "final_number_set_splice":
            live_path = run_dir / "live-run-evidence.json"
            live = json.loads(live_path.read_text(encoding="utf-8"))
            consistency = live["samples"][0]["consistency"]
            for name in (
                "workbench_numbers",
                "reviewed_numbers",
                "pdf_numbers",
                "excel_numbers",
            ):
                consistency[name] = [number + 2 for number in consistency[name]]
            report_path = run_dir / consistency["evidence_ref"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["consistency"] = {
                key: value
                for key, value in consistency.items()
                if key not in {"evidence_ref", "evidence_sha256"}
            }
            _write_json(report_path, report)
            consistency["evidence_sha256"] = hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest()
            _write_json(live_path, live)
        else:
            raise ValueError(f"unknown receipt defect: {defect}")
        return replace(self, run=run, results=results, now=now)

    def with_diagnostic_projection_drift(self) -> RunEvidence:
        run = copy.deepcopy(self.run)
        mirror = copy.deepcopy(self.mirror)
        run["git_revision_at_start"] = "later-diagnostic-commit"
        mirror["status_projection_hash"] = "f" * 64
        return replace(self, run=run, mirror=mirror)


def make_valid_run_evidence(tmp_path: Path) -> RunEvidence:
    root = tmp_path / "repository"
    harness = root / ".agent/harness"
    for name in ("schemas", "policy", "contracts"):
        shutil.copytree(HARNESS / name, harness / name)

    receipt_module = _load_module(
        f"qi_generate_receipt_support_{tmp_path.name}",
        HARNESS / "scripts/generate-receipt.py",
    )
    run_dir = harness / "runs" / RUN_ID
    _materialize_bound_live_evidence(run_dir, root / "design-qa.md")
    live_path = run_dir / "live-run-evidence.json"
    live = json.loads(live_path.read_text(encoding="utf-8"))
    for sample in live["samples"]:
        consistency = sample["consistency"]
        numbers = consistency["excel_numbers"]
        consistency["excel_numbers"] = [*numbers[1:], numbers[0]]
        report_path = run_dir / consistency["evidence_ref"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["consistency"]["excel_numbers"] = consistency["excel_numbers"]
        _write_json(report_path, report)
        consistency["evidence_sha256"] = hashlib.sha256(
            report_path.read_bytes()
        ).hexdigest()
    _write_json(live_path, live)

    mirror = json.loads(
        (harness / "contracts/p0-contracts.json").read_text(encoding="utf-8")
    )
    bindings = json.loads(
        (harness / "contracts/global-contract-bindings.json").read_text(
            encoding="utf-8"
        )
    )
    policies = receipt_module.load_policies(root)
    manifest_bytes = (
        run_dir / "artifacts/current-four-manifest.json"
    ).read_bytes()
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run.update(
        {
            "code_identity": receipt_module.code_identity(root),
            "git_revision_at_start": "diagnostic-only-test-revision",
            "config_identity": receipt_module.config_identity(
                "live", "full-p0", None, root
            ),
            "input_identity": receipt_module.input_identity(
                "live",
                "full-p0",
                None,
                {"artifacts/current-four-manifest.json": manifest_bytes},
                root=root,
            ),
            "contract_definition_hash": mirror["contract_definition_hash"],
            "status_projection_hash_at_start": mirror["status_projection_hash"],
            "policy_versions": receipt_module.policy_versions(policies),
            "selected_contract_ids": sorted(
                row["p0_contract_id"] for row in mirror["contracts"]
            ),
            "execution_state": "completed",
            "failure_reason": None,
            "started_at": "2026-07-22T00:00:00Z",
            "completed_at": "2026-07-22T00:04:00Z",
        }
    )
    run["pause_identity"] = {
        "code_identity": run["code_identity"],
        "config_identity": run["config_identity"],
        "contract_definition_hash": run["contract_definition_hash"],
        "input_identity": run["input_identity"],
        "live_identity": run["live_identity"],
    }

    failure_report = run_dir / "reports/no-silent-success.json"
    failure_junit = run_dir / "reports/no-silent-success.junit.xml"
    proof = policies["failure_severity_policy"]["failure_proof"]
    cases = []
    xml_cases = []
    for point in proof["failure_points"]:
        case = {
            "test_name": f"test_p0_acc_007_no_silent_success[{point}]",
            "failure_point": point,
            "export_status": "failed",
            **{name: "0" for name in proof["zero_count_properties"]},
            **{
                name: str(value)
                for name, value in proof["evidence_requirements"][point].items()
            },
        }
        cases.append(case)
        properties = "".join(
            f'<property name="{name}" value="{value}" />'
            for name, value in case.items()
            if name != "test_name"
        )
        xml_cases.append(
            f'<testcase name="{case["test_name"]}"><properties>{properties}'
            "</properties></testcase>"
        )
    failure_junit.write_text(
        '<testsuite tests="7" failures="0" errors="0" skipped="0">'
        + "".join(xml_cases)
        + "</testsuite>\n",
        encoding="utf-8",
    )
    _write_json(
        failure_report,
        {
            "schema_version": "failure-proof/1",
            "run_id": RUN_ID,
            "selector": proof["selector"],
            "command": [
                sys.executable,
                "-m",
                "pytest",
                proof["test_path"],
            ],
            "exit_code": 0,
            "result_state": "passed",
            "junit_ref": proof["junit_ref"],
            "pytest_summary": {
                "tests": 7,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
            },
            "failure_points": proof["failure_points"],
            "cases": cases,
            "validation_errors": [],
        },
    )

    results = [
        {
            "schema_version": "contract-result/1",
            "run_id": RUN_ID,
            "p0_contract_id": row["p0_contract_id"],
            "command": row["verification_selector"],
            "exit_code": 0,
            "result_state": "passed",
            "started_at": "2026-07-22T00:03:00Z",
            "completed_at": "2026-07-22T00:03:30Z",
            "artifact_refs": (
                [
                    "reports/no-silent-success.json",
                    "reports/no-silent-success.junit.xml",
                ]
                if row["p0_contract_id"] == "P0-ACC-007"
                else []
            ),
        }
        for row in mirror["contracts"]
    ]
    _write_json(run_dir / "run.json", run)
    _write_json(
        run_dir / "contract-results.json",
        {
            "schema_version": "contract-results/1",
            "run_id": RUN_ID,
            "results": results,
        },
    )
    return RunEvidence(
        root=root,
        run=run,
        results=results,
        mirror=mirror,
        bindings=bindings,
        policies=policies,
        generated_at=GENERATED_AT,
        now=GENERATED_AT,
    )


def evaluate_receipt(evidence: RunEvidence) -> dict[str, Any]:
    receipt_module = _load_module(
        f"qi_generate_receipt_evaluate_{id(evidence)}",
        HARNESS / "scripts/generate-receipt.py",
    )
    try:
        receipt = receipt_module.build_receipt(
            evidence.root,
            evidence.run,
            evidence.results,
            evidence.mirror,
            evidence.bindings,
            evidence.policies,
            generated_at=evidence.generated_at.isoformat().replace("+00:00", "Z"),
            now=evidence.now,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ReceiptRejected(str(exc)) from exc
    if (
        receipt["overall_verdict"] != "passed"
        or receipt["formal_p0_verdict"] != "passed"
        or receipt["freshness"]["fresh"] is not True
    ):
        raise ReceiptRejected("evidence did not produce a fresh passed formal receipt")
    return receipt
