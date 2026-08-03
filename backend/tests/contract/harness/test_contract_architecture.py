import ast
import copy
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from test_live_run_contract import (
    ACCOUNT_READINESS_KEY,
    ACCOUNT_READINESS_WORKSPACE,
    _account_readiness_module,
    _configure_account_readiness_paths,
    _issue_account_readiness,
    _validate_account_readiness,
)


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


def _runtime_acceptance_owner_inventory(source: str) -> tuple[set[str], set[str]]:
    """Return AST-observed fact writers and active-path projection calls."""
    tree = ast.parse(source)
    writers: set[str] = set()
    projection_callers: set[str] = set()
    for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
        handles_runtime_fact = any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.endswith("provider-account-runtime-acceptance.json")
            for node in ast.walk(function)
        )
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "_project_runtime_account_acceptance":
                projection_callers.add(function.name)
            if not (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "open"
            ):
                continue
            if handles_runtime_fact and any(
                isinstance(argument, ast.Attribute)
                and isinstance(argument.value, ast.Name)
                and argument.value.id == "os"
                and argument.attr == "O_CREAT"
                for argument in ast.walk(node)
            ):
                writers.add(function.name)
    return writers, projection_callers


def test_runtime_acceptance_ast_gate_has_one_reachable_writer_and_projection() -> None:
    """Mutation caught: adding a dead fact writer or a second host projection call site."""
    source = (HARNESS / "scripts/run-p0.py").read_text(encoding="utf-8")
    writers, projection_callers = _runtime_acceptance_owner_inventory(source)
    assert writers == {"_seal_runtime_account_acceptance"}
    assert projection_callers == {"start_live_run"}

    injected = source + "\n\ndef _dead_runtime_acceptance_writer():\n    target = 'provider-account-runtime-acceptance.json'\n    os.open(target, os.O_CREAT)\n\ndef _second_projection():\n    _project_runtime_account_acceptance(None, {})\n"
    writers, projection_callers = _runtime_acceptance_owner_inventory(injected)
    assert writers == {"_seal_runtime_account_acceptance", "_dead_runtime_acceptance_writer"}
    assert projection_callers == {"start_live_run", "_second_projection"}


