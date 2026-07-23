from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from harness_test_support import (
    HARNESS,
    RUN_ID,
    ReceiptRejected,
    RunEvidence,
    evaluate_receipt,
    make_valid_run_evidence,
)


@pytest.fixture
def valid_run_evidence(tmp_path: Path) -> RunEvidence:
    return make_valid_run_evidence(tmp_path)


def test_valid_evidence_produces_fresh_passed_formal_receipt(
    valid_run_evidence: RunEvidence,
) -> None:
    receipt = evaluate_receipt(valid_run_evidence)

    assert receipt["result_counts"] == {
        "passed": 111,
        "failed": 0,
        "blocked": 0,
        "not_run": 0,
    }
    assert receipt["formal_p0_verdict"] == "passed"


def test_status_projection_and_diagnostic_git_drift_do_not_stale_receipt(
    valid_run_evidence: RunEvidence,
) -> None:
    receipt = evaluate_receipt(
        valid_run_evidence.with_diagnostic_projection_drift()
    )

    assert receipt["freshness"] == {
        "fresh": True,
        "valid_until": "2026-07-23T00:04:01Z",
        "receipt_freshness_hours": 24,
        "reasons": [],
    }
    assert receipt["status_projection_hash"] == (
        valid_run_evidence.run["status_projection_hash_at_start"]
    )


@pytest.mark.parametrize(
    "defect",
    [
        "stale",
        "not_run",
        "code_mismatch",
        "missing_current_four",
        "required_artifact_symlink",
        "blocking_failed",
        "corrupt_failure_proof",
        "invalid_candidate_box",
        "browser_mapping_splice",
        "review_owner_splice",
        "review_operation_splice",
        "design_route_splice",
        "design_document_splice",
        "browser_content_type_splice",
        "final_item_id_splice",
        "manifest_page_count_splice",
        "final_number_set_splice",
    ],
)
def test_defective_evidence_cannot_produce_passed_receipt(
    valid_run_evidence: RunEvidence,
    defect: str,
) -> None:
    evidence = valid_run_evidence.with_defect(defect)

    with pytest.raises(ReceiptRejected):
        evaluate_receipt(evidence)


def test_summary_reports_only_counts_and_refs_without_mutating_run(
    valid_run_evidence: RunEvidence,
) -> None:
    receipt = evaluate_receipt(valid_run_evidence)
    run_dir = (
        valid_run_evidence.root / ".agent/harness/runs" / valid_run_evidence.run["run_id"]
    )
    (run_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    script = HARNESS / "scripts/summarize-run.py"
    assert script.is_file(), "missing D7-T3 read-only run summarizer"
    spec = importlib.util.spec_from_file_location("qi_summarize_run_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def snapshot() -> dict[str, str]:
        return {
            str(path.relative_to(run_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in run_dir.rglob("*")
            if path.is_file()
        }

    before = snapshot()
    lines = module.summary_lines(
        valid_run_evidence.root,
        RUN_ID,
        receipt,
    )

    assert lines[:9] == [
        "contracts=111",
        "passed=111",
        "failed=0",
        "blocked=0",
        "not_run=0",
        "stale=0",
        "current_four=4",
        "artifacts_per_sample=3",
        "overall_verdict=passed",
    ]
    assert "artifact_ref=artifacts/current-four-manifest.json" in lines
    assert "artifact_ref=artifacts/human-verdict.json" in lines
    assert "artifact_ref=live-run-evidence.json" in lines
    assert snapshot() == before
