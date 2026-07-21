import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[4]
TRACE = ROOT / "docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md"
GLOBAL = ROOT / "docs/contracts/MAIN_CONTRACT_MATRIX.md"
HARNESS = ROOT / ".agent/harness"


def _load_receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location("test_generate_receipt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runner_module() -> ModuleType:
    path = HARNESS / "scripts/run-p0.py"
    spec = importlib.util.spec_from_file_location("test_run_p0", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECEIPT = _load_receipt_module()
RUNNER = _load_runner_module()


def _receipt_sources() -> tuple[dict, dict, dict]:
    mirror = json.loads((HARNESS / "contracts/p0-contracts.json").read_text())
    bindings = json.loads((HARNESS / "contracts/global-contract-bindings.json").read_text())
    policies = RECEIPT.load_policies(ROOT)
    return mirror, bindings, policies


def _run(
    mirror: dict,
    policies: dict,
    *,
    scope: str,
    task_id: str | None,
    selected_contract_ids: list[str],
) -> dict:
    return {
        "schema_version": "run/1",
        "run_id": "20260721T000000000000Z-00000000",
        "mode": "fixture",
        "scope": scope,
        "task_id": task_id,
        "code_identity": RECEIPT.code_identity(ROOT),
        "git_revision_at_start": "test-revision",
        "config_identity": RECEIPT.config_identity("fixture", scope, task_id, ROOT),
        "input_identity": RECEIPT.input_identity("fixture", scope, task_id),
        "contract_definition_hash": mirror["contract_definition_hash"],
        "status_projection_hash_at_start": mirror["status_projection_hash"],
        "policy_versions": RECEIPT.policy_versions(policies),
        "selected_contract_ids": selected_contract_ids,
        "started_at": "2026-07-21T00:00:00Z",
        "completed_at": "2026-07-21T00:00:01Z",
    }


def _results(run_id: str, selected_contract_ids: list[str]) -> list[dict]:
    return [
        {
            "schema_version": "contract-result/1",
            "run_id": run_id,
            "p0_contract_id": p0_id,
            "command": "controlled-test-selector",
            "exit_code": 0,
            "result_state": "passed",
            "started_at": "2026-07-21T00:00:00Z",
            "completed_at": "2026-07-21T00:00:01Z",
            "artifact_refs": [],
        }
        for p0_id in selected_contract_ids
    ]


def test_contract_mirror_is_generated_from_the_only_p0_markdown_source() -> None:
    result = subprocess.run(
        [sys.executable, str(HARNESS / "scripts/check-contracts.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    mirror = json.loads((HARNESS / "contracts/p0-contracts.json").read_text())
    assert len(mirror["contracts"]) == 111
    assert mirror["source"] == str(TRACE.relative_to(ROOT))
    assert mirror["global_source"] == str(GLOBAL.relative_to(ROOT))
    assert all(row["current_status"] in {"passed", "failed", "blocked", "not_run"} for row in mirror["contracts"])


def test_run_schema_requires_immutable_evidence_members() -> None:
    schema = json.loads((HARNESS / "schemas/run.schema.json").read_text())
    required = set(schema["required"])
    assert {
        "run_id", "mode", "scope", "code_identity", "git_revision_at_start", "config_identity", "input_identity",
        "contract_definition_hash", "status_projection_hash_at_start", "started_at",
    } <= required


def test_receipt_rejects_contract_result_from_another_run() -> None:
    mirror, bindings, policies = _receipt_sources()
    selected = sorted(
        row["p0_contract_id"]
        for row in mirror["contracts"]
        if row["task_id"] == "D1-T2"
    )
    run = _run(
        mirror,
        policies,
        scope="task",
        task_id="D1-T2",
        selected_contract_ids=selected,
    )
    results = _results(run["run_id"], selected)
    results[0]["run_id"] = "20260721T000000000000Z-00000001"

    with pytest.raises(ValueError, match="contract result run_id"):
        RECEIPT.build_receipt(ROOT, run, results, mirror, bindings, policies)


def test_task_receipt_rejects_subset_or_cross_task_contracts() -> None:
    mirror, bindings, policies = _receipt_sources()
    expected = sorted(
        row["p0_contract_id"]
        for row in mirror["contracts"]
        if row["task_id"] == "D1-T3"
    )
    assert len(expected) > 1
    foreign_id = next(
        row["p0_contract_id"]
        for row in mirror["contracts"]
        if row["task_id"] != "D1-T3"
    )
    for selected in (expected[:-1], sorted([*expected, foreign_id])):
        run = _run(
            mirror,
            policies,
            scope="task",
            task_id="D1-T3",
            selected_contract_ids=selected,
        )
        with pytest.raises(ValueError, match="task scope selected_contract_ids"):
            RECEIPT.build_receipt(
                ROOT,
                run,
                _results(run["run_id"], selected),
                mirror,
                bindings,
                policies,
            )


def test_full_p0_receipt_rejects_any_contract_subset() -> None:
    mirror, bindings, policies = _receipt_sources()
    all_contract_ids = sorted(row["p0_contract_id"] for row in mirror["contracts"])
    selected = all_contract_ids[:-1]
    run = _run(
        mirror,
        policies,
        scope="full-p0",
        task_id=None,
        selected_contract_ids=selected,
    )

    with pytest.raises(ValueError, match="full-p0 selected_contract_ids"):
        RECEIPT.build_receipt(
            ROOT,
            run,
            _results(run["run_id"], selected),
            mirror,
            bindings,
            policies,
        )

    mismatched_policies = copy.deepcopy(policies)
    mismatched_policies["p0_acceptance_policy"]["required_contract_count"] += 1
    complete_run = _run(
        mirror,
        policies,
        scope="full-p0",
        task_id=None,
        selected_contract_ids=all_contract_ids,
    )
    with pytest.raises(ValueError, match="full-p0 mirror contract count"):
        RECEIPT.build_receipt(
            ROOT,
            complete_run,
            _results(complete_run["run_id"], all_contract_ids),
            mirror,
            bindings,
            mismatched_policies,
        )


def test_config_identity_tracks_only_normalized_provider_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_control_keys = (
        "QI_PROVIDER_NETWORK_ENABLED",
        "PROVIDER_NETWORK_ENABLED",
        "OCR_PROVIDER_NETWORK_ENABLED",
        "VISION_PROVIDER_NETWORK_ENABLED",
        "QI_PROVIDER_MODE",
        "PROVIDER_MODE",
        "OCR_PROVIDER_MODE",
        "VISION_PROVIDER_MODE",
        "VISION_LLM_PROVIDER_MODE",
    )
    for key in provider_control_keys:
        monkeypatch.delenv(key, raising=False)

    baseline = RECEIPT.config_identity("fixture", "task", "D1-T2", ROOT)
    monkeypatch.setenv("PROVIDER_MODE", " LIVE ")
    with_provider_mode = RECEIPT.config_identity("fixture", "task", "D1-T2", ROOT)
    assert with_provider_mode["digest"] != baseline["digest"]
    assert "provider-control:PROVIDER_MODE" in with_provider_mode["components"]
    assert all("live" not in component.lower() for component in with_provider_mode["components"])

    monkeypatch.setenv("PROVIDER_MODE", "live")
    assert RECEIPT.config_identity("fixture", "task", "D1-T2", ROOT) == with_provider_mode

    monkeypatch.setenv("PROVIDER_API_TOKEN", "must-not-be-read-or-recorded")
    assert RECEIPT.config_identity("fixture", "task", "D1-T2", ROOT) == with_provider_mode
    assert all("TOKEN" not in component for component in with_provider_mode["components"])


def test_code_identity_reads_only_safe_executable_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_source = tmp_path / "backend/app/service.py"
    allowed_source.parent.mkdir(parents=True)
    allowed_source.write_text("VALUE = 1\n", encoding="utf-8")
    frontend_source = tmp_path / "frontend/src/app.ts"
    frontend_source.parent.mkdir(parents=True)
    frontend_source.write_text("export const value = 1;\n", encoding="utf-8")
    frontend_e2e = tmp_path / "frontend/e2e/app.spec.ts"
    frontend_e2e.parent.mkdir(parents=True)
    frontend_e2e.write_text("export const scenario = 1;\n", encoding="utf-8")
    planned_configs = (
        tmp_path / "backend/alembic.ini",
        tmp_path / "frontend/index.html",
        tmp_path / "frontend/vitest.config.ts",
    )
    for path in planned_configs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("safe-planned-config\n", encoding="utf-8")

    secret_env = tmp_path / "backend/.env"
    forbidden_paths = (
        tmp_path / "backend/unlisted.py",
        secret_env,
        tmp_path / "backend/app/.secret.py",
        tmp_path / "backend/private/credential.py",
        tmp_path / "backend/uploads/input.py",
        tmp_path / "backend/app/state.db",
        tmp_path / "backend/app/document.pdf",
        tmp_path / "backend/app/data.json",
        tmp_path / "frontend/src/unlisted.vue",
    )
    for path in forbidden_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("never-read-secret-sentinel\n", encoding="utf-8")
    symlink = tmp_path / "backend/app/symlink.py"
    symlink.symlink_to(secret_env)

    original_read_bytes = Path.read_bytes
    reads: list[Path] = []

    def guarded_read_bytes(path: Path) -> bytes:
        reads.append(path)
        if path in {*forbidden_paths, symlink}:
            raise AssertionError(f"unsafe identity read: {path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    baseline = RECEIPT.code_identity(tmp_path)
    assert allowed_source in reads
    assert frontend_source in reads
    assert frontend_e2e in reads
    assert set(planned_configs) <= set(reads)

    allowed_source.write_text("VALUE = 2\n", encoding="utf-8")
    changed_source = RECEIPT.code_identity(tmp_path)
    assert changed_source["digest"] != baseline["digest"]

    secret_env.write_text("changed-secret-sentinel\n", encoding="utf-8")
    assert RECEIPT.code_identity(tmp_path) == changed_source
    assert not ({*forbidden_paths, symlink} & set(reads))


def test_contract_authority_preflight_fails_before_evidence_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker_calls: list[tuple[list[str], Path]] = []

    def reject_checker(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        checker_calls.append((command, kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="mirror drift")

    monkeypatch.setattr(
        RECEIPT,
        "subprocess",
        SimpleNamespace(run=reject_checker),
        raising=False,
    )
    with pytest.raises(ValueError, match="contract authority preflight failed"):
        RECEIPT.check_contract_authority(tmp_path)
    assert checker_calls == [
        (
            [
                sys.executable,
                str(tmp_path / ".agent/harness/scripts/check-contracts.py"),
            ],
            tmp_path,
        )
    ]

    def reject_authority(_root: Path) -> None:
        raise ValueError("controlled authority drift")

    monkeypatch.setattr(RECEIPT, "check_contract_authority", reject_authority, raising=False)
    monkeypatch.setattr(
        RECEIPT,
        "_load_json",
        lambda _path: pytest.fail("check_run read evidence before authority preflight"),
    )
    with pytest.raises(ValueError, match="controlled authority drift"):
        RECEIPT.check_run("20260721T000000000000Z-00000000", tmp_path)

    receipt_stub = SimpleNamespace(
        provider_network_enabled=lambda: False,
        check_contract_authority=reject_authority,
    )
    monkeypatch.setattr(RUNNER, "_receipt_module", lambda: receipt_stub)
    monkeypatch.setattr(RUNNER, "ROOT", tmp_path)
    monkeypatch.setattr(RUNNER, "RUNS", tmp_path / ".agent/harness/runs")
    monkeypatch.setattr(
        RUNNER,
        "_load_json",
        lambda _path: pytest.fail("run_task read mirror before authority preflight"),
    )
    with pytest.raises(ValueError, match="controlled authority drift"):
        RUNNER.run_task("fixture", "task", "D1-T2")
    assert not RUNNER.RUNS.exists()
