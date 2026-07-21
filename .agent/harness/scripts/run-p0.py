#!/usr/bin/env python3
"""Run the literal selectors for one P0 task and seal immutable evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
MIRROR_PATH = HARNESS / "contracts/p0-contracts.json"
BINDINGS_PATH = HARNESS / "contracts/global-contract-bindings.json"
TASK_RE = re.compile(r"^D[0-9]+-T[0-9]+$")
NETWORK_ENABLED_KEYS = (
    "QI_PROVIDER_NETWORK_ENABLED",
    "PROVIDER_NETWORK_ENABLED",
    "OCR_PROVIDER_NETWORK_ENABLED",
    "VISION_PROVIDER_NETWORK_ENABLED",
)
NETWORK_MODE_KEYS = (
    "QI_PROVIDER_MODE",
    "PROVIDER_MODE",
    "OCR_PROVIDER_MODE",
    "VISION_PROVIDER_MODE",
    "VISION_LLM_PROVIDER_MODE",
)
TRUTHY = {"1", "true", "yes", "on", "enabled", "live"}
OFFLINE_PROVIDER_MODES = {"", "disabled", "fixture", "mock", "none", "offline"}
SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location("qi_generate_receipt", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate-receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else "unavailable"


def _fixture_network_enabled() -> bool:
    explicit_switch = any(
        os.environ.get(key, "").strip().lower() in TRUTHY
        for key in NETWORK_ENABLED_KEYS
    )
    configured_network_mode = any(
        os.environ.get(key, "").strip().lower() not in OFFLINE_PROVIDER_MODES
        for key in NETWORK_MODE_KEYS
    )
    return explicit_switch or configured_network_mode


def _phase_outcome(selector: str, mode: str) -> tuple[int | None, str, str]:
    parsed = urlsplit(selector)
    requested_mode = parsed.netloc
    phase = parsed.path.lstrip("/")
    if requested_mode != mode:
        return (
            None,
            "blocked",
            f"phase mode mismatch: runner={mode} selector={requested_mode}",
        )
    return (
        None,
        "blocked",
        f"phase://{requested_mode}/{phase} has no D1-T1 handler; no child run was created",
    )


def _command_outcome(selector: str) -> tuple[int | None, str, str]:
    try:
        argv = shlex.split(selector)
    except ValueError as exc:
        return None, "blocked", f"invalid selector argv: {exc}"
    if not argv or any(token in SHELL_OPERATORS for token in argv):
        return None, "blocked", "selector is not one exact argv command"
    try:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return None, "blocked", f"selector could not start: {exc}"
    state = "passed" if result.returncode == 0 else "failed"
    output = "\n".join(
        (
            f"command={selector}",
            f"exit_code={result.returncode}",
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        )
    )
    return result.returncode, state, output


def _execute_selector(selector: str, mode: str) -> dict[str, Any]:
    started_at = _iso_now()
    if selector.startswith("phase://"):
        exit_code, state, output = _phase_outcome(selector, mode)
    else:
        exit_code, state, output = _command_outcome(selector)
    return {
        "exit_code": exit_code,
        "result_state": state,
        "started_at": started_at,
        "completed_at": _iso_now(),
        "output": output,
    }


def _seal_run(run_dir: Path) -> None:
    descendants = sorted(
        run_dir.rglob("*"),
        key=lambda path: (len(path.parts), str(path)),
        reverse=True,
    )
    for path in descendants:
        if path.is_symlink():
            raise ValueError("run evidence must not contain symlinks")
        if path.is_dir():
            path.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    run_dir.chmod(
        stat.S_IRUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )


def run_task(mode: str, scope: str, task_id: str) -> tuple[str, str]:
    if scope != "task":
        raise ValueError("D1-T1 implements task scope only; full-p0 orchestration is not available")
    if not TASK_RE.fullmatch(task_id):
        raise ValueError("--task must be a literal Dn-Tn identifier")
    if mode == "fixture" and _fixture_network_enabled():
        raise ValueError("fixture mode rejects network-enabled Provider configuration")

    receipt_module = _receipt_module()
    mirror = _load_json(MIRROR_PATH)
    bindings = _load_json(BINDINGS_PATH)
    policies = receipt_module.load_policies(ROOT)
    receipt_module.validate_schema(mirror, "p0-contracts.schema.json", ROOT)
    receipt_module.validate_schema(bindings, "global-contract-bindings.schema.json", ROOT)

    selected = sorted(
        (row for row in mirror["contracts"] if row["task_id"] == task_id),
        key=lambda row: row["p0_contract_id"],
    )
    if not selected:
        raise ValueError(f"no P0 contracts select task {task_id}")

    # The identity and run directory exist before any selector is invoked.
    run_id = _new_run_id()
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started_at = _iso_now()
    run = {
        "schema_version": "run/1",
        "run_id": run_id,
        "mode": mode,
        "scope": scope,
        "task_id": task_id,
        "code_identity": receipt_module.code_identity(ROOT),
        "git_revision_at_start": _git_revision(),
        "config_identity": receipt_module.config_identity(mode, scope, task_id, ROOT),
        "input_identity": receipt_module.input_identity(mode, scope, task_id),
        "contract_definition_hash": mirror["contract_definition_hash"],
        "status_projection_hash_at_start": mirror["status_projection_hash"],
        "policy_versions": receipt_module.policy_versions(policies),
        "selected_contract_ids": [row["p0_contract_id"] for row in selected],
        "started_at": started_at,
        "completed_at": None,
    }
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)
    for name in ("logs", "reports", "artifacts"):
        (run_dir / name).mkdir()

    # Identical selectors execute once; every selected P0 ID still gets a result.
    outcomes: dict[str, dict[str, Any]] = {}
    log_refs: dict[str, str] = {}
    for index, selector in enumerate(dict.fromkeys(row["verification_selector"] for row in selected), start=1):
        outcome = _execute_selector(selector, mode)
        log_ref = f"logs/selector-{index:03d}.log"
        (run_dir / log_ref).write_text(outcome.pop("output") + "\n", encoding="utf-8")
        outcomes[selector] = outcome
        log_refs[selector] = log_ref

    results: list[dict[str, Any]] = []
    for row in selected:
        selector = row["verification_selector"]
        outcome = outcomes[selector]
        result = {
            "schema_version": "contract-result/1",
            "run_id": run_id,
            "p0_contract_id": row["p0_contract_id"],
            "command": selector,
            "exit_code": outcome["exit_code"],
            "result_state": outcome["result_state"],
            "started_at": outcome["started_at"],
            "completed_at": outcome["completed_at"],
            "artifact_refs": [log_refs[selector]],
        }
        receipt_module.validate_schema(result, "contract-result.schema.json", ROOT)
        results.append(result)

    _write_json(
        run_dir / "contract-results.json",
        {
            "schema_version": "contract-results/1",
            "run_id": run_id,
            "results": results,
        },
    )
    run["completed_at"] = _iso_now()
    receipt_module.validate_schema(run, "run.schema.json", ROOT)
    _write_json(run_dir / "run.json", run)
    receipt = receipt_module.build_receipt(
        ROOT,
        run,
        results,
        mirror,
        bindings,
        policies,
    )
    _write_json(run_dir / "receipt.json", receipt)
    _seal_run(run_dir)
    return run_id, receipt["overall_verdict"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fixture", "failure", "live"))
    parser.add_argument("--scope", required=True, choices=("task", "full-p0"))
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    try:
        run_id, verdict = run_task(args.mode, args.scope, args.task)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"run-p0: {exc}", file=sys.stderr)
        return 2
    print(f"run_id={run_id} scope={args.scope} task={args.task} overall_verdict={verdict}")
    return 0 if verdict == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