def test_gdt10e_harness_runs_root_has_one_owner_without_local_selectors() -> None:
    """Mutation caught: reintroducing a local, environment, CLI, or fallback run-root selector."""
    readiness_source = (
        HARNESS / "scripts/provider_account_readiness.py"
    ).read_text(encoding="utf-8")
    authorization_source = (
        HARNESS / "scripts/live_cycle_authorization.py"
    ).read_text(encoding="utf-8")
    readiness_tree = ast.parse(readiness_source)
    authorization_tree = ast.parse(authorization_source)
    expected_root = (
        "/home/reggie/vscode_folder/Quality_Inspection/.worktrees/"
        "gdt10e-retry-archive-continuation/.agent/harness/runs"
    )
    assignments = [
        node
        for node in readiness_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "HARNESS_RUNS_ROOT" for target in node.targets)
    ]
    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value.args[0]) == expected_root

    functions = {
        node.name: node
        for node in authorization_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    active_consumers = {
        "_terminal_cleanup_paths",
        "_gdt10e_runtime_acceptance_path",
        "_validate_terminal_public_binding",
        "_write_close_bridge_evidence",
        "_run_state",
        "prove_run_quiescence",
        "validate_paused_run",
        "execute_start",
        "execute_resume",
    }
    assert active_consumers <= set(functions)

    def derives_local_run_root(node: ast.AST) -> bool:
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            return False
        return (
            isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
            and ".agent/harness/runs" in node.right.value
            and any(
                isinstance(part, ast.Name) and part.id == "ROOT"
                for part in ast.walk(node.left)
            )
        )

    for name in active_consumers:
        function = functions[name]
        assert not any(derives_local_run_root(node) for node in ast.walk(function))

    owner_function = functions["_gdt10e_harness_runs_root"]
    assert not owner_function.args.posonlyargs
    assert not owner_function.args.args
    assert not owner_function.args.kwonlyargs
    assert owner_function.args.vararg is None
    assert owner_function.args.kwarg is None
    body = owner_function.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert len(body) == 1
    statement = body[0]
    assert isinstance(statement, ast.Return)
    assert isinstance(statement.value, ast.Attribute)
    assert statement.value.attr == "HARNESS_RUNS_ROOT"
    assert isinstance(statement.value.value, ast.Call)
    assert isinstance(statement.value.value.func, ast.Name)
    assert statement.value.value.func.id == "_provider_account_readiness_module"
    assert not statement.value.value.args
    assert not statement.value.value.keywords


def _load_stage_module() -> ModuleType:
    path = HARNESS / "scripts/stage-current-four.py"
    spec = importlib.util.spec_from_file_location("test_stage_current_four", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_provider_contract_module() -> ModuleType:
    path = HARNESS / "scripts/run-provider-contracts.py"
    spec = importlib.util.spec_from_file_location("test_run_provider_contracts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_contract_checker_module() -> ModuleType:
    path = HARNESS / "scripts/check-contracts.py"
    spec = importlib.util.spec_from_file_location(
        "test_check_contracts",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECEIPT = _load_receipt_module()
RUNNER = _load_runner_module()


def test_live_prepare_uses_canonical_processing_task() -> None:
    source = (ROOT / ".agent/harness/scripts/run-p0.py").read_text(
        encoding="utf-8"
    )
    program = source.split('_PREPARE_PROJECT_PROGRAM = r"""', 1)[1].split(
        '"""',
        1,
    )[0]

    assert "inventory_project.run(" in program
    assert "InventoryPipeline(" not in program


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


def test_contract_check_rejects_failure_proof_selector_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_contract_checker_module()
    policy = yaml.safe_load(
        (HARNESS / "policy/failure-severity-policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    policy["failure_proof"]["selector"] = (
        "phase://failure/no-silent-success?recognition_mode=stale"
    )
    stale_policy = tmp_path / "failure-severity-policy.yaml"
    stale_policy.write_text(
        yaml.safe_dump(policy, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        checker,
        "FAILURE_SEVERITY_POLICY_PATH",
        stale_policy,
        raising=False,
    )

    with pytest.raises(
        checker.ContractCheckError,
        match="failure proof selector drift",
    ):
        checker.check()


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
    runtime_schema = tmp_path / "backend/app/providers/candidate_review.schema.json"
    runtime_schema.parent.mkdir(parents=True)
    runtime_schema.write_text('{"type": "object"}\n', encoding="utf-8")
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
    assert runtime_schema in reads
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


def _current_four_manifest_bytes(*, pretty: bool = False) -> bytes:
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
    manifest = {
        "schema_version": "current-four-manifest/1",
        "input_set": "current-four",
        "first_checkpoint": {
            key: entries[0][key]
            for key in ("order", "basename", "sha256", "opaque_ref")
        },
        "entries": entries,
    }
    RECEIPT.validate_schema(manifest, "current-four-manifest.schema.json", ROOT)
    if pretty:
        return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def test_input_identity_binds_current_four_manifest_bytes(tmp_path: Path) -> None:
    """P0-REC-002: current-four artifact bytes participate in input identity."""
    artifact_name = "artifacts/current-four-manifest.json"
    original = _current_four_manifest_bytes()
    changed = _current_four_manifest_bytes(pretty=True)
    assert changed != original
    baseline = RECEIPT.input_identity("live", "task", "D2-T1")
    bound = RECEIPT.input_identity(
        "live",
        "task",
        "D2-T1",
        {artifact_name: original},
    )

    assert bound["digest"] != baseline["digest"]
    assert bound["components"] == [
        f"input-artifact:{artifact_name}",
        "task-selector-set",
    ]
    assert RECEIPT.input_identity(
        "live",
        "task",
        "D2-T1",
        {artifact_name: changed},
    )["digest"] != bound["digest"]

    run_dir = tmp_path / "sealed-run"
    artifact_path = run_dir / artifact_name
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(original)
    run = {"input_identity": bound}
    loaded = RECEIPT.input_artifacts_from_run(run, run_dir)
    assert loaded == {artifact_name: original}

    artifact_path.write_bytes(changed)
    recomputed = RECEIPT.input_identity("live", "task", "D2-T1", RECEIPT.input_artifacts_from_run(run, run_dir))
    assert recomputed != bound


def test_receipt_freshness_recomputes_current_four_artifact_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-002: receipt freshness rejects changed sealed manifest bytes."""
    run_id = "20260721T000000000000Z-00000000"
    run_dir = tmp_path / ".agent/harness/runs" / run_id
    artifact_path = run_dir / RECEIPT.CURRENT_FOUR_ARTIFACT
    artifact_path.parent.mkdir(parents=True)
    original = _current_four_manifest_bytes()
    artifact_path.write_bytes(original)
    run = {
        "run_id": run_id,
        "mode": "live",
        "scope": "task",
        "task_id": "D2-T1",
        "contract_definition_hash": "0" * 64,
        "policy_versions": {},
        "code_identity": {"digest": "code"},
        "config_identity": {"digest": "config"},
        "input_identity": RECEIPT.input_identity(
            "live",
            "task",
            "D2-T1",
            {RECEIPT.CURRENT_FOUR_ARTIFACT: original},
        ),
    }
    monkeypatch.setattr(RECEIPT, "policy_versions", lambda _policies: {})
    monkeypatch.setattr(RECEIPT, "code_identity", lambda _root: run["code_identity"])
    monkeypatch.setattr(
        RECEIPT,
        "config_identity",
        lambda *_args: run["config_identity"],
    )
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)

    assert RECEIPT._freshness_reasons(
        tmp_path,
        run,
        {"contract_definition_hash": "0" * 64},
        {},
        now,
        now + timedelta(hours=1),
    ) == []

    artifact_path.write_bytes(_current_four_manifest_bytes(pretty=True))
    assert RECEIPT._freshness_reasons(
        tmp_path,
        run,
        {"contract_definition_hash": "0" * 64},
        {},
        now,
        now + timedelta(hours=1),
    ) == ["input_identity_changed"]


def test_input_identity_binds_symbol_eval_pair_with_current_four() -> None:
    """P0-REC-005: full-P0 identity can bind all three exact input artifacts."""
    symbol_artifacts = {
        RECEIPT.SYMBOL_EVAL_ARTIFACT: b'{"manifest":1}',
        RECEIPT.SYMBOL_VERDICT_ARTIFACT: b'{"verdict":1}',
    }
    symbol_identity = RECEIPT.input_identity(
        "live",
        "task",
        "D7-T2",
        symbol_artifacts,
    )
    assert {
        f"{RECEIPT.INPUT_ARTIFACT_PREFIX}{name}"
        for name in symbol_artifacts
    } <= set(symbol_identity["components"])

    combined_identity = RECEIPT.input_identity(
        "live",
        "full-p0",
        None,
        {
            RECEIPT.CURRENT_FOUR_ARTIFACT: b'{"current_four":1}',
            **symbol_artifacts,
        },
    )
    assert len(
        [
            component
            for component in combined_identity["components"]
            if component.startswith(RECEIPT.INPUT_ARTIFACT_PREFIX)
        ]
    ) == 3
    assert combined_identity != symbol_identity

    with pytest.raises(ValueError, match="artifact set"):
        RECEIPT.input_identity(
            "live",
            "task",
            "D7-T2",
            {RECEIPT.SYMBOL_EVAL_ARTIFACT: b'{"manifest":1}'},
        )


@pytest.mark.parametrize(
    "artifact_name",
    (
        "../current-four-manifest.json",
        "/tmp/current-four-manifest.json",
        "artifacts/../current-four-manifest.json",
        "artifacts/current-four.pdf",
        "artifacts/other.json",
    ),
)
def test_runner_rejects_uncontrolled_input_artifact_names(artifact_name: str) -> None:
    """P0-REC-002: D2-T1 accepts only its controlled manifest artifact."""
    with pytest.raises(ValueError, match="current-four-manifest"):
        RUNNER._validate_input_artifacts({artifact_name: b"controlled"})


@pytest.mark.parametrize("mode", ("live", "fixture"))
def test_runner_writes_input_artifact_before_selectors(
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-002: live registration and fixture reuse stage bytes first."""
    runs = tmp_path / "runs"
    mirror = {
        "contract_definition_hash": "0" * 64,
        "status_projection_hash": "1" * 64,
        "contracts": [
            {
                "p0_contract_id": "P0-REC-001",
                "task_id": "D2-T1",
                "verification_selector": "controlled-selector",
            }
        ],
    }
    identity = {"algorithm": "sha256", "digest": "2" * 64, "components": ["test"]}
    receipt_stub = SimpleNamespace(
        provider_network_enabled=lambda: False,
        check_contract_authority=lambda _root: None,
        load_policies=lambda _root: {},
        validate_schema=lambda *_args: None,
        code_identity=lambda _root: identity,
        config_identity=lambda *_args: identity,
        input_identity=RECEIPT.input_identity,
        policy_versions=lambda _policies: {},
        build_receipt=lambda *_args: {"overall_verdict": "passed"},
    )
    artifact_name = "artifacts/current-four-manifest.json"
    artifact_bytes = _current_four_manifest_bytes()

    monkeypatch.setattr(RUNNER, "ROOT", tmp_path)
    monkeypatch.setattr(RUNNER, "RUNS", runs)
    monkeypatch.setattr(RUNNER, "MIRROR_PATH", tmp_path / "mirror.json")
    monkeypatch.setattr(RUNNER, "BINDINGS_PATH", tmp_path / "bindings.json")
    monkeypatch.setattr(RUNNER, "_receipt_module", lambda: receipt_stub)
    monkeypatch.setattr(
        RUNNER,
        "_load_json",
        lambda path: mirror if path == RUNNER.MIRROR_PATH else {"bindings": []},
    )
    monkeypatch.setattr(RUNNER, "_git_revision", lambda: "test-revision")

    def assert_artifact_precedes_selector(_selector: str, _mode: str) -> dict:
        run_dir = next(runs.iterdir())
        assert (run_dir / artifact_name).read_bytes() == artifact_bytes
        return {
            "exit_code": 0,
            "result_state": "passed",
            "started_at": "2026-07-21T00:00:00Z",
            "completed_at": "2026-07-21T00:00:01Z",
            "output": "controlled",
        }

    monkeypatch.setattr(RUNNER, "_execute_selector", assert_artifact_precedes_selector)

    run_id, verdict = RUNNER.run_task(
        mode,
        "task",
        "D2-T1",
        input_artifacts={artifact_name: artifact_bytes},
    )

    assert verdict == "passed"
    assert (runs / run_id / artifact_name).read_bytes() == artifact_bytes


@pytest.mark.parametrize(
    ("mode", "task_id"),
    (("failure", "D2-T1"), ("live", "D2-T2"), ("fixture", "D2-T2")),
)
def test_current_four_artifact_rejects_failure_mode_and_other_tasks(
    mode: str,
    task_id: str,
) -> None:
    """P0-REC-002: manifest reuse cannot widen beyond fixture/live D2-T1."""
    with pytest.raises(ValueError, match="fixture/live D2-T1"):
        RUNNER.run_task(
            mode,
            "task",
            task_id,
            input_artifacts={
                RUNNER.CURRENT_FOUR_ARTIFACT: _current_four_manifest_bytes()
            },
        )


@pytest.mark.parametrize("writable_mode", (0o464, 0o446))
def test_current_four_seal_rejects_group_or_world_write_bits(
    tmp_path: Path,
    writable_mode: int,
) -> None:
    """P0-REC-002: a sealed artifact has no owner, group, or world write bit."""
    artifact = tmp_path / "manifest.json"
    artifact.write_bytes(b"controlled")
    artifact.chmod(writable_mode)

    assert RUNNER._is_sealed(artifact) is False

    artifact.chmod(0o444)
    assert RUNNER._is_sealed(artifact) is True


def test_current_four_loader_requires_literal_sealed_registration_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-REC-002: reuse requires a literal sealed byte-identical registration."""
    run_id = "20260721T000000000000Z-00000000"
    run_dir = tmp_path / run_id
    artifact_path = run_dir / "artifacts/current-four-manifest.json"
    artifact_path.parent.mkdir(parents=True)
    artifact = _current_four_manifest_bytes()
    artifact_path.write_bytes(artifact)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "mode": "live",
                "scope": "task",
                "task_id": "D2-T1",
                "completed_at": "2026-07-21T00:00:01Z",
                "input_identity": RECEIPT.input_identity(
                    "live",
                    "task",
                    "D2-T1",
                    {RUNNER.CURRENT_FOUR_ARTIFACT: artifact},
                ),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "receipt.json").write_text(
        json.dumps({"run_id": run_id, "overall_verdict": "passed"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(RUNNER, "RUNS", tmp_path)

    with pytest.raises(ValueError, match="literal registration run ID"):
        RUNNER._load_current_four_artifact("latest")

    for path in (artifact_path, run_dir / "run.json", run_dir / "receipt.json"):
        path.chmod(0o444)
    artifact_path.parent.chmod(0o555)
    run_dir.chmod(0o555)
    try:
        loaded = RUNNER._load_current_four_artifact(run_id)
        assert loaded == {RUNNER.CURRENT_FOUR_ARTIFACT: artifact}

        artifact_path.chmod(0o644)
        artifact_path.write_bytes(_current_four_manifest_bytes(pretty=True))
        artifact_path.chmod(0o444)
        with pytest.raises(ValueError, match="input identity"):
            RUNNER._load_current_four_artifact(run_id)
    finally:
        run_dir.chmod(0o755)
        artifact_path.parent.chmod(0o755)
        for path in (artifact_path, run_dir / "run.json", run_dir / "receipt.json"):
            path.chmod(0o644)


def test_current_four_manifest_excludes_host_paths_and_pdf_bytes() -> None:
    """P0-REC-002: current-four evidence stores identity facts, not source bytes."""
    stage = _load_stage_module()
    manifest = stage.manifest_from_documents(stage.FROZEN_DOCUMENTS)
    RECEIPT.validate_schema(
        manifest,
        "current-four-manifest.schema.json",
        ROOT,
    )
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True)

    assert len(manifest["entries"]) == 4
    assert manifest["first_checkpoint"] == {
        key: manifest["entries"][0][key]
        for key in ("order", "basename", "sha256", "opaque_ref")
    }
    assert all(
        set(entry) == {"order", "basename", "sha256", "opaque_ref", "page_metadata"}
        for entry in manifest["entries"]
    )
    assert "%PDF" not in encoded
    assert "source_path" not in encoded
    assert "source_root" not in encoded


def test_d2_t2_input_identity_binds_only_sanitized_provider_fixtures(
    tmp_path: Path,
) -> None:
    """P0-RES-005: D2-T2 fixture bytes are bound without becoming run artifacts."""
    relative_paths = (
        ".agent/harness/fixtures/providers/tencent-ocr/general-accurate-v1.json",
        ".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json",
        ".agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v2.json",
    )
    assert not any(
        path.endswith("visual-symbol-review-v1.json")
        for path in relative_paths
    )
    for index, relative_path in enumerate(relative_paths):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture-{index}".encode())

    baseline = RECEIPT.input_identity(
        "fixture",
        "task",
        "D2-T2",
        root=tmp_path,
    )
    assert baseline["components"] == sorted(
        [f"provider-fixture:{relative_path}" for relative_path in relative_paths]
        + ["task-selector-set"]
    )

    (tmp_path / relative_paths[0]).write_bytes(b"changed-fixture")
    assert RECEIPT.input_identity(
        "fixture",
        "task",
        "D2-T2",
        root=tmp_path,
    )["digest"] != baseline["digest"]
    assert RECEIPT.input_identity(
        "fixture",
        "task",
        "D2-T3",
        root=tmp_path / "missing-fixtures",
    )["components"] == ["task-selector-set"]


def test_d2_t2_input_identity_rejects_symlinked_fixture_parent(
    tmp_path: Path,
) -> None:
    """P0-RES-005: fixture identity cannot follow a parent symlink outside root."""
    outside = tmp_path / "outside/providers"
    for relative_path in RECEIPT.PROVIDER_FIXTURE_PATHS:
        provider_relative = Path(relative_path).relative_to(
            ".agent/harness/fixtures/providers"
        )
        path = outside / provider_relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"external-fixture")
    fixture_parent = tmp_path / ".agent/harness/fixtures/providers"
    fixture_parent.parent.mkdir(parents=True)
    fixture_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        RECEIPT.input_identity(
            "fixture",
            "task",
            "D2-T2",
            root=tmp_path,
        )


def test_provider_fixture_guard_rejects_secrets_and_full_base64(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-RES-005: sanitized fixtures reject recursive secrets and image bodies."""
    provider_contracts = _load_provider_contract_module()

    with pytest.raises(ValueError, match="forbidden fixture key"):
        provider_contracts.validate_sanitized_payload(
            {"nested": {"api_key": "redacted"}}
        )
    with pytest.raises(ValueError, match="base64-like"):
        provider_contracts.validate_sanitized_payload(
            {"image": "A" * 128}
        )

    relative_path = Path(provider_contracts.FIXTURE_RELATIVE_PATHS[0])
    external_fixture = tmp_path / "outside" / relative_path.name
    external_fixture.parent.mkdir(parents=True)
    external_fixture.write_bytes(
        (ROOT / relative_path).read_bytes()
    )
    linked_parent = tmp_path / relative_path.parent
    linked_parent.parent.mkdir(parents=True, exist_ok=True)
    linked_parent.symlink_to(external_fixture.parent, target_is_directory=True)
    monkeypatch.setattr(provider_contracts, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="symlink"):
        provider_contracts.load_fixture(tmp_path / relative_path)


def test_confidence_decision_contract_has_one_canonical_definition() -> None:
    confidence_source = (
        ROOT / "backend/app/candidates/confidence.py"
    ).read_text(encoding="utf-8")
    automatic_result_source = (
        ROOT / "backend/app/processing/automatic_result.py"
    ).read_text(encoding="utf-8")

    assert (
        confidence_source.count(
            'CONFIDENCE_POLICY_VERSION = "candidate-confidence/1"'
        )
        == 1
    )
    assert "CONFIDENCE_EVIDENCE_CODE_ORDER = (" in confidence_source
    assert "def validate_confidence_decision(" in confidence_source
    assert "candidate-confidence/1" not in automatic_result_source
    assert (
        "from app.candidates.confidence import (" in automatic_result_source
    )
    assert "validate_confidence_decision(" in automatic_result_source
    assert (
        'AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/3"'
        in automatic_result_source
    )
    assert (
        'COMPAT_AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/2"'
        in automatic_result_source
    )
    assert (
        'LEGACY_AUTOMATIC_RESULT_SCHEMA_VERSION = "automatic-result/1"'
        in automatic_result_source
    )
    assert "NEXT_AUTOMATIC_RESULT_SCHEMA_VERSION" not in automatic_result_source


def test_account_readiness_architecture_exposes_only_the_public_evidence_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutation caught: allowing a private readiness marker into a public schema or serializer."""
    module = _account_readiness_module()
    root, _, _ = _configure_account_readiness_paths(module, tmp_path, monkeypatch)
    issued = _issue_account_readiness(module, root)
    public = _validate_account_readiness(module, root).public_dict()

    assert {"binding_salt", "credential_bundle_binding_sha256", "api_key", "workspace_id"}.isdisjoint(public)
    serialized = json.dumps(public, sort_keys=True)
    for private_marker in (
        ACCOUNT_READINESS_KEY,
        ACCOUNT_READINESS_WORKSPACE,
        issued["binding_salt"],
        issued["credential_bundle_binding_sha256"],
    ):
        assert private_marker not in serialized

    forbidden_fields = {
        "api_key",
        "workspace_id",
        "binding_salt",
        "credential_bundle_binding_sha256",
    }

    def schema_field_names(value: object) -> set[str]:
        if isinstance(value, dict):
            names = set(value)
            for child in value.values():
                names.update(schema_field_names(child))
            return names
        if isinstance(value, list):
            return set().union(*(schema_field_names(child) for child in value))
        return set()

    # These are the actual public schemas consumed by run/live/receipt writers;
    # none may carry private readiness fields, including in nested schema branches.
    for name in ("run.schema.json", "live-run-evidence.schema.json", "receipt.schema.json"):
        schema = json.loads((HARNESS / "schemas" / name).read_text(encoding="utf-8"))
        assert forbidden_fields.isdisjoint(schema_field_names(schema))
        nested_mutation = {
            "$defs": {
                "private": {
                    "oneOf": [{"allOf": [{"properties": {"binding_salt": {}}}]}]
                }
            }
        }
        assert "binding_salt" in schema_field_names(nested_mutation)


def test_gdt10e_retry_receipt_archive_owner_is_fixed_no_overwrite_and_durable() -> None:
    """Mutation caught: a second function or CLI path owns the fixed archive action."""
    source = (HARNESS / "scripts/live_cycle_authorization.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
    ]
    owners = [
        function for function in functions
        if function.name == "retire_no_issuance_receipt"
    ]
    callers = {
        function.name
        for function in functions
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "retire_no_issuance_receipt"
            for node in ast.walk(function)
        )
    }
    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }

    assert len(owners) == 1
    assert callers == {"main"}
    assert constants["_GDT10E_RETRY_RECEIPT_BYTES_SHA256"] == (
        "67b901bff1dd44431fb3bda6cf1aa0cbcbe79f62ce7302486a1c80f32d3281bb"
    )
    assert constants["_GDT10E_RETRY_RECEIPT_CONTENT_SHA256"] == (
        "15e4865a81244962b6e20438fa0bf577084ad63a878f3e6f7e1072605210a532"
    )


def test_gdt10e_final_retry_archive_and_live_recipes_have_no_generic_or_bytecode_surface() -> None:
    """Mutation caught: final retry becomes caller-configurable or dirty-head prone."""
    source = (HARNESS / "scripts/live_cycle_authorization.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "retire_no_issuance_receipt"
    )
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    companion = (
        ROOT
        / "docs/superpowers/plans/"
        "2026-08-02-gdt10e-credential-readiness-and-replacement-cycle.md"
    ).read_text(encoding="utf-8")

    final_archive = next(
        node.value.args[0].value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "_GDT10E_FINAL_RETRY_ARCHIVE_PATH"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "Path"
        and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Constant)
    )
    assert final_archive == (
        "/var/tmp/quality-inspection-gdt10e-20260802-db2265ae5e7d-"
        "cleanup-receipt-zero-paid-retry-2.json"
    )
    assert constants["_GDT10E_FINAL_RETRY_RECEIPT_BYTES_SHA256"] == (
        "a70b73faefcffcdf6977bd70f602d6798de2328abd4c4fb948f8cceebab04d9b"
    )
    assert constants["_GDT10E_FINAL_RETRY_RECEIPT_CONTENT_SHA256"] == (
        "215f2973036e4b4620cc7daa8b4331ebb11fced1c9406fb1fa1add47473d26bd"
    )
    assert {argument.arg for argument in owner.args.kwonlyargs} == {
        "receipt",
        "archive"
    }
    assert "_gdt10e_retry_archive_identity" not in source
    assert "sys.dont_write_bytecode" not in source
    for recipe in ("verify-p0-live", "resume-gdt10e-live"):
        start = makefile.index(f"{recipe}:")
        command = makefile[start:].splitlines()[1]
        assert "PYTHONDONTWRITEBYTECODE=1 micromamba run -n qi-p0 python" in command
    task_five_and_six = companion[
        companion.index("### Task 5:") : companion.index("### Task 7:")
    ]
    direct_commands = [
        command
        for command in task_five_and_six.splitlines()
        if "micromamba run -n qi-p0 python" in command
    ]
    assert len(direct_commands) == 9
    assert all(
        "PYTHONDONTWRITEBYTECODE=1" in command
        for command in direct_commands
    )


def test_cycle_revision_policy_has_one_fixed_writer_without_an_override_surface() -> None:
    """Mutation caught: a consumer or CLI restores caller-selected revisions."""
    authorization_source = (
        HARNESS / "scripts/live_cycle_authorization.py"
    ).read_text(encoding="utf-8")
    authorization_tree = ast.parse(authorization_source)
    functions = {
        node.name: node
        for node in authorization_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert functions["expected_db_revision_for_cycle"].args.args[0].arg == "cycle_id"
    for name in ("issue_authorization", "issue_gdt10e_authorization"):
        assert "expected_db_revision" not in {
            argument.arg for argument in functions[name].args.args
        }
        assert "expected_db_revision" not in {
            argument.arg for argument in functions[name].args.kwonlyargs
        }
    assert not any(
        isinstance(node, ast.Constant) and node.value == "--expected-db-revision"
        for node in ast.walk(functions["_parser"])
    )

    runner_source = (HARNESS / "scripts/run-p0.py").read_text(encoding="utf-8")
    assert ".expected_db_revision_for_cycle(" in runner_source

    backend_source = (
        ROOT / "backend/app/providers/cycle_authorization.py"
    ).read_text(encoding="utf-8")
    backend_tree = ast.parse(backend_source)
    backend_functions = {
        node.name: node
        for node in backend_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "_validate_expected_db_revision" in backend_functions
