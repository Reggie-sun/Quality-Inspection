from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
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
from test_live_run_contract import (
    ACCOUNT_READINESS_KEY,
    ACCOUNT_READINESS_MODEL,
    ACCOUNT_READINESS_WORKSPACE,
    ROOT as PROJECT_ROOT,
    _account_readiness_environment,
    _account_readiness_module,
    _configure_account_readiness_paths,
    _issue_account_readiness,
    _load_module,
    _paid_policy_evidence,
    _validate_account_readiness,
)


@pytest.fixture
def valid_run_evidence(tmp_path: Path) -> RunEvidence:
    return make_valid_run_evidence(tmp_path)


def _complete_gdt10e_v3_paid_evidence(
    valid_run_evidence: RunEvidence,
    tmp_path: Path,
    public_readiness: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], RunEvidence]:
    """Upgrade a complete v2 paid lifecycle without bypassing receipt policy."""
    policy, paid_run, paid_live, paid_run_dir = _paid_policy_evidence(
        tmp_path / "complete-paid-cycle"
    )
    run_dir = valid_run_evidence.root / ".agent/harness/runs" / RUN_ID
    shutil.copytree(
        paid_run_dir / "reports", run_dir / "reports", dirs_exist_ok=True
    )
    pricing_path = (
        valid_run_evidence.root
        / "backend/app/providers/provider_pricing_gdt10d_v1.json"
    )
    pricing_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "backend/app/providers/provider_pricing_gdt10d_v1.json",
        pricing_path,
    )

    run = copy.deepcopy(valid_run_evidence.run)
    authorization = copy.deepcopy(paid_run["cycle_authorization"])
    authorization.update(
        {
            "cycle_id": "gdt10e-auth-remediated-live-20260802",
            "historical_committed_cny": "3.526656",
            "max_total_cny": "46.473344",
            "overall_envelope_cny": "50.000000",
            "readiness_evidence": public_readiness,
        }
    )
    run.update(
        {"schema_version": "run/3", "cycle_authorization": authorization}
    )

    ledger_path = run_dir / "reports/provider-usage-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger.pop("content_sha256")
    ledger.update(
        {
            "cycle_id": "gdt10e-auth-remediated-live-20260802",
            "journal_ref": (
                "asset://provider-usage-cycles/"
                "gdt10e-auth-remediated-live-20260802/"
            ),
        }
    )
    ledger["content_sha256"] = hashlib.sha256(
        json.dumps(
            ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    ledger_path.write_bytes(
        (
            json.dumps(
                ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode()
    )

    live_path = run_dir / "live-run-evidence.json"
    live = json.loads(live_path.read_text(encoding="utf-8"))
    paid = copy.deepcopy(paid_live["paid_cycle"])
    paid.update(
        {
            "cycle_id": authorization["cycle_id"],
            "journal_ref": (
                "asset://provider-usage-cycles/"
                "gdt10e-auth-remediated-live-20260802/"
            ),
            "historical_committed_cny": "3.526656",
            "max_total_cny": "46.473344",
            "overall_envelope_cny": "50.000000",
            "readiness_evidence": public_readiness,
        }
    )
    paid["ledger"]["evidence_sha256"] = ledger["content_sha256"]
    live.update(
        {"schema_version": "live-run-evidence/3", "paid_cycle": paid}
    )

    fact = {
        "schema_version": "provider-account-runtime-acceptance/1",
        "cycle_id": authorization["cycle_id"],
        "run_id": RUN_ID,
        "project_id": "project-1",
        "readiness_sha256": public_readiness["readiness_sha256"],
        "submission_started_sha256": "1" * 64,
        "settlement_sha256": "2" * 64,
        "call_evidence_sha256": "3" * 64,
        "model": ACCOUNT_READINESS_MODEL,
        "ledger_attempt_index": 1,
        "accepted_at": "2026-08-02T00:04:00Z",
    }
    fact["content_sha256"] = hashlib.sha256(
        json.dumps(
            fact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    live = policy.account_readiness_projection(run, live, fact)
    fact_path = run_dir / "reports/provider-account-runtime-acceptance.json"
    fact_path.write_bytes(
        (
            json.dumps(
                fact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode()
    )
    fact_path.chmod(0o600)
    (run_dir / "run.json").write_text(
        json.dumps(run, sort_keys=True), encoding="utf-8"
    )
    live_path.write_text(json.dumps(live, sort_keys=True), encoding="utf-8")
    evidence = copy.copy(valid_run_evidence)
    object.__setattr__(evidence, "run", run)
    return run, live, evidence


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


def test_gdt10e_v3_public_serializers_never_leak_actual_private_markers(
    valid_run_evidence: RunEvidence,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mutation caught: leaking runtime-issued credential data through public v3 output."""
    readiness_module = _account_readiness_module()
    (tmp_path / "private").mkdir()
    private_root, _, _ = _configure_account_readiness_paths(
        readiness_module, tmp_path / "private", monkeypatch
    )
    issued = _issue_account_readiness(readiness_module, private_root)
    public = {
        "schema_version": "provider-account-readiness-evidence/1",
        "readiness_sha256": issued["content_sha256"],
        "operator_state": "operator_attested",
        "runtime_state": "not_yet_accepted",
        "binding_match": True,
        "runtime_acceptance_sha256": None,
    }
    run, live, evidence = _complete_gdt10e_v3_paid_evidence(
        valid_run_evidence, tmp_path, public
    )
    receipt = evaluate_receipt(evidence)
    assert receipt["formal_p0_verdict"] == "passed"
    receipt_bytes = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    with pytest.raises(ValueError) as failure:
        _validate_account_readiness(
            readiness_module,
            private_root,
            environment=_account_readiness_environment(api_key="wrong-private-api-key"),
        )
    assert readiness_module.main(["validate", "--root", str(tmp_path / "wrong")]) == 2
    output = capsys.readouterr()
    run_dir = valid_run_evidence.root / ".agent/harness/runs" / RUN_ID
    surfaces = "\n".join(
        (
            (run_dir / "run.json").read_bytes().decode(),
            (run_dir / "live-run-evidence.json").read_bytes().decode(),
            receipt_bytes.decode(),
            output.out,
            output.err,
            str(failure.value),
            repr(failure.value),
            repr(_validate_account_readiness(readiness_module, private_root)),
            caplog.text,
        )
    )
    for marker in (
        ACCOUNT_READINESS_KEY,
        ACCOUNT_READINESS_WORKSPACE,
        issued["binding_salt"],
        issued["credential_bundle_binding_sha256"],
    ):
        assert marker not in surfaces


def test_incomplete_gdt10e_v3_paid_cycle_cannot_produce_receipt(
    valid_run_evidence: RunEvidence,
    tmp_path: Path,
) -> None:
    public = {
        "schema_version": "provider-account-readiness-evidence/1",
        "readiness_sha256": "a" * 64,
        "operator_state": "operator_attested",
        "runtime_state": "not_yet_accepted",
        "binding_match": True,
        "runtime_acceptance_sha256": None,
    }
    _, live, evidence = _complete_gdt10e_v3_paid_evidence(
        valid_run_evidence, tmp_path, public
    )
    live["paid_cycle"]["terminal"] = None
    run_dir = valid_run_evidence.root / ".agent/harness/runs" / RUN_ID
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(live, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(ReceiptRejected, match="terminal evidence is missing"):
        evaluate_receipt(evidence)


def test_gdt10e_v3_receipt_rejects_cost_above_issued_incremental_ceiling(
    valid_run_evidence: RunEvidence,
    tmp_path: Path,
) -> None:
    """A v3 ledger is bounded by its issued 46.473344 CNY ceiling, not 50."""
    public = {
        "schema_version": "provider-account-readiness-evidence/1",
        "readiness_sha256": "a" * 64,
        "operator_state": "operator_attested",
        "runtime_state": "not_yet_accepted",
        "binding_match": True,
        "runtime_acceptance_sha256": None,
    }
    _, live, evidence = _complete_gdt10e_v3_paid_evidence(
        valid_run_evidence, tmp_path, public
    )
    run_dir = valid_run_evidence.root / ".agent/harness/runs" / RUN_ID
    ledger_path = run_dir / "reports/provider-usage-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger.pop("content_sha256")
    ledger["entries"][0].update(
        {"reservation_cny": "46.473345", "charged_cny": "46.473345"}
    )
    ledger["entries"][1].update(
        {"reservation_cny": "0.000000", "charged_cny": "0.000000"}
    )
    ledger["committed_total_cny"] = "46.473345"
    ledger["content_sha256"] = hashlib.sha256(
        json.dumps(
            ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    live["paid_cycle"]["ledger"].update(
        {
            "committed_total_cny": "46.473345",
            "evidence_sha256": ledger["content_sha256"],
        }
    )
    (run_dir / "live-run-evidence.json").write_text(
        json.dumps(live, sort_keys=True), encoding="utf-8"
    )

    policy = _load_module(
        f"qi_gdt10e_paid_ceiling_{tmp_path.name}",
        HARNESS / "scripts/live_evidence_policy.py",
    )
    with pytest.raises(ValueError, match="ledger aggregate"):
        policy._paid_ledger_entries(
            run=evidence.run,
            paid=live["paid_cycle"],
            ledger=live["paid_cycle"]["ledger"],
            evidence_dir=run_dir,
        )
    with pytest.raises(ReceiptRejected, match="aggregate"):
        evaluate_receipt(evidence)


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
